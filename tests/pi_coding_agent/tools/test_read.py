from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_coding_agent.tools.read import ReadToolError, read_file


def test_reads_utf8_bom_unicode_and_crlf_without_rewriting(tmp_path: Path) -> None:
    path = tmp_path / "中文 file.txt"
    original = b"\xef\xbb\xbfalpha\r\n\xe4\xb8\xad\xe6\x96\x87\r\n"
    path.write_bytes(original)

    result = asyncio.run(read_file(path.name, cwd=tmp_path))

    assert result.text == "\ufeffalpha\r\n中文\r\n"
    assert result.truncated is False
    assert path.read_bytes() == original


def test_offset_and_limit_are_one_based_with_continuation_hint(tmp_path: Path) -> None:
    path = tmp_path / "lines.txt"
    path.write_text("one\ntwo\nthree\nfour", encoding="utf-8", newline="")

    result = asyncio.run(read_file(path, cwd=tmp_path, offset=2, limit=2))

    assert result.text == "two\nthree\n\n[1 more lines in file. Use offset=4 to continue.]"
    assert result.next_offset == 4
    assert result.start_line == 2
    assert result.end_line == 3


def test_default_head_truncation_keeps_complete_lines_and_does_not_save_output(
    tmp_path: Path,
) -> None:
    path = tmp_path / "large.txt"
    path.write_text(
        "\n".join(f"line-{index}" for index in range(2_005)),
        encoding="utf-8",
        newline="",
    )
    before = {item.name for item in tmp_path.iterdir()}

    result = asyncio.run(read_file(path, cwd=tmp_path))

    assert result.truncated is True
    assert result.truncated_by == "lines"
    assert result.next_offset == 2_001
    assert "[Showing lines 1-2000 of 2005. Use offset=2001 to continue.]" in result.text
    assert {item.name for item in tmp_path.iterdir()} == before


def test_first_oversized_line_returns_instruction_without_partial_utf8(tmp_path: Path) -> None:
    path = tmp_path / "one-line.txt"
    path.write_text("界" * 20_000, encoding="utf-8", newline="")

    result = asyncio.run(read_file(path, cwd=tmp_path))

    assert result.truncated is True
    assert result.first_line_exceeds_limit is True
    assert result.text.startswith("[Line 1 is ")
    assert "exceeds 50.0KB limit" in result.text
    assert "界" not in result.text


def test_rejects_invalid_ranges_and_offsets_beyond_eof(tmp_path: Path) -> None:
    path = tmp_path / "short.txt"
    path.write_text("one\ntwo", encoding="utf-8", newline="")

    with pytest.raises(ReadToolError):
        asyncio.run(read_file(path, cwd=tmp_path, offset=0))
    with pytest.raises(ReadToolError):
        asyncio.run(read_file(path, cwd=tmp_path, limit=0))
    with pytest.raises(ReadToolError):
        asyncio.run(read_file(path, cwd=tmp_path, offset=3))


def test_pre_aborted_read_never_opens_the_file(tmp_path: Path) -> None:
    abort_event = asyncio.Event()
    abort_event.set()

    with pytest.raises(ReadToolError, match="aborted"):
        asyncio.run(
            read_file(
                tmp_path / "missing.txt",
                cwd=tmp_path,
                abort_event=abort_event,
            )
        )
