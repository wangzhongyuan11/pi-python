"""System prompt selection and safe context embedding."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

from ..resources.context_files import ContextFile

_DEFAULT_PROMPT = """You are an expert coding assistant operating inside pi-python.

Use the tools made available by the caller to inspect and change code. Be concise, preserve
unrelated user work, and show file paths clearly."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PromptFiles:
    system_prompt: str | None
    append_system_prompt: str | None


def _preferred_file(*, cwd: Path, agent_dir: Path, project_trusted: bool, name: str) -> Path | None:
    project = cwd.resolve() / ".pi-python" / name
    if project_trusted and project.is_file():
        return project
    global_path = agent_dir.resolve() / name
    return global_path if global_path.is_file() else None


def discover_prompt_files(*, cwd: Path, agent_dir: Path, project_trusted: bool) -> PromptFiles:
    system_path = _preferred_file(
        cwd=cwd, agent_dir=agent_dir, project_trusted=project_trusted, name="SYSTEM.md"
    )
    append_path = _preferred_file(
        cwd=cwd,
        agent_dir=agent_dir,
        project_trusted=project_trusted,
        name="APPEND_SYSTEM.md",
    )
    return PromptFiles(
        system_prompt=None if system_path is None else system_path.read_text(encoding="utf-8"),
        append_system_prompt=(
            None if append_path is None else append_path.read_text(encoding="utf-8")
        ),
    )


def build_system_prompt(
    *,
    cwd: Path,
    system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    context_files: tuple[ContextFile, ...] = (),
) -> str:
    prompt = _DEFAULT_PROMPT if system_prompt is None else system_prompt
    if append_system_prompt:
        prompt += f"\n\n{append_system_prompt}"
    if context_files:
        prompt += "\n\n<project_context>\nProject-specific instructions and guidelines:\n"
        for context in context_files:
            path = escape(context.path.as_posix(), quote=True)
            content = escape(context.content, quote=False)
            prompt += f'<project_instructions path="{path}">\n{content}\n</project_instructions>\n'
        prompt += "</project_context>"
    return f"{prompt}\nCurrent working directory: {cwd.resolve().as_posix()}"


__all__ = ["PromptFiles", "build_system_prompt", "discover_prompt_files"]
