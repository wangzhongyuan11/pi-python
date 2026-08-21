from __future__ import annotations

import random

from tests.randomness import seeded_random


def test_seeded_random_restores_the_previous_state() -> None:
    random.seed(1234)
    previous_state = random.getstate()

    with seeded_random(0):
        assert random.random() == random.Random(0).random()

    assert random.getstate() == previous_state
