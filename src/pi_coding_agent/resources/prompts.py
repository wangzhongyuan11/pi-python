"""Lazy prompt-template descriptors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .metadata import FrontmatterError, read_body, read_frontmatter


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceDiagnostic:
    code: str
    message: str
    path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class PromptDescriptor:
    name: str
    description: str
    argument_hint: str | None
    path: Path

    def load_content(self) -> str:
        return read_body(self.path)


@dataclass(frozen=True, slots=True, kw_only=True)
class LoadPromptsResult:
    prompts: tuple[PromptDescriptor, ...]
    diagnostics: tuple[ResourceDiagnostic, ...]


def load_prompt_descriptors(paths: tuple[Path, ...]) -> LoadPromptsResult:
    prompts: list[PromptDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    names: set[str] = set()
    for raw_path in paths:
        path = raw_path.resolve()
        if not path.is_file() or path.suffix.casefold() != ".md":
            diagnostics.append(
                ResourceDiagnostic(code="invalid", message="not a markdown file", path=path)
            )
            continue
        try:
            metadata = read_frontmatter(path)
        except (OSError, UnicodeError, FrontmatterError) as error:
            diagnostics.append(ResourceDiagnostic(code="invalid", message=str(error), path=path))
            continue
        name = path.stem
        if name in names:
            diagnostics.append(
                ResourceDiagnostic(
                    code="duplicate", message=f'prompt name "{name}" collision', path=path
                )
            )
            continue
        description_value = metadata.get("description", name)
        hint_value = metadata.get("argument-hint")
        if not isinstance(description_value, str) or not isinstance(hint_value, str | type(None)):
            diagnostics.append(
                ResourceDiagnostic(code="invalid", message="invalid metadata", path=path)
            )
            continue
        names.add(name)
        prompts.append(
            PromptDescriptor(
                name=name,
                description=description_value,
                argument_hint=hint_value,
                path=path,
            )
        )
    return LoadPromptsResult(prompts=tuple(prompts), diagnostics=tuple(diagnostics))


__all__ = [
    "LoadPromptsResult",
    "PromptDescriptor",
    "ResourceDiagnostic",
    "load_prompt_descriptors",
]
