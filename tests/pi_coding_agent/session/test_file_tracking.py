from __future__ import annotations

from typing import cast

from pi_ai import JsonValue
from pi_coding_agent.file_tracking import compute_file_lists, track_file_operations
from pi_coding_agent.session.models import MessageEntry

STAMP = "2026-08-24T00:00:00.000Z"

_ASSISTANT_BASE: dict[str, JsonValue] = {
    "api": "test",
    "provider": "test",
    "model": "test-model",
    "usage": {},
    "stopReason": "toolUse",
    "timestamp": 1,
}


def _assistant(
    entry_id: str, parent_id: str | None, blocks: list[dict[str, JsonValue]]
) -> MessageEntry:
    return MessageEntry(
        type="message",
        id=entry_id,
        parent_id=parent_id,
        timestamp=STAMP,
        message=cast(
            "dict[str, JsonValue]",
            {"role": "assistant", "content": blocks, **_ASSISTANT_BASE},
        ),
    )


def _tool_result(entry_id: str, parent_id: str | None) -> MessageEntry:
    return MessageEntry(
        type="message",
        id=entry_id,
        parent_id=parent_id,
        timestamp=STAMP,
        message={
            "role": "toolResult",
            "toolCallId": f"{entry_id}-call",
            "toolName": "read",
            "content": [{"type": "text", "text": "ok"}],
            "isError": False,
            "timestamp": 1,
        },
    )


def _tool_call(name: str, arguments: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"type": "toolCall", "id": f"call-{name}", "name": name, "arguments": arguments}


def test_tool_calls_reduce_to_read_write_and_edit_sets() -> None:
    entries = (
        _assistant(
            "a1",
            None,
            [
                _tool_call("read", {"path": "a.py"}),
                _tool_call("write", {"path": "b.py"}),
                _tool_call("edit", {"path": "c.py"}),
            ],
        ),
        _tool_result("a2", "a1"),
    )

    ops = track_file_operations(entries)

    assert ops.read == frozenset({"a.py"})
    assert ops.written == frozenset({"b.py"})
    assert ops.edited == frozenset({"c.py"})


def test_tool_results_do_not_contribute_file_operations() -> None:
    ops = track_file_operations((_tool_result("r1", None),))

    assert ops.read == frozenset()
    assert ops.written == frozenset()
    assert ops.edited == frozenset()


def test_non_file_tools_and_missing_paths_are_ignored() -> None:
    entries = (
        _assistant(
            "a1",
            None,
            [
                _tool_call("bash", {"command": "mv a.py b.py"}),
                _tool_call("grep", {"pattern": "x", "path": "src"}),
                _tool_call("read", {}),
                _tool_call("edit", {"path": 7}),
            ],
        ),
    )

    ops = track_file_operations(entries)

    assert ops.read == frozenset()
    assert ops.written == frozenset()
    assert ops.edited == frozenset()


def test_file_lists_are_sorted_and_modified_files_shadow_reads() -> None:
    entries = (
        _assistant(
            "a1",
            None,
            [
                _tool_call("read", {"path": "e.py"}),
                _tool_call("read", {"path": "x.py"}),
                _tool_call("write", {"path": "x.py"}),
                _tool_call("edit", {"path": "d.py"}),
            ],
        ),
    )

    lists = compute_file_lists(track_file_operations(entries))

    assert lists.read_files == ("e.py",)
    assert lists.modified_files == ("d.py", "x.py")
