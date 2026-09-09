from __future__ import annotations

from io import StringIO
from pathlib import Path

from pi_coding_agent.cli.main import main
from pi_coding_agent.extensions.api import ExtensionAPI
from pi_coding_agent.extensions.runtime import DefaultExtensionRuntime
from pi_coding_agent.resources.default_loader import DefaultResourceLoader
from pi_coding_agent.services import ServiceOverrides


class _HelpExtensionRuntime(DefaultExtensionRuntime):
    async def start(self):  # type: ignore[no-untyped-def]
        api = ExtensionAPI("help-extension", registry=self.registry)
        api.define_flag("--review", default=False)
        api.define_flag("--profile", value_type="string")
        return ()


def _help_runtime(tmp_path: Path) -> _HelpExtensionRuntime:
    resources = DefaultResourceLoader(agent_dir=tmp_path / "agent")
    return _HelpExtensionRuntime(cwd=tmp_path, resources=resources)


def test_help_includes_extension_flags_and_stays_on_stdout(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()

    code = main(
        ["--help"],
        stdout=stdout,
        stderr=stderr,
        cwd=tmp_path,
        environ={},
        service_overrides=ServiceOverrides(extensions=_help_runtime(tmp_path)),
    )

    assert code == 0
    assert "Extension flags:" in stdout.getvalue()
    assert "--review" in stdout.getvalue()
    assert "--profile <value>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_unknown_extension_flag_is_a_usage_error_without_traceback(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()

    code = main(
        ["--unknown-extension-flag", "-p", "hello"],
        stdout=stdout,
        stderr=stderr,
        cwd=tmp_path,
        environ={},
    )

    assert code == 2
    assert stdout.getvalue() == ""
    assert "unrecognized arguments: --unknown-extension-flag" in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()
