from __future__ import annotations

import json
from pathlib import Path

from pi_coding_agent.packages import inspect_package


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_inspector_classifies_portable_python_and_typescript_resources(tmp_path: Path) -> None:
    root = tmp_path / "package"
    _write(
        root / "package.json",
        json.dumps(
            {
                "name": "@acme/mixed-kit",
                "pi": {
                    "extensions": ["extensions"],
                    "skills": ["skills"],
                    "prompts": ["prompts"],
                },
            }
        ),
    )
    _write(
        root / "extensions/python/pi-extension.json",
        json.dumps({"name": "python", "version": "1", "entry": "main.py"}),
    )
    _write(root / "extensions/python/main.py", "def activate(api): pass")
    _write(root / "extensions/simple.ts", "export default function (pi) { pi.registerTool({}); }")
    _write(root / "skills/review/SKILL.md", "# Review")
    _write(root / "prompts/review.md", "Review")

    report = inspect_package(root)

    assert report.package_name == "@acme/mixed-kit"
    assert report.overall == "bridged"
    assert {(item.level, item.kind, item.path) for item in report.capabilities} == {
        ("native", "extension", "extensions/python"),
        ("bridged", "extension", "extensions/simple.ts"),
        ("portable", "skill", "skills"),
        ("portable", "prompt", "prompts"),
    }


def test_inspector_reports_advanced_tui_and_unknown_extension_entries(tmp_path: Path) -> None:
    root = tmp_path / "package"
    _write(
        root / "package.json",
        json.dumps(
            {
                "name": "advanced-kit",
                "pi": {"extensions": ["advanced.ts", "extension.txt"]},
            }
        ),
    )
    _write(
        root / "advanced.ts",
        'import { Box } from "@earendil-works/pi-tui";\nexport default (pi) => pi.ui.custom(Box);',
    )
    _write(root / "extension.txt", "unknown")

    report = inspect_package(root)

    assert report.overall == "unsupported"
    assert [(item.level, item.reason) for item in report.capabilities] == [
        ("unsupported", "custom upstream TUI components cannot cross the Node bridge"),
        ("unsupported", "extension entry is neither a Python manifest nor JavaScript/TypeScript"),
    ]
