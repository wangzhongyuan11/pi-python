"""Persistent package source management."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import cast

from pi_coding_agent.config.models import PackageSource
from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.ports import ConfiguredPackage, PackageScope, ResourceRoot

from .manifest import PackageManifestError, read_package_manifest

_INSTALL_METADATA = ".pi-python-install.json"


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
        scopes: tuple[PackageScope, ...] = (
            ("user", "project") if self._settings.project_trusted else ("user",)
        )
        for scope in scopes:
            installed = self._installed_packages(scope)
            for source in self._settings.package_sources(scope):
                text = _source_text(source)
                configured.append(
                    ConfiguredPackage(
                        source=text,
                        scope=scope,
                        filtered=isinstance(source, PackageSource),
                        enabled=not isinstance(source, PackageSource) or source.autoload,
                        installed_path=installed.get(text),
                    )
                )
        return tuple(configured)

    def install_local(
        self, source: str | Path, *, scope: PackageScope = "user"
    ) -> tuple[ResourceRoot, ...]:
        source_root = Path(source).resolve()
        _validate_local_tree(source_root)
        packages_root = self._packages_root(scope)
        packages_root.mkdir(parents=True, exist_ok=True)
        nonce = uuid.uuid4().hex
        staging = packages_root / f".{source_root.name}.{nonce}.staging"
        backup: Path | None = None
        target: Path | None = None
        try:
            shutil.copytree(source_root, staging)
            staged_manifest = read_package_manifest(staging)
            (staging / _INSTALL_METADATA).write_text(
                json.dumps({"source": str(source_root), "scope": scope}), encoding="utf-8"
            )
            target = packages_root / staged_manifest.name
            backup = packages_root / f".{staged_manifest.name}.{nonce}.backup"
            if target.exists():
                target.rename(backup)
            staging.rename(target)
            try:
                self.add_source(str(source_root), scope=scope)
            except BaseException:
                shutil.rmtree(target, ignore_errors=True)
                if backup.exists():
                    backup.rename(target)
                raise
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            return read_package_manifest(target).resources
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            if (
                backup is not None
                and backup.exists()
                and target is not None
                and not target.exists()
            ):
                backup.rename(target)
            raise

    def resource_roots(self) -> tuple[ResourceRoot, ...]:
        roots: list[ResourceRoot] = []
        scopes: tuple[PackageScope, ...] = (
            ("user", "project") if self._settings.project_trusted else ("user",)
        )
        for scope in scopes:
            installed = self._installed_packages(scope)
            for configured in self._settings.package_sources(scope):
                if isinstance(configured, PackageSource) and not configured.autoload:
                    continue
                package_root = installed.get(_source_text(configured))
                if package_root is not None:
                    roots.extend(read_package_manifest(package_root).resources)
        return tuple(roots)

    def set_enabled(self, source: str, enabled: bool, *, scope: PackageScope = "user") -> bool:
        current = self._settings.package_sources(scope)
        changed = False
        updated: list[str | PackageSource] = []
        for configured in current:
            if _source_text(configured) != source:
                updated.append(configured)
                continue
            current_enabled = not isinstance(configured, PackageSource) or configured.autoload
            if current_enabled == enabled:
                updated.append(configured)
                continue
            changed = True
            if (
                enabled
                and isinstance(configured, PackageSource)
                and not any(
                    (
                        configured.extensions,
                        configured.skills,
                        configured.prompts,
                        configured.themes,
                    )
                )
            ):
                updated.append(configured.source)
            elif isinstance(configured, PackageSource):
                updated.append(configured.model_copy(update={"autoload": enabled}))
            else:
                updated.append(PackageSource(source=configured, autoload=enabled))
        if changed:
            self._settings.set_package_sources(tuple(updated), scope=scope)
        return changed

    def remove_installed(self, source: str, *, scope: PackageScope = "user") -> bool:
        installed = self._installed_packages(scope).get(source)
        current = self._settings.package_sources(scope)
        if not any(_source_text(item) == source for item in current):
            return False
        backup: Path | None = None
        if installed is not None:
            backup = installed.parent / f".{installed.name}.{uuid.uuid4().hex}.backup"
            installed.rename(backup)
        try:
            removed = self.remove_source(source, scope=scope)
        except BaseException:
            if backup is not None and backup.exists():
                assert installed is not None
                backup.rename(installed)
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
        return removed

    def _installed_packages(self, scope: PackageScope) -> dict[str, Path]:
        packages_root = self._packages_root(scope)
        if not packages_root.is_dir():
            return {}
        installed: dict[str, Path] = {}
        for package_root in sorted(packages_root.iterdir()):
            metadata = package_root / _INSTALL_METADATA
            if package_root.name.startswith(".") or not metadata.is_file():
                continue
            try:
                raw: object = json.loads(metadata.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if isinstance(raw, dict):
                payload = cast(dict[str, object], raw)
                source = payload.get("source")
                if isinstance(source, str):
                    installed[source] = package_root.resolve()
        return installed

    def _packages_root(self, scope: PackageScope) -> Path:
        if scope == "user":
            return self._settings.agent_dir / "packages"
        if not self._settings.project_trusted:
            raise PermissionError("project trust is required to install project packages")
        return self._settings.cwd / ".pi-python" / "packages"


def _source_text(source: str | PackageSource) -> str:
    return source if isinstance(source, str) else source.source


def _validate_source(source: str) -> None:
    if not source.strip():
        raise ValueError("package source cannot be empty")


def _validate_local_tree(source: Path) -> None:
    if not source.is_dir() or source.is_symlink() or source.is_junction():
        raise PackageManifestError(f"local package is not a regular directory: {source}")
    for path in source.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise PackageManifestError(f"local package contains a link: {path}")


__all__ = ["DefaultPackageManager"]
