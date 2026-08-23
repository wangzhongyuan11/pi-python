"""Asynchronous SDK composition shared by future CLI and TUI adapters."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from uuid import uuid4

from pi_agent import Agent, AgentTool
from pi_ai import CredentialResolver, ModelThinkingLevel

from .agent_session import AgentSession
from .agent_session_runtime import AgentSessionRuntime, RuntimeComponents, RuntimeTarget
from .bootstrap import BootstrapConfig, ProductBootstrap, bootstrap
from .deepseek_credentials import DeepSeekCredentialResolver
from .model_runtime import ModelRuntime, create_model_runtime
from .services import ProductServices, ServiceOverrides, create_product_services
from .session.context import project_session_context
from .session.manager import SessionManager
from .session.tree import SessionTree


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _default_session_dir(cwd: Path) -> Path:
    encoded = str(cwd).lstrip("/\\").replace("/", "-").replace("\\", "-").replace(":", "-")
    configured = os.environ.get("PI_PYTHON_AGENT_DIR")
    agent_dir = (
        Path(configured).expanduser() if configured else Path.home() / ".pi-python" / "agent"
    )
    return agent_dir.resolve() / "sessions" / f"--{encoded}--"


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateAgentSessionOptions:
    cwd: Path = field(default_factory=Path.cwd)
    service_overrides: ServiceOverrides = field(default_factory=ServiceOverrides)
    model_runtime: ModelRuntime | None = None
    credential_resolver: CredentialResolver | None = None
    session_manager: SessionManager | None = None
    system_prompt: str = ""
    thinking_level: ModelThinkingLevel = "high"
    tools: tuple[AgentTool[Any, Any], ...] = ()
    agent_clock: Callable[[], int] | None = None
    entry_id_factory: Callable[[], str] = lambda: uuid4().hex
    timestamp_factory: Callable[[], str] = _timestamp


class CreatedAgentSession:
    __slots__ = ("_bootstrap", "_closed", "_model_runtime", "_runtime")

    def __init__(
        self,
        *,
        product_bootstrap: ProductBootstrap,
        model_runtime: ModelRuntime,
        runtime: AgentSessionRuntime[AgentSession, ProductServices],
    ) -> None:
        self._bootstrap = product_bootstrap
        self._model_runtime = model_runtime
        self._runtime = runtime
        self._closed = False

    @property
    def session(self) -> AgentSession:
        return self._runtime.session

    @property
    def services(self) -> ProductServices:
        return self._runtime.services

    @property
    def model_runtime(self) -> ModelRuntime:
        return self._model_runtime

    @property
    def product_bootstrap(self) -> ProductBootstrap:
        return self._bootstrap

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._runtime.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback
        await self.close()


async def create_agent_session(
    options: CreateAgentSessionOptions | None = None,
) -> CreatedAgentSession:
    selected = CreateAgentSessionOptions() if options is None else options
    cwd = selected.cwd.resolve()
    manager = selected.session_manager or SessionManager.create(
        cwd=cwd,
        session_dir=_default_session_dir(cwd),
        session_id=uuid4().hex,
        timestamp=selected.timestamp_factory(),
    )
    manager_cwd = Path(manager.header.cwd).resolve()
    if manager_cwd != cwd:
        raise ValueError(f"session cwd {manager_cwd} does not match requested cwd {cwd}")

    product_bootstrap = bootstrap(
        BootstrapConfig(cwd=cwd, service_overrides=selected.service_overrides)
    )
    resolver = selected.credential_resolver or DeepSeekCredentialResolver(cwd=cwd)
    model_runtime = selected.model_runtime or create_model_runtime(
        credential_resolver=resolver,
        thinking_level=selected.thinking_level,
    )

    async def factory(
        target: RuntimeTarget,
    ) -> RuntimeComponents[AgentSession, ProductServices]:
        services = (
            product_bootstrap.services
            if target.generation == 0
            else create_product_services(target.cwd, selected.service_overrides)
        )
        messages = ()
        if target.session_manager.leaf_id is not None:
            tree = SessionTree.build(target.session_manager.entries)
            messages = project_session_context(tree, target.session_manager.leaf_id).messages
        agent = Agent(
            model=model_runtime.model,
            stream_function=model_runtime.stream,
            system_prompt=selected.system_prompt,
            thinking_level=selected.thinking_level,
            tools=selected.tools,
            messages=messages,
            clock=selected.agent_clock,
        )
        session = AgentSession(
            agent=agent,
            session_manager=target.session_manager,
            services=services,
            entry_id_factory=selected.entry_id_factory,
            timestamp_factory=selected.timestamp_factory,
        )
        return RuntimeComponents(session=session, services=services)

    runtime = await AgentSessionRuntime[AgentSession, ProductServices].create(
        factory,
        cwd=cwd,
        session_manager=manager,
    )
    return CreatedAgentSession(
        product_bootstrap=product_bootstrap,
        model_runtime=model_runtime,
        runtime=runtime,
    )


__all__ = ["CreateAgentSessionOptions", "CreatedAgentSession", "create_agent_session"]
