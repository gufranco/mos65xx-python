from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import ROOT
from conformance.family_shared import RECORD


def quoted_sentences(node: Any) -> int:
    if isinstance(node, dict):
        held = sum(1 for key in node if "quote" in str(key).lower())
        return held + sum(quoted_sentences(one) for one in node.values())
    if isinstance(node, list):
        return sum(quoted_sentences(one) for one in node)
    return 0


QUOTED = quoted_sentences(json.loads(RECORD.read_text())) if RECORD.is_file() else 0


class EveryQuoteIsCheckableTest(unittest.TestCase):
    @unittest.skipUnless(QUOTED, "this record quotes nothing")
    def test_a_record_that_quotes_ships_a_checker_for_it(self) -> None:
        # Arrange
        checker = ROOT / "conformance" / "quotes.py"

        # Act
        shipped = checker.is_file()

        # Assert
        self.assertTrue(shipped)

    @unittest.skipUnless(QUOTED, "this record quotes nothing")
    def test_and_the_pipeline_runs_it(self) -> None:
        # Arrange
        step = "conformance.quotes"

        # Act
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        # Assert
        self.assertIn(step, workflow)

    def test_the_reader_of_that_counts_a_quote_however_its_key_is_spelled(self) -> None:
        # Arrange
        record = {"a": {"quote": "x"}, "b": {"countRangeQuote": "y"}}

        # Act
        counted = quoted_sentences(record)

        # Assert
        self.assertEqual(counted, 2)

    def test_and_counts_none_in_a_record_that_quotes_nothing(self) -> None:
        # Arrange
        record = {"facts": {"window": [1, 2]}, "note": "a chip"}

        # Act
        counted = quoted_sentences(record)

        # Assert
        self.assertEqual(counted, 0)


HELD_BY = "heldBy"


UNREACHABLE = "unreachable"


SUPPORTING = "alsoSays"


NOT_PRINTED = frozenset({"notStated", "documents"})


Fact = tuple[tuple[str, ...], dict[str, Any]]


def is_a_sentence(value: Any) -> bool:
    return isinstance(value, str) or (
        isinstance(value, list) and any(isinstance(one, str) for one in value)
    )


def quotes_a_sentence(entry: dict[str, Any]) -> bool:
    return any(
        str(key).lower().endswith(("quote", "quotes")) and is_a_sentence(value)
        for key, value in entry.items()
    )


def printed_facts(node: Any, path: tuple[str, ...] = ()) -> list[Fact]:
    if NOT_PRINTED & set(path) or (path and path[-1] == SUPPORTING):
        return []
    if isinstance(node, list):
        return [fact for one in node for fact in printed_facts(one, path)]
    if not isinstance(node, dict):
        return []
    own: list[Fact] = [(path, node)] if quotes_a_sentence(node) else []
    return own + [
        fact for key, value in node.items() for fact in printed_facts(value, (*path, str(key)))
    ]


def named_test(source: str, dotted: str) -> str | None:
    owner, _, method = dotted.rpartition(".")
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.ClassDef) and node.name == owner):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method:
                return ast.get_source_segment(source, item) or ""
    return None


def holding_problem(root: Path, held: str, name: str | None) -> str | None:
    file, _, dotted = held.partition("::")
    path = root / file
    if not path.is_file():
        return f"{held} names a file that is not there"
    body = named_test(path.read_text(), dotted)
    if body is None:
        return f"{held} names a test that is not there"
    if name is not None and f'"{name}"' not in body and f"'{name}'" not in body:
        return f"{held} never reads {name} from the record"
    return None


def unheld(record: Any, root: Path) -> list[str]:
    problems = []
    for path, entry in printed_facts(record):
        where = "/".join(path) or "the record itself"
        reason = entry.get(UNREACHABLE)
        if isinstance(reason, str) and reason.strip():
            continue
        held = entry.get(HELD_BY)
        if not isinstance(held, list) or not held:
            problems.append(f"{where}: held by no test and not marked unreachable")
            continue
        name = path[-1] if path else None
        problems.extend(
            f"{where}: {problem}"
            for one in held
            if (problem := holding_problem(root, str(one), name)) is not None
        )
    return problems


A_HOLDING_TEST = (
    "class RecordTest:\n"
    "    def test_the_counter_has_the_printed_width(self):\n"
    '        printed = value("toneCounter")\n'
)


def a_folder_with_a_test(source: str = A_HOLDING_TEST) -> Path:
    folder = Path(tempfile.mkdtemp())
    (folder / "held.test.py").write_text(source)
    return folder


def a_printed_fact(**fields: Any) -> dict[str, Any]:
    return {"facts": {"toneCounter": {"value": 10, "quote": "a 10 stage counter", **fields}}}


HELD = ["held.test.py::RecordTest.test_the_counter_has_the_printed_width"]


class EveryPrintedFactIsHeldTest(unittest.TestCase):
    @unittest.skipUnless(RECORD.is_file(), "this repository keeps no record")
    def test_every_fact_the_manufacturer_printed_is_held_by_a_test_or_unreachable(self) -> None:
        # Arrange
        record = json.loads(RECORD.read_text())

        # Act
        problems = unheld(record, ROOT)

        # Assert
        self.assertEqual(problems, [])

    def test_a_fact_held_by_a_test_that_reads_it_passes(self) -> None:
        # Arrange
        record = a_printed_fact(heldBy=HELD)

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, [])

    def test_a_fact_held_by_nothing_is_reported(self) -> None:
        # Arrange
        record = a_printed_fact()

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(
            problems, ["facts/toneCounter: held by no test and not marked unreachable"]
        )

    def test_a_fact_with_an_empty_reason_is_still_reported(self) -> None:
        # Arrange
        record = a_printed_fact(unreachable="  ")

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(
            problems, ["facts/toneCounter: held by no test and not marked unreachable"]
        )

    def test_a_fact_no_test_can_reach_passes_when_it_says_why(self) -> None:
        # Arrange
        record = a_printed_fact(unreachable="an electrical level on a pin the model does not have")

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, [])

    def test_a_test_file_that_is_not_there_is_reported(self) -> None:
        # Arrange
        record = a_printed_fact(heldBy=["gone.test.py::RecordTest.test_x"])

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(
            problems,
            ["facts/toneCounter: gone.test.py::RecordTest.test_x names a file that is not there"],
        )

    def test_a_test_that_is_not_there_is_reported(self) -> None:
        # Arrange
        gone = "held.test.py::RecordTest.test_gone"

        # Act
        problems = unheld(a_printed_fact(heldBy=[gone]), a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, [f"facts/toneCounter: {gone} names a test that is not there"])

    def test_a_method_of_another_class_is_not_the_named_test(self) -> None:
        # Arrange
        record = a_printed_fact(
            heldBy=["held.test.py::OtherTest.test_the_counter_has_the_printed_width"]
        )

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(len(problems), 1)

    def test_a_test_that_never_reads_the_fact_is_reported(self) -> None:
        # Arrange
        source = (
            "class RecordTest:\n"
            "    def test_the_counter_has_the_printed_width(self):\n"
            "        printed = 10\n"
        )

        # Act
        problems = unheld(a_printed_fact(heldBy=HELD), a_folder_with_a_test(source))

        # Assert
        self.assertEqual(
            problems, [f"facts/toneCounter: {HELD[0]} never reads toneCounter from the record"]
        )

    def test_a_test_that_reads_the_fact_in_single_quotes_passes(self) -> None:
        # Arrange
        source = A_HOLDING_TEST.replace('"toneCounter"', "'toneCounter'")

        # Act
        problems = unheld(a_printed_fact(heldBy=HELD), a_folder_with_a_test(source))

        # Assert
        self.assertEqual(problems, [])

    def test_a_fact_quoting_several_sentences_is_a_printed_fact(self) -> None:
        # Arrange
        record = {"facts": {"tableBases": {"quotes": ["the first", "the second"]}}}

        # Act
        found = [path for path, _ in printed_facts(record)]

        # Assert
        self.assertEqual(found, [("facts", "tableBases")])

    def test_a_list_holding_no_sentence_is_not_a_quote(self) -> None:
        # Arrange
        record = {"facts": {"x": {"quotes": [3]}, "y": {"quotes": []}}}

        # Act
        found = printed_facts(record)

        # Assert
        self.assertEqual(found, [])

    def test_a_quote_kept_outside_the_printed_facts_needs_no_test(self) -> None:
        # Arrange
        record = {
            "notStated": {"x": {"quote": "a"}},
            "documents": [{"quote": "b"}],
            "facts": {"y": {"value": 1}},
        }

        # Act
        found = printed_facts(record)

        # Assert
        self.assertEqual(found, [])

    def test_a_supporting_quote_belongs_to_the_fact_it_supports(self) -> None:
        # Arrange
        record = a_printed_fact(heldBy=HELD, alsoSays=[{"quote": "and again on page 3"}])

        # Act
        found = [path for path, _ in printed_facts(record)]

        # Assert
        self.assertEqual(found, [("facts", "toneCounter")])

    def test_a_fact_inside_a_list_is_named_by_the_list_it_sits_in(self) -> None:
        # Arrange
        record = {"fields": [{"quote": "bit 7 selects", "value": 7}, 3]}

        # Act
        found = [path for path, _ in printed_facts(record)]

        # Assert
        self.assertEqual(found, [("fields",)])

    def test_a_quote_on_the_record_itself_needs_only_a_test_that_exists(self) -> None:
        # Arrange
        source = (
            "class RecordTest:\n"
            "    def test_the_counter_has_the_printed_width(self):\n"
            "        pass\n"
        )

        # Act
        problems = unheld({"quote": "the part", "heldBy": HELD}, a_folder_with_a_test(source))

        # Assert
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
