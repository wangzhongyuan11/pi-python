"""Manual /compact slash command (P11.5-T06)."""

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path
from typing import Any

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


def _drive(tmp_path: Path, replies: list[str], responses: list[Any]) -> str:
    provider = FakeProvider(responses)
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    answer = iter(replies)
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(answer, None)

    asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )
    return output.getvalue()


def test_compact_command_reports_nothing_to_summarize_for_small_sessions(
    tmp_path: Path,
) -> None:
    # A single tiny turn leaves nothing to summarize: upstream skips the
    # compaction entirely instead of writing an empty-summary checkpoint.
    output = _drive(
        tmp_path,
        ["hello", "/compact", "/exit"],
        [
            fake_assistant_message("first reply"),
            fake_assistant_message("## Goal\n- checkpoint"),
        ],
    )
    assert "nothing to compact" in output


def test_compact_command_reports_nothing_to_compact(tmp_path: Path) -> None:
    output = _drive(
        tmp_path,
        ["/compact", "/exit"],
        [fake_assistant_message("first reply")],
    )
    assert "nothing to compact" in output


def test_compact_command_rejects_arguments(tmp_path: Path) -> None:
    output = _drive(
        tmp_path,
        ["/compact focus on tests", "/exit"],
        [fake_assistant_message("first reply")],
    )
    assert "usage: /compact" in output
