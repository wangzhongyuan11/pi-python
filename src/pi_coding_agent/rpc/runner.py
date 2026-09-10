"""Compose the shared product runtime with a stdio RPC transport."""

from __future__ import annotations

import asyncio
from contextlib import redirect_stdout
from dataclasses import replace
from threading import Thread
from typing import TextIO

from pi_ai import clamp_thinking_level

from ..cli.run import HeadlessOptions, resolve_session_manager
from ..model_runtime import create_model_runtime
from ..sdk import CreateAgentSessionOptions, ToolSelection, create_agent_session
from .commands import RpcCommandAdapter
from .server import RpcOutput, RpcServer
from .ui_bridge import RpcUiBridge


async def _readline(stream: TextIO) -> str:
    # A daemon read avoids keeping Python's default executor alive indefinitely
    # when a client disconnects on stdout while its stdin remains open (Windows).
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()

    def deliver(value: str | BaseException) -> None:
        if future.done():
            return
        if isinstance(value, BaseException):
            future.set_exception(value)
        else:
            future.set_result(value)

    def read() -> None:
        try:
            buffer = getattr(stream, "buffer", None)
            value = stream.readline() if buffer is None else buffer.readline().decode("utf-8")
        except Exception as error:
            value = error
        try:
            loop.call_soon_threadsafe(deliver, value)
        except RuntimeError:
            pass  # The owning transport has already shut down.

    Thread(target=read, daemon=True, name="pi-rpc-stdin").start()
    return await future


async def run_rpc(
    options: HeadlessOptions,
    *,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    def write(line: str) -> None:
        stdout.write(line)
        stdout.flush()

    output = RpcOutput(write)
    await output.start()
    ui = RpcUiBridge(output.emit)
    server: RpcServer | None = None
    pending: set[asyncio.Task[None]] = set()
    try:
        # Capture extension prints throughout activation, turns and disposal.
        # The protocol writer retains the original stdout stream explicitly.
        with redirect_stdout(stderr):
            runtime = options.model_runtime or create_model_runtime(
                credential_resolver=options.credential_resolver,
                provider_id=options.provider_id,
                model_id=options.model_id,
            )
            if options.model_runtime is not None and options.model_id is not None:
                runtime.select_model(options.model_id)
            selection = options.tool_selection or ToolSelection()
            factory = options.runtime_factory or create_agent_session
            created = await factory(
                CreateAgentSessionOptions(
                    cwd=options.cwd,
                    service_overrides=replace(options.service_overrides, ui=ui),
                    project_trusted=options.project_trusted,
                    extension_flags=options.extension_flags,
                    model_runtime=runtime,
                    session_manager=resolve_session_manager(options),
                    thinking_level=clamp_thinking_level(runtime.model, options.thinking_level),
                    no_tools=selection.no_tools,
                    tool_names=selection.tool_names,
                    exclude_tools=selection.exclude_tools,
                )
            )
            async with created:
                if options.name:
                    created.session.set_session_name(options.name)
                server = RpcServer(
                    session=created.session,
                    output=output,
                    commands=RpcCommandAdapter(created),
                    ui=ui,
                )
                try:
                    while line := await _readline(stdin):
                        # Long-running commands must not block abort/UI replies.
                        if len(pending) >= 64:
                            done, pending = await asyncio.wait(
                                pending,
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            for task in done:
                                task.result()
                        pending.add(asyncio.create_task(server.handle_line(line)))
                    await ui.close()
                    created.session.abort()
                    if pending:
                        done, _ = await asyncio.wait(pending, timeout=1)
                        for task in done:
                            task.result()
                finally:
                    await ui.close()
                    created.session.abort()
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    await server.close(abort=True)
    finally:
        await ui.close()
        await output.close()
    return 0


__all__ = ["run_rpc"]
