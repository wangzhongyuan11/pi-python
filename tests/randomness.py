"""Deterministic random-state helpers for tests."""

from __future__ import annotations

import random
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def seeded_random(seed: int) -> Iterator[None]:
    state = random.getstate()
    random.seed(seed)
    try:
        yield
    finally:
        random.setstate(state)


__all__ = ["seeded_random"]
