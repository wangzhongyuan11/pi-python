"""P15.5/1.1.0 gap closure: --tools +name/-name and * patterns.

``+name`` adds to the default selection instead of replacing it, ``-name``
removes, and fnmatch-style ``*`` patterns match against the full tool list.
"""

from __future__ import annotations

from pi_coding_agent.tools.registry import (
    expand_tool_selection,
)


def test_plus_and_minus_adjust_the_default_selection() -> None:
    result = expand_tool_selection(("+grep", "-edit"))

    assert "grep" in result
    assert "edit" not in result
    assert "read" in result  # defaults survive
    assert "bash" in result


def test_plain_entries_still_replace_the_selection() -> None:
    result = expand_tool_selection(("read", "grep"))

    assert result == ("read", "grep")


def test_star_pattern_matches_against_all_tools() -> None:
    result = expand_tool_selection(("*e*",))

    assert "read" in result
    assert "write" in result
    assert "ls" not in result


def test_mcp_prefix_pattern_is_preserved_for_extension_tools() -> None:
    result = expand_tool_selection(("mcp__radius__*",))

    # MCP tools are not built-ins; the pattern must survive expansion so the
    # extension-layer can match it against runtime-registered names.
    assert result == ("mcp__radius__*",)


def test_plus_and_star_can_combine() -> None:
    result = expand_tool_selection(("+*e*", "-write"))

    # +*e* matches read/edit/write/grep; defaults minus write keep bash.
    assert "read" in result
    assert "write" not in result
    assert "grep" in result
    assert "bash" in result
    assert "edit" in result
