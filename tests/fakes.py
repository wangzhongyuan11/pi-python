"""Scripted test doubles shared across future vertical slices."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable


class FakeProvider:
    """Return pre-scripted values while recording provider requests."""

    def __init__(self, responses: Iterable[object] = ()) -> None:
        self._responses = deque(responses)
        self.requests: list[object] = []

    async def respond(self, request: object) -> object:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("provider script exhausted")
        return self._responses.popleft()


class FakeTool:
    """Return pre-scripted values while recording tool calls."""

    def __init__(self, results: Iterable[object] = ()) -> None:
        self._results = deque(results)
        self.calls: list[object] = []

    async def execute(self, arguments: object) -> object:
        self.calls.append(arguments)
        if not self._results:
            raise AssertionError("tool script exhausted")
        return self._results.popleft()


__all__ = ["FakeProvider", "FakeTool"]
