from __future__ import annotations

import json
from pathlib import Path

import pytest

from pi_coding_agent.config.models import SettingsValidationError
from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.resources.default_loader import DefaultResourceLoader
from pi_coding_agent.services import create_product_services


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_project_trust_reloads_the_same_settings_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    _write(agent_dir / "settings.json", {"defaultModel": "global-model"})
    _write(project / ".pi-python" / "settings.json", {"defaultModel": "project-model"})
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))

    services = create_product_services(project)
    manager = services.settings

    assert isinstance(manager, SettingsManager)
    assert manager.get("defaultModel") == "global-model"

    services.reload_project_trust(True)

    assert services.settings is manager
    assert manager.get("defaultModel") == "project-model"
    assert isinstance(services.resources, DefaultResourceLoader)
    assert services.resources.last_result.project_trusted is True

    services.reload_project_trust(False)

    assert services.settings is manager
    assert manager.get("defaultModel") == "global-model"
    assert services.resources.last_result.project_trusted is False
    assert any("untrusted" in item for item in services.resources.last_result.diagnostics)


def test_invalid_project_settings_do_not_partially_apply_trust(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    _write(agent_dir / "settings.json", {"defaultModel": "global-model"})
    _write(project / ".pi-python" / "settings.json", {"retry": {"maxRetries": -1}})
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))
    services = create_product_services(project)
    manager = services.settings

    with pytest.raises(SettingsValidationError, match="project settings"):
        services.reload_project_trust(True)

    assert manager.get("defaultModel") == "global-model"
    assert isinstance(manager, SettingsManager)
    assert manager.project_trusted is False
    assert isinstance(services.resources, DefaultResourceLoader)
    with pytest.raises(RuntimeError, match="not been discovered"):
        _ = services.resources.last_result
