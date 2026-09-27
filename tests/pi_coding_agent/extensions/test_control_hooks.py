from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from pi_agent import AgentTool, AgentToolResult
from pi_ai import (
    AssistantMessage,
    AssistantStream,
    Context,
    FakeProvider,
    Model,
    StreamOptions,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
    fake_assistant_message,
)
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import ResourceRoot
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides


class _EchoArgs(BaseModel):
    text: str


class _HookAwareFakeProvider(FakeProvider):
    def __init__(self, responses: list[AssistantMessage]) -> None:
        super().__init__(responses)
        self.payloads: list[dict[str, object]] = []
        self.request_headers: list[dict[str, str | None]] = []

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantStream:
        if options is None or options.on_payload is None or options.transform_headers is None:
            return super().stream(model, context, options)
        outer = AssistantStream()
        on_payload = options.on_payload
        transform_headers = options.transform_headers

        async def produce() -> None:
            payload = await on_payload({"marker": "original"}, model)
            self.payloads.append(cast("dict[str, object]", payload))
            headers = await transform_headers(dict(model.headers or {}), model)
            self.request_headers.append(dict(headers))
            inner = FakeProvider.stream(
                self,
                model,
                context,
                replace(options, on_payload=None, transform_headers=None),
            )
            async for event in inner:
                outer.push(event)

        task = asyncio.create_task(produce())
        task.add_done_callback(lambda completed: completed.exception())
        return outer


def _control_extension(root: Path) -> None:
    directory = root / "control-hooks"
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": "control-hooks", "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "from dataclasses import replace\n"
        "from pi_ai import TextContent, UserMessage\n\n"
        "def context(event):\n"
        "    messages = list(event.messages)\n"
        "    first = messages[0]\n"
        "    if isinstance(first, UserMessage):\n"
        "        messages[0] = replace(\n"
        "            first, content=(TextContent(text='context-hook'),)\n"
        "        )\n"
        "    return {'messages': tuple(messages)}\n\n"
        "def context_second(event):\n"
        "    messages = list(event.messages)\n"
        "    first = messages[0]\n"
        "    text = first.content[0].text\n"
        "    messages[0] = replace(\n"
        "        first, content=(TextContent(text=text + '-chained'),)\n"
        "    )\n"
        "    return {'messages': tuple(messages)}\n\n"
        "def request(event):\n"
        "    payload = dict(event.payload)\n"
        "    payload['marker'] = 'request-hook'\n"
        "    return payload\n\n"
        "def request_second(event):\n"
        "    payload = dict(event.payload)\n"
        "    payload['chained'] = payload['marker'] == 'request-hook'\n"
        "    return payload\n\n"
        "def headers(event):\n"
        "    event.headers['X-Extension-Hook'] = 'enabled'\n\n"
        "def tool_call(event):\n"
        "    event.input['text'] = 'argument-hook'\n\n"
        "def tool_result(_event):\n"
        "    return {\n"
        "        'content': (TextContent(text='result-hook'),),\n"
        "        'details': {'hooked': True},\n"
        "        'is_error': False,\n"
        "    }\n\n"
        "def tool_result_second(event):\n"
        "    details = dict(event.details)\n"
        "    details['chained'] = event.content[0].text == 'result-hook'\n"
        "    return {'details': details}\n\n"
        "def activate(api):\n"
        "    api.on('context', context)\n"
        "    api.on('context', context_second)\n"
        "    api.on('before_provider_request', request)\n"
        "    api.on('before_provider_request', request_second)\n"
        "    api.on('before_provider_headers', headers)\n"
        "    api.on('tool_call', tool_call)\n"
        "    api.on('tool_result', tool_result)\n"
        "    api.on('tool_result', tool_result_second)\n",
        encoding="utf-8",
    )


def _invalid_args_extension(root: Path) -> None:
    directory = root / "invalid-args"
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": "invalid-args", "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "def tool_call(event):\n"
        "    event.input.clear()\n\n"
        "def activate(api):\n"
        "    api.on('tool_call', tool_call)\n",
        encoding="utf-8",
    )


def test_control_hooks_modify_provider_context_headers_tool_args_and_result(
    tmp_path: Path,
) -> None:
    extension_root = tmp_path / "extensions"
    _control_extension(extension_root)
    executed: list[str] = []

    async def execute(
        _call_id: str,
        params: _EchoArgs,
        _abort: asyncio.Event | None,
        _update: object,
    ) -> AgentToolResult[dict[str, str]]:
        executed.append(params.text)
        return AgentToolResult(
            content=(TextContent(text=f"tool:{params.text}"),),
            details={"original": params.text},
        )

    tool = AgentTool(
        name="echo",
        label="Echo",
        description="Echo one value",
        parameter_type=_EchoArgs,
        execute=execute,
    )
    provider = _HookAwareFakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="call-1", name="echo", arguments={"text": "original"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("done"),
        ]
    )

    async def scenario() -> ToolResultMessage:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                tools=(tool,),
                service_overrides=ServiceOverrides(
                    resource_roots=(
                        ResourceRoot(kind="extension", path=extension_root, source="explicit"),
                    )
                ),
            )
        )
        await created.session.prompt("original prompt")
        result = next(
            message
            for message in created.session.messages
            if isinstance(message, ToolResultMessage)
        )
        await created.close()
        return result

    result = asyncio.run(scenario())

    assert executed == ["argument-hook"]
    assert [block.text for block in result.content if isinstance(block, TextContent)] == [
        "result-hook"
    ]
    assert result.details == {"hooked": True, "chained": True}
    assert result.is_error is False
    assert len(provider.calls) == 2
    _request_model, request_context = provider.calls[0]
    first_message = request_context.messages[0]
    assert isinstance(first_message, UserMessage)
    assert [block.text for block in first_message.content if isinstance(block, TextContent)] == [
        "context-hook-chained"
    ]
    assert provider.payloads[0]["marker"] == "request-hook"
    assert provider.payloads[0]["chained"] is True
    assert provider.request_headers[0] == {"X-Extension-Hook": "enabled"}


def test_extension_modified_tool_arguments_are_revalidated(tmp_path: Path) -> None:
    extension_root = tmp_path / "extensions"
    _invalid_args_extension(extension_root)
    executed: list[str] = []

    async def execute(
        _call_id: str,
        params: _EchoArgs,
        _abort: asyncio.Event | None,
        _update: object,
    ) -> AgentToolResult[None]:
        executed.append(params.text)
        return AgentToolResult(content=(TextContent(text=params.text),), details=None)

    provider = FakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="call-1", name="echo", arguments={"text": "original"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("done"),
        ]
    )

    async def scenario() -> ToolResultMessage:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                tools=(
                    AgentTool(
                        name="echo",
                        label="Echo",
                        description="Echo one value",
                        parameter_type=_EchoArgs,
                        execute=execute,
                    ),
                ),
                service_overrides=ServiceOverrides(
                    resource_roots=(
                        ResourceRoot(kind="extension", path=extension_root, source="explicit"),
                    )
                ),
            )
        )
        await created.session.prompt("run")
        result = next(
            message
            for message in created.session.messages
            if isinstance(message, ToolResultMessage)
        )
        await created.close()
        return result

    result = asyncio.run(scenario())

    assert executed == []
    assert result.is_error is True
    assert "text" in "".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )
