from __future__ import annotations

import pi_coding_agent
import pi_coding_agent.builtin_extensions as builtin_extensions
import pi_coding_agent.extensions as extensions
import pi_coding_agent.packages as packages
import pi_coding_agent.resources as resources


def test_phase10_public_packages_export_their_supported_runtime_surfaces() -> None:
    assert {
        "CapabilityRegistry",
        "DefaultExtensionRuntime",
        "ExtensionAPI",
        "ExtensionLifecycle",
        "ExtensionLoader",
        "HookRunner",
    } <= set(extensions.__all__)
    assert {
        "ManagedEnvironment",
        "PackageSpec",
        "ResolvedSource",
        "build_tarball",
        "extract_npm_data",
    } <= set(packages.__all__)
    assert {"DefaultResourceLoader", "FileProjectTrustStore", "TrustDecision"} <= set(
        resources.__all__
    )
    assert {"PermissionGate", "PowerShellExtension"} <= set(builtin_extensions.__all__)
    assert {"DefaultExtensionRuntime", "DefaultResourceLoader"} <= set(pi_coding_agent.__all__)
