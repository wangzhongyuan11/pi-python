"""Headless text and JSON execution through the shared asynchronous SDK."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TextIO
from uuid import uuid4

from pi_ai import AssistantMessage, CredentialResolver, ModelThinkingLevel, clamp_thinking_level

from ..model_runtime import ModelRuntime, create_model_runtime, select_model_argument
from ..presenters import JsonEventPresenter, assistant_text
from ..sdk import (
    AgentSessionFactory,
    CreateAgentSessionOptions,
    ToolSelection,
    create_agent_session,
    default_session_dir,
)
from ..services import ServiceOverrides
from ..session.catalog import list_sessions, open_or_create_session, open_session
from ..session.errors import SessionNotFoundError
from ..session.fork import fork_session
from ..session.manager import SessionManager


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _empty_flags() -> dict[str, bool | str]:
    return {}


@dataclass(frozen=True, slots=True, kw_only=True)
class HeadlessOptions:
    cwd: Path
    prompt: str
    mode: Literal["text", "json"]
    credential_resolver: CredentialResolver
    provider_id: str = "deepseek"
    model_id: str | None = None
    thinking_level: ModelThinkingLevel | None = None
    no_session: bool = False
    session: str | None = None
    session_id: str | None = None
    fork: str | None = None
    resume: bool = False
    session_dir: Path | None = None
    model_runtime: ModelRuntime | None = None
    tool_selection: ToolSelection | None = None
    name: str | None = None
    service_overrides: ServiceOverrides = field(default_factory=ServiceOverrides)
    runtime_factory: AgentSessionFactory | None = None
    project_trusted: bool = False
    extension_flags: Mapping[str, bool | str] = field(default_factory=_empty_flags)


def _fork_source(options: HeadlessOptions) -> SessionManager:
    assert options.fork is not None
    candidate = Path(options.fork)
    if candidate.exists():
        return open_session(candidate)
    session_dir = options.session_dir or default_session_dir(options.cwd)
    catalog = list_sessions(cwd=options.cwd, session_dir=session_dir)
    exact = [summary for summary in catalog.sessions if summary.id == options.fork]
    matches = exact or [
        summary for summary in catalog.sessions if summary.id.startswith(options.fork)
    ]
    if len(matches) != 1:
        raise SessionNotFoundError(f"no session found matching {options.fork!r}")
    return open_session(matches[0].path)


def resolve_session_manager(options: HeadlessOptions) -> SessionManager | None:
    if options.no_session:
        return SessionManager.in_memory(
            cwd=options.cwd,
            session_id=uuid4().hex,
            timestamp=_timestamp(),
        )
    if options.fork is not None:
        source = _fork_source(options)
        if source.path is None or source.leaf_id is None:
            raise SessionNotFoundError("cannot fork a session without persisted turns")
        return fork_session(
            source.path,
            leaf_id=source.leaf_id,
            target_cwd=options.cwd,
            session_dir=options.session_dir or default_session_dir(options.cwd),
            session_id=uuid4().hex,
            timestamp=_timestamp(),
        )
    if options.session is not None:
        return open_session(options.session, session_dir=options.session_dir)
    if options.session_id is not None:
        return open_or_create_session(
            options.session_id,
            session_dir=options.session_dir or default_session_dir(options.cwd),
            cwd=options.cwd,
            timestamp_factory=_timestamp,
        )
    if options.resume:
        session_dir = options.session_dir or default_session_dir(options.cwd)
        catalog = list_sessions(cwd=options.cwd, session_dir=session_dir)
        if not catalog.sessions:
            raise SessionNotFoundError(f"no sessions found in {session_dir}")
        return open_session(catalog.sessions[0].path)
    if options.session_dir is not None:
        return SessionManager.create(
            cwd=options.cwd,
            session_dir=options.session_dir,
            session_id=uuid4().hex,
            timestamp=_timestamp(),
        )
    return None


async def run_headless(options: HeadlessOptions, *, stdout: TextIO, stderr: TextIO) -> int:
    model_thinking: ModelThinkingLevel | None = None
    runtime = options.model_runtime
    if runtime is None:
        runtime = create_model_runtime(
            credential_resolver=options.credential_resolver,
            provider_id=options.provider_id,
        )
    if options.model_id is not None:
        _selected, model_thinking = select_model_argument(runtime, options.model_id)
    thinking = clamp_thinking_level(
        runtime.model, options.thinking_level or model_thinking or "high"
    )
    selection = options.tool_selection or ToolSelection()
    runtime_factory = options.runtime_factory or create_agent_session
    created = await runtime_factory(
        CreateAgentSessionOptions(
            cwd=options.cwd,
            service_overrides=options.service_overrides,
            project_trusted=options.project_trusted,
            extension_flags=options.extension_flags,
            model_runtime=runtime,
            session_manager=resolve_session_manager(options),
            thinking_level=thinking,
            no_tools=selection.no_tools,
            tool_names=selection.tool_names,
            exclude_tools=selection.exclude_tools,
        )
    )
    async with created:
        if options.name:
            created.session.session_manager.append_session_info(
                options.name,
                entry_id_factory=lambda: uuid4().hex,
                timestamp_factory=_timestamp,
            )
        if options.mode == "json":
            created.session.subscribe(JsonEventPresenter(stdout))
        await created.session.prompt(options.prompt)
        assistants = [
            message for message in created.session.messages if isinstance(message, AssistantMessage)
        ]
        if not assistants:
            stderr.write("Agent returned no assistant message\n")
            return 1
        final = assistants[-1]
        if final.stop_reason in ("error", "aborted"):
            stderr.write(f"{final.error_message or 'Provider request failed'}\n")
            return 1
        if options.mode == "text":
            text = assistant_text(final)
            stdout.write(text)
            stdout.write("\n")
    return 0


__all__ = ["HeadlessOptions", "resolve_session_manager", "run_headless"]
