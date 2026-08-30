"""Model-backed compaction summarizer with upstream-aligned prompts."""

from __future__ import annotations

from ..session.models import CompactionEntry, MessageEntry, SessionEntry
from .summarizer import CompactionSummarizer

SUMMARIZATION_SYSTEM_PROMPT = (
    "You are a context summarization assistant. Your task is to read a conversation between "
    "a user and an AI assistant, then produce a structured summary following the exact format "
    "specified.\n\nDo NOT continue the conversation. Do NOT respond to any questions in the "
    "conversation. ONLY output the structured summary."
)

_SUMMARIZATION_PROMPT = """The messages above are a conversation to summarize. Create a structured context checkpoint summary that another LLM will use to continue the work.

Use this EXACT format:

## Goal
[What is the user trying to accomplish? Can be multiple items if the session covers different tasks.]

## Constraints & Preferences
- [Any constraints, preferences, or requirements mentioned by user]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks/changes]

### In Progress
- [ ] [Current work]

### Blocked
- [Issues preventing progress, if any]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [Ordered list of what should happen next]

## Critical Context
- [Any data, examples, or references needed to continue]
- [Or "(none)" if not applicable]

Keep each section concise. Preserve exact file paths, function names, and error messages."""

_UPDATE_SUMMARIZATION_PROMPT = """The messages above are NEW conversation messages to incorporate into the existing summary provided in <previous-summary> tags.

Update the existing structured summary with new information. RULES:
- PRESERVE all existing information from the previous summary
- ADD new progress, decisions, and context from the new messages
- UPDATE the Progress section: move items from "In Progress" to "Done" when completed
- UPDATE "Next Steps" based on what was accomplished
- PRESERVE exact file paths, function names, and error messages
- If something is no longer relevant, you may remove it

Use the same structured format as the existing summary (## Goal, ## Constraints & Preferences,
## Progress with Done/In Progress/Blocked, ## Key Decisions, ## Next Steps, ## Critical Context)."""


def _message_text(entry: MessageEntry) -> str:
    role = entry.message.get("role")
    content = entry.message.get("content")
    parts: list[str] = []
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
    prefix = role if isinstance(role, str) else "unknown"
    return f"[{prefix}] {' '.join(parts)}"


def serialize_entries(entries: tuple[SessionEntry, ...]) -> str:
    """Render session entries as readable conversation text for the summarizer."""
    lines: list[str] = []
    for entry in entries:
        if isinstance(entry, CompactionEntry):
            lines.append(f"[compaction]\n{entry.summary}")
        elif isinstance(entry, MessageEntry):
            text = _message_text(entry)
            if text.strip():
                lines.append(text)
    return "\n\n".join(lines)


def build_summarization_prompt(
    entries: tuple[SessionEntry, ...],
    *,
    previous_summary: str | None,
    custom_instructions: str | None = None,
) -> str:
    base = _UPDATE_SUMMARIZATION_PROMPT if previous_summary is not None else _SUMMARIZATION_PROMPT
    if custom_instructions:
        base = f"{base}\n\nAdditional focus: {custom_instructions}"
    prompt = f"<conversation>\n{serialize_entries(entries)}\n</conversation>\n\n"
    if previous_summary is not None:
        prompt += f"<previous-summary>\n{previous_summary}\n</previous-summary>\n\n"
    return prompt + base


class ModelRuntimeSummarizer(CompactionSummarizer):
    """Summarizes session entries with the currently selected model."""

    __slots__ = ("_model_runtime",)

    def __init__(self, *, model_runtime: object) -> None:
        self._model_runtime = model_runtime

    async def summarize(
        self,
        entries: tuple[SessionEntry, ...],
        *,
        previous_summary: str | None,
    ) -> str:
        from pi_ai import Context, StreamOptions, TextContent, UserMessage

        runtime = self._model_runtime
        model = runtime.model  # type: ignore[attr-defined]
        prompt = build_summarization_prompt(entries, previous_summary=previous_summary)
        message = UserMessage(
            content=(TextContent(text=prompt),),
            timestamp=0,
        )
        context = Context(
            system_prompt=SUMMARIZATION_SYSTEM_PROMPT,
            messages=(message,),
        )
        stream = runtime.stream(model, context, StreamOptions())  # type: ignore[attr-defined]
        pieces: list[str] = []
        async for event in stream:
            delta = getattr(event, "delta", None)
            if isinstance(delta, str):
                pieces.append(delta)
        return "".join(pieces)


__all__ = [
    "ModelRuntimeSummarizer",
    "SUMMARIZATION_SYSTEM_PROMPT",
    "build_summarization_prompt",
    "serialize_entries",
]
