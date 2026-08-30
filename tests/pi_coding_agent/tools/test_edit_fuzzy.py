"""Tiered fuzzy edit matching: NFKC, smart quotes, trailing whitespace (P11.5-T11)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_coding_agent.tools.edit import Edit, EditToolError, edit_file


def test_smart_quote_is_normalized_to_ascii_quote(tmp_path: Path) -> None:
    target = tmp_path / "quotes.txt"
    target.write_bytes("say it’s loud\n".encode())
    result = asyncio.run(
        edit_file(target, [Edit(old_text="it's", new_text="it was")], cwd=tmp_path)
    )
    assert result.replacements == 1
    assert "it was loud" in target.read_text(encoding="utf-8")


def test_trailing_whitespace_is_stripped_for_matching(tmp_path: Path) -> None:
    target = tmp_path / "whitespace.txt"
    target.write_text("value: 42   \nnext line\n", encoding="utf-8")
    result = asyncio.run(
        edit_file(
            target,
            [Edit(old_text="value: 42\nnext line", new_text="value: 43\nnext line")],
            cwd=tmp_path,
        )
    )
    assert result.replacements == 1
    content = target.read_text(encoding="utf-8")
    assert "value: 43" in content


def test_nfkc_compatibility_characters_match_ascii(tmp_path: Path) -> None:
    target = tmp_path / "nfkc.txt"
    target.write_text("ＢETA token\n", encoding="utf-8")
    result = asyncio.run(edit_file(target, [Edit(old_text="BETA", new_text="GAMMA")], cwd=tmp_path))
    assert result.replacements == 1
    assert "GAMMA" in target.read_text(encoding="utf-8")


def test_fuzzy_match_still_requires_uniqueness(tmp_path: Path) -> None:
    target = tmp_path / "duplicate.txt"
    target.write_text("say it’s loud\nsay it’s proud\n", encoding="utf-8")
    with pytest.raises(EditToolError, match="must be unique"):
        asyncio.run(edit_file(target, [Edit(old_text="it's", new_text="it was")], cwd=tmp_path))
    assert "say it’s loud" in target.read_text(encoding="utf-8")


def test_exact_match_survives_a_file_without_variants(tmp_path: Path) -> None:
    target = tmp_path / "plain.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    result = asyncio.run(edit_file(target, [Edit(old_text="beta", new_text="BETA")], cwd=tmp_path))
    assert result.replacements == 1
    assert result.first_changed_line == 2
    assert "alpha\nBETA\n" == target.read_text(encoding="utf-8")


def test_no_variant_found_reports_missing_edit(tmp_path: Path) -> None:
    target = tmp_path / "missing.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    with pytest.raises(EditToolError, match="Could not find"):
        asyncio.run(edit_file(target, [Edit(old_text="delta", new_text="GAMMA")], cwd=tmp_path))
