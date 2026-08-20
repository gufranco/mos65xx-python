from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

models = importlib.import_module("mos65xx.models")
mos65xx = importlib.import_module("mos65xx")


class CatalogueTest(unittest.TestCase):
    def test_the_family_names_every_model_it_covers(self) -> None:
        for name in ("65816", "65802"):
            self.assertIn(name, models.MODELS)

    def test_a_model_says_which_processor_it_is_and_what_it_can_do(self) -> None:
        found = models.describe("65816")

        self.assertEqual(found.name, "65816")
        self.assertTrue(found.summary)
        self.assertEqual(found.address_bits, 24)

    def test_a_model_the_family_does_not_have_is_refused_by_name(self) -> None:
        with self.assertRaises(models.UnknownModelError) as raised:
            models.describe("6809")

        self.assertIn("6809", str(raised.exception))

    def test_the_refusal_lists_what_is_available(self) -> None:
        with self.assertRaises(models.UnknownModelError) as raised:
            models.describe("nonsense")

        self.assertIn("65816", str(raised.exception))

    def test_a_model_name_is_matched_however_it_is_written(self) -> None:
        self.assertIs(models.describe("65816"), models.describe("W65C816S"))
        self.assertIs(models.describe("65816"), models.describe(" 65816 "))


class BuildTest(unittest.TestCase):
    def memory(self) -> Any:
        return mos65xx.SparseMemory()

    def test_a_processor_is_built_from_its_model_name(self) -> None:
        cpu = mos65xx.Cpu(self.memory(), model="65816")

        self.assertEqual(cpu.model, "65816")

    def test_the_default_model_is_the_largest_of_the_family(self) -> None:
        self.assertEqual(mos65xx.Cpu(self.memory()).model, "65816")

    def test_the_smaller_part_carries_the_same_core_with_less_address_space(self) -> None:
        cpu = mos65xx.Cpu(self.memory(), model="65802")

        self.assertEqual(cpu.model, "65802")
        self.assertEqual(cpu.address_mask, 0xFFFF)

    def test_the_larger_part_reaches_the_whole_address_space(self) -> None:
        self.assertEqual(mos65xx.Cpu(self.memory(), model="65816").address_mask, 0xFFFFFF)

    def test_the_address_mask_confines_where_a_read_can_land(self) -> None:
        memory = self.memory()
        memory.write8(0x0012, 0x5A)
        cpu = mos65xx.Cpu(memory, model="65802")

        self.assertEqual(cpu.read8(0x7E0012), 0x5A)

    def test_the_larger_part_does_not_confine_it(self) -> None:
        memory = self.memory()
        memory.write8(0x7E0012, 0x5A)
        cpu = mos65xx.Cpu(memory, model="65816")

        self.assertEqual(cpu.read8(0x7E0012), 0x5A)

    def test_options_reach_the_processor_that_gets_built(self) -> None:
        cpu = mos65xx.Cpu(self.memory(), model="65816", reset=False)

        self.assertFalse(cpu.emulation)


class DescriptionTest(unittest.TestCase):
    def test_a_model_prints_as_its_name_and_reach(self) -> None:
        printed = repr(models.describe("65816"))

        self.assertIn("65816", printed)
        self.assertIn("24", printed)


class FamilyTest(unittest.TestCase):
    def test_every_model_builds_a_processor_of_its_own_kind(self) -> None:
        from mos65xx import Cpu, SparseMemory

        for name in models.MODELS:
            cpu = Cpu(SparseMemory(seed=1), model=name)

            self.assertEqual(cpu.model, name)
            self.assertEqual(cpu.address_mask, models.describe(name).address_mask)

    def test_the_part_with_no_decimal_adder_says_so(self) -> None:
        self.assertFalse(models.describe("2a03").decimal)

    def test_the_parts_that_have_one_say_so(self) -> None:
        for name in ("6502", "6507", "65816", "65802"):
            self.assertTrue(models.describe(name).decimal, name)

    def test_the_smaller_package_reaches_less(self) -> None:
        self.assertLess(models.describe("6507").address_mask, models.describe("6502").address_mask)


if __name__ == "__main__":
    unittest.main(verbosity=2)
