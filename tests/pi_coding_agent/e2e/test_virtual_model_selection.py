"""Phase 18.5: headless/RPC/TUI honor settings-defined virtual model aliases."""

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path

import pytest

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.cli.run import HeadlessOptions, run_headless
from pi_coding_agent.model_runtime import ModelRuntime, virtual_models_from_payload


def _runtime(provider: FakeProvider) -> ModelRuntime:
    return ModelRuntime(provider=provider, model=provider.models[0])


def test_headless_model_argument_resolves_virtual_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    provider = FakeProvider([fake_assistant_message("ok")])
    runtime = _runtime(provider)
    virtual = virtual_models_from_payload(
        {"fast": {"model": provider.models[0].id, "thinkingLevel": "low"}}
    )

    output = StringIO()
    errors = StringIO()
    code = asyncio.run(
        run_headless(
            HeadlessOptions(
                cwd=tmp_path,
                prompt="hi",
                mode="text",
                credential_resolver=_FakeResolver(),
                model_runtime=runtime,
                model_id="fast",
                virtual_models=virtual,
                project_trusted=True,
            ),
            stdout=output,
            stderr=errors,
        )
    )

    assert code == 0, errors.getvalue()
    assert runtime.model.id == provider.models[0].id


class _FakeResolver:
    def resolve(self, provider_id: str) -> dict[str, str]:
        return {"base_url": "https://api.test", "api_key": "k"}
