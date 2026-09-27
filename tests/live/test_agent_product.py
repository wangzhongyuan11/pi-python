from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from pi_ai import FakeProvider, JsonObject, ToolCall, fake_assistant_message
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime, create_model_runtime
from tests.live.scenarios import (
    CORRECTED_IMPLEMENTATION,
    INITIAL_IMPLEMENTATION,
    BudgetedProvider,
    build_task_prompt,
    create_disposable_project,
    run_product_scenario,
    verification_command,
)

MAX_REQUESTS = 18
MAX_COST_USD = 0.50


def test_live_task_prompt_names_a_bounded_available_verifier() -> None:
    prompt = build_task_prompt("Do the work.")

    assert Path(sys.executable).as_posix() in prompt
    assert "-m pytest -q" in prompt
    assert "timeout" in prompt
    assert "Do not search outside the project" in prompt


def _tool(call_id: str, name: str, arguments: JsonObject):
    return fake_assistant_message(
        ToolCall(id=call_id, name=name, arguments=arguments),
        stop_reason="toolUse",
    )


def test_product_scenario_proves_tools_correction_and_session_resume_offline(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    create_disposable_project(project)
    fake = FakeProvider(
        [
            _tool("read-readme", "read", {"path": "README.md"}),
            _tool("read-source", "read", {"path": "tags.py"}),
            _tool(
                "write-initial",
                "write",
                {"path": "tags.py", "content": INITIAL_IMPLEMENTATION},
            ),
            _tool(
                "test-initial",
                "bash",
                {"command": verification_command(), "timeout": 60.0},
            ),
            fake_assistant_message("Initial behavior implemented and verified."),
            _tool("read-correction", "read", {"path": "test_tags.py"}),
            _tool(
                "edit-correction",
                "edit",
                {
                    "path": "tags.py",
                    "edits": [
                        {
                            "oldText": INITIAL_IMPLEMENTATION,
                            "newText": CORRECTED_IMPLEMENTATION,
                        }
                    ],
                },
            ),
            _tool(
                "test-correction",
                "bash",
                {"command": verification_command(), "timeout": 60.0},
            ),
            fake_assistant_message("Correction implemented and verified."),
            _tool(
                "test-resume",
                "bash",
                {"command": verification_command(), "timeout": 60.0},
            ),
            fake_assistant_message("Existing session verified; all tests pass."),
        ]
    )
    budgeted = BudgetedProvider(fake, max_requests=11)
    runtime = ModelRuntime(provider=budgeted, model=budgeted.models[0])

    evidence = asyncio.run(
        run_product_scenario(
            project=project,
            session_dir=tmp_path / "sessions",
            model_runtime=runtime,
            budgeted_provider=budgeted,
        )
    )

    assert evidence.request_count == 11
    assert evidence.total_cost == 0
    assert evidence.session_path.is_file()
    assert evidence.changed_paths == ("README.md", "tags.py", "test_tags.py")


@pytest.mark.live_provider
@pytest.mark.network
def test_live_deepseek_completes_multi_turn_product_task_with_budgets(
    tmp_path: Path,
) -> None:
    if os.environ.get("PI_PYTHON_RUN_LIVE_AGENT_PRODUCT") != "1":
        pytest.skip("set PI_PYTHON_RUN_LIVE_AGENT_PRODUCT=1 after approving this exact live run")
    project = tmp_path / "project"
    create_disposable_project(project)
    repository_root = Path(__file__).resolve().parents[2]
    resolver = DeepSeekCredentialResolver(
        environ=os.environ,
        env_file=repository_root / ".env",
        cwd=project,
    )
    base_runtime = create_model_runtime(
        credential_resolver=resolver,
        model_id="deepseek-v4-flash",
        thinking_level="off",
        max_tokens=4_096,
        timeout_seconds=120,
    )
    budgeted = BudgetedProvider(base_runtime.provider, max_requests=MAX_REQUESTS)
    runtime = ModelRuntime(provider=budgeted, model=base_runtime.model)

    evidence = asyncio.run(
        run_product_scenario(
            project=project,
            session_dir=tmp_path / "sessions",
            model_runtime=runtime,
            budgeted_provider=budgeted,
        )
    )

    assert 3 <= evidence.request_count <= MAX_REQUESTS
    assert evidence.total_cost <= MAX_COST_USD
    assert evidence.session_path.is_file()
    assert evidence.changed_paths == ("README.md", "tags.py", "test_tags.py")
