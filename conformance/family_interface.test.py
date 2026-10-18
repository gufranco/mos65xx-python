from __future__ import annotations

import inspect
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import (
    A_MODEL,
    CLOCKED,
    COUNTERS,
    FAMILY,
    INTERFACE,
    INTERRUPT_LINES,
    KIND,
    PACKAGE,
    ROOT,
    a_part,
    a_running_part,
    accounts_for_one_interrupt,
    store_attribute,
)
from conformance.family_shared import RECORD


class ModelsAClockedPartTest(unittest.TestCase):
    def row(self) -> str:
        pattern = rf"^\|\s*\[{re.escape(ROOT.name)}\]\([^)]*\)\s*\|(.+)\|(.+)\|\s*$"
        found = re.search(pattern, FAMILY, re.M)

        assert found is not None, f"{ROOT.name} is not in the membership table"
        return found.group(2).strip()

    def test_this_member_is_in_the_membership_table(self) -> None:
        # Arrange
        member = ROOT.name

        # Act
        standard = (ROOT / "FAMILY.md").read_text()

        # Assert
        self.assertIn(member, standard)

    def test_and_the_kind_it_declares_is_the_kind_the_table_gives_it(self) -> None:
        # Arrange
        declared = KIND

        # Act
        given = self.row()

        # Assert
        self.assertEqual(declared, given)

    def test_the_table_only_uses_kinds_the_standard_explains(self) -> None:
        # Arrange
        explained = {"Clocked part", "Part", "Board", "Format", "Tool"}

        # Act
        kinds = set(re.findall(r"\|\s*(Clocked part|Part|Board|Format|Tool)\s*\|", FAMILY))

        # Assert
        self.assertLessEqual(kinds, explained)
        self.assertIn(KIND, kinds)

    def test_the_standard_says_what_a_kind_that_is_not_clocked_skips(self) -> None:
        # Arrange
        sentence = "skips the section about a clock"

        # Act
        standard = (ROOT / "FAMILY.md").read_text()

        # Assert
        self.assertIn(sentence, standard)


@unittest.skipUnless(CLOCKED, "not a clocked part")
class PromisedInterfaceTest(unittest.TestCase):
    def test_every_call_the_standard_names_exists_here(self) -> None:
        # Arrange
        part = a_part()

        # Act
        absent = [name for name in INTERFACE if not hasattr(part, name)]

        # Assert
        self.assertEqual(absent, [])

    def test_and_every_interrupt_line_the_part_has(self) -> None:
        # Arrange
        part = a_part()

        # Act
        absent = [name for name in INTERRUPT_LINES if not hasattr(part, name)]

        # Assert
        self.assertEqual(absent, [])

    def test_and_the_record_accounts_for_what_lines_it_names(self) -> None:
        # Arrange
        record = json.loads(RECORD.read_text())

        # Act
        accounted = accounts_for_one_interrupt(record)

        # Assert
        self.assertTrue(accounted)

    def test_a_record_naming_an_interrupt_as_a_key_is_read(self) -> None:
        # Arrange
        record = {"facts": {"interruptVector": 4}}

        # Act
        accounted = accounts_for_one_interrupt(record)

        # Assert
        self.assertTrue(accounted)

    def test_and_one_naming_it_only_in_a_sentence(self) -> None:
        # Arrange
        record = {"notStated": ["what the interrupt pin does"]}

        # Act
        accounted = accounts_for_one_interrupt(record)

        # Assert
        self.assertTrue(accounted)

    def test_and_one_naming_it_inside_a_list(self) -> None:
        # Arrange
        record = [{"note": "one interrupt line"}]

        # Act
        accounted = accounts_for_one_interrupt(record)

        # Assert
        self.assertTrue(accounted)

    def test_and_a_record_that_never_mentions_one_is_reported(self) -> None:
        # Arrange
        record = {"facts": {"window": [1, 2]}, "note": "a part"}

        # Act
        accounted = accounts_for_one_interrupt(record)

        # Assert
        self.assertFalse(accounted)

    def test_and_every_counter(self) -> None:
        # Arrange
        part = a_part()

        # Act
        absent = [name for name in COUNTERS if not hasattr(part, name)]

        # Assert
        self.assertEqual(absent, [])

    def test_the_standard_names_each_of_them(self) -> None:
        # Arrange
        names = INTERFACE + COUNTERS

        # Act
        unnamed = [name for name in names if name not in FAMILY]

        # Assert
        self.assertEqual(unnamed, [])


@unittest.skipUnless(CLOCKED, "not a clocked part")
class PromisedBehaviourTest(unittest.TestCase):
    def test_a_step_reports_what_it_cost(self) -> None:
        # Arrange
        part = a_running_part()

        # Act
        cost = part.step()

        # Assert
        self.assertIsInstance(cost, int)

    def test_a_budget_reports_what_it_spent(self) -> None:
        # Arrange
        part = a_running_part()

        # Act
        spent = part.run_for(64)

        # Assert
        self.assertGreaterEqual(spent, 64)

    def test_the_budget_parameter_is_named_for_the_family(self) -> None:
        # Arrange
        part = a_part()

        # Act
        named = list(inspect.signature(part.run_for).parameters)

        # Assert
        self.assertEqual(named, ["cycles"])

    def test_a_reset_hands_the_part_back(self) -> None:
        # Arrange
        part = a_part()

        # Act
        handed = part.reset()

        # Assert
        self.assertIs(handed, part)

    def test_the_tally_survives_a_reset(self) -> None:
        # Arrange
        part = a_running_part()
        part.run_for(64)
        before = part.cycles

        # Act
        part.reset()

        # Assert
        self.assertGreaterEqual(part.cycles, before)

    def test_a_bounded_run_gives_up_rather_than_hanging(self) -> None:
        # Arrange
        part = a_running_part()

        # Act
        attempt = lambda: part.run_until(lambda _: False, limit=32)  # noqa: E731

        # Assert
        self.assertRaises(PACKAGE.RunLimit, attempt)

    def test_a_running_part_is_not_held(self) -> None:
        # Arrange
        part = a_part()

        # Act
        held = part.held()

        # Assert
        self.assertFalse(held)


@unittest.skipUnless(CLOCKED, "not a clocked part")
class SuppliedMemoryTest(unittest.TestCase):
    def test_a_supplied_store_is_the_one_the_part_uses(self) -> None:
        # Arrange
        where = store_attribute()
        own = getattr(PACKAGE.Cpu(A_MODEL), where)

        # Act
        built = PACKAGE.Cpu(A_MODEL, own)

        # Assert
        self.assertIs(getattr(built, where), own)

    def test_and_one_is_built_when_the_argument_is_left_out(self) -> None:
        # Arrange
        model = A_MODEL

        # Act
        built = PACKAGE.Cpu(model)

        # Assert
        self.assertIsNotNone(getattr(built, store_attribute()))

    def test_the_standard_names_this_part_spelling(self) -> None:
        # Arrange
        spelling = f"cpu.{store_attribute()}"

        # Act
        standard = (ROOT / "FAMILY.md").read_text()

        # Assert
        self.assertIn(spelling, standard)


if __name__ == "__main__":
    unittest.main()
