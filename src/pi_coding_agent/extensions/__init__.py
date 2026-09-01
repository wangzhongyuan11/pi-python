"""Python extension surface for the coding agent."""

from .api import ExtensionAPI
from .auth_api import CredentialStore, CredentialStoreUnavailableError, ExtensionAuthApi
from .events import (
    AgentSettledEvent,
    ExtensionAgentEndEvent,
    ExtensionAgentStartEvent,
    ExtensionLifecycleEvent,
    ExtensionMessageEndEvent,
    ExtensionMessageStartEvent,
    ExtensionMessageUpdateEvent,
    ExtensionTurnEndEvent,
    ExtensionTurnStartEvent,
    UiPromptEndEvent,
    UiPromptStartEvent,
)
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
    "AgentSettledEvent",
    "CapabilityRegistry",
    "CredentialStore",
    "CredentialStoreUnavailableError",
    "DefaultExtensionRuntime",
    "ExtensionAgentEndEvent",
    "ExtensionAgentStartEvent",
    "ExtensionAPI",
    "ExtensionAuthApi",
    "ExtensionIdentity",
    "ExtensionLifecycle",
    "ExtensionLifecycleEvent",
    "ExtensionLoader",
    "ExtensionManifestError",
    "ExtensionMetadata",
    "ExtensionMessageEndEvent",
    "ExtensionMessageStartEvent",
    "ExtensionMessageUpdateEvent",
    "ExtensionNotTrustedError",
    "ExtensionTurnEndEvent",
    "ExtensionTurnStartEvent",
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
    "UiPromptEndEvent",
    "UiPromptStartEvent",
    "UiUnavailableError",
    "discover_extensions",
    "invoke_hook",
    "read_manifest",
]
