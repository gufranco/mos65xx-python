from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mos65xx  # noqa: E402
from mos65xx import MODELS, Memory, SparseMemory  # noqa: E402

HARDWARE = Path(__file__).resolve().parent / "hardware.json"

BOTH_LINES = {"irq", "nmi"}


def declared() -> dict[str, Any]:
    held = json.loads(HARDWARE.read_text())
    assert isinstance(held, dict), f"{HARDWARE} does not hold an object"
    return held


def fact(name: str) -> dict[str, Any]:
    found = declared()["facts"][name]
    assert isinstance(found, dict), f"{name} is not recorded as a fact"
    return found


def packages() -> list[str]:
    return [str(name) for name in fact("nmosFamilyPackages")["packages"]]


def overreaching(facts: dict[str, Any], documents: dict[str, Any]) -> list[str]:
    found = []
    for name, fact in facts.items():
        held = documents.get(fact["document"], {}).get("appliesTo")
        if held and not set(fact["appliesTo"]) <= set(held):
            found.append(f"{name}: {fact['appliesToCore']} from {fact['document']}")
    return found


def built_cores() -> list[list[str]]:
    held: dict[type, list[str]] = {}
    for name in sorted(MODELS):
        held.setdefault(type(mos65xx.Cpu(name, SparseMemory())), []).append(name)
    return sorted(held.values())


def recorded_cores() -> dict[str, Any]:
    return {name: one for name, one in declared()["cores"].items() if name != "note"}


def closing_conditions() -> dict[str, Any]:
    return {name: one for name, one in declared()["closingConditions"].items() if name != "note"}


class HonestyTest(unittest.TestCase):
    def test_the_late_arriving_rotate_is_recorded_as_not_modelled(self) -> None:
        # Arrange
        name = "nmosRorArrivedLate"

        # Act
        held = fact(name)

        # Assert
        self.assertIn("notModelled", held)

    def test_the_pin_this_project_does_not_drive_says_so(self) -> None:
        # Arrange
        name = "memoryLock"

        # Act
        note = fact(name)["note"]

        # Assert
        self.assertIn("Nothing in this project drives it", note)

    def test_the_earliest_revision_names_two_modes_the_later_ones_drop(self) -> None:
        # Arrange
        early = fact("stackRangeInEmulationAsFirstPrinted")["quote"]

        # Act
        late = fact("stackRangeInEmulation")["quote"]

        # Assert
        self.assertEqual(("d, s" in early, "d, s" in late), (True, False))

    def test_a_stack_relative_read_leaves_the_emulation_stack_range(self) -> None:
        # Arrange
        memory = Memory(0x1000000)
        memory.write8(0x000200, 0xA3)
        memory.write8(0x000201, 0xFF)
        cpu = mos65xx.Cpu("65816", memory)
        cpu.pc, cpu.pb, cpu.db, cpu.d = 0x0200, 0, 0, 0
        cpu.emulation = True
        cpu.s = 0x01FF
        cpu.trace = []

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.trace[-1][0], 0x0002FE)

    def test_which_is_what_the_earliest_revision_says_and_the_later_ones_omit(self) -> None:
        # Arrange
        name = "stackRangeInEmulationAsFirstPrinted"

        # Act
        note = fact(name)["note"]

        # Assert
        self.assertIn("lands above 0001FF rather than wrapping", note)

    def test_the_second_source_names_all_but_one_of_them(self) -> None:
        # Arrange
        synertek = fact("nmosFamilyPackages")["alsoNamedBySynertek"]

        # Act
        unnamed = set(packages()) - set(synertek)

        # Assert
        self.assertEqual(unnamed, {"6507"})

    def test_and_the_record_says_which_one_and_why_that_is_unsurprising(self) -> None:
        # Arrange
        name = "nmosFamilyPackages"

        # Act
        second = fact(name)["secondSource"]

        # Assert
        self.assertIn("made for a single customer", second)

    def test_the_data_sheet_lists_ten_packages(self) -> None:
        # Arrange
        name = "nmosFamilyPackages"

        # Act
        listed = fact(name)["packages"]

        # Assert
        self.assertEqual(len(listed), 10)

    def test_the_family_table_matches_the_parts_this_package_builds(self) -> None:
        # Arrange
        recorded = fact("nmosFamilyPackages")["whatIsImplemented"]["interruptPins"]

        # Act
        both = [name for name in packages() if set(MODELS[name].pins) >= BOTH_LINES]

        # Assert
        self.assertEqual(
            (both, "6502, 6503, 6512 and 6513" in recorded),
            (["6502", "6503", "6512", "6513"], True),
        )

    def test_and_the_one_with_neither_line_is_the_one_the_table_names(self) -> None:
        # Arrange
        recorded = fact("nmosFamilyPackages")["whatIsImplemented"]["interruptPins"]

        # Act
        neither = [name for name in packages() if not BOTH_LINES & set(MODELS[name].pins)]

        # Assert
        self.assertEqual((neither, "Neither on the 6507" in recorded), (["6507"], True))

    def test_the_comparison_table_is_the_same_in_both_revisions_that_carry_it(self) -> None:
        # Arrange
        name = "caveatsTableIsStableAcrossRevisions"

        # Act
        note = fact(name)["note"]

        # Assert
        self.assertIn("Only the section number moved", note)

    def test_the_two_places_the_document_contradicts_itself_are_both_recorded(self) -> None:
        # Arrange
        jump = fact("indirectJumpBanks")

        # Act
        erratum = fact("vectors")["erratumInTable6_3"]

        # Assert
        self.assertEqual(("contradictedBy" in jump, "whyItIsAnErratum" in erratum), (True, True))


class CoreScopeTest(unittest.TestCase):
    def test_the_record_names_the_cores_the_package_builds(self) -> None:
        # Arrange
        recorded = sorted(one["models"] for one in recorded_cores().values())

        # Act
        built = built_cores()

        # Assert
        self.assertEqual(built, recorded)

    def test_and_names_no_builder_the_reader_would_have_to_find_in_the_source(self) -> None:
        # Arrange
        cores = recorded_cores()

        # Act
        keys = {key for one in cores.values() for key in one}

        # Assert
        self.assertEqual(keys, {"models"})

    def test_every_fact_names_the_models_it_governs(self) -> None:
        # Arrange
        facts = declared()["facts"]

        # Act
        unscoped = [
            name
            for name, one in facts.items()
            if not isinstance(one.get("appliesTo"), list) or not one["appliesTo"]
        ]

        # Assert
        self.assertEqual(unscoped, [])

    def test_and_every_model_it_names_is_one_the_package_builds(self) -> None:
        # Arrange
        facts = declared()["facts"]

        # Act
        invented = sorted(
            {model for one in facts.values() for model in one["appliesTo"] if model not in MODELS}
        )

        # Assert
        self.assertEqual(invented, [])

    def test_and_the_shorthand_it_was_expanded_from_agrees(self) -> None:
        # Arrange
        cores = {name: one["models"] for name, one in recorded_cores().items()}

        # Act
        wrong = [
            name
            for name, one in declared()["facts"].items()
            if one["appliesTo"] != cores[one["appliesToCore"]]
        ]

        # Assert
        self.assertEqual(wrong, [])

    def test_no_fact_claims_a_core_its_document_does_not_cover(self) -> None:
        # Arrange
        held = declared()

        # Act
        found = overreaching(held["facts"], held["documents"])

        # Assert
        self.assertEqual(found, [])

    def test_and_one_that_did_would_be_reported(self) -> None:
        # Arrange
        facts = {
            "borrowed": {
                "document": "wide-only",
                "appliesTo": ["65c02"],
                "appliesToCore": "cmos",
            }
        }
        documents = {"wide-only": {"appliesTo": ["65802", "65816"]}}

        # Act
        found = overreaching(facts, documents)

        # Assert
        self.assertEqual(found, ["borrowed: cmos from wide-only"])

    def test_every_document_says_which_cores_it_covers(self) -> None:
        # Arrange
        documents = declared()["documents"]

        # Act
        silent = [name for name, one in documents.items() if "cores" not in one]

        # Assert
        self.assertEqual(silent, [])


class ClosingConditionTest(unittest.TestCase):
    def test_every_condition_names_a_document_the_record_declares(self) -> None:
        # Arrange
        known = set(declared()["documents"])

        # Act
        unknown = sorted(
            name for name, one in closing_conditions().items() if one["document"] not in known
        )

        # Assert
        self.assertEqual(unknown, [])

    def test_and_the_question_it_would_settle(self) -> None:
        # Arrange
        questions = (ROOT / "OPEN-QUESTIONS.md").read_text()

        # Act
        missing = sorted(
            name for name, one in closing_conditions().items() if one["settles"] not in questions
        )

        # Assert
        self.assertEqual(missing, [])

    def test_and_says_it_is_not_carried_here(self) -> None:
        # Arrange
        conditions = closing_conditions()

        # Act
        carried = sorted(name for name, one in conditions.items() if one["carried"])

        # Assert
        self.assertEqual(carried, [])

    def test_none_of_them_is_scoped_as_though_it_were_a_fact(self) -> None:
        # Arrange
        conditions = closing_conditions()

        # Act
        scoped = sorted(
            name for name, one in conditions.items() if "appliesTo" in one or "appliesToCore" in one
        )

        # Assert
        self.assertEqual(scoped, [])


if __name__ == "__main__":
    unittest.main()
