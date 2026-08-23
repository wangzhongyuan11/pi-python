"""Small frontmatter reader that leaves resource bodies lazy."""

from __future__ import annotations

from pathlib import Path


class FrontmatterError(ValueError):
    pass


def _value(text: str) -> str | bool:
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if value.casefold() == "true":
        return True
    if value.casefold() == "false":
        return False
    return value


def read_frontmatter(path: Path) -> dict[str, str | bool]:
    with path.open(encoding="utf-8") as source:
        if source.readline().rstrip("\r\n") != "---":
            return {}
        metadata: dict[str, str | bool] = {}
        for line in source:
            stripped = line.rstrip("\r\n")
            if stripped == "---":
                return metadata
            if not stripped or stripped.lstrip().startswith("#"):
                continue
            key, separator, value = stripped.partition(":")
            if not separator or not key.strip():
                raise FrontmatterError(f"invalid frontmatter line in {path.resolve()}")
            metadata[key.strip()] = _value(value)
    raise FrontmatterError(f"unterminated frontmatter in {path.resolve()}")


def read_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            return "".join(lines[index + 1 :])
    raise FrontmatterError(f"unterminated frontmatter in {path.resolve()}")


__all__ = ["FrontmatterError", "read_body", "read_frontmatter"]
