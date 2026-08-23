"""Strict JSON theme loading and cycle-safe variable resolution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from pi_tui.theme import Theme, ThemeColor, create_theme

from .prompts import ResourceDiagnostic

type PaletteIndex = Annotated[StrictInt, Field(ge=0, le=255)]
type ColorValue = str | PaletteIndex

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_REQUIRED_COLORS = frozenset(
    {
        "accent",
        "bashMode",
        "border",
        "borderAccent",
        "borderMuted",
        "customMessageBg",
        "customMessageLabel",
        "customMessageText",
        "dim",
        "error",
        "mdCode",
        "mdCodeBlock",
        "mdCodeBlockBorder",
        "mdHeading",
        "mdHr",
        "mdLink",
        "mdLinkUrl",
        "mdListBullet",
        "mdQuote",
        "mdQuoteBorder",
        "muted",
        "selectedBg",
        "success",
        "syntaxComment",
        "syntaxFunction",
        "syntaxKeyword",
        "syntaxNumber",
        "syntaxOperator",
        "syntaxPunctuation",
        "syntaxString",
        "syntaxType",
        "syntaxVariable",
        "text",
        "thinkingHigh",
        "thinkingLow",
        "thinkingMedium",
        "thinkingMinimal",
        "thinkingOff",
        "thinkingText",
        "thinkingXhigh",
        "toolDiffAdded",
        "toolDiffContext",
        "toolDiffRemoved",
        "toolErrorBg",
        "toolOutput",
        "toolPendingBg",
        "toolSuccessBg",
        "toolTitle",
        "userMessageBg",
        "userMessageText",
        "warning",
    }
)


class ThemeLoadError(ValueError):
    pass


class _ThemeWire(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_url: str | None = Field(default=None, alias="$schema")
    name: str
    vars: dict[str, ColorValue] = Field(default_factory=dict)
    colors: dict[str, ColorValue] = Field(min_length=1)
    export: dict[str, ColorValue] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        if not value or "/" in value or "\\" in value:
            raise ValueError("theme name must be non-empty and contain no path separator")
        return value

    @model_validator(mode="after")
    def _required_color_roles(self) -> _ThemeWire:
        missing = sorted(_REQUIRED_COLORS.difference(self.colors))
        if missing:
            raise ValueError(f"missing required theme colors: {', '.join(missing)}")
        return self


@dataclass(frozen=True, slots=True, kw_only=True)
class LoadThemesResult:
    themes: tuple[Theme, ...]
    diagnostics: tuple[ResourceDiagnostic, ...]


def _resolve(
    value: ColorValue, variables: dict[str, ColorValue], stack: tuple[str, ...]
) -> ThemeColor:
    if isinstance(value, int) or value == "" or _HEX_COLOR.fullmatch(value):
        return value
    if value in stack:
        chain = " -> ".join((*stack, value))
        raise ThemeLoadError(f"theme variable cycle: {chain}")
    target = variables.get(value)
    if target is None:
        raise ThemeLoadError(f'unknown theme variable "{value}"')
    return _resolve(target, variables, (*stack, value))


def _load(path: Path) -> Theme:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        wire = _ThemeWire.model_validate(raw)
        colors = {key: _resolve(value, wire.vars, ()) for key, value in wire.colors.items()}
        export = {key: _resolve(value, wire.vars, ()) for key, value in wire.export.items()}
    except ThemeLoadError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as error:
        raise ThemeLoadError(f"invalid theme {path.resolve()}: {type(error).__name__}") from error
    return create_theme(name=wire.name, colors=colors, export_colors=export)


def load_themes(paths: tuple[Path, ...], *, strict: bool = False) -> LoadThemesResult:
    themes: list[Theme] = []
    diagnostics: list[ResourceDiagnostic] = []
    names: set[str] = set()
    for path in paths:
        resolved = path.resolve()
        try:
            theme = _load(resolved)
        except ThemeLoadError as error:
            if strict:
                raise ThemeLoadError(f"invalid theme {resolved}: {error}") from error
            diagnostics.append(
                ResourceDiagnostic(code="invalid", message=str(error), path=resolved)
            )
            continue
        if theme.name in names:
            diagnostics.append(
                ResourceDiagnostic(
                    code="duplicate",
                    message=f'theme name "{theme.name}" collision',
                    path=resolved,
                )
            )
            continue
        names.add(theme.name)
        themes.append(theme)
    return LoadThemesResult(themes=tuple(themes), diagnostics=tuple(diagnostics))


__all__ = ["LoadThemesResult", "ThemeLoadError", "load_themes"]
