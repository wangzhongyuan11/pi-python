"""Verify a wheel functions from a clean, repository-external environment.

Installs the wheel into a throwaway venv and drives CLI, SDK, TUI imports,
RPC mode, and package management from a temporary HOME and a cwd outside the
repository. Any dependence on the checkout (editable import, source-tree path
leak) fails the verification.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path


class WheelVerificationError(RuntimeError):
    """The wheel did not function from the clean installation."""


def _python_path(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _entry_path(environment: Path) -> Path:
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    return scripts / ("pi-python.exe" if os.name == "nt" else "pi-python")


REPOSITORY_HINTS = ("pi-python-claude", "d:\\pi-python-claude")


def assert_clean_output(output: str) -> None:
    """Reject probe output that leaks checkout paths or a traceback."""

    lowered = output.lower()
    if any(hint in lowered for hint in REPOSITORY_HINTS) or "traceback" in lowered:
        raise WheelVerificationError(
            f"clean-install probe leaked repository paths or a traceback:\n{output[:2000]}"
        )


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stdin: str = "",
    timeout: float = 120,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    assert_clean_output(completed.stdout + completed.stderr)
    return completed


def verify_wheel(root: str | Path, wheel: str | Path) -> None:
    repository = Path(root).resolve()
    artifact = Path(wheel).resolve()
    if not artifact.exists():
        raise WheelVerificationError(f"wheel not found: {artifact}")

    with tempfile.TemporaryDirectory(prefix="pi-python-wheel-") as temporary_name:
        temporary = Path(temporary_name).resolve()
        environment = temporary / "venv"
        subprocess.run(
            ["uv", "venv", "--python", "3.12", str(environment)],
            cwd=temporary,
            check=True,
            capture_output=True,
            text=True,
        )
        python = _python_path(environment)
        # Dependency resolution may use the network; this verifier runs outside
        # the offline test gate and checks function, not cache warmth.
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(artifact)],
            cwd=temporary,
            check=True,
            capture_output=True,
            text=True,
        )
        work = temporary / "work"
        work.mkdir()
        home = temporary / "home"
        home.mkdir()
        agent_dir = temporary / "agent"
        clean_environment = os.environ.copy()
        clean_environment.pop("PYTHONPATH", None)
        clean_environment["PYTHONNOUSERSITE"] = "1"
        clean_environment["HOME"] = str(home)
        clean_environment["USERPROFILE"] = str(home)
        clean_environment["PI_PYTHON_AGENT_DIR"] = str(agent_dir)
        for credential in (
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_BASE_URL",
            "DEEPSEEK_API_KEY_FILE",
            "PI_PYTHON_DEEPSEEK_API_KEY",
        ):
            clean_environment.pop(credential, None)

        entry = _entry_path(environment)

        # CLI basics.
        versioned = _run([str(entry), "--version"], cwd=work, env=clean_environment)
        if "pi-python" not in versioned.stdout:
            raise WheelVerificationError(f"--version output unexpected: {versioned.stdout!r}")
        _run([str(entry), "--help"], cwd=work, env=clean_environment)

        # A print turn reaches the provider factory and fails typed without keys.
        turn = _run(
            [str(entry), "-p", "hello", "--no-session"],
            cwd=work,
            env=clean_environment,
        )
        if turn.returncode != 1 or "credential" not in turn.stderr.lower():
            raise WheelVerificationError(
                f"expected a typed credential failure, got rc={turn.returncode}: "
                f"{turn.stderr[:300]!r}"
            )

        # SDK and TUI import from site-packages, not the checkout.
        probe = _run(
            [
                str(python),
                "-c",
                "import pi_coding_agent, pi_coding_agent.tui.runner as tui;"
                "assert 'site-packages' in pi_coding_agent.__file__, pi_coding_agent.__file__;"
                "assert callable(tui.run_interactive); print('clean-imports-ok')",
            ],
            cwd=work,
            env=clean_environment,
        )
        if probe.stdout.strip() != "clean-imports-ok":
            raise WheelVerificationError(f"import probe failed: {probe.stdout!r}")

        # Package management drives a real local install from a copied fixture
        # so no repository path ever reaches the installed CLI.
        fixture = repository / "tests" / "fixtures" / "golden_package"
        if not fixture.exists():
            raise WheelVerificationError("golden package fixture missing from the repository")
        staged = temporary / "golden-package"
        shutil.copytree(fixture, staged)
        _run([str(entry), "install", str(staged), "--no-approve"], cwd=work, env=clean_environment)
        listed = _run([str(entry), "list"], cwd=work, env=clean_environment)
        if str(staged) not in listed.stdout:
            raise WheelVerificationError(f"installed package not listed: {listed.stdout!r}")

        # RPC mode boots the composition (including the installed extension).
        rpc = _run(
            [str(entry), "--mode", "rpc", "--no-session", "--no-tools"],
            cwd=work,
            env=clean_environment,
            stdin='{"id":"state","type":"get_state"}\n',
        )
        records = [json.loads(line) for line in rpc.stdout.splitlines() if line.strip()]
        if not any(
            record.get("type") == "response" and record.get("success") is True for record in records
        ):
            raise WheelVerificationError(f"RPC get_state did not succeed: {rpc.stdout[:300]!r}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    arguments = parser.parse_args(argv)
    try:
        verify_wheel(arguments.root, arguments.wheel)
    except (WheelVerificationError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"wheel verification failed: {error}")
        return 1
    print("wheel verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
