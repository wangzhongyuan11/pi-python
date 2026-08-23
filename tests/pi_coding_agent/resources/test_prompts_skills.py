from __future__ import annotations

from pathlib import Path

from pi_coding_agent.resources.prompts import load_prompt_descriptors
from pi_coding_agent.resources.skills import format_skills_for_prompt, load_skill_descriptors


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_prompt_metadata_collision_and_content_are_lazy(tmp_path: Path) -> None:
    first = _write(
        tmp_path / "first.md",
        "---\ndescription: First description\nargument-hint: <file>\n---\nold body\n",
    )
    duplicate = _write(
        tmp_path / "nested" / "first.md",
        "---\ndescription: Duplicate\n---\nduplicate body\n",
    )

    result = load_prompt_descriptors((first, duplicate))
    first.write_text(
        "---\ndescription: First description\nargument-hint: <file>\n---\nnew body\n",
        encoding="utf-8",
    )

    assert len(result.prompts) == 1
    assert result.prompts[0].description == "First description"
    assert result.prompts[0].argument_hint == "<file>"
    assert result.prompts[0].load_content() == "new body\n"
    assert result.diagnostics[0].code == "duplicate"


def test_skill_validation_duplicate_xml_and_content_are_lazy(tmp_path: Path) -> None:
    first = _write(
        tmp_path / "safe" / "SKILL.md",
        "---\nname: safe-skill\ndescription: Use <safe> & careful work\n---\nold\n",
    )
    duplicate = _write(
        tmp_path / "duplicate" / "SKILL.md",
        "---\nname: safe-skill\ndescription: duplicate\n---\nduplicate\n",
    )
    invalid = _write(
        tmp_path / "invalid" / "SKILL.md",
        "---\nname: Bad Name\ndescription:\n---\ninvalid\n",
    )

    result = load_skill_descriptors((first, duplicate, invalid))
    first.write_text(
        "---\nname: safe-skill\ndescription: Use <safe> & careful work\n---\nnew\n",
        encoding="utf-8",
    )
    formatted = format_skills_for_prompt(result.skills)

    assert len(result.skills) == 1
    assert result.skills[0].load_content() == "new\n"
    assert "Use &lt;safe&gt; &amp; careful work" in formatted
    assert "<location>" in formatted
    assert {item.code for item in result.diagnostics} == {"duplicate", "invalid"}


def test_disable_model_invocation_excludes_skill_from_xml(tmp_path: Path) -> None:
    skill = _write(
        tmp_path / "manual" / "SKILL.md",
        "---\nname: manual\ndescription: Manual only\ndisable-model-invocation: true\n---\nbody\n",
    )

    result = load_skill_descriptors((skill,))

    assert len(result.skills) == 1
    assert format_skills_for_prompt(result.skills) == ""
