"""Composition-root boundary for the Pi Python distribution."""

from importlib.metadata import version as _distribution_version

from .extensions import DefaultExtensionRuntime, ExtensionAPI
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
from .resources import DefaultResourceLoader
from .sdk import import_pi_session
from .session.manager import SessionManager
from .session.models import ImportResult

__version__ = _distribution_version("pi-python")

__all__ = [
    "DefaultSessionImporter",
    "DefaultExtensionRuntime",
    "DefaultResourceLoader",
    "ExtensionAPI",
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
