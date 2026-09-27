"""P15.5-T01: the TypeScript protocol mirror speaks the same wire contract."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PROTOCOL_TS = REPO / "node" / "extension-host" / "src" / "protocol.ts"


def _run_node_probe() -> dict[str, object]:
    probe = (
        "import { pathToFileURL } from 'node:url';\n"
        "const module = await import(pathToFileURL(process.argv[1]).href);\n"
        "const ack = module.negotiate({"
        " type: 'hello', protocol: module.PROTOCOL_VERSION, generation: 2, cwd: '/p' });\n"
        "const request = module.parseFrame("
        " '{\"type\":\"request\",\"id\":\"r1\",\"command\":\"events\"}');\n"
        "const errors = [];\n"
        "try { module.parseFrame('not json'); } catch (error) { errors.push(error.code); }\n"
        "try { module.parseFrame('{\"type\":\"mystery\"}'); }"
        " catch (error) { errors.push(error.code); }\n"
        "try { module.negotiate({ type: 'hello', protocol: 99, generation: 0, cwd: '' }); }"
        " catch (error) { errors.push(error.code); }\n"
        "process.stdout.write(JSON.stringify({"
        " protocol: ack.protocol, generation: ack.generation,"
        " capabilities: ack.capabilities, command: request.command,"
        " errors, capabilityCount: module.CAPABILITIES.length }));\n"
    )
    completed = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--disable-warning=ExperimentalWarning",
            "-e",
            probe,
            str(PROTOCOL_TS),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_typescript_protocol_mirrors_the_python_contract() -> None:
    payload = _run_node_probe()
    assert payload["protocol"] == 1
    assert payload["generation"] == 2
    assert payload["command"] == "events"
    assert payload["errors"] == ["invalid_frame", "invalid_frame", "version_mismatch"]
    assert payload["capabilityCount"] == 10


@pytest.mark.parametrize(
    ("python_file", "typescript_file"),
    [
        (
            Path("src/pi_coding_agent/node_host/models.py"),
            Path("node/extension-host/src/protocol.ts"),
        )
    ],
)
def test_both_sides_exist_side_by_side(python_file: Path, typescript_file: Path) -> None:
    assert (REPO / python_file).exists()
    assert (REPO / typescript_file).exists()
