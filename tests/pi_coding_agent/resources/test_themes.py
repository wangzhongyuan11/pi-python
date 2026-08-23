from __future__ import annotations

import json
from pathlib import Path

import pytest

from pi_coding_agent.resources.themes import ThemeLoadError, load_themes

_REQUIRED = {
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


def _theme(
    path: Path,
    *,
    name: str,
    accent: str = "brand",
    variables: dict[str, object] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    colors: dict[str, object] = dict.fromkeys(_REQUIRED, "brand")
    colors.update({"accent": accent, "text": "", "error": 196})
    path.write_text(
        json.dumps(
            {
                "name": name,
                "vars": {"brand": "#112233", **(variables or {})},
                "colors": colors,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_theme_resolves_variables_and_first_descriptor_wins(tmp_path: Path) -> None:
    first = _theme(tmp_path / "explicit.json", name="night")
    duplicate = _theme(tmp_path / "global.json", name="night", variables={"brand": "#ffffff"})

    result = load_themes((first, duplicate))

    assert len(result.themes) == 1
    assert result.themes[0].name == "night"
    assert result.themes[0].colors["accent"] == "#112233"
    assert result.themes[0].colors["text"] == ""
    assert result.themes[0].colors["error"] == 196
    assert set(result.themes[0].colors) == _REQUIRED
    assert result.diagnostics[0].code == "duplicate"


def test_theme_rejects_invalid_schema_and_variable_cycle(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"name":"incomplete","colors":{"accent":"#112233"}}', encoding="utf-8")
    cycle = _theme(
        tmp_path / "cycle.json",
        name="cycle",
        accent="a",
        variables={"a": "b", "b": "a"},
    )

    result = load_themes((invalid, cycle))

    assert result.themes == ()
    assert [item.code for item in result.diagnostics] == ["invalid", "invalid"]
    assert "cycle" in result.diagnostics[1].message


def test_direct_load_error_does_not_expose_raw_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"name":"broken","colors":{"accent":999}}', encoding="utf-8")

    with pytest.raises(ThemeLoadError, match="invalid theme"):
        load_themes((bad,), strict=True)
