from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mos65xx
from mos65xx import MODELS, Cpu, Memory, SparseMemory, UnknownModelError


class CatalogueTest(unittest.TestCase):
    def test_the_family_names_every_model_it_covers(self) -> None:
        # Arrange
        wanted = ("65816", "65802")

        # Act
        missing = [name for name in wanted if name not in MODELS]

        # Assert
        self.assertEqual(missing, [])

    def test_a_model_says_which_processor_it_is_and_what_it_can_do(self) -> None:
        # Arrange
        name = "65816"

        # Act
        found = MODELS[name]

        # Assert
        self.assertEqual((found.name, bool(found.summary), found.address_bits), ("65816", True, 24))

    def test_a_model_the_family_does_not_have_is_refused_by_name(self) -> None:
        # Arrange
        def attempt() -> Any:
            return Cpu("6809")

        # Act
        with self.assertRaises(UnknownModelError) as raised:
            attempt()

        # Assert
        self.assertIn("6809 is not a model this family covers", str(raised.exception))

    def test_the_refusal_lists_what_is_available(self) -> None:
        # Arrange
        def attempt() -> Any:
            return Cpu("nonsense")

        # Act
        with self.assertRaises(UnknownModelError) as raised:
            attempt()

        # Assert
        self.assertIn("65816", str(raised.exception))

    def test_a_model_name_is_matched_however_it_is_written(self) -> None:
        # Arrange
        spellings = ("65816", "W65C816S", " 65816 ", "w65c816")

        # Act
        found = {Cpu(name, SparseMemory()).model for name in spellings}

        # Assert
        self.assertEqual(found, {"65816"})


class BuildTest(unittest.TestCase):
    def test_a_processor_is_built_from_its_model_name(self) -> None:
        # Arrange
        memory = SparseMemory()

        # Act
        cpu = Cpu("65816", memory)

        # Assert
        self.assertEqual(cpu.model, "65816")

    def test_building_without_naming_a_model_is_refused(self) -> None:
        # Arrange
        def attempt() -> Any:
            return Cpu()

        # Act
        with self.assertRaises(UnknownModelError) as raised:
            attempt()

        # Assert
        self.assertIn("no model was named", str(raised.exception))

    def test_and_the_refusal_names_every_model_there_is(self) -> None:
        # Arrange
        def attempt() -> Any:
            return Cpu()

        # Act
        with self.assertRaises(UnknownModelError) as raised:
            attempt()

        # Assert
        self.assertEqual([name for name in MODELS if name not in str(raised.exception)], [])

    def test_nothing_named_describe_is_published(self) -> None:
        # Arrange
        package = mos65xx

        # Act
        published = hasattr(package, "describe")

        # Assert
        self.assertFalse(published)

    def test_and_no_default_model_is_published_either(self) -> None:
        # Arrange
        package = mos65xx

        # Act
        published = hasattr(package, "DEFAULT_MODEL")

        # Assert
        self.assertFalse(published)

    def test_the_smaller_part_carries_the_same_core_with_less_address_space(self) -> None:
        # Arrange
        memory = SparseMemory()

        # Act
        cpu = Cpu("65802", memory)

        # Assert
        self.assertEqual((cpu.model, cpu.address_mask), ("65802", 0xFFFF))

    def test_the_larger_part_reaches_the_whole_address_space(self) -> None:
        # Arrange
        memory = SparseMemory()

        # Act
        cpu = Cpu("65816", memory)

        # Assert
        self.assertEqual(cpu.address_mask, 0xFFFFFF)

    def test_the_address_mask_confines_where_a_read_can_land(self) -> None:
        # Arrange
        memory = SparseMemory()
        memory.write8(0x0012, 0x5A)
        cpu = Cpu("65802", memory)

        # Act
        value = cpu.read8(0x7E0012)

        # Assert
        self.assertEqual(value, 0x5A)

    def test_the_larger_part_does_not_confine_it(self) -> None:
        # Arrange
        memory = SparseMemory()
        memory.write8(0x7E0012, 0x5A)
        cpu = Cpu("65816", memory)

        # Act
        value = cpu.read8(0x7E0012)

        # Assert
        self.assertEqual(value, 0x5A)

    def test_a_part_that_was_built_has_spent_no_cycle(self) -> None:
        # Arrange
        memory = SparseMemory()

        # Act
        cpu = Cpu("65816", memory)

        # Assert
        self.assertEqual(cpu.cycles, 0)

    def test_a_part_that_was_never_reset_does_not_come_up_cleared(self) -> None:
        # Arrange
        memory = SparseMemory()

        # Act
        cpu = Cpu("65816", memory)

        # Assert
        self.assertNotEqual((cpu.a, cpu.x, cpu.y, cpu.pc, cpu.d), (0, 0, 0, 0, 0))


class DescriptionTest(unittest.TestCase):
    def test_a_model_prints_as_its_name_and_reach(self) -> None:
        # Arrange
        model = MODELS["65816"]

        # Act
        printed = repr(model)

        # Assert
        self.assertEqual(printed, "<Model 65816, 24 address bits>")


class FamilyTest(unittest.TestCase):
    def test_every_model_builds_a_processor_of_its_own_kind(self) -> None:
        # Arrange
        names = sorted(MODELS)

        # Act
        built = {name: Cpu(name, SparseMemory(seed=1)) for name in names}

        # Assert
        self.assertEqual(
            {name: (cpu.model, cpu.address_mask) for name, cpu in built.items()},
            {name: (name, (1 << MODELS[name].address_bits) - 1) for name in names},
        )

    def test_the_part_with_no_decimal_adder_says_so(self) -> None:
        # Arrange
        name = "2a03"

        # Act
        model = MODELS[name]

        # Assert
        self.assertFalse(model.decimal)

    def test_the_parts_that_have_one_say_so(self) -> None:
        # Arrange
        names = ("6502", "6507", "65816", "65802")

        # Act
        found = [MODELS[name].decimal for name in names]

        # Assert
        self.assertEqual(found, [True, True, True, True])

    def test_the_smaller_package_reaches_less(self) -> None:
        # Arrange
        smaller = MODELS["6507"]

        # Act
        larger = MODELS["6502"]

        # Assert
        self.assertEqual((smaller.address_mask, larger.address_mask), (0x1FFF, 0xFFFF))


class QuietStoreTest(unittest.TestCase):
    def test_a_fill_puts_that_byte_everywhere(self) -> None:
        # Arrange
        fill = 0

        # Act
        part = Cpu("6502", fill=fill)

        # Assert
        self.assertEqual({part.memory.read8(address) for address in range(0x40)}, {0})

    def test_and_any_byte_works_rather_than_only_zero(self) -> None:
        # Arrange
        fill = 0xAA

        # Act
        part = Cpu("6502", fill=fill)

        # Assert
        self.assertEqual({part.memory.read8(address) for address in range(0x40)}, {0xAA})

    def test_without_one_the_store_is_scrambled_rather_than_cleared(self) -> None:
        # Arrange
        name = "6502"

        # Act
        part = Cpu(name)

        # Assert
        self.assertNotEqual({part.memory.read8(address) for address in range(0x40)}, {0})

    def test_and_a_store_handed_in_is_left_alone(self) -> None:
        # Arrange
        own = Memory(fill=0xAA)

        # Act
        part = Cpu("6502", own, fill=0)

        # Assert
        self.assertIs(part.memory, own)
        self.assertEqual({part.memory.read8(address) for address in range(0x40)}, {0xAA})


if __name__ == "__main__":
    unittest.main(verbosity=2)
