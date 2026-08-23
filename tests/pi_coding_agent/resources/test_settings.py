from __future__ import annotations

import json
from pathlib import Path

import pytest

from pi_coding_agent.config.models import SettingsValidationError
from pi_coding_agent.config.settings import SettingsManager


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_settings_merge_nested_layers_and_resolve_resource_paths(tmp_path: Path) -> None:
    agent_dir = tmp_path / "home" / ".pi-python" / "agent"
    cwd = tmp_path / "project"
    _write(
        agent_dir / "settings.json",
        {"retry": {"maxRetries": 2}, "skills": ["global-skill"], "future": {"x": 1}},
    )
    _write(
        cwd / ".pi-python" / "settings.json",
        {"retry": {"enabled": False}, "skills": ["project-skill"]},
    )

    settings = SettingsManager.load(
        agent_dir=agent_dir,
        cwd=cwd,
        project_trusted=True,
        environment_overrides={"quietStartup": True},
        cli_overrides={"defaultModel": "deepseek-v4-flash"},
    )

    assert settings.values.retry.enabled is False
    assert settings.values.retry.max_retries == 2
    assert settings.values.default_model == "deepseek-v4-flash"
    assert settings.values.quiet_startup is True
    assert settings.resource_paths("skills") == ((cwd / "project-skill").resolve(),)
    assert settings.compatibility == {"future": {"x": 1}}
    assert settings.warnings == ("unknown global setting preserved: future",)


def test_untrusted_project_settings_are_not_read(tmp_path: Path) -> None:
    project_file = tmp_path / "project" / ".pi-python" / "settings.json"
    _write(project_file, {"defaultModel": "must-not-load"})

    settings = SettingsManager.load(
        agent_dir=tmp_path / "agent",
        cwd=tmp_path / "project",
        project_trusted=False,
    )

    assert settings.values.default_model is None


def test_project_cannot_override_global_only_trust_default(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    project = tmp_path / "project"
    _write(agent / "settings.json", {"defaultProjectTrust": "never"})
    _write(project / ".pi-python" / "settings.json", {"defaultProjectTrust": "always"})

    settings = SettingsManager.load(agent_dir=agent, cwd=project, project_trusted=True)

    assert settings.values.default_project_trust == "never"
    assert "global-only" in settings.warnings[-1]


def test_invalid_known_setting_reports_scope_and_path(tmp_path: Path) -> None:
    path = tmp_path / "agent" / "settings.json"
    _write(path, {"retry": {"maxRetries": -1}})

    with pytest.raises(SettingsValidationError) as caught:
        SettingsManager.load(agent_dir=tmp_path / "agent", cwd=tmp_path / "project")

    assert "global settings" in str(caught.value)
    assert str(path.resolve()) in str(caught.value)


def test_remaining_supported_settings_are_validated_not_preserved_as_unknown(
    tmp_path: Path,
) -> None:
    agent = tmp_path / "agent"
    _write(
        agent / "settings.json",
        {
            "terminal": {"clearOnShrink": True, "showTerminalProgress": True},
            "images": {"autoResize": False, "blockImages": True},
            "enabledModels": ["deepseek/*"],
            "defaultTools": ["read", "bash"],
            "doubleEscapeAction": "fork",
            "treeFilterMode": "no-tools",
            "thinkingBudgets": {"minimal": 1, "high": 8},
            "editorPaddingX": 2,
            "outputPad": 0,
            "autocompleteMaxVisible": 7,
            "showHardwareCursor": True,
            "markdown": {"codeBlockIndent": "    ", "mermaid": "final"},
            "sessionDir": "sessions",
            "httpProxy": "http://proxy.invalid",
            "httpIdleTimeoutMs": 0,
            "tuiMode": "fullscreen",
            "fullscreenExitOutput": "resume-hint",
            "fullscreenScrollbar": "always",
        },
    )

    settings = SettingsManager.load(agent_dir=agent, cwd=tmp_path)

    assert settings.compatibility == {}
    assert settings.values.images.block_images
    assert settings.values.markdown.mermaid == "final"
    assert settings.values.fullscreen_scrollbar == "always"


def test_websocket_setting_has_clear_migration_failure(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    _write(agent / "settings.json", {"websocketConnectTimeoutMs": 1000})

    with pytest.raises(SettingsValidationError, match="websocket transport is not supported"):
        SettingsManager.load(agent_dir=agent, cwd=tmp_path)
