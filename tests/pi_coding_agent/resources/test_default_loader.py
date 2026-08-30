from __future__ import annotations

import json
from pathlib import Path

from pi_coding_agent.resources.default_loader import DefaultResourceLoader
from pi_coding_agent.resources.trust import TrustDecision


class _FakeTrustStore:
    def __init__(self, decision: TrustDecision) -> None:
        self._decision = decision

    def get(self, cwd: Path) -> TrustDecision:
        return self._decision


def _make_skill(root: Path, layer: str, name: str) -> None:
    directory = root / layer / "skills"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(f"# {layer}:{name}", encoding="utf-8")


def test_precedence_project_beats_package_and_global_when_trusted(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    packages = tmp_path / "npm"
    for root in (cwd, agent_dir, packages):
        _make_skill(root, ".pi-python" if root is cwd else "", "shared")
    _make_skill(agent_dir, "", "global-only")

    loader = DefaultResourceLoader(
        trust_store=_FakeTrustStore(TrustDecision.TRUSTED),
        package_roots={"skill": (packages / "skills",)},
    )

    result = loader.load(cwd=cwd, agent_dir=agent_dir)

    skills = {
        descriptor.source: descriptor
        for descriptor in result.descriptors
        if descriptor.kind == "skill"
    }
    shared = [item for item in result.descriptors if item.kind == "skill" and item.name == "shared"]
    assert len(shared) == 1
    assert shared[0].source == "project"
    assert "global-only" in skills or any(item.name == "global-only" for item in result.descriptors)


def test_untrusted_project_is_skipped_with_diagnostic(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    _make_skill(cwd, ".pi-python", "private")
    _make_skill(agent_dir, "", "public")

    loader = DefaultResourceLoader(trust_store=_FakeTrustStore(TrustDecision.UNTRUSTED))
    result = loader.load(cwd=cwd, agent_dir=agent_dir)

    names = {(item.kind, item.name) for item in result.descriptors}
    assert ("skill", "private") not in names
    assert ("skill", "public") in names
    assert any("untrusted" in diagnostic for diagnostic in result.diagnostics)


def test_untrusted_project_prompt_excludes_project_instructions(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    (cwd / ".pi-python").mkdir(parents=True)
    (cwd / ".pi-python" / "SYSTEM.md").write_text("untrusted system", encoding="utf-8")
    (cwd / "AGENTS.md").write_text("untrusted instructions", encoding="utf-8")
    loader = DefaultResourceLoader(
        trust_store=_FakeTrustStore(TrustDecision.UNTRUSTED),
        agent_dir=agent_dir,
    )

    loader.discover(cwd)
    prompt = loader.build_system_prompt(cwd)

    assert "expert coding assistant" in prompt
    assert "untrusted system" not in prompt
    assert "untrusted instructions" not in prompt


def test_extension_manifests_are_enumerated_without_import(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    extension_root = tmp_path / "extensions" / "spy"
    extension_root.mkdir(parents=True)
    (extension_root / "pi-extension.json").write_text(
        json.dumps({"name": "spy", "version": "0.1.0", "entry": "main.py"}), encoding="utf-8"
    )
    (extension_root / "main.py").write_text(f"open({str(marker)!r}, 'w').close()", encoding="utf-8")
    cwd = tmp_path / "project"
    agent_dir = tmp_path / "agent"

    result = DefaultResourceLoader(extension_roots=(tmp_path / "extensions",)).load(
        cwd=cwd, agent_dir=agent_dir
    )

    assert [item.name for item in result.extensions] == ["spy"]
    assert not marker.exists()


def test_missing_package_root_records_diagnostic_but_loads_rest(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    _make_skill(agent_dir, "", "kept")

    loader = DefaultResourceLoader(package_roots={"skill": (tmp_path / "does-not-exist",)})
    result = loader.load(cwd=cwd, agent_dir=agent_dir)

    assert any(item.name == "kept" for item in result.descriptors)
    assert any("does-not-exist" in diagnostic for diagnostic in result.diagnostics)


def test_default_loader_satisfies_product_discovery_port(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    _make_skill(agent_dir, "", "global")
    loader = DefaultResourceLoader(agent_dir=agent_dir)

    descriptors = loader.discover(cwd)

    assert [(item.kind, item.name, item.source) for item in descriptors] == [
        ("skill", "global", "global")
    ]
    assert loader.last_result.descriptors == descriptors
