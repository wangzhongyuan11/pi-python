"""Headless text and JSON execution through the shared asynchronous SDK."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TextIO
from uuid import uuid4

from pi_ai import AssistantMessage, CredentialResolver, ModelThinkingLevel, clamp_thinking_level

from ..model_runtime import ModelRuntime, create_model_runtime
from ..presenters import JsonEventPresenter, assistant_text
from ..sdk import CreateAgentSessionOptions, ToolSelection, create_agent_session
from ..session.catalog import list_sessions, open_session
from ..session.errors import SessionNotFoundError
from ..session.manager import SessionManager


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True, kw_only=True)
class HeadlessOptions:
    cwd: Path
    prompt: str
    mode: Literal["text", "json"]
    credential_resolver: CredentialResolver
    provider_id: str = "deepseek"
    model_id: str | None = None
    thinking_level: ModelThinkingLevel = "high"
    no_session: bool = False
    session: str | None = None
    resume: bool = False
    session_dir: Path | None = None
    model_runtime: ModelRuntime | None = None
    tool_selection: ToolSelection | None = None
    name: str | None = None


def resolve_session_manager(options: HeadlessOptions) -> SessionManager | None:
    if options.no_session:
        return SessionManager.in_memory(
            cwd=options.cwd,
            session_id=uuid4().hex,
            timestamp=_timestamp(),
        )
    if options.session is not None:
        return open_session(options.session, session_dir=options.session_dir)
    if options.resume:
        if options.session_dir is None:
            raise SessionNotFoundError("--session-dir is required with --resume in headless mode")
        catalog = list_sessions(cwd=options.cwd, session_dir=options.session_dir)
        if not catalog.sessions:
            raise SessionNotFoundError(f"no sessions found in {options.session_dir}")
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
    runtime = options.model_runtime
    if runtime is None:
        runtime = create_model_runtime(
            credential_resolver=options.credential_resolver,
            provider_id=options.provider_id,
            model_id=options.model_id,
        )
    elif options.model_id is not None:
        runtime.select_model(options.model_id)
    thinking = clamp_thinking_level(runtime.model, options.thinking_level)
    selection = options.tool_selection or ToolSelection()
    created = await create_agent_session(
        CreateAgentSessionOptions(
            cwd=options.cwd,
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
