from __future__ import annotations

import asyncio

import pytest

from pi_coding_agent.extensions.auth_api import (
    CredentialStoreUnavailableError,
    ExtensionAuthApi,
)
from pi_coding_agent.extensions.registry import RegistryConflictError
from pi_coding_agent.extensions.ui_api import ExtensionUiApi, UiUnavailableError

SECRET = "sk-super-secret-value"


def test_ui_actions_require_a_bound_bridge_and_never_leak_text() -> None:
    ui = ExtensionUiApi()

    with pytest.raises(UiUnavailableError) as first_error:
        ui.show_message(SECRET)
    with pytest.raises(UiUnavailableError):
        ui.request_input("password?")
    with pytest.raises(UiUnavailableError):
        ui.request_confirmation("proceed?")

    assert SECRET not in str(first_error.value)


def test_bound_bridge_receives_ui_requests() -> None:
    class FakeBridge:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def show_message(self, text: str) -> None:
            self.messages.append(text)

        def request_input(self, prompt: str) -> str | None:
            return "typed"

        def request_confirmation(self, prompt: str) -> bool | None:
            return True

    ui = ExtensionUiApi()
    bridge = FakeBridge()
    ui.bind(bridge)

    ui.show_message("hello")
    assert ui.request_input("name") == "typed"
    assert ui.request_confirmation("sure") is True
    assert bridge.messages == ["hello"]


def test_auth_without_store_raises_and_error_excludes_secret() -> None:
    auth = ExtensionAuthApi()

    with pytest.raises(CredentialStoreUnavailableError) as error:
        auth.store_secret("deepseek", SECRET)

    assert SECRET not in str(error.value)


def test_auth_round_trips_through_store_and_uses_ui_for_prompting() -> None:
    class MemoryStore:
        def __init__(self) -> None:
            self.secrets: dict[str, str] = {}

        def get(self, provider: str) -> str | None:
            return self.secrets.get(provider)

        def set(self, provider: str, secret: str) -> None:
            self.secrets[provider] = secret

    class PromptBridge:
        def show_message(self, text: str) -> None:
            return None

        def request_input(self, prompt: str) -> str | None:
            return SECRET

        def request_confirmation(self, prompt: str) -> bool | None:
            return True

    ui = ExtensionUiApi()
    ui.bind(PromptBridge())
    store = MemoryStore()
    auth = ExtensionAuthApi(store=store)

    prompted = asyncio.run(auth.prompt_for_secret("deepseek", ui))
    auth.store_secret("deepseek", prompted or "")

    assert store.get("deepseek") == SECRET


def test_duplicate_renderer_registration_conflicts_and_errors_are_isolated() -> None:
    ui = ExtensionUiApi()

    def renderer(payload: object) -> str:
        raise RuntimeError("render bug")

    ui.register_renderer("tool_result", renderer)
    with pytest.raises(RegistryConflictError):
        ui.register_renderer("tool_result", renderer)

    outcome = asyncio.run(ui.render("tool_result", {"x": 1}))
    assert not outcome.ok
    assert isinstance(outcome.error, RuntimeError)
