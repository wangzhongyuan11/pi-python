"""Differential oracle comparing core Python semantics against frozen upstream.

Two probes run the same canonical v3 fixture through both implementations and
compare normalized outputs:

- ``tree``: entry graph (parent indices), leaf, and active path derived by the
  Python SessionTree versus the frozen TypeScript SessionManager.
- ``cutpoint``: the compaction cut chosen by ``choose_compaction_cutpoint``
  versus the frozen TypeScript ``findCutPoint``. The Python side mirrors the
  upstream per-entry token estimator so both sides decide on equal budgets.

Entry ids, timestamps, and absolute paths never take part in the comparison:
positions in the fixture are the only identity.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pi_coding_agent.compaction.cutpoint import choose_compaction_cutpoint
from pi_coding_agent.session.models import MessageEntry, SessionEntry
from pi_coding_agent.session.reader import read_session
from pi_coding_agent.session.tree import SessionTree
from scripts.ts_oracle import verify_frozen_commit

ESTIMATED_IMAGE_CHARS = 200
_PROBE_PATHS = {
    "tree": Path("packages") / "coding-agent" / "src" / "core" / "session-manager.ts",
    "cutpoint": Path("packages") / "coding-agent" / "src" / "core" / "compaction" / "compaction.ts",
}


class DifferentialOracleError(RuntimeError):
    """A probe failed to run on either side or produced an invalid result."""


def _read_fixture(path: str | Path) -> tuple[SessionEntry, ...]:
    parsed = read_session(path)
    SessionTree.build(parsed.entries)
    return parsed.entries


def _indices(entries: Sequence[SessionEntry]) -> dict[str, int]:
    return {entry.id: index for index, entry in enumerate(entries)}


def _ceil4(chars: int) -> int:
    return math.ceil(chars / 4)


def _content_chars(content: object) -> int:
    if isinstance(content, str):
        return len(content)
    if not isinstance(content, Sequence):
        return 0
    chars = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            chars += len(cast("str", block.get("text", "")))
        elif block.get("type") == "image":
            chars += ESTIMATED_IMAGE_CHARS
    return chars


def _upstream_entry_tokens(entry: SessionEntry) -> int:
    """Mirror upstream ``estimateTokens`` over a wire-format message entry."""

    if not isinstance(entry, MessageEntry):
        return 0
    message = entry.message
    role = message.get("role")
    if role == "assistant":
        chars = 0
        for block in message.get("content") or ():
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text":
                chars += len(cast("str", block.get("text", "")))
            elif kind == "thinking":
                chars += len(cast("str", block.get("thinking", "")))
            elif kind == "toolCall":
                chars += len(cast("str", block.get("name", ""))) + len(
                    json.dumps(block.get("arguments", {}))
                )
        return _ceil4(chars)
    if role in {"user", "toolResult"}:
        return _ceil4(_content_chars(message.get("content")))
    return 0


def _python_tree(fixture: str | Path) -> dict[str, object]:
    entries = _read_fixture(fixture)
    tree = SessionTree.build(entries)
    leaf_id = tree.leaf_ids[-1] if tree.leaf_ids else None
    index = _indices(entries)
    parents = [
        index.get(entry.parent_id) if entry.parent_id is not None else None for entry in entries
    ]
    active_path = (
        [index[entry.id] for entry in tree.active_path(leaf_id)] if leaf_id is not None else []
    )
    return {
        "leaf": index.get(leaf_id) if leaf_id is not None else None,
        "parents": parents,
        "activePath": active_path,
    }


def _python_cutpoint(fixture: str | Path, keep_recent_tokens: int) -> dict[str, object]:
    entries = _read_fixture(fixture)
    cutpoint = choose_compaction_cutpoint(
        entries,
        keep_recent_tokens=keep_recent_tokens,
        token_count=_upstream_entry_tokens,
    )
    return {
        "firstKeptEntryIndex": cutpoint.first_kept_index,
        "turnStartIndex": -1 if cutpoint.turn_start_index is None else cutpoint.turn_start_index,
        "isSplitTurn": cutpoint.splits_turn,
    }


def _run_typescript(source: Path, script: str, *arguments: str) -> str:
    completed = subprocess.run(
        [
            "node",
            "--import",
            "tsx",
            "--input-type=module",
            "-e",
            script,
            *[str(argument) for argument in arguments],
        ],
        cwd=source,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise DifferentialOracleError(completed.stderr.strip() or "TypeScript probe failed")
    return completed.stdout.strip()


_TREE_SCRIPT = (
    "import {pathToFileURL} from 'node:url';"
    "import {readFileSync} from 'node:fs';"
    "const m = await import(pathToFileURL(process.argv[1]).href);"
    "const lines = readFileSync(process.argv[2], 'utf8').split(/\\r?\\n/).filter(Boolean);"
    "const entries = lines.slice(1).map((line) => JSON.parse(line));"
    "const index = new Map(entries.map((entry, position) => [entry.id, position]));"
    "const leaf = m.SessionManager.open(process.argv[2]).getLeafId();"
    "const parents = entries.map((entry) => entry.parentId ? index.get(entry.parentId) : null);"
    "const activePath = [];"
    "let cursor = leaf ? index.get(leaf) : undefined;"
    "while (cursor !== undefined && cursor !== null) { activePath.unshift(cursor);"
    "  const parent = parents[cursor]; cursor = parent === null ? null : parent; }"
    "process.stdout.write(JSON.stringify("
    "  {leaf: leaf ? index.get(leaf) : null, parents, activePath}));"
)

_CUTPOINT_SCRIPT = (
    "import {pathToFileURL} from 'node:url';"
    "import {readFileSync} from 'node:fs';"
    "const m = await import(pathToFileURL(process.argv[1]).href);"
    "const lines = readFileSync(process.argv[2], 'utf8').split(/\\r?\\n/).filter(Boolean);"
    "const entries = lines.slice(1).map((line) => JSON.parse(line));"
    "const result = m.findCutPoint(entries, 0, entries.length, Number(process.argv[3]));"
    "process.stdout.write(JSON.stringify(result));"
)


def typescript_tree(source: Path, fixture: str | Path) -> dict[str, object]:
    payload = _run_typescript(source, _TREE_SCRIPT, source / _PROBE_PATHS["tree"], fixture)
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise DifferentialOracleError("TypeScript tree probe returned an invalid result")
    return parsed


def typescript_cutpoint(
    source: Path, fixture: str | Path, keep_recent_tokens: int
) -> dict[str, object]:
    payload = _run_typescript(
        source, _CUTPOINT_SCRIPT, source / _PROBE_PATHS["cutpoint"], fixture, keep_recent_tokens
    )
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise DifferentialOracleError("TypeScript cutpoint probe returned an invalid result")
    return parsed


def compare(
    label: str, python_result: dict[str, object], typescript_result: dict[str, object]
) -> str | None:
    if python_result == typescript_result:
        return None
    return (
        f"{label} diverged:\n"
        f"  python:     {json.dumps(python_result, sort_keys=True)}\n"
        f"  typescript: {json.dumps(typescript_result, sort_keys=True)}"
    )


def run_probe(
    probe: str,
    fixture: str | Path,
    source: Path,
    *,
    keep_recent_tokens: int = 1000,
) -> str | None:
    """Return None on semantic parity, otherwise a human-readable diff."""

    verify_frozen_commit(source)
    fixture_path = Path(fixture).resolve()
    if probe == "tree":
        return compare(
            f"tree[{fixture_path.name}]",
            _python_tree(fixture_path),
            typescript_tree(source, fixture_path),
        )
    if probe == "cutpoint":
        return compare(
            f"cutpoint[{fixture_path.name}, keep={keep_recent_tokens}]",
            _python_cutpoint(fixture_path, keep_recent_tokens),
            typescript_cutpoint(source, fixture_path, keep_recent_tokens),
        )
    raise DifferentialOracleError(f"unknown probe {probe!r}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", choices=("tree", "cutpoint"))
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--keep-recent-tokens", type=int, default=1000)
    arguments = parser.parse_args(argv)
    try:
        diff = run_probe(
            arguments.probe,
            arguments.fixture,
            arguments.source,
            keep_recent_tokens=arguments.keep_recent_tokens,
        )
    except (DifferentialOracleError, OSError, ValueError) as error:
        print(f"differential oracle error: {error}")
        return 1
    if diff is None:
        print("match")
        return 0
    print(diff)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
