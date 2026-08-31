from __future__ import annotations

import asyncio
import json
import os
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

TUI_MAX_REQUESTS = 12
TUI_MAX_COST_USD = 0.50
TUI_PROCESS_TIMEOUT_SECONDS = 300

_TUI_CHILD = r"""
import json
import os
import sys
from pathlib import Path

from pi_ai import AssistantMessage, FakeProvider, ToolCall, fake_assistant_message
from pi_coding_agent.cli.main import main
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime, create_model_runtime
from pi_coding_agent.session.agent_messages import parse_message_entry
from pi_coding_agent.session.catalog import open_session
from pi_coding_agent.session.models import MessageEntry
from tests.live.scenarios import BudgetedProvider, TUI_MAX_REQUESTS

project = Path(os.environ["PI_LIVE_TUI_PROJECT"])
agent_dir = Path(os.environ["PI_PYTHON_AGENT_DIR"])
session_dir = Path(os.environ["PI_LIVE_TUI_SESSION_DIR"])
evidence_path = Path(os.environ["PI_LIVE_TUI_EVIDENCE"])

if os.environ.get("PI_LIVE_TUI_FAKE") == "1":
    skill = agent_dir / "packages" / "golden-package" / "skills" / "golden-skill.md"
    first = "golden-package-skill-v1\n"
    final = first + "golden-package-prompt-v2\n"
    provider = FakeProvider([
        fake_assistant_message(
            ToolCall(id="read-skill", name="read", arguments={"path": str(skill)}),
            stop_reason="toolUse",
        ),
        fake_assistant_message(
            ToolCall(
                id="write-proof",
                name="write",
                arguments={"path": "package-proof.txt", "content": first},
            ),
            stop_reason="toolUse",
        ),
        fake_assistant_message("Golden skill applied."),
        fake_assistant_message(
            ToolCall(id="read-proof", name="read", arguments={"path": "package-proof.txt"}),
            stop_reason="toolUse",
        ),
        fake_assistant_message(
            ToolCall(
                id="edit-proof",
                name="edit",
                arguments={
                    "path": "package-proof.txt",
                    "edits": [{"oldText": first, "newText": final}],
                },
            ),
            stop_reason="toolUse",
        ),
        fake_assistant_message("Golden prompt applied; both lines verified."),
    ])
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
else:
    repository = Path(os.environ["PI_LIVE_TUI_REPOSITORY"])
    resolver = DeepSeekCredentialResolver(
        environ=os.environ,
        env_file=repository / ".env",
        cwd=project,
    )
    runtime = create_model_runtime(
        credential_resolver=resolver,
        model_id="deepseek-v4-flash",
        thinking_level="off",
        max_tokens=4096,
        timeout_seconds=120,
    )

budgeted = BudgetedProvider(runtime.provider, max_requests=TUI_MAX_REQUESTS)
runtime = ModelRuntime(provider=budgeted, model=runtime.model)
exit_code = main(
    [
        "--provider", runtime.model.provider,
        "--model", runtime.model.id,
        "--thinking", "off",
        "--session-dir", str(session_dir),
        "--tools", "all",
        "--approve",
    ],
    model_runtime=runtime,
)

session_files = tuple(session_dir.glob("*.jsonl"))
if len(session_files) != 1:
    raise AssertionError(f"expected one persisted TUI session, got {len(session_files)}")
manager = open_session(session_files[0])
messages = [
    parse_message_entry(entry)
    for entry in manager.active_path()
    if isinstance(entry, MessageEntry)
]
total_cost = sum(
    message.usage.cost.total for message in messages if isinstance(message, AssistantMessage)
)
evidence_path.write_text(
    json.dumps(
        {
            "exit_code": exit_code,
            "request_count": budgeted.request_count,
            "session_path": str(session_files[0]),
            "total_cost": total_cost,
        }
    ),
    encoding="utf-8",
)
raise SystemExit(exit_code)
"""


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


@dataclass(frozen=True, slots=True)
class TuiScenarioEvidence:
    request_count: int
    total_cost: float
    session_path: Path
    transcript: str


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


def run_packaged_tui_scenario(
    *,
    root: Path,
    live: bool,
) -> TuiScenarioEvidence:
    repository = Path(__file__).resolve().parents[2]
    project = root / "project"
    agent_dir = root / "agent"
    session_dir = root / "sessions"
    evidence_path = root / "tui-evidence.json"
    project.mkdir(parents=True)
    (project / "task.md").write_text(
        "Use the installed golden package resources to create package-proof.txt.\n",
        encoding="utf-8",
    )
    entrypoint_name = "pi-python.exe" if os.name == "nt" else "pi-python"
    entrypoint = Path(sys.executable).with_name(entrypoint_name)
    environ = dict(os.environ)
    environ.update(
        {
            "PI_LIVE_TUI_EVIDENCE": str(evidence_path),
            "PI_LIVE_TUI_PROJECT": str(project),
            "PI_LIVE_TUI_REPOSITORY": str(repository),
            "PI_LIVE_TUI_SESSION_DIR": str(session_dir),
            "PI_PYTHON_AGENT_DIR": str(agent_dir),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    if not live:
        environ["PI_LIVE_TUI_FAKE"] = "1"

    installed = subprocess.run(
        [entrypoint, "install", str(repository / "tests" / "fixtures" / "golden_package")],
        cwd=project,
        env=environ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    if installed.returncode != 0:
        raise AssertionError(f"package install failed: {installed.stderr}")

    completed = subprocess.run(
        [sys.executable, "-c", _TUI_CHILD],
        input=("/skill:golden-skill package-proof.txt\n/golden-prompt package-proof.txt\n/exit\n"),
        cwd=project,
        env=environ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TUI_PROCESS_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"TUI process failed with {completed.returncode}:\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    proof = (project / "package-proof.txt").read_text(encoding="utf-8")
    if proof.splitlines() != ["golden-package-skill-v1", "golden-package-prompt-v2"]:
        raise AssertionError(f"unexpected package proof: {proof!r}")
    return TuiScenarioEvidence(
        request_count=int(payload["request_count"]),
        total_cost=float(payload["total_cost"]),
        session_path=Path(payload["session_path"]),
        transcript=completed.stdout,
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
