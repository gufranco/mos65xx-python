from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import ROOT
from conformance.family_shared import RECORD, a_folder_holding


def declared(node: Any) -> dict[str, Any]:
    found: dict[str, Any] = {}
    if isinstance(node, dict):
        held = node.get("documents")
        if isinstance(held, dict):
            found.update(held)
        for value in node.values():
            found.update(declared(value))
    elif isinstance(node, list):
        for one in node:
            found.update(declared(one))
    return found


def cited(node: Any, where: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        named = node.get("document")
        if isinstance(named, str):
            found.append((where or ".", named))
        for name, value in node.items():
            found += cited(value, f"{where}.{name}")
    elif isinstance(node, list):
        for index, one in enumerate(node):
            found += cited(one, f"{where}[{index}]")
    return found


def astray_citations(held: Any) -> list[str]:
    keys = set(declared(held))
    return sorted({named for _, named in cited(held) if named not in keys})


def nameless_sources(held: Any) -> list[str]:
    return sorted(key for key, one in declared(held).items() if not one.get("file"))


class OneVocabularyForADocumentTest(unittest.TestCase):
    def record(self) -> Any:
        return json.loads(RECORD.read_text())

    def test_the_standard_asks_for_a_documents_block(self) -> None:
        # Arrange
        phrase = "`documents` block"

        # Act
        standard = (ROOT / "FAMILY.md").read_text()

        # Assert
        self.assertIn(phrase, standard)

    def test_the_record_declares_its_sources_in_one(self) -> None:
        # Arrange
        record = self.record()

        # Act
        block = record.get("documents")

        # Assert
        self.assertIsInstance(block, dict)

    def test_every_source_declared_anywhere_names_the_file_it_is(self) -> None:
        # Arrange
        record = self.record()

        # Act
        nameless = nameless_sources(record)

        # Assert
        self.assertEqual(nameless, [])

    def test_every_citation_names_one_of_them(self) -> None:
        # Arrange
        record = self.record()

        # Act
        astray = astray_citations(record)

        # Assert
        self.assertEqual(astray, [])

    def test_there_is_a_record_to_check(self) -> None:
        # Arrange
        record = self.record()

        # Act
        fields = [key for key in record if key != "documents"]

        # Assert
        self.assertGreater(len(fields), 0)

    def test_the_reader_of_that_finds_a_citation_wherever_it_sits(self) -> None:
        # Arrange
        held = {
            "facts": {"pin": {"document": "sheet", "page": 6}},
            "parts": [{"timing": [{"document": "book"}]}],
            "note": "not a citation",
        }

        # Act
        found = sorted(cited(held))

        # Assert
        self.assertEqual(found, [(".facts.pin", "sheet"), (".parts[0].timing[0]", "book")])

    def test_and_finds_a_block_declared_beside_a_part(self) -> None:
        # Arrange
        held = {
            "documents": {"a": {"file": "a.pdf"}},
            "parts": [{"documents": {"b": {"file": "b.pdf"}}}],
        }

        # Act
        found = sorted(declared(held))

        # Assert
        self.assertEqual(found, ["a", "b"])

    def test_a_block_declared_beside_a_part_is_read_as_well_as_a_top_level_one(
        self,
    ) -> None:
        # Arrange
        held = {
            "documents": {},
            "parts": [
                {"documents": {"sheet": {"file": "a.pdf"}}},
                {"documents": {"book": {"file": "b.pdf"}}},
            ],
        }

        # Act
        found = sorted(declared(held))

        # Assert
        self.assertEqual(found, ["book", "sheet"])

    def test_a_source_reached_through_a_sibling_still_has_to_name_the_sibling(
        self,
    ) -> None:
        # Arrange
        held = {"documents": {"manual": {"file": "book1.pdf", "through": "snes-graphics-python"}}}

        # Act
        borrowed = {key: one["through"] for key, one in declared(held).items() if "through" in one}

        # Assert
        self.assertEqual(borrowed, {"manual": "snes-graphics-python"})

    def test_an_empty_block_is_a_declaration_and_not_a_missing_one(self) -> None:
        # Arrange
        held = {"documents": {}, "facts": {"pin": 1}}

        # Act
        found = (held.get("documents"), declared(held), cited(held))

        # Assert
        self.assertEqual(found, ({}, {}, []))

    def test_a_record_citing_a_key_that_is_not_declared_is_reported(self) -> None:
        # Arrange
        held = {"documents": {"sheet": {"file": "a.pdf"}}, "facts": {"document": "elsewhere"}}

        # Act
        astray = astray_citations(held)

        # Assert
        self.assertEqual(astray, ["elsewhere"])

    def test_and_a_source_with_no_file_beside_it_is_reported(self) -> None:
        # Arrange
        held = {"documents": {"sheet": {"title": "a manual with no file named"}}}

        # Act
        nameless = nameless_sources(held)

        # Assert
        self.assertEqual(nameless, ["sheet"])


class EveryRecordStatesItsAuthorityTest(unittest.TestCase):
    def record(self) -> Any:
        return json.loads(RECORD.read_text())

    def authority(self) -> Any:
        held = self.record().get("authority")
        return held if isinstance(held, dict) else {}

    def compared_against(self) -> dict[str, Any]:
        held = self.authority().get("comparedAgainst")
        assert isinstance(held, dict)
        return held

    def test_the_record_states_the_order_it_answers_in(self) -> None:
        # Arrange
        authority = self.authority()

        # Act
        order = authority.get("order")

        # Assert
        self.assertGreater(len(order), 0)

    def test_and_the_order_is_a_list_of_rungs_rather_than_a_sentence(self) -> None:
        # Arrange
        authority = self.authority()

        # Act
        order = authority.get("order")

        # Assert
        self.assertIsInstance(order, list)

    def test_and_says_why_it_is_that_order(self) -> None:
        # Arrange
        authority = self.authority()

        # Act
        why = str(authority.get("why", "")).strip()

        # Assert
        self.assertNotEqual(why, "")

    def test_the_record_names_what_this_member_is_held_to(self) -> None:
        # Arrange
        held = self.compared_against()

        # Act
        what = str(held.get("what", "")).strip()

        # Assert
        self.assertNotEqual(what, "")

    def test_and_the_runner_that_does_the_comparing_is_here(self) -> None:
        # Arrange
        held = self.compared_against()

        # Act
        present = (ROOT / str(held.get("runner"))).is_file()

        # Assert
        self.assertTrue(present, held.get("runner"))

    def test_the_standard_carries_the_ladder_this_is_measured_against(self) -> None:
        # Arrange
        heading = "The authority ladder"

        # Act
        standard = (ROOT / "FAMILY.md").read_text()

        # Assert
        self.assertIn(heading, standard)

    def test_a_record_with_no_ladder_at_all_is_reported(self) -> None:
        # Arrange
        held = {"note": "layouts, pinned to the figures", "documents": {}}

        # Act
        found = held.get("authority")

        # Assert
        self.assertIsNone(found)


DIVERGENCES = ROOT / "conformance" / "divergences.json"


DIVERGENCE_STATUS = (
    "open",
    "narrowed",
    "acknowledged",
    "closed",
    "notADisagreement",
    "notModelled",
)


DIVERGENCE_SEVERITY = (
    "contradiction",
    "high",
    "medium",
    "low",
    "unstated",
    "unchecked",
    "outOfScope",
)


DIVERGENCE_SOURCES = (
    "document",
    "reference",
    "recording",
    "corpus",
    "cartridges",
    "microcode",
    "neither",
)


def divergence_entries(where: Path) -> list[Any]:
    if not where.is_file():
        return []
    held = json.loads(where.read_text())
    for value in held.values():
        if isinstance(value, list):
            return list(value)
    return []


def outside_vocabulary(entries: Any, field: str, allowed: Any) -> list[str]:
    return sorted({str(one.get(field)) for one in entries if one.get(field) not in allowed})


class DivergenceRecordTest(unittest.TestCase):
    @property
    def entries(self) -> Any:
        return divergence_entries(DIVERGENCES)

    def test_there_is_a_record_to_check(self) -> None:
        # Arrange
        where = DIVERGENCES

        # Act
        entries = divergence_entries(where)

        # Assert
        self.assertGreater(len(entries), 0)

    def test_every_entry_says_where_it_stands(self) -> None:
        # Arrange
        entries = self.entries

        # Act
        found = outside_vocabulary(entries, "status", DIVERGENCE_STATUS)

        # Assert
        self.assertEqual(found, [])

    def test_every_entry_says_how_much_it_costs(self) -> None:
        # Arrange
        entries = self.entries

        # Act
        found = outside_vocabulary(entries, "severity", DIVERGENCE_SEVERITY)

        # Assert
        self.assertEqual(found, [])

    def test_every_entry_says_what_this_package_followed(self) -> None:
        # Arrange
        entries = self.entries

        # Act
        found = outside_vocabulary(entries, "packageFollows", DIVERGENCE_SOURCES)

        # Assert
        self.assertEqual(found, [])

    def test_a_value_nobody_agreed_on_is_caught(self) -> None:
        # Arrange
        entries = [{"status": "mostly open"}]

        # Act
        found = outside_vocabulary(entries, "status", DIVERGENCE_STATUS)

        # Assert
        self.assertEqual(found, ["mostly open"])

    def test_a_field_left_out_entirely_is_caught(self) -> None:
        # Arrange
        entries: list[dict[str, Any]] = [{}]

        # Act
        found = outside_vocabulary(entries, "severity", DIVERGENCE_SEVERITY)

        # Assert
        self.assertEqual(found, ["None"])

    def test_a_record_that_is_not_here_reads_as_empty(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp()) / "divergences.json"

        # Act
        found = divergence_entries(where)

        # Assert
        self.assertEqual(found, [])

    def test_a_record_with_no_list_in_it_reads_as_empty(self) -> None:
        # Arrange
        where = a_folder_holding("divergences.json", '{"note": "nothing here yet"}')

        # Act
        found = divergence_entries(where / "divergences.json")

        # Assert
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
