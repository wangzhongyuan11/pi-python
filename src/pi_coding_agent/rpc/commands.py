"""Adapters from RPC commands to the shared AgentSession product runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from pydantic.alias_generators import to_camel

from pi_ai import (
    AssistantMessage,
    Model,
    ToolResultMessage,
    UserMessage,
    get_supported_thinking_levels,
)
from pi_ai.wire.messages import dump_message

from ..agent_session import AgentSession
from ..ports import NoopSessionExporter
from ..presenters import assistant_text
from ..resources.prompts import load_prompt_descriptors
from ..resources.skills import load_skill_descriptors
from ..sdk import CreatedAgentSession
from ..session.catalog import open_session
from ..session.codec import dump_record
from ..session.fork import fork_session
from ..session.manager import SessionManager
from ..session.models import MessageEntry, SessionInfoEntry
from ..session.tree import SessionTree
from ..tools.bash import BashResult, execute_bash
from .models import RpcCommand

type BashRunner = Callable[..., Awaitable[BashResult]]

NO_DATA = object()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class RpcCommandAdapter:
    """One command facade over the same runtime used by CLI, TUI, and SDK."""

    __slots__ = ("_bash_abort", "_bash_runner", "_bash_timeout", "_created")

    def __init__(
        self,
        created: CreatedAgentSession,
        *,
        bash_timeout_seconds: float | None = None,
        bash_runner: BashRunner = execute_bash,
    ) -> None:
        self._created = created
        self._bash_timeout = bash_timeout_seconds
        self._bash_runner = bash_runner
        self._bash_abort: asyncio.Event | None = None

    @property
    def session(self) -> AgentSession:
        return self._created.session

    async def execute(self, command: RpcCommand) -> object:
        session = self._created.session
        agent = session.agent
        runtime = self._created.model_runtime
        kind = command.type

        if kind == "get_state":
            return _state(self._created)
        if kind == "set_model":
            if session.state.is_streaming:
                raise RuntimeError("cannot change model while Agent is streaming")
            model = runtime.select_model(command.model_id or "", provider_id=command.provider)
            session.set_model(model)
            return _model(model)
        if kind == "cycle_model":
            if session.state.is_streaming:
                raise RuntimeError("cannot change model while Agent is streaming")
            models = runtime.models
            if len(models) < 2:
                return None
            index = models.index(runtime.model)
            model = models[(index + 1) % len(models)]
            runtime.select_model(model.id, provider_id=model.provider)
            session.set_model(model)
            return {
                "model": _model(model),
                "thinkingLevel": session.state.thinking_level,
                "isScoped": False,
            }
        if kind == "get_available_models":
            return {"models": [_model(model) for model in runtime.models]}
        if kind == "set_thinking_level":
            session.set_thinking_level(cast("Any", command.level))
            return NO_DATA
        if kind == "cycle_thinking_level":
            levels = get_supported_thinking_levels(session.state.model)
            if len(levels) < 2:
                return None
            level = levels[(levels.index(session.state.thinking_level) + 1) % len(levels)]
            session.set_thinking_level(level)
            return {"level": level}
        if kind == "get_available_thinking_levels":
            return {"levels": list(get_supported_thinking_levels(session.state.model))}
        if kind == "set_steering_mode":
            agent.set_steering_mode(cast("Any", command.mode))
            return NO_DATA
        if kind == "set_follow_up_mode":
            agent.set_follow_up_mode(cast("Any", command.mode))
            return NO_DATA
        if kind == "compact":
            return dump_record(
                await session.compact(custom_instructions=command.custom_instructions)
            )
        if kind == "set_auto_compaction":
            session.set_auto_compaction_enabled(bool(command.enabled))
            return NO_DATA
        if kind == "set_auto_retry":
            session.set_auto_retry_enabled(bool(command.enabled))
            return NO_DATA
        if kind == "abort_retry":
            session.cancel_retry()
            return NO_DATA
        if kind == "bash":
            return await self._bash(command.command or "", bool(command.exclude_from_context))
        if kind == "abort_bash":
            if self._bash_abort is not None:
                self._bash_abort.set()
            return NO_DATA
        if kind == "clear_queue":
            agent.clear_all_queues()
            return NO_DATA
        if kind == "get_session_stats":
            return _session_stats(self._created)
        if kind == "export_html":
            return self._export(command.output_path)
        if kind == "new_session":
            return await self._new_session(command.parent_session)
        if kind == "switch_session":
            cancelled = await self._created.switch(open_session(command.session_path or ""))
            return {"cancelled": cancelled}
        if kind in {"fork", "clone"}:
            entry_id = command.entry_id if kind == "fork" else session.session_manager.leaf_id
            return await self._fork(entry_id, include_text=kind == "fork")
        if kind == "get_fork_messages":
            return {"messages": _fork_messages(session.session_manager.entries)}
        if kind == "get_entries":
            return _entries(session.session_manager, command.since)
        if kind == "get_tree":
            return _tree(session.session_manager)
        if kind == "get_last_assistant_text":
            last = next(
                (
                    message
                    for message in reversed(session.messages)
                    if isinstance(message, AssistantMessage)
                ),
                None,
            )
            return {"text": None if last is None else assistant_text(last)}
        if kind == "set_session_name":
            name = (command.name or "").strip()
            if not name:
                raise ValueError("Session name cannot be empty")
            session.set_session_name(name)
            return NO_DATA
        if kind == "get_messages":
            return {"messages": [_dump_agent_message(message) for message in session.messages]}
        if kind == "get_commands":
            actions = getattr(session.services.extensions, "actions", None)
            commands = () if actions is None else actions.get_commands()
            result: list[dict[str, object]] = [
                {
                    "name": item.name,
                    "source": "extension",
                    "sourceInfo": {"source": item.source},
                }
                for item in commands
            ]
            resources = session.services.resources.discover(session.services.cwd)
            for resource in resources:
                if resource.path is None or resource.kind not in {"prompt", "skill"}:
                    continue
                descriptors = (
                    load_prompt_descriptors((resource.path,)).prompts
                    if resource.kind == "prompt"
                    else load_skill_descriptors((resource.path,)).skills
                )
                for item in descriptors:
                    result.append(
                        {
                            "name": f"skill:{item.name}" if resource.kind == "skill" else item.name,
                            "description": item.description,
                            "source": resource.kind,
                            "sourceInfo": {"source": resource.source, "path": str(resource.path)},
                        }
                    )
            return {"commands": result}
        raise ValueError(f"unsupported RPC command: {kind}")

    async def _bash(self, command: str, exclude_from_context: bool) -> dict[str, object]:
        session = self._created.session
        if session.state.is_streaming:
            raise RuntimeError("cannot run user bash while Agent is streaming")
        if self._bash_abort is not None:
            raise RuntimeError("user bash is already running")
        self._bash_abort = asyncio.Event()
        try:
            shell = session.services.settings.get("shellPath")
            result = await self._bash_runner(
                command,
                cwd=session.services.cwd,
                custom_shell_path=shell if isinstance(shell, str) else None,
                timeout=self._bash_timeout,
                abort_event=self._bash_abort,
            )
        finally:
            self._bash_abort = None
        session.record_bash_result(command, result, exclude_from_context=exclude_from_context)
        return {
            "output": result.output,
            "exitCode": result.exit_code,
            "aborted": result.aborted,
            "timedOut": result.timed_out,
            "truncated": result.truncated,
            "fullOutputPath": (
                None if result.full_output_path is None else str(result.full_output_path)
            ),
        }

    def _export(self, output_path: str | None) -> dict[str, str]:
        from ..session.export import export_session

        if isinstance(self._created.services.exporter, NoopSessionExporter):
            raise RuntimeError("HTML exporter is not configured (planned in Phase 17)")
        manager = self._created.session.session_manager
        destination = Path(output_path or f"{manager.header.id}.html")
        if not destination.is_absolute():
            destination = self._created.services.cwd / destination
        destination = destination.resolve()
        path = self._created.services.exporter.export(export_session(manager), destination)
        return {"path": str(path)}

    async def _new_session(self, parent_session: str | None) -> dict[str, bool]:
        current = self._created.session.session_manager
        if current.path is None:
            manager = SessionManager.in_memory(
                cwd=current.header.cwd, session_id=uuid4().hex, timestamp=_timestamp()
            )
            if parent_session is not None:
                manager.header = manager.header.model_copy(
                    update={"parent_session": parent_session}
                )
            return {"cancelled": await self._created.new_session(manager)}
        manager = SessionManager.create(
            cwd=current.header.cwd,
            session_dir=current.path.parent,
            session_id=uuid4().hex,
            timestamp=_timestamp(),
            parent_session=parent_session,
        )
        return {"cancelled": await self._created.new_session(manager)}

    async def _fork(self, entry_id: str | None, *, include_text: bool) -> dict[str, object]:
        manager = self._created.session.session_manager
        tree = SessionTree.build(manager.entries)
        if entry_id is None or entry_id not in tree.by_id:
            raise ValueError("Invalid entry ID for forking")
        selected = tree.by_id[entry_id]
        text = ""
        leaf_id = entry_id
        if include_text:
            messages = _fork_messages((selected,))
            if not messages:
                raise ValueError("fork requires a user message entry")
            text = messages[0]["text"]
            leaf_id = selected.parent_id
        if manager.path is not None and leaf_id is not None:
            forked = fork_session(
                manager.path,
                leaf_id=leaf_id,
                target_cwd=manager.header.cwd,
                session_dir=manager.path.parent,
                session_id=uuid4().hex,
                timestamp=_timestamp(),
            )
        else:
            base = (
                SessionManager.in_memory(
                    cwd=manager.header.cwd, session_id=uuid4().hex, timestamp=_timestamp()
                )
                if manager.path is None
                else SessionManager.create(
                    cwd=manager.header.cwd,
                    session_dir=manager.path.parent,
                    session_id=uuid4().hex,
                    timestamp=_timestamp(),
                    parent_session=str(manager.path),
                )
            )
            forked = SessionManager(
                header=base.header,
                path=base.path,
                entries=() if leaf_id is None else tree.active_path(leaf_id),
            )
        cancelled = await self._created.fork(forked)
        data: dict[str, object] = {"cancelled": cancelled}
        if include_text:
            data["text"] = text
        return data


def _model(model: Model) -> dict[str, object]:
    return {
        "id": model.id,
        "name": model.name,
        "api": model.api,
        "provider": model.provider,
        "baseUrl": model.base_url,
        "reasoning": model.reasoning,
        "input": list(model.input),
        "cost": _camel_value(model.cost),
        "contextWindow": model.context_window,
        "maxTokens": model.max_tokens,
    }


def _state(created: CreatedAgentSession) -> dict[str, object]:
    session = created.session
    manager = session.session_manager
    name = next(
        (entry.name for entry in reversed(manager.entries) if isinstance(entry, SessionInfoEntry)),
        None,
    )
    return {
        "model": _model(session.state.model),
        "thinkingLevel": session.state.thinking_level,
        "isStreaming": session.state.is_streaming,
        "isCompacting": session.is_compacting,
        "steeringMode": session.agent.steering_mode,
        "followUpMode": session.agent.follow_up_mode,
        "sessionFile": None if manager.path is None else str(manager.path),
        "sessionId": manager.header.id,
        "sessionName": name,
        "autoCompactionEnabled": session.auto_compaction_enabled,
        "messageCount": len(session.messages),
        "pendingMessageCount": session.agent.pending_message_count,
    }


def _session_stats(created: CreatedAgentSession) -> dict[str, object]:
    manager = created.session.session_manager
    messages = [entry.message for entry in manager.entries if isinstance(entry, MessageEntry)]
    tokens: dict[str, float] = {key: 0 for key in ("input", "output", "cacheRead", "cacheWrite")}
    cost = 0.0
    tool_calls = 0
    for entry in manager.entries:
        payload = dump_record(entry)
        usage: object = payload.get("usage")
        if isinstance(entry, MessageEntry):
            usage = entry.message.get("usage")
            content = entry.message.get("content")
            if entry.message.get("role") == "assistant" and isinstance(content, list):
                tool_calls += sum(
                    1
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "toolCall"
                )
        if isinstance(usage, dict):
            values = cast("dict[str, object]", usage)
            for key in tokens:
                value = values.get(key)
                if isinstance(value, int | float) and not isinstance(value, bool):
                    tokens[key] += value
            usage_cost = values.get("cost")
            if isinstance(usage_cost, dict):
                total = cast("dict[str, object]", usage_cost).get("total")
                if isinstance(total, int | float):
                    cost += total
    tokens["total"] = sum(tokens.values())
    return {
        "sessionId": manager.header.id,
        "sessionFile": None if manager.path is None else str(manager.path),
        "userMessages": sum(message.get("role") == "user" for message in messages),
        "assistantMessages": sum(message.get("role") == "assistant" for message in messages),
        "toolResults": sum(message.get("role") == "toolResult" for message in messages),
        "toolCalls": tool_calls,
        "totalMessages": len(messages),
        "tokens": tokens,
        "cost": cost,
    }


def _entries(manager: SessionManager, since: str | None) -> dict[str, object]:
    entries = list(manager.entries)
    if since is not None:
        index = next((index for index, entry in enumerate(entries) if entry.id == since), None)
        if index is None:
            raise LookupError(f"Entry not found: {since}")
        entries = entries[index + 1 :]
    return {"entries": [dump_record(entry) for entry in entries], "leafId": manager.leaf_id}


def _tree(manager: SessionManager) -> dict[str, object]:
    tree = SessionTree.build(manager.entries)
    nodes: dict[str, dict[str, object]] = {}
    for entry in reversed(manager.entries):
        nodes[entry.id] = {
            "entry": dump_record(entry),
            "children": [nodes[child] for child in tree.child_ids[entry.id]],
        }
    roots = [] if tree.root_id is None else [nodes[tree.root_id]]
    return {"tree": roots, "leafId": manager.leaf_id}


def _fork_messages(entries: tuple[object, ...]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for raw in entries:
        if not isinstance(raw, MessageEntry) or raw.message.get("role") != "user":
            continue
        content = raw.message.get("content")
        text = ""
        if isinstance(content, list):
            text = "".join(
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        messages.append({"entryId": raw.id, "text": text})
    return messages


def _dump_agent_message(message: object) -> object:
    if isinstance(message, UserMessage | AssistantMessage | ToolResultMessage):
        return dump_message(message)
    return _camel_value(message)


def _camel_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            to_camel(field.name): _camel_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, tuple | list):
        return [_camel_value(item) for item in cast("tuple[object, ...] | list[object]", value)]
    return value


__all__ = ["NO_DATA", "RpcCommandAdapter"]
