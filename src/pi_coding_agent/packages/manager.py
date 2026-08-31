"""Persistent package source management."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from pi_coding_agent.config.models import PackageSource
from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.ports import ConfiguredPackage, PackageScope, ResourceRoot

from .environment import Installer, install_requirement
from .manifest import PackageManifestError, read_package_manifest
from .npm_data import NpmPackRunner, build_tarball, extract_npm_data
from .resolver import resolve_source
from .spec import parse_package_spec

_INSTALL_METADATA = ".pi-python-install.json"
type CommandRunner = Callable[[Sequence[str]], str]


class DefaultPackageManager:
    def __init__(
        self,
        *,
        settings: SettingsManager,
        command_runner: CommandRunner | None = None,
        pypi_installer: Installer | None = None,
        npm_pack_runner: NpmPackRunner | None = None,
    ) -> None:
        self._settings = settings
        self._command_runner = command_runner or _run_command
        self._pypi_installer = pypi_installer or install_requirement
        self._npm_pack_runner = npm_pack_runner

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
        staging = packages_root / f".{source_root.name}.{uuid.uuid4().hex}.staging"
        shutil.copytree(source_root, staging)
        return self._activate_staging(staging, str(source_root), scope)

    def install_git(self, source: str, *, scope: PackageScope = "user") -> tuple[ResourceRoot, ...]:
        spec = parse_package_spec(source)
        if spec.kind != "git":
            raise ValueError(f"expected a git package source: {source}")
        resolved = resolve_source(spec, runner=self._command_runner)
        assert resolved.commit is not None
        packages_root = self._packages_root(scope)
        packages_root.mkdir(parents=True, exist_ok=True)
        staging = packages_root / f".git.{uuid.uuid4().hex}.staging"
        try:
            self._command_runner(("git", "clone", "--quiet", resolved.location, str(staging)))
            self._command_runner(
                ("git", "-C", str(staging), "checkout", "--quiet", resolved.commit)
            )
            _validate_local_tree(staging)
            return self._activate_staging(staging, source, scope)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def update_git(self, source: str, *, scope: PackageScope = "user") -> tuple[ResourceRoot, ...]:
        if not any(_source_text(item) == source for item in self._settings.package_sources(scope)):
            raise ValueError(f"No matching package found for {source}")
        return self.install_git(source, scope=scope)

    def install_pypi(
        self, source: str, *, scope: PackageScope = "user"
    ) -> tuple[ResourceRoot, ...]:
        spec = parse_package_spec(source)
        if spec.kind != "pypi":
            raise ValueError(f"expected a PyPI package source: {source}")
        requirement = spec.location if spec.rev is None else f"{spec.location}=={spec.rev}"
        packages_root = self._packages_root(scope)
        packages_root.mkdir(parents=True, exist_ok=True)
        staging = packages_root / f".pypi.{uuid.uuid4().hex}.staging"
        try:
            self._pypi_installer(requirement, staging)
            _validate_local_tree(staging)
            return self._activate_staging(staging, source, scope)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def update_pypi(self, source: str, *, scope: PackageScope = "user") -> tuple[ResourceRoot, ...]:
        if not any(_source_text(item) == source for item in self._settings.package_sources(scope)):
            raise ValueError(f"No matching package found for {source}")
        return self.install_pypi(source, scope=scope)

    def install_npm_data(
        self, source: str, *, scope: PackageScope = "user"
    ) -> tuple[ResourceRoot, ...]:
        if not source.startswith("npm:") or not source[4:].strip():
            raise ValueError(f"expected an npm data package source: {source}")
        packages_root = self._packages_root(scope)
        packages_root.mkdir(parents=True, exist_ok=True)
        cache_dir = self._settings.agent_dir / "package-cache" / "npm"
        tarball = build_tarball(source[4:], cache_dir=cache_dir, runner=self._npm_pack_runner)
        staging = packages_root / f".npm.{uuid.uuid4().hex}.staging"
        try:
            extracted = extract_npm_data(tarball, staging)
            safe_name = extracted.name.lstrip("@").replace("/", "--")
            (staging / "package.json").write_text(
                json.dumps(
                    {
                        "name": safe_name,
                        "pi": {
                            "skills": ["skills"],
                            "prompts": ["prompts"],
                            "themes": ["themes"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            return self._activate_staging(staging, source, scope)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def update(self, source: str | None = None, *, offline: bool = False) -> tuple[str, ...]:
        configured = self.list_configured_packages()
        selected = (
            tuple(item for item in configured if item.source == source)
            if source is not None
            else configured
        )
        if source is not None and not selected:
            available = ", ".join(item.source for item in configured) or "none"
            raise ValueError(
                f"No matching package found for {source}; configured packages: {available}"
            )
        updated: list[str] = []
        seen: set[tuple[PackageScope, str]] = set()
        for item in selected:
            identity = (item.scope, item.source)
            if identity in seen:
                continue
            seen.add(identity)
            if item.source.startswith("git+"):
                if offline:
                    continue
                self.update_git(item.source, scope=item.scope)
            elif item.source.startswith("npm:"):
                if offline:
                    continue
                self.install_npm_data(item.source, scope=item.scope)
            else:
                spec = parse_package_spec(item.source)
                if spec.kind == "local":
                    self.install_local(spec.location, scope=item.scope)
                elif not offline:
                    self.update_pypi(item.source, scope=item.scope)
                else:
                    continue
            updated.append(item.source)
        return tuple(updated)

    def _activate_staging(
        self, staging: Path, source: str, scope: PackageScope
    ) -> tuple[ResourceRoot, ...]:
        packages_root = self._packages_root(scope)
        nonce = uuid.uuid4().hex
        backup: Path | None = None
        target: Path | None = None
        try:
            staged_manifest = read_package_manifest(staging)
            (staging / _INSTALL_METADATA).write_text(
                json.dumps({"source": source, "scope": scope}), encoding="utf-8"
            )
            target = packages_root / staged_manifest.name
            backup = packages_root / f".{staged_manifest.name}.{nonce}.backup"
            if target.exists():
                target.rename(backup)
            staging.rename(target)
            try:
                self.add_source(source, scope=scope)
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


def _run_command(command: Sequence[str]) -> str:
    completed = subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    return completed.stdout


__all__ = ["DefaultPackageManager"]
