import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

models = importlib.import_module("mos65xx.models")
mos65xx = importlib.import_module("mos65xx")


class CatalogueTest(unittest.TestCase):
    def test_the_family_names_every_model_it_covers(self):
        for name in ("65816", "65802"):
            self.assertIn(name, models.MODELS)

    def test_a_model_says_which_processor_it_is_and_what_it_can_do(self):
        found = models.describe("65816")

        self.assertEqual(found.name, "65816")
        self.assertTrue(found.summary)
        self.assertEqual(found.address_bits, 24)

    def test_a_model_the_family_does_not_have_is_refused_by_name(self):
        with self.assertRaises(models.UnknownModelError) as raised:
            models.describe("6809")

        self.assertIn("6809", str(raised.exception))

    def test_the_refusal_lists_what_is_available(self):
        with self.assertRaises(models.UnknownModelError) as raised:
            models.describe("nonsense")

        self.assertIn("65816", str(raised.exception))

    def test_a_model_name_is_matched_however_it_is_written(self):
        self.assertIs(models.describe("65816"), models.describe("W65C816S"))
        self.assertIs(models.describe("65816"), models.describe(" 65816 "))


class BuildTest(unittest.TestCase):
    def memory(self):
        return mos65xx.SparseMemory()

    def test_a_processor_is_built_from_its_model_name(self):
        cpu = mos65xx.Cpu(self.memory(), model="65816")

        self.assertEqual(cpu.model, "65816")

    def test_the_default_model_is_the_largest_of_the_family(self):
        self.assertEqual(mos65xx.Cpu(self.memory()).model, "65816")

    def test_the_smaller_part_carries_the_same_core_with_less_address_space(self):
        cpu = mos65xx.Cpu(self.memory(), model="65802")

        self.assertEqual(cpu.model, "65802")
        self.assertEqual(cpu.address_mask, 0xFFFF)

    def test_the_larger_part_reaches_the_whole_address_space(self):
        self.assertEqual(mos65xx.Cpu(self.memory(), model="65816").address_mask, 0xFFFFFF)

    def test_the_address_mask_confines_where_a_read_can_land(self):
        memory = self.memory()
        memory.write8(0x0012, 0x5A)
        cpu = mos65xx.Cpu(memory, model="65802")

        self.assertEqual(cpu.read8(0x7E0012), 0x5A)

    def test_the_larger_part_does_not_confine_it(self):
        memory = self.memory()
        memory.write8(0x7E0012, 0x5A)
        cpu = mos65xx.Cpu(memory, model="65816")

        self.assertEqual(cpu.read8(0x7E0012), 0x5A)

    def test_options_reach_the_processor_that_gets_built(self):
        cpu = mos65xx.Cpu(self.memory(), model="65816", reset=False)

        self.assertFalse(cpu.emulation)


class DescriptionTest(unittest.TestCase):
    def test_a_model_prints_as_its_name_and_reach(self):
        printed = repr(models.describe("65816"))

        self.assertIn("65816", printed)
        self.assertIn("24", printed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
