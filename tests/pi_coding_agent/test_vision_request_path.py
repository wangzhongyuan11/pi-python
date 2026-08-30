"""Image attachment request path end to end (P11.5-T09)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pi_ai import (
    Context,
    FakeProvider,
    ImageContent,
    TextContent,
    UserMessage,
    fake_assistant_message,
    fake_model,
)
from pi_ai.providers.deepseek.models import get_deepseek_model
from pi_ai.providers.deepseek.request import DeepSeekCapabilityError, build_deepseek_request
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.session.manager import SessionManager

_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAFklEQVR42mNkYPjPwMDAwMgABXAGACwBA/+8s0MIAAAA"
    "AElFTkSuQmCC"
)


def _image_message() -> UserMessage:
    return UserMessage(
        content=(
            TextContent(text="what is in this image?"),
            ImageContent(data=_PNG_BASE64, mime_type="image/png"),
        ),
        timestamp=0,
    )


class TestWireConversion:
    def test_vision_model_request_includes_image_url(self) -> None:
        vision = get_deepseek_model("deepseek-v4-flash-vision-exp")
        context = Context(system_prompt=None, messages=(_image_message(),))
        request = build_deepseek_request(vision, context, thinking_level="off")
        user = next(m for m in request["messages"] if m["role"] == "user")
        assert isinstance(user["content"], list)
        image_part = next(part for part in user["content"] if part["type"] == "image_url")
        assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
        assert _PNG_BASE64 in image_part["image_url"]["url"]
        text_part = next(part for part in user["content"] if part["type"] == "text")
        assert text_part["text"] == "what is in this image?"

    def test_text_only_model_rejects_image_request(self) -> None:
        flash = get_deepseek_model("deepseek-v4-flash")
        context = Context(system_prompt=None, messages=(_image_message(),))
        try:
            build_deepseek_request(flash, context, thinking_level="off")
        except DeepSeekCapabilityError as error:
            assert "deepseek-v4-flash" in str(error)
        else:
            raise AssertionError("text-only model accepted an image request")


def _session_manager(cwd: Path) -> SessionManager:
    return SessionManager.in_memory(
        cwd=cwd,
        session_id="vision-path",
        timestamp="2026-08-30T00:00:00.000Z",
    )


class TestProductPath:
    def test_attached_image_reaches_the_provider_context(self, tmp_path: Path) -> None:
        provider = FakeProvider([fake_assistant_message("I see a red square")])

        async def scenario() -> Context:
            runtime = ModelRuntime(provider=provider, model=fake_model())
            created = await create_agent_session(
                CreateAgentSessionOptions(
                    cwd=tmp_path,
                    model_runtime=runtime,
                    session_manager=_session_manager(tmp_path),
                    agent_clock=lambda: 1,
                )
            )
            async with created:
                await created.session.prompt(
                    [
                        UserMessage(
                            content=(
                                TextContent(text="what is in this image?"),
                                ImageContent(data=_PNG_BASE64, mime_type="image/png"),
                            ),
                            timestamp=0,
                        )
                    ]
                )
                return provider.calls[0][1]

        first_context = asyncio.run(scenario())
        user = next(m for m in first_context.messages if isinstance(m, UserMessage))
        assert any(isinstance(block, ImageContent) for block in user.content)
