"""Strict LF-only JSONL framing used by both RPC transports."""

from __future__ import annotations

import codecs
import json


def serialize_json_line(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"


class JsonlFramer:
    __slots__ = ("_buffer", "_decoder")

    def __init__(self) -> None:
        self._buffer = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")()

    def feed(self, chunk: str | bytes) -> list[str]:
        self._buffer += chunk if isinstance(chunk, str) else self._decoder.decode(chunk)
        records: list[str] = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            records.append(line[:-1] if line.endswith("\r") else line)
        return records

    def finish(self) -> list[str]:
        self._buffer += self._decoder.decode(b"", final=True)
        if not self._buffer:
            return []
        line = self._buffer
        self._buffer = ""
        return [line[:-1] if line.endswith("\r") else line]


__all__ = ["JsonlFramer", "serialize_json_line"]
