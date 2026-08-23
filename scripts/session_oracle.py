"""Read-only interoperability probe for Session v3 fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pi_coding_agent.session.reader import read_session
from pi_coding_agent.session.tree import SessionTree
from scripts.ts_oracle import verify_frozen_commit


class SessionOracleError(RuntimeError):
    """The fixture or frozen TypeScript reader failed the parity probe."""


def validate_python_fixture(path: str | Path) -> tuple[str, int]:
    parsed = read_session(path)
    SessionTree.build(parsed.entries)
    return parsed.header.id, len(parsed.entries)


def open_with_typescript(source: str | Path, fixture: str | Path) -> tuple[str, int]:
    """Open a fixture with frozen SessionManager without mutating source or fixture."""

    source_path = Path(source).resolve()
    fixture_path = Path(fixture).resolve()
    verify_frozen_commit(source_path)
    before = hashlib.sha256(fixture_path.read_bytes()).digest()
    session_manager = (
        source_path / "packages" / "coding-agent" / "src" / "core" / "session-manager.ts"
    )
    script = (
        "import {pathToFileURL} from 'node:url';"
        "const m=await import(pathToFileURL(process.argv[1]).href);"
        "const s=m.SessionManager.open(process.argv[2]);"
        "process.stdout.write(JSON.stringify({id:s.getSessionId(),count:s.getEntries().length}));"
    )
    completed = subprocess.run(
        [
            "node",
            "--import",
            "tsx",
            "--input-type=module",
            "-e",
            script,
            str(session_manager),
            str(fixture_path),
        ],
        cwd=source_path,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise SessionOracleError(completed.stderr.strip() or "TypeScript SessionManager failed")
    if hashlib.sha256(fixture_path.read_bytes()).digest() != before:
        raise SessionOracleError("TypeScript oracle mutated the fixture")
    payload = cast("dict[str, object]", json.loads(completed.stdout))
    session_id = payload.get("id")
    count = payload.get("count")
    if not isinstance(session_id, str) or not isinstance(count, int):
        raise SessionOracleError("TypeScript oracle returned an invalid result")
    return session_id, count


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--source", type=Path)
    arguments = parser.parse_args(argv)
    python_result = validate_python_fixture(arguments.fixture)
    result = (
        python_result
        if arguments.source is None
        else open_with_typescript(arguments.source, arguments.fixture)
    )
    print(json.dumps({"id": result[0], "entries": result[1]}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
