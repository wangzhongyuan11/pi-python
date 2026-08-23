from __future__ import annotations

import hashlib
import json
from io import StringIO
from pathlib import Path

from pi_coding_agent.cli.main import main


def _run(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    code = main(argv, stdout=stdout, stderr=stderr, cwd=cwd, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


def test_import_command_outputs_new_file_info_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text(
        json.dumps(
            {
                "type": "session",
                "version": 3,
                "id": "cli-import",
                "timestamp": "2026-08-24T00:00:00.000Z",
                "cwd": str(tmp_path.resolve()),
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    target = tmp_path / "sessions"

    code, stdout, stderr = _run(
        ["import-pi-session", str(source), "--session-dir", str(target)],
        tmp_path,
    )
    payload = json.loads(stdout)

    assert code == 0
    assert stderr == ""
    assert payload["sessionId"] == "cli-import"
    assert Path(payload["sessionFile"]).read_bytes() == source.read_bytes()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_import_command_rejects_old_version_without_traceback(tmp_path: Path) -> None:
    source = tmp_path / "old.jsonl"
    source.write_text(
        '{"type":"session","version":2,"id":"old","timestamp":"x","cwd":"x"}\n',
        encoding="utf-8",
    )

    code, stdout, stderr = _run(["import-pi-session", str(source)], tmp_path)

    assert code == 1
    assert stdout == ""
    assert "only Session version 3" in stderr
    assert "Traceback" not in stderr
