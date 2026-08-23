from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

models = importlib.import_module("mos65xx.models")
memory = importlib.import_module("mos65xx.memory")
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
        cpu = mos65xx.Cpu("65816", self.memory())

        self.assertEqual(cpu.model, "65816")

    def test_the_default_model_is_the_largest_of_the_family(self) -> None:
        self.assertEqual(mos65xx.Cpu().model, "65816")

    def test_the_smaller_part_carries_the_same_core_with_less_address_space(self) -> None:
        cpu = mos65xx.Cpu("65802", self.memory())

        self.assertEqual(cpu.model, "65802")
        self.assertEqual(cpu.address_mask, 0xFFFF)

    def test_the_larger_part_reaches_the_whole_address_space(self) -> None:
        self.assertEqual(mos65xx.Cpu("65816", self.memory()).address_mask, 0xFFFFFF)

    def test_the_address_mask_confines_where_a_read_can_land(self) -> None:
        memory = self.memory()
        memory.write8(0x0012, 0x5A)
        cpu = mos65xx.Cpu("65802", memory)

        self.assertEqual(cpu.read8(0x7E0012), 0x5A)

    def test_the_larger_part_does_not_confine_it(self) -> None:
        memory = self.memory()
        memory.write8(0x7E0012, 0x5A)
        cpu = mos65xx.Cpu("65816", memory)

        self.assertEqual(cpu.read8(0x7E0012), 0x5A)

    def test_options_reach_the_processor_that_gets_built(self) -> None:
        cpu = mos65xx.Cpu("65816", self.memory(), reset=False)

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
            cpu = Cpu(name, SparseMemory(seed=1))

            self.assertEqual(cpu.model, name)
            self.assertEqual(cpu.address_mask, models.describe(name).address_mask)

    def test_the_part_with_no_decimal_adder_says_so(self) -> None:
        self.assertFalse(models.describe("2a03").decimal)

    def test_the_parts_that_have_one_say_so(self) -> None:
        for name in ("6502", "6507", "65816", "65802"):
            self.assertTrue(models.describe(name).decimal, name)

    def test_the_smaller_package_reaches_less(self) -> None:
        self.assertLess(models.describe("6507").address_mask, models.describe("6502").address_mask)


class NarrowingTest(unittest.TestCase):
    """The parts with no suite, held to the sibling each of them narrows."""

    def parts(self) -> list[tuple[str, str]]:
        return [
            (model.name, model.narrows)
            for model in models.MODELS.values()
            if model.narrows is not None
        ]

    def program(self, name: str, code: list[int], at: int = 0x0200) -> list[tuple[int, int, str]]:
        space = memory.Memory()
        for offset, byte in enumerate(code):
            space.write8(at + offset, byte)
        cpu = models.describe(name).build(space)
        cpu.pc = at
        cpu.trace = []
        for _ in range(4):
            cpu.step()
        return list(cpu.trace)

    def test_every_part_without_a_suite_names_the_one_it_narrows(self) -> None:
        self.assertEqual(
            dict(self.parts()),
            {
                "6503": "6502",
                "6504": "6502",
                "6505": "6502",
                "6506": "6502",
                "6507": "6502",
                "6512": "6502",
                "6513": "6502",
                "6514": "6502",
                "6515": "6502",
                "65802": "65816",
            },
        )

    def test_which_is_every_nmos_package_the_data_sheet_lists_but_one(self) -> None:
        narrowed = {name for name, _ in self.parts() if name.startswith("65") and len(name) == 4}

        self.assertEqual(len(narrowed), 9)

    def test_and_the_part_it_narrows_is_one_this_family_covers(self) -> None:
        missing = [wider for _, wider in self.parts() if wider not in models.MODELS]

        self.assertEqual(missing, [])

    def test_a_narrowed_part_is_built_from_the_same_core(self) -> None:
        same = [
            (name, wider)
            for name, wider in self.parts()
            if models.describe(name).core is not models.describe(wider).core
        ]

        self.assertEqual(same, [])

    def test_and_reaches_no_further_than_the_part_it_narrows(self) -> None:
        wider = [
            (name, w)
            for name, w in self.parts()
            if models.describe(name).address_bits > models.describe(w).address_bits
        ]

        self.assertEqual(wider, [])

    def test_the_smaller_package_puts_the_same_cycles_on_the_bus(self) -> None:
        for name, wider in self.parts():
            code = [0xEA, 0xEA, 0xEA, 0xEA]

            self.assertEqual(
                [(kind, value) for _, value, kind in self.program(name, code)],
                [(kind, value) for _, value, kind in self.program(wider, code)],
                name,
            )

    def test_and_differs_only_in_how_far_an_address_reaches_or_which_pins_it_has(self) -> None:
        """Lines left inside a smaller package, and a whole bank byte in the 65802."""
        held = {
            name: models.describe(wider).address_bits - models.describe(name).address_bits
            for name, wider in self.parts()
        }

        self.assertEqual(
            held,
            {
                "6503": 4,
                "6504": 3,
                "6505": 4,
                "6506": 4,
                "6507": 3,
                "6512": 0,
                "6513": 4,
                "6514": 3,
                "6515": 4,
                "65802": 8,
            },
        )

    def test_the_one_that_reaches_just_as_far_differs_only_in_its_clock(self) -> None:
        part = models.describe("6512")

        self.assertEqual(
            (part.address_bits, part.pins, "clock" in part.summary),
            (16, ("irq", "nmi", "rdy"), True),
        )

    def test_the_one_that_reaches_less_wraps_where_its_pins_stop(self) -> None:
        part = models.describe("6507")

        self.assertEqual(part.address_mask, (1 << part.address_bits) - 1)


class PinTest(unittest.TestCase):
    """Which lines each package brings out, and what happens when one does not.

    The narrower parts are the same die with fewer pins on the package. A line
    that is not there cannot be asserted by any system, so a model that took the
    request anyway would be describing a part nobody could build.
    """

    def part(self, name: str) -> Any:
        return models.describe(name).build(memory.Memory())

    def test_the_widest_part_brings_out_all_three(self) -> None:
        self.assertEqual(models.describe("6502").pins, ("irq", "nmi", "rdy"))

    def test_the_atari_part_brings_out_none_of_the_interrupt_lines(self) -> None:
        self.assertEqual(models.describe("6507").pins, ("rdy",))

    def test_and_refuses_both_of_them_rather_than_pretending(self) -> None:
        cpu = self.part("6507")

        for pin in ("irq", "nmi"):
            with self.assertRaises(models.NoSuchPin):
                getattr(cpu, pin)()

    def test_the_error_says_what_the_package_does_bring_out(self) -> None:
        cpu = self.part("6504")

        with self.assertRaises(models.NoSuchPin) as caught:
            cpu.nmi()

        self.assertIn("it brings out irq", str(caught.exception))

    def test_a_part_with_the_request_line_still_takes_a_request(self) -> None:
        cpu = self.part("6504")
        cpu.i = False

        self.assertTrue(cpu.irq())

    def test_five_of_the_ten_nmos_packages_leave_the_non_maskable_line_off(self) -> None:
        without = [
            model.name
            for model in models.MODELS.values()
            if model.core is models.describe("6502").core and "nmi" not in model.pins
        ]

        self.assertEqual(without, ["6507", "6504", "6505", "6506", "6514", "6515"])

    def test_only_one_leaves_the_request_line_off_as_well(self) -> None:
        without = [
            model.name
            for model in models.MODELS.values()
            if model.core is models.describe("6502").core and "irq" not in model.pins
        ]

        self.assertEqual(without, ["6507"])

    def test_a_built_part_reports_the_pins_its_package_has(self) -> None:
        found = {name: self.part(name).package_pins for name in ("6502", "6507", "65816")}

        self.assertEqual(
            found,
            {
                "6502": ("irq", "nmi", "rdy"),
                "6507": ("rdy",),
                "65816": ("irq", "nmi", "rdy"),
            },
        )

    def test_every_part_the_suites_cover_brings_out_all_three(self) -> None:
        covered = ("6502", "2a03", "65c02", "r65c02", "w65c02", "65816")
        found = {models.describe(name).pins for name in covered}

        self.assertEqual(found, {("irq", "nmi", "rdy")})


if __name__ == "__main__":
    unittest.main(verbosity=2)
