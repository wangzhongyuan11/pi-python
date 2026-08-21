from __future__ import annotations

import re
import unittest
from pathlib import Path

CONTRACT = Path(__file__).parents[1] / "docs" / "contracts" / "message-event-tool.md"


class MessageEventToolContractTests(unittest.TestCase):
    def test_initial_event_order_is_frozen(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        event_sequence = re.compile(
            r"agent_start\s*->\s*turn_start\s*\n"
            r"->\s*message_start\(user\)\s*->\s*message_end\(user\)"
        )

        self.assertIsNotNone(event_sequence.search(text))

    def test_transform_precedes_llm_conversion(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")

        self.assertLess(text.index("transform_context"), text.index("convert_to_llm"))
