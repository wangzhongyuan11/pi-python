"""Extension package management for the coding agent."""

from .compatibility import (
    CompatibilityLevel,
    PackageCapability,
    PackageCompatibility,
    inspect_package,
)
from .environment import EnvironmentInstallError, ManagedEnvironment, install_requirement
from .lockfile import LockEntry, LockfileError, LockfileWriteError, load_entries, save_entries
from .manager import DefaultPackageManager
from .manifest import PackageManifest, PackageManifestError, read_package_manifest
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
    "CompatibilityLevel",
    "DefaultPackageManager",
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
    "PackageManifest",
    "PackageManifestError",
    "PackageCapability",
    "PackageCompatibility",
    "PackageSpec",
    "PackageSpecError",
    "RefDriftError",
    "ResolvedSource",
    "build_tarball",
    "extract_npm_data",
    "install_requirement",
    "inspect_package",
    "load_entries",
    "parse_package_spec",
    "resolve_source",
    "read_package_manifest",
    "save_entries",
]
