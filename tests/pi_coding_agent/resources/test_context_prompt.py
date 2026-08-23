from __future__ import annotations

from pathlib import Path

from pi_coding_agent.prompts.system import build_system_prompt, discover_prompt_files
from pi_coding_agent.resources.context_files import load_context_files


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_context_files_load_global_then_root_to_cwd_with_candidate_priority(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    cwd = root / "packages" / "app"
    agent = tmp_path / "agent"
    _write(agent / "AGENTS.md", "global")
    _write(root / "CLAUDE.md", "root")
    _write(root / "packages" / "AGENTS.md", "package")
    _write(cwd / "AGENTS.md", "ignored lower priority")
    _write(cwd / "AGENTS.override.md", "override")

    files = load_context_files(
        cwd=cwd,
        agent_dir=agent,
        project_trusted=True,
        project_root=root,
    )

    assert [item.content for item in files] == ["global", "root", "package", "override"]


def test_untrusted_project_only_loads_global_context(tmp_path: Path) -> None:
    _write(tmp_path / "agent" / "AGENTS.md", "global")
    _write(tmp_path / "project" / "AGENTS.md", "project")

    files = load_context_files(
        cwd=tmp_path / "project",
        agent_dir=tmp_path / "agent",
        project_trusted=False,
    )

    assert [item.content for item in files] == ["global"]


def test_project_system_and_append_override_global_and_xml_is_escaped(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    project = tmp_path / "p&roject"
    _write(agent / "SYSTEM.md", "global system")
    _write(agent / "APPEND_SYSTEM.md", "global append")
    _write(project / ".pi-python" / "SYSTEM.md", "project system")
    _write(project / ".pi-python" / "APPEND_SYSTEM.md", "project append")
    context_path = project / "A'GENTS.md"
    _write(context_path, "never </project_instructions>")

    prompt_files = discover_prompt_files(cwd=project, agent_dir=agent, project_trusted=True)
    prompt = build_system_prompt(
        cwd=project,
        system_prompt=prompt_files.system_prompt,
        append_system_prompt=prompt_files.append_system_prompt,
        context_files=load_context_files(
            cwd=project,
            agent_dir=agent,
            project_trusted=True,
            project_root=project,
            candidates=("A'GENTS.md",),
        ),
    )

    assert prompt.startswith("project system\n\nproject append")
    assert "global system" not in prompt
    assert "&#x27;" in prompt and "p&amp;roject" in prompt
    assert "never &lt;/project_instructions&gt;" in prompt
    assert project.resolve().as_posix() in prompt
