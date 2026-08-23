from __future__ import annotations

from pathlib import Path

from pi_coding_agent.config.env import resolve_environment
from pi_coding_agent.config.paths import ConfigPaths


def test_configuration_paths_are_absolute_and_scoped(tmp_path: Path) -> None:
    paths = ConfigPaths.create(home=tmp_path / "home", cwd=tmp_path / "project")

    assert paths.agent_dir == (tmp_path / "home" / ".pi-python" / "agent").resolve()
    assert paths.project_dir == (tmp_path / "project" / ".pi-python").resolve()
    assert paths.compatibility_dir == (tmp_path / "project" / ".pi").resolve()
    assert paths.session_dir == paths.agent_dir / "sessions"


def test_python_environment_wins_over_legacy_and_warns(tmp_path: Path) -> None:
    resolved = resolve_environment(
        {
            "PI_PYTHON_AGENT_DIR": str(tmp_path / "new"),
            "PI_CODING_AGENT_DIR": str(tmp_path / "old"),
            "PI_PYTHON_SESSION_DIR": str(tmp_path / "new-sessions"),
            "PI_CODING_AGENT_SESSION_DIR": str(tmp_path / "old-sessions"),
            "PI_PYTHON_OFFLINE": "1",
            "PI_OFFLINE": "0",
        },
        compatibility=True,
    )

    assert resolved.agent_dir == (tmp_path / "new").resolve()
    assert resolved.session_dir == (tmp_path / "new-sessions").resolve()
    assert resolved.offline
    assert len(resolved.warnings) == 3


def test_legacy_environment_requires_explicit_compatibility(tmp_path: Path) -> None:
    environment = {
        "PI_CODING_AGENT_DIR": str(tmp_path / "legacy"),
        "PI_OFFLINE": "true",
    }

    disabled = resolve_environment(environment, compatibility=False)
    enabled = resolve_environment(environment, compatibility=True)

    assert disabled.agent_dir is None
    assert not disabled.offline
    assert enabled.agent_dir == (tmp_path / "legacy").resolve()
    assert enabled.offline


def test_false_boolean_values_are_not_treated_as_enabled() -> None:
    for value in ("", "0", "false", "no", "off"):
        assert not resolve_environment({"PI_PYTHON_OFFLINE": value}).offline
