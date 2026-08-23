"""Canonical product configuration paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfigPaths:
    home: Path
    cwd: Path
    agent_dir: Path
    project_dir: Path
    compatibility_dir: Path
    session_dir: Path

    @classmethod
    def create(
        cls,
        *,
        home: Path,
        cwd: Path,
        agent_dir: Path | None = None,
        session_dir: Path | None = None,
    ) -> ConfigPaths:
        resolved_home = home.resolve()
        resolved_cwd = cwd.resolve()
        resolved_agent = (
            (resolved_home / ".pi-python" / "agent").resolve()
            if agent_dir is None
            else agent_dir.expanduser().resolve()
        )
        resolved_sessions = (
            resolved_agent / "sessions"
            if session_dir is None
            else session_dir.expanduser().resolve()
        )
        return cls(
            home=resolved_home,
            cwd=resolved_cwd,
            agent_dir=resolved_agent,
            project_dir=(resolved_cwd / ".pi-python").resolve(),
            compatibility_dir=(resolved_cwd / ".pi").resolve(),
            session_dir=resolved_sessions,
        )
