"""Composition-root boundary for the Pi Python distribution."""

from importlib.metadata import version as _distribution_version

from .ports import (
    DefaultSessionImporter,
    ExtensionRuntime,
    InMemorySettings,
    NoopExtensionRuntime,
    NoopResourceLoader,
    NoopSessionExporter,
    ResourceDescriptor,
    ResourceLoader,
    SessionExporter,
    SessionImporter,
    Settings,
)
from .session.importer import import_pi_session
from .session.manager import SessionManager
from .session.models import ImportResult

__version__ = _distribution_version("pi-python")

__all__ = [
    "DefaultSessionImporter",
    "ExtensionRuntime",
    "InMemorySettings",
    "ImportResult",
    "NoopExtensionRuntime",
    "NoopResourceLoader",
    "NoopSessionExporter",
    "ResourceDescriptor",
    "ResourceLoader",
    "SessionExporter",
    "SessionImporter",
    "SessionManager",
    "Settings",
    "__version__",
    "import_pi_session",
]
