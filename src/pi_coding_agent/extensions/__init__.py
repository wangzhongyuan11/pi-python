"""Python extension surface for the coding agent."""

from .api import ExtensionAPI
from .auth_api import CredentialStore, CredentialStoreUnavailableError, ExtensionAuthApi
from .hooks import HookOutcome, HookRunner, invoke_hook
from .lifecycle import ExtensionLifecycle, LifecycleClosedError, TeardownToken
from .loader import (
    ExtensionIdentity,
    ExtensionLoader,
    ExtensionNotTrustedError,
    discover_extensions,
)
from .metadata import ExtensionManifestError, ExtensionMetadata, read_manifest
from .registry import (
    CapabilityRegistry,
    FlagState,
    Registration,
    RegistryConflictError,
    RegistryError,
    RegistryInvalidNameError,
)
from .runtime import DefaultExtensionRuntime
from .ui_api import ExtensionUiApi, UiBridge, UiUnavailableError

__all__ = [
    "CapabilityRegistry",
    "CredentialStore",
    "CredentialStoreUnavailableError",
    "DefaultExtensionRuntime",
    "ExtensionAPI",
    "ExtensionAuthApi",
    "ExtensionIdentity",
    "ExtensionLifecycle",
    "ExtensionLoader",
    "ExtensionManifestError",
    "ExtensionMetadata",
    "ExtensionNotTrustedError",
    "ExtensionUiApi",
    "FlagState",
    "HookOutcome",
    "HookRunner",
    "LifecycleClosedError",
    "Registration",
    "RegistryConflictError",
    "RegistryError",
    "RegistryInvalidNameError",
    "TeardownToken",
    "UiBridge",
    "UiUnavailableError",
    "discover_extensions",
    "invoke_hook",
    "read_manifest",
]
