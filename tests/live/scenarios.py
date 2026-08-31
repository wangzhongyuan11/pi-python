from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pi_ai import (
    AssistantMessage,
    AssistantStream,
    Context,
    Model,
    Provider,
    StreamOptions,
)
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.session.catalog import open_session
from pi_coding_agent.session.manager import SessionManager

INITIAL_IMPLEMENTATION = '''def normalize_tags(values: list[str]) -> list[str]:
    """Return sorted, unique, normalized tags."""
    return sorted({value.strip().lower() for value in values if value.strip()})
'''

CORRECTED_IMPLEMENTATION = '''def normalize_tags(values: list[str]) -> list[str]:
    """Normalize tags while preserving first occurrence casing and order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        identity = normalized.casefold()
        if normalized and identity not in seen:
            seen.add(identity)
            result.append(normalized)
    return result
'''

INITIAL_PROMPT = """Inspect README.md, tags.py, and the tests. Implement the requested
normalize_tags behavior and leave the project passing. Do not modify the tests. Keep the
change focused and report what you verified."""

CORRECTION_PROMPT = """The requirement has changed. Preserve input order and the original
casing of the first occurrence while still stripping whitespace, dropping empty values, and
deduplicating case-insensitively. Inspect the updated failing test, correct the implementation,
and do not modify the tests."""

RESUME_PROMPT = """Continue this existing session. Re-run the tests, inspect the current
result, and report a concise final status. Do not change behavior if the tests pass."""

PROMPT_TIMEOUT_SECONDS = 240
TOOL_TIMEOUT_SECONDS = 60


def verification_command() -> str:
    executable = Path(sys.executable).as_posix()
    return f'"{executable}" -m pytest -q'


def build_task_prompt(instructions: str) -> str:
    return (
        f"{instructions}\n\n"
        f"Run this exact verification command with the bash tool: `{verification_command()}`. "
        f"Set the bash `timeout` argument to {TOOL_TIMEOUT_SECONDS} seconds. Do not search "
        "outside the project for interpreters or test tools."
    )


class RequestBudgetExceeded(RuntimeError):
    pass


class BudgetedProvider:
    """Provider proxy that makes the live request ceiling executable."""

    def __init__(self, provider: Provider, *, max_requests: int) -> None:
        self._provider = provider
        self._max_requests = max_requests
        self.request_count = 0

    @property
    def id(self) -> str:
        return self._provider.id

    @property
    def name(self) -> str:
        return self._provider.name

    @property
    def models(self) -> tuple[Model, ...]:
        return self._provider.models

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantStream:
        if self.request_count >= self._max_requests:
            raise RequestBudgetExceeded(f"provider request budget exceeded ({self._max_requests})")
        self.request_count += 1
        return self._provider.stream(model, context, options)


@dataclass(frozen=True, slots=True)
class ProductScenarioEvidence:
    request_count: int
    total_cost: float
    session_path: Path
    changed_paths: tuple[str, ...]


def create_disposable_project(project: Path) -> None:
    project.mkdir(parents=True)
    (project / "README.md").write_text(
        "# Tag normalizer\n\nReturn sorted unique lowercase tags after stripping whitespace.\n",
        encoding="utf-8",
    )
    (project / "tags.py").write_text(
        "def normalize_tags(values: list[str]) -> list[str]:\n    raise NotImplementedError\n",
        encoding="utf-8",
    )
    (project / "test_tags.py").write_text(
        "from tags import normalize_tags\n\n\n"
        "def test_normalize_tags():\n"
        '    assert normalize_tags([" Beta ", "alpha", "ALPHA", ""]) == ["alpha", "beta"]\n',
        encoding="utf-8",
    )
    _git(project, "init", "--quiet")
    _git(project, "add", "README.md", "tags.py", "test_tags.py")
    _git(
        project,
        "-c",
        "user.name=Pi Python Test",
        "-c",
        "user.email=pi-python@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "fixture baseline",
    )


def apply_requirement_correction(project: Path) -> None:
    (project / "README.md").write_text(
        "# Tag normalizer\n\nPreserve first-occurrence order and casing while deduplicating "
        "case-insensitively.\n",
        encoding="utf-8",
    )
    (project / "test_tags.py").write_text(
        "from tags import normalize_tags\n\n\n"
        "def test_normalize_tags():\n"
        '    assert normalize_tags([" Beta ", "alpha", "ALPHA", "beta", ""]) == '
        '["Beta", "alpha"]\n',
        encoding="utf-8",
    )


async def run_product_scenario(
    *,
    project: Path,
    session_dir: Path,
    model_runtime: ModelRuntime,
    budgeted_provider: BudgetedProvider,
) -> ProductScenarioEvidence:
    manager = SessionManager.create(
        cwd=project,
        session_dir=session_dir,
        session_id="live-product-session",
        timestamp="2026-08-31T00:00:00.000Z",
    )
    created = await create_agent_session(
        CreateAgentSessionOptions(
            cwd=project,
            session_manager=manager,
            model_runtime=model_runtime,
            thinking_level="off",
        )
    )
    await _prompt_with_deadline(created.session, build_task_prompt(INITIAL_PROMPT))
    _assert_command_succeeds(project, "python", "-m", "pytest", "-q")

    apply_requirement_correction(project)
    correction_failure = _run(project, "python", "-m", "pytest", "-q")
    if correction_failure.returncode == 0:
        raise AssertionError("the correction must begin with a failing behavioral test")
    await _prompt_with_deadline(created.session, build_task_prompt(CORRECTION_PROMPT))
    _assert_final_project(project)
    session_path = created.session.session_manager.path
    if session_path is None:
        raise AssertionError("the product scenario must persist a session")
    await created.close()

    resumed_manager = open_session(session_path)
    resumed = await create_agent_session(
        CreateAgentSessionOptions(
            cwd=project,
            session_manager=resumed_manager,
            model_runtime=model_runtime,
            thinking_level="off",
        )
    )
    await _prompt_with_deadline(resumed.session, build_task_prompt(RESUME_PROMPT))
    _assert_final_project(project)
    total_cost = sum(
        message.usage.cost.total
        for message in resumed.session.messages
        if isinstance(message, AssistantMessage)
    )
    await resumed.close()
    changed_paths = tuple(
        line for line in _git(project, "diff", "--name-only").stdout.splitlines() if line
    )
    return ProductScenarioEvidence(
        request_count=budgeted_provider.request_count,
        total_cost=total_cost,
        session_path=session_path,
        changed_paths=changed_paths,
    )


async def _prompt_with_deadline(session: AgentSession, prompt: str) -> None:
    try:
        await asyncio.wait_for(session.prompt(prompt), timeout=PROMPT_TIMEOUT_SECONDS)
    except TimeoutError as error:
        session.abort()
        await session.wait_for_idle()
        raise AssertionError(f"agent prompt exceeded {PROMPT_TIMEOUT_SECONDS} seconds") from error


def _assert_final_project(project: Path) -> None:
    _assert_command_succeeds(project, "python", "-m", "pytest", "-q")
    source = (project / "tags.py").read_text(encoding="utf-8")
    if "casefold" not in source:
        raise AssertionError("the corrected implementation must deduplicate case-insensitively")
    expected_test = (
        "from tags import normalize_tags\n\n\n"
        "def test_normalize_tags():\n"
        '    assert normalize_tags([" Beta ", "alpha", "ALPHA", "beta", ""]) == '
        '["Beta", "alpha"]\n'
    )
    if (project / "test_tags.py").read_text(encoding="utf-8") != expected_test:
        raise AssertionError("the agent modified the behavioral test")


def _assert_command_succeeds(project: Path, *command: str) -> None:
    result = _run(project, *command)
    if result.returncode != 0:
        raise AssertionError(
            f"command failed with {result.returncode}: {' '.join(command)}\n{result.stdout}"
        )


def _run(project: Path, *command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _git(project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    result = _run(project, "git", *arguments)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(arguments)} failed: {result.stdout}{result.stderr}")
    return result
