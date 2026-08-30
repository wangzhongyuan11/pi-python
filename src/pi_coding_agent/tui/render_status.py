"""Session status lines: retry progress and compaction activity."""

from __future__ import annotations

from dataclasses import dataclass, field

from pi_tui.layout import wrap_text
from pi_tui.width import visible_width


def _pad(line: str, width: int) -> str:
    return line + " " * max(0, width - visible_width(line))


@dataclass(slots=True)
class RetryStatusLine:
    """Shows auto-retry attempts; settles into a final one-line outcome."""

    attempt: int = 0
    max_attempts: int = 0
    delay_ms: int | None = None
    finished: bool = False
    success: bool = False
    _fragments: list[str] = field(default_factory=list[str])

    def retry_started(
        self, *, attempt: int, max_attempts: int, delay_seconds: float
    ) -> RetryStatusLine:
        self.attempt = attempt
        self.max_attempts = max_attempts
        self.delay_ms = int(delay_seconds * 1000)
        self.finished = False
        self._fragments.append(f"retry {attempt}/{max_attempts} in {self.delay_ms}ms")
        return self

    def retry_finished(self, *, success: bool) -> RetryStatusLine:
        self.finished = True
        self.success = success
        self._fragments.append("recovered" if success else "retry exhausted")
        return self

    def render(self, width: int) -> tuple[str, ...]:
        text = "; ".join(self._fragments)
        return tuple(_pad(line, width) for line in wrap_text(text, width))


@dataclass(slots=True)
class SessionStatusLine:
    """Compaction and other session-level activity lines."""

    _fragments: list[str] = field(default_factory=list[str])

    def activity(self, text: str) -> SessionStatusLine:
        self._fragments.append(text)
        return self

    def compaction_started(self) -> SessionStatusLine:
        self._fragments.append("compacting context")
        return self

    def compaction_finished(self, *, tokens_before: int) -> SessionStatusLine:
        self._fragments.append(f"compacted (was {tokens_before} tokens)")
        return self

    def render(self, width: int) -> tuple[str, ...]:
        lines = (
            _pad(line, width) for fragment in self._fragments for line in wrap_text(fragment, width)
        )
        return tuple(lines)


__all__ = ["RetryStatusLine", "SessionStatusLine"]
