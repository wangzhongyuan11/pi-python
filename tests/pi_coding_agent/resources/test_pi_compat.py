from __future__ import annotations

import hashlib
from pathlib import Path

from pi_coding_agent.resources.pi_compat import discover_pi_compatibility


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_compatibility_adapter_only_enumerates_safe_data_resources(tmp_path: Path) -> None:
    root = tmp_path / ".pi"
    _write(root / "skills" / "review.md", "skill")
    _write(root / "prompts" / "fix.md", "prompt")
    _write(root / "themes" / "night.json", "{}")
    _write(root / "sessions" / "project" / "one.jsonl", "session")
    _write(root / "extensions" / "danger.ts", "throw new Error('executed')")
    _write(root / "auth.json", '{"apiKey":"secret"}')
    _write(root / "settings.json", '{"packages":["evil"]}')
    before = _tree_hash(root)

    result = discover_pi_compatibility(root)

    assert [(item.kind, item.name, item.source) for item in result.resources] == [
        ("prompt", "fix", "compatibility"),
        ("skill", "review", "compatibility"),
        ("theme", "night", "compatibility"),
    ]
    assert result.sessions == ((root / "sessions" / "project" / "one.jsonl").resolve(),)
    assert result.skipped_extensions == ((root / "extensions" / "danger.ts").resolve(),)
    assert _tree_hash(root) == before


def test_missing_compatibility_root_is_empty_and_never_created(tmp_path: Path) -> None:
    root = tmp_path / "missing"

    result = discover_pi_compatibility(root)

    assert result.resources == ()
    assert result.sessions == ()
    assert not root.exists()
