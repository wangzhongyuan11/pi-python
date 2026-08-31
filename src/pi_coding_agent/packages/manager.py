"""Persistent package source management."""

from __future__ import annotations

from pi_coding_agent.config.models import PackageSource
from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.ports import ConfiguredPackage, PackageScope


class DefaultPackageManager:
    def __init__(self, *, settings: SettingsManager) -> None:
        self._settings = settings

    def add_source(self, source: str, *, scope: PackageScope = "user") -> bool:
        _validate_source(source)
        current = self._settings.package_sources(scope)
        if any(_source_text(existing) == source for existing in current):
            return False
        self._settings.set_package_sources((*current, source), scope=scope)
        return True

    def remove_source(self, source: str, *, scope: PackageScope = "user") -> bool:
        _validate_source(source)
        current = self._settings.package_sources(scope)
        remaining = tuple(existing for existing in current if _source_text(existing) != source)
        if len(remaining) == len(current):
            return False
        self._settings.set_package_sources(remaining, scope=scope)
        return True

    def list_configured_packages(self) -> tuple[ConfiguredPackage, ...]:
        configured: list[ConfiguredPackage] = []
        for scope in ("user", "project"):
            for source in self._settings.package_sources(scope):
                configured.append(
                    ConfiguredPackage(
                        source=_source_text(source),
                        scope=scope,
                        filtered=isinstance(source, PackageSource),
                    )
                )
        return tuple(configured)


def _source_text(source: str | PackageSource) -> str:
    return source if isinstance(source, str) else source.source


def _validate_source(source: str) -> None:
    if not source.strip():
        raise ValueError("package source cannot be empty")


__all__ = ["DefaultPackageManager"]
