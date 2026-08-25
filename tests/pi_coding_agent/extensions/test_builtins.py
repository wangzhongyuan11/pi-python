from __future__ import annotations

from pi_coding_agent.builtin_extensions.permission_gate import PermissionGate
from pi_coding_agent.builtin_extensions.powershell import PowerShellExtension


def test_permission_gate_is_disabled_by_default_and_never_prompts() -> None:
    prompts: list[str] = []

    def record(tool: str) -> bool:
        prompts.append(tool)
        return True

    gate = PermissionGate(confirmer=record)

    decision = gate.decide("bash")

    assert decision.allowed is True
    assert prompts == []


def test_enabled_gate_denies_when_confirmer_declines() -> None:
    def deny(_tool: str) -> bool:
        return False

    gate = PermissionGate(enabled=True, confirmer=deny)

    decision = gate.decide("write")

    assert decision.allowed is False
    assert decision.tool == "write"


def test_enabled_gate_asks_confirmer_per_tool() -> None:
    asked: list[str] = []

    def confirm(tool: str) -> bool:
        asked.append(tool)
        return tool != "edit"

    gate = PermissionGate(enabled=True, confirmer=confirm)

    assert gate.decide("read").allowed is True
    assert gate.decide("edit").allowed is False
    assert asked == ["read", "edit"]


def test_powershell_is_windows_only_and_opt_in() -> None:
    extension = PowerShellExtension()

    assert extension.enabled is False

    linux = PowerShellExtension(platform="linux")
    linux.enable()

    assert linux.available is False

    windows = PowerShellExtension(platform="win32")
    assert windows.available is False
    windows.enable()

    assert windows.enabled is True
    assert windows.available is True
