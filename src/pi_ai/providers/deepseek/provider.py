"""DeepSeek Provider implementation with explicit request-level retry control."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace
from typing import Any, Protocol, cast

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

from ...context import Context
from ...credentials import MissingCredentialError
from ...events import (
    AssistantMessageEvent,
    AssistantMessageStartEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    TextStartEvent,
    ThinkingDeltaEvent,
    ThinkingStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from ...messages import AssistantMessage
from ...models import Model
from ...provider import CredentialResolver, StreamOptions
from ...stream import AssistantStream
from ...usage import ModelThinkingLevel, Usage, UsageCost
from .models import DEEPSEEK_MODELS
from .request import build_deepseek_request
from .retry import is_retryable_provider_error, provider_status_code, retry_delay_seconds
from .stream import adapt_deepseek_stream


class _CompletionsPort(Protocol):
    async def create(self, **request: Any) -> AsyncIterator[object]: ...


class _ChatPort(Protocol):
    @property
    def completions(self) -> _CompletionsPort: ...


class DeepSeekClientPort(Protocol):
    @property
    def chat(self) -> _ChatPort: ...

    async def close(self) -> None: ...


type ClientFactory = Callable[[str, str, float], DeepSeekClientPort]
type SleepFunction = Callable[[float], Awaitable[None]]


class _ProviderAbortedError(RuntimeError):
    pass


def create_deepseek_client(
    api_key: str,
    base_url: str,
    timeout_seconds: float,
) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout_seconds,
        max_retries=0,
    )


def _default_client_factory(
    api_key: str,
    base_url: str,
    timeout_seconds: float,
) -> DeepSeekClientPort:
    return cast(
        "DeepSeekClientPort",
        create_deepseek_client(api_key, base_url, timeout_seconds),
    )


def _empty_message(model: Model, timestamp_ms: int) -> AssistantMessage:
    return AssistantMessage(
        content=(),
        api=model.api,
        provider=model.provider,
        model=model.id,
        usage=Usage(
            input=0,
            output=0,
            cache_read=0,
            cache_write=0,
            total_tokens=0,
            reasoning=0,
            cost=UsageCost(input=0, output=0, cache_read=0, cache_write=0, total=0),
        ),
        stop_reason="pending",
        timestamp=timestamp_ms,
    )


def _safe_error_message(error: BaseException) -> str:
    if isinstance(error, MissingCredentialError):
        return str(error)
    status = provider_status_code(error)
    if status is not None:
        return f"DeepSeek request failed with HTTP {status}"
    if isinstance(error, APITimeoutError) or "timeout" in type(error).__name__.lower():
        return "DeepSeek request timed out"
    if isinstance(error, APIConnectionError):
        return "DeepSeek connection failed"
    return "DeepSeek request failed"


def _error_event(message: AssistantMessage, error: BaseException) -> ErrorEvent:
    failed = replace(
        message,
        stop_reason="error",
        error_message=_safe_error_message(error),
    )
    return ErrorEvent(reason="error", error=failed)


def _aborted_event(message: AssistantMessage) -> ErrorEvent:
    aborted = replace(
        message,
        stop_reason="aborted",
        error_message="DeepSeek request was aborted",
    )
    return ErrorEvent(reason="aborted", error=aborted)


def _event_message(event: AssistantMessageEvent, fallback: AssistantMessage) -> AssistantMessage:
    if isinstance(event, DoneEvent):
        return event.message
    if isinstance(event, ErrorEvent):
        return event.error
    return event.partial


async def _record_errors(
    chunks: AsyncIterator[object],
    errors: list[BaseException],
) -> AsyncIterator[object]:
    try:
        async for chunk in chunks:
            yield chunk
    except BaseException as error:
        errors.append(error)
        raise


async def _abortable_chunks(
    chunks: AsyncIterator[object],
    abort_event: asyncio.Event | None,
) -> AsyncIterator[object]:
    if abort_event is None:
        async for chunk in chunks:
            yield chunk
        return

    iterator = chunks.__aiter__()
    while True:
        next_chunk = asyncio.create_task(_next_chunk(iterator))
        aborted = asyncio.create_task(abort_event.wait())
        done, _ = await asyncio.wait(
            (next_chunk, aborted),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if aborted in done and abort_event.is_set():
            next_chunk.cancel()
            await asyncio.gather(next_chunk, return_exceptions=True)
            raise _ProviderAbortedError
        aborted.cancel()
        await asyncio.gather(aborted, return_exceptions=True)
        try:
            yield next_chunk.result()
        except StopAsyncIteration:
            return


async def _next_chunk(iterator: AsyncIterator[object]) -> object:
    return await anext(iterator)


class DeepSeekProvider:
    def __init__(
        self,
        *,
        credential_resolver: CredentialResolver,
        client_factory: ClientFactory = _default_client_factory,
        thinking_level: ModelThinkingLevel = "high",
        max_request_retries: int = 0,
        timeout_seconds: float = 300.0,
        max_tokens: int | None = None,
        sleep: SleepFunction = asyncio.sleep,
        timestamp_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        if thinking_level not in ("off", "high", "max"):
            raise ValueError("DeepSeek thinking level must be off, high, or max")
        if max_request_retries < 0:
            raise ValueError("max_request_retries must be non-negative")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_tokens is not None and max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        self._credential_resolver = credential_resolver
        self._client_factory = client_factory
        self._thinking_level: ModelThinkingLevel = cast("ModelThinkingLevel", thinking_level)
        self._max_request_retries = max_request_retries
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._sleep = sleep
        self._timestamp_ms = timestamp_ms

    @property
    def id(self) -> str:
        return "deepseek"

    @property
    def name(self) -> str:
        return "DeepSeek"

    @property
    def models(self) -> tuple[Model, ...]:
        return DEEPSEEK_MODELS

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantStream:
        stream = AssistantStream()
        task = asyncio.create_task(self._produce(stream, model, context, options))
        task.add_done_callback(_consume_task_exception)
        return stream

    async def _produce(
        self,
        stream: AssistantStream,
        model: Model,
        context: Context,
        options: StreamOptions | None,
    ) -> None:
        initial = _empty_message(model, self._timestamp_ms())
        stream.push(AssistantMessageStartEvent(partial=initial))
        current = initial
        abort_event = options.abort_event if options is not None else None
        if abort_event is not None and abort_event.is_set():
            stream.push(_aborted_event(current))
            return

        client: DeepSeekClientPort | None = None
        try:
            credential = await self._credential_resolver.resolve("deepseek")
            if credential is None:
                raise MissingCredentialError("deepseek", "DEEPSEEK_API_KEY")
            request = build_deepseek_request(
                model,
                context,
                thinking_level=self._thinking_level,
                max_tokens=self._max_tokens,
            )
            client = self._client_factory(credential, model.base_url, self._timeout_seconds)

            for attempt in range(self._max_request_retries + 1):
                if abort_event is not None and abort_event.is_set():
                    stream.push(_aborted_event(current))
                    return
                try:
                    chunks = await client.chat.completions.create(**request)
                except BaseException as error:
                    if (
                        not isinstance(error, asyncio.CancelledError)
                        and is_retryable_provider_error(error)
                        and attempt < self._max_request_retries
                    ):
                        await self._sleep(retry_delay_seconds(error, attempt))
                        continue
                    if isinstance(error, asyncio.CancelledError):
                        raise
                    stream.push(_error_event(current, error))
                    return

                captured_errors: list[BaseException] = []
                inner = adapt_deepseek_stream(
                    model,
                    _record_errors(
                        _abortable_chunks(chunks, abort_event),
                        captured_errors,
                    ),
                    timestamp_ms=current.timestamp,
                )
                pending_starts: list[AssistantMessageEvent] = []
                emitted_semantic_delta = False
                retry_error: BaseException | None = None

                async for event in inner:
                    if isinstance(event, AssistantMessageStartEvent):
                        continue
                    current = _event_message(event, current)
                    if abort_event is not None and abort_event.is_set():
                        stream.push(_aborted_event(current))
                        return
                    if isinstance(event, TextStartEvent | ThinkingStartEvent | ToolCallStartEvent):
                        pending_starts.append(event)
                        continue
                    if isinstance(event, TextDeltaEvent | ThinkingDeltaEvent | ToolCallDeltaEvent):
                        for start in pending_starts:
                            stream.push(start)
                        pending_starts.clear()
                        emitted_semantic_delta = True
                        stream.push(event)
                        continue
                    if isinstance(event, ToolCallEndEvent) and pending_starts:
                        for start in pending_starts:
                            stream.push(start)
                        pending_starts.clear()
                        emitted_semantic_delta = True
                        stream.push(event)
                        continue
                    if isinstance(event, ErrorEvent):
                        original = captured_errors[-1] if captured_errors else None
                        if (
                            original is not None
                            and is_retryable_provider_error(original)
                            and not emitted_semantic_delta
                            and attempt < self._max_request_retries
                        ):
                            retry_error = original
                            break
                        if original is not None:
                            stream.push(_error_event(current, original))
                        else:
                            stream.push(event)
                        return
                    stream.push(event)
                    if isinstance(event, DoneEvent):
                        return

                if retry_error is not None:
                    await self._sleep(retry_delay_seconds(retry_error, attempt))
                    continue
                return
        except asyncio.CancelledError:
            stream.push(_aborted_event(current))
        except BaseException as error:
            stream.push(_error_event(current, error))
        finally:
            if client is not None:
                await client.close()


def _consume_task_exception(task: asyncio.Task[None]) -> None:
    if not task.cancelled():
        task.exception()


def create_deepseek_provider(
    *,
    credential_resolver: CredentialResolver,
    thinking_level: ModelThinkingLevel = "high",
    max_request_retries: int = 0,
    timeout_seconds: float = 300.0,
    max_tokens: int | None = None,
) -> DeepSeekProvider:
    return DeepSeekProvider(
        credential_resolver=credential_resolver,
        thinking_level=thinking_level,
        max_request_retries=max_request_retries,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
    )


__all__ = [
    "DeepSeekClientPort",
    "DeepSeekProvider",
    "create_deepseek_client",
    "create_deepseek_provider",
]
