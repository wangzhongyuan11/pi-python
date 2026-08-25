"""Extension package management for the coding agent."""

from .environment import EnvironmentInstallError, ManagedEnvironment
from .lockfile import LockEntry, LockfileError, LockfileWriteError, load_entries, save_entries
from .npm_data import (
    NpmDataError,
    NpmDataExtraction,
    NpmDataForbiddenError,
    NpmOfflineError,
    build_tarball,
    extract_npm_data,
)
from .resolver import (
    OfflineResolutionError,
    PackageResolutionError,
    RefDriftError,
    ResolvedSource,
    resolve_source,
)
from .spec import PackageSpec, PackageSpecError, parse_package_spec

__all__ = [
    "EnvironmentInstallError",
    "LockEntry",
    "LockfileError",
    "LockfileWriteError",
    "ManagedEnvironment",
    "NpmDataError",
    "NpmDataExtraction",
    "NpmDataForbiddenError",
    "NpmOfflineError",
    "OfflineResolutionError",
    "PackageResolutionError",
    "PackageSpec",
    "PackageSpecError",
    "RefDriftError",
    "ResolvedSource",
    "build_tarball",
    "extract_npm_data",
    "load_entries",
    "parse_package_spec",
    "resolve_source",
    "save_entries",
]
