"""Validated lazy Agent Skill descriptors and prompt formatting."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import cast

from .metadata import FrontmatterError, read_body, read_frontmatter
from .prompts import ResourceDiagnostic

_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True, kw_only=True)
class SkillDescriptor:
    name: str
    description: str
    path: Path
    disable_model_invocation: bool = False

    def load_content(self) -> str:
        return read_body(self.path)


@dataclass(frozen=True, slots=True, kw_only=True)
class LoadSkillsResult:
    skills: tuple[SkillDescriptor, ...]
    diagnostics: tuple[ResourceDiagnostic, ...]


def load_skill_descriptors(paths: tuple[Path, ...]) -> LoadSkillsResult:
    skills: list[SkillDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    names: set[str] = set()
    for raw_path in paths:
        path = raw_path.resolve()
        try:
            metadata = read_frontmatter(path)
        except (OSError, UnicodeError, FrontmatterError) as error:
            diagnostics.append(ResourceDiagnostic(code="invalid", message=str(error), path=path))
            continue
        name_value = metadata.get("name", path.parent.name)
        description_value = metadata.get("description")
        disabled_value = metadata.get("disable-model-invocation", False)
        valid = (
            isinstance(name_value, str)
            and len(name_value) <= 64
            and _SKILL_NAME.fullmatch(name_value) is not None
            and isinstance(description_value, str)
            and 0 < len(description_value.strip()) <= 1024
            and isinstance(disabled_value, bool)
        )
        if not valid:
            diagnostics.append(
                ResourceDiagnostic(code="invalid", message="invalid skill metadata", path=path)
            )
            continue
        name = cast(str, name_value)
        description = cast(str, description_value)
        disabled = cast(bool, disabled_value)
        if name in names:
            diagnostics.append(
                ResourceDiagnostic(
                    code="duplicate", message=f'skill name "{name}" collision', path=path
                )
            )
            continue
        names.add(name)
        skills.append(
            SkillDescriptor(
                name=name,
                description=description,
                path=path,
                disable_model_invocation=disabled,
            )
        )
    return LoadSkillsResult(skills=tuple(skills), diagnostics=tuple(diagnostics))


def format_skills_for_prompt(skills: tuple[SkillDescriptor, ...]) -> str:
    visible = tuple(skill for skill in skills if not skill.disable_model_invocation)
    if not visible:
        return ""
    lines = [
        "<available_skills>",
    ]
    for skill in visible:
        lines.extend(
            (
                "  <skill>",
                f"    <name>{escape(skill.name, quote=True)}</name>",
                f"    <description>{escape(skill.description, quote=True)}</description>",
                f"    <location>{escape(skill.path.as_posix(), quote=True)}</location>",
                "  </skill>",
            )
        )
    lines.append("</available_skills>")
    return "\n".join(lines)


__all__ = [
    "LoadSkillsResult",
    "SkillDescriptor",
    "format_skills_for_prompt",
    "load_skill_descriptors",
]
