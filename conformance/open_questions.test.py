"""That the open questions document names every question that is actually open.

A file like this is worth having only while it is complete. One divergence added
to the record and not to the document, and the document quietly becomes a claim
that the project knows more than it does, which is the failure it exists to
prevent.
"""

import json
import sys
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCUMENT = ROOT / "OPEN-QUESTIONS.md"

RECORD = ROOT / "conformance" / "divergences.json"


def divergences() -> list[dict[str, Any]]:
    held: list[dict[str, Any]] = json.loads(RECORD.read_text())["divergences"]
    return held


def opened() -> list[dict[str, Any]]:
    return [one for one in divergences() if one["status"] == "open"]


class RecordTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.text = DOCUMENT.read_text()

    def test_every_divergence_says_whether_it_is_open(self) -> None:
        missing = [
            one["subject"] for one in divergences() if one.get("status") not in ("open", "settled")
        ]

        self.assertEqual(missing, [])

    def test_the_document_names_every_open_one(self) -> None:
        missing = [one["subject"] for one in opened() if one["subject"][1:] not in self.text]

        self.assertEqual(missing, [])

    def test_and_names_none_that_are_settled(self) -> None:
        named = [
            one["subject"]
            for one in divergences()
            if one["status"] == "settled" and one["subject"][1:] in self.text
        ]

        self.assertEqual(named, [])

    def test_each_open_one_says_what_measurement_would_close_it(self) -> None:
        silent = [one["subject"] for one in opened() if not one.get("whatWouldSettleIt")]

        self.assertEqual(silent, [])

    def test_the_document_says_what_is_not_in_question(self) -> None:
        self.assertIn("What is not in question", self.text)

    def test_and_separates_what_is_unknown_from_what_is_absent_on_purpose(self) -> None:
        self.assertIn("What is deliberately not modelled", self.text)

    def test_there_are_open_questions_to_report(self) -> None:
        self.assertEqual(len(opened()), 9)

    def test_and_the_settled_ones_are_kept_rather_than_deleted(self) -> None:
        settled = [one for one in divergences() if one["status"] == "settled"]

        self.assertEqual(len(settled), 3)


if __name__ == "__main__":
    unittest.main()
