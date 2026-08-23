from __future__ import annotations

from pathlib import Path

from pi_coding_agent.resources.descriptors import ResourceDescriptor, ResourceKind
from pi_coding_agent.resources.discovery import DiscoveryInputs, discover_resources


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("data", encoding="utf-8")
    return path


def test_resource_precedence_and_order_are_deterministic(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    project = tmp_path / "project"
    compatibility = project / ".pi"
    explicit = _touch(tmp_path / "explicit" / "same.md")
    _touch(agent / "skills" / "same.md")
    _touch(agent / "skills" / "global-only.md")
    _touch(compatibility / "skills" / "same.md")
    _touch(compatibility / "skills" / "compat-only.md")
    _touch(project / ".pi-python" / "skills" / "same.md")
    _touch(project / ".pi-python" / "skills" / "project-only.md")
    builtin = ResourceDescriptor(
        kind="skill",
        name="builtin-only",
        path=None,
        source="builtin",
    )

    resources = discover_resources(
        DiscoveryInputs(
            cwd=project,
            agent_dir=agent,
            project_trusted=True,
            explicit={"skill": (explicit,)},
            compatibility_root=compatibility,
            builtins=(builtin,),
        )
    )

    assert [(item.name, item.source) for item in resources] == [
        ("same", "explicit"),
        ("project-only", "project"),
        ("compat-only", "compatibility"),
        ("global-only", "global"),
        ("builtin-only", "builtin"),
    ]


def test_untrusted_project_and_disabled_compatibility_are_not_enumerated(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _touch(project / ".pi-python" / "prompts" / "secret.md")
    _touch(project / ".pi" / "prompts" / "legacy.md")

    resources = discover_resources(
        DiscoveryInputs(cwd=project, agent_dir=tmp_path / "agent", project_trusted=False)
    )

    assert resources == ()


def test_all_resource_kinds_are_enumerated_without_loading_content(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    suffixes: dict[ResourceKind, str] = {
        "extension": ".py",
        "skill": ".md",
        "prompt": ".md",
        "theme": ".json",
    }
    for kind, suffix in suffixes.items():
        _touch(agent / f"{kind}s" / f"named{suffix}")

    resources = discover_resources(DiscoveryInputs(cwd=tmp_path, agent_dir=agent))

    assert {item.kind for item in resources} == set(suffixes)
