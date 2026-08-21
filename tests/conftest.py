from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests._bootstrap import (
    ALLOW_LIVE_PROVIDER_ENV,
    ALLOW_NETWORK_ENV,
    ISOLATION_MARKER_ENV,
    PytestEnvironment,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_ACTIVE_ENVIRONMENT = PytestEnvironment(_REPOSITORY_ROOT)
_ACTIVE_ENVIRONMENT.start()

_ENVIRONMENT_KEY = pytest.StashKey[PytestEnvironment]()


def pytest_configure(config: pytest.Config) -> None:
    config.stash[_ENVIRONMENT_KEY] = _ACTIVE_ENVIRONMENT


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    environment = config.stash[_ENVIRONMENT_KEY]
    live_skip = pytest.mark.skip(
        reason=f"set {ALLOW_LIVE_PROVIDER_ENV}=1 for this explicit live run"
    )
    network_skip = pytest.mark.skip(
        reason=f"set {ALLOW_NETWORK_ENV}=1 for this explicit network run"
    )
    for item in items:
        if item.get_closest_marker("live_provider") and not environment.allow_live_provider:
            item.add_marker(live_skip)
        if item.get_closest_marker("network") and not environment.allow_network:
            item.add_marker(network_skip)


def pytest_unconfigure(config: pytest.Config) -> None:
    environment = config.stash.get(_ENVIRONMENT_KEY, None)
    if environment is not None:
        environment.restore()
        del config.stash[_ENVIRONMENT_KEY]


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    config = home / ".config"
    cache = home / ".cache"
    data = home / ".local" / "share"
    roaming = home / "AppData" / "Roaming"
    local = home / "AppData" / "Local"
    git_config = home / ".gitconfig"

    for directory in (home, config, cache, data, roaming, local):
        directory.mkdir(parents=True, exist_ok=True)
    git_config.touch()

    for name, value in {
        "HOME": home,
        "USERPROFILE": home,
        "XDG_CONFIG_HOME": config,
        "XDG_CACHE_HOME": cache,
        "XDG_DATA_HOME": data,
        "APPDATA": roaming,
        "LOCALAPPDATA": local,
        "GIT_CONFIG_GLOBAL": git_config,
    }.items():
        monkeypatch.setenv(name, str(value))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    return home


@pytest.fixture(autouse=True)
def cleared_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    if _ACTIVE_ENVIRONMENT.allow_live_provider:
        return
    for name in tuple(os.environ):
        if name.upper().endswith("_API_KEY"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def no_external_network() -> None:
    assert os.environ[ISOLATION_MARKER_ENV] == "1"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "workspace"
    path.mkdir()
    return path
