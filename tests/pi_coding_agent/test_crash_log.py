"""P15.5/1.1.0 gap closure: crash-log."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from pi_coding_agent.crash_log import write_crash_log


def test_writes_error_meta_and_recent_entries(tmp_path: Path) -> None:
    try:
        raise ValueError("boom")
    except ValueError as error:
        path = write_crash_log(
            tmp_path / "agent",
            error,
            session_path=Path("/s/session.jsonl"),
            transcript_entries=[{"type": "message", "id": "e1"}, {"type": "message", "id": "e2"}],
            now_ms=1_760_000_000_000,
        )

    assert path is not None
    assert "crash" in str(path)
    assert "boom" in (path / "error.txt").read_text(encoding="utf-8")
    meta = (path / "meta.json").read_text(encoding="utf-8")
    assert "ValueError" in meta
    assert "session.jsonl" in meta
    entries = (path / "recent-entries.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(entries) == 2


def test_logging_failure_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("not a dir", encoding="utf-8")
    monkeypatch.setattr(Path, "mkdir", lambda self, *a, **k: (_ for _ in ()).throw(OSError("no")))

    class _Err(Exception):
        pass

    try:
        raise _Err("x")
    except _Err as error:
        path = write_crash_log(blocked, error)

    assert path is None


def test_cli_top_level_exception_writes_crash_log(tmp_path: Path, monkeypatch) -> None:
    import pi_coding_agent.cli.main as main_mod
    from pi_ai import FakeProvider, fake_model
    from pi_coding_agent.cli.main import main
    from pi_coding_agent.model_runtime import ModelRuntime

    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated crash in headless")

    monkeypatch.setattr(main_mod, "run_headless", boom)

    with pytest.raises(RuntimeError, match="simulated crash"):
        main(
            ["-p", "hi", "--no-session"],
            stdout=StringIO(),
            stderr=StringIO(),
            cwd=project,
            environ={"PI_PYTHON_AGENT_DIR": str(agent_dir)},
            model_runtime=ModelRuntime(provider=FakeProvider([]), model=fake_model()),
        )

    crash_root = agent_dir / "crash"
    crash_dirs = list(crash_root.iterdir()) if crash_root.exists() else []
    assert crash_dirs, "crash log directory must be created"
    error_txt = (crash_dirs[0] / "error.txt").read_text(encoding="utf-8")
    assert "simulated crash in headless" in error_txt
