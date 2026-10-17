from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import MODELS, Memory, NoSuchPin, SparseMemory

FOUR_NOPS = [0xEA, 0xEA, 0xEA, 0xEA]


def narrowed() -> list[tuple[str, str]]:
    return [(model.name, model.narrows) for model in MODELS.values() if model.narrows is not None]


def core_of(name: str) -> type:
    return type(MODELS[name].build(SparseMemory()))


def program(name: str, code: list[int], at: int = 0x0200) -> list[tuple[int, int, str]]:
    space = Memory()
    for offset, byte in enumerate(code):
        space.write8(at + offset, byte)
    cpu = MODELS[name].build(space)
    cpu.reset()
    cpu.pc = at
    cpu.trace = []
    for _ in range(4):
        cpu.step()
    return list(cpu.trace)


def part(name: str) -> Any:
    return MODELS[name].build(Memory())


class NarrowingTest(unittest.TestCase):
    def test_every_part_without_a_suite_names_the_one_it_narrows(self) -> None:
        # Arrange
        models = MODELS

        # Act
        found = {model.name: model.narrows for model in models.values() if model.narrows}

        # Assert
        self.assertEqual(
            found,
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
        # Arrange
        parts = narrowed()

        # Act
        nmos = {name for name, _ in parts if name.startswith("65") and len(name) == 4}

        # Assert
        self.assertEqual(len(nmos), 9)

    def test_and_the_part_it_narrows_is_one_this_family_covers(self) -> None:
        # Arrange
        parts = narrowed()

        # Act
        missing = [wider for _, wider in parts if wider not in MODELS]

        # Assert
        self.assertEqual(missing, [])

    def test_a_narrowed_part_is_built_from_the_same_core(self) -> None:
        # Arrange
        parts = narrowed()

        # Act
        apart = [(name, wider) for name, wider in parts if core_of(name) is not core_of(wider)]

        # Assert
        self.assertEqual(apart, [])

    def test_and_reaches_no_further_than_the_part_it_narrows(self) -> None:
        # Arrange
        parts = narrowed()

        # Act
        wider = [
            (name, w) for name, w in parts if MODELS[name].address_bits > MODELS[w].address_bits
        ]

        # Assert
        self.assertEqual(wider, [])

    def test_the_smaller_package_puts_the_same_cycles_on_the_bus(self) -> None:
        # Arrange
        parts = narrowed()

        # Act
        differing = [
            name
            for name, wider in parts
            if [(kind, value) for _, value, kind in program(name, FOUR_NOPS)]
            != [(kind, value) for _, value, kind in program(wider, FOUR_NOPS)]
        ]

        # Assert
        self.assertEqual(differing, [])

    def test_and_differs_only_in_how_far_an_address_reaches_or_which_pins_it_has(self) -> None:
        # Arrange
        parts = narrowed()

        # Act
        held = {
            name: MODELS[wider].address_bits - MODELS[name].address_bits for name, wider in parts
        }

        # Assert
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
        # Arrange
        name = "6512"

        # Act
        model = MODELS[name]

        # Assert
        self.assertEqual(
            (model.address_bits, model.pins, "clock" in model.summary),
            (16, ("irq", "nmi", "rdy"), True),
        )

    def test_the_one_that_reaches_less_wraps_where_its_pins_stop(self) -> None:
        # Arrange
        name = "6507"

        # Act
        model = MODELS[name]

        # Assert
        self.assertEqual((model.address_bits, model.address_mask), (13, 0x1FFF))

    def test_an_eight_bit_part_with_fewer_pins_reads_and_writes_through_them(self) -> None:
        # Arrange
        space = SparseMemory()
        space.write8(0x1234, 0x5A)
        cpu = MODELS["6507"].build(space)
        cpu.trace = []

        # Act
        cpu.write8(0xE010, cpu.read8(0xF234))

        # Assert
        self.assertEqual(
            (cpu.trace, space.read8(0x0010)),
            ([(0x1234, 0x5A, "read"), (0x0010, 0x5A, "write")], 0x5A),
        )


class PinTest(unittest.TestCase):
    def test_the_widest_part_brings_out_all_three(self) -> None:
        # Arrange
        name = "6502"

        # Act
        pins = MODELS[name].pins

        # Assert
        self.assertEqual(pins, ("irq", "nmi", "rdy"))

    def test_the_atari_part_brings_out_none_of_the_interrupt_lines(self) -> None:
        # Arrange
        name = "6507"

        # Act
        pins = MODELS[name].pins

        # Assert
        self.assertEqual(pins, ("rdy",))

    def test_and_refuses_both_of_them_rather_than_pretending(self) -> None:
        # Arrange
        cpu = part("6507")
        refused = []

        # Act
        for line in (cpu.irq, cpu.nmi):
            with self.assertRaises(NoSuchPin) as raised:
                line()
            refused.append(str(raised.exception))

        # Assert
        self.assertEqual(
            refused,
            [
                "the 6507 has no irq pin; it brings out rdy",
                "the 6507 has no nmi pin; it brings out rdy",
            ],
        )

    def test_the_error_says_what_the_package_does_bring_out(self) -> None:
        # Arrange
        cpu = part("6504")

        # Act
        with self.assertRaises(NoSuchPin) as raised:
            cpu.nmi()

        # Assert
        self.assertIn("it brings out irq", str(raised.exception))

    def test_a_part_with_the_request_line_still_takes_a_request(self) -> None:
        # Arrange
        cpu = part("6504")
        cpu.i = False

        # Act
        taken = cpu.irq()

        # Assert
        self.assertTrue(taken)

    def test_five_of_the_ten_nmos_packages_leave_the_non_maskable_line_off(self) -> None:
        # Arrange
        nmos = core_of("6502")

        # Act
        without = [
            model.name
            for model in MODELS.values()
            if core_of(model.name) is nmos and "nmi" not in model.pins
        ]

        # Assert
        self.assertEqual(without, ["6507", "6504", "6505", "6506", "6514", "6515"])

    def test_only_one_leaves_the_request_line_off_as_well(self) -> None:
        # Arrange
        nmos = core_of("6502")

        # Act
        without = [
            model.name
            for model in MODELS.values()
            if core_of(model.name) is nmos and "irq" not in model.pins
        ]

        # Assert
        self.assertEqual(without, ["6507"])

    def test_a_built_part_reports_the_pins_its_package_has(self) -> None:
        # Arrange
        names = ("6502", "6507", "65816")

        # Act
        found = {name: part(name).package_pins for name in names}

        # Assert
        self.assertEqual(
            found,
            {
                "6502": ("irq", "nmi", "rdy"),
                "6507": ("rdy",),
                "65816": ("irq", "nmi", "rdy"),
            },
        )

    def test_every_part_the_suites_cover_brings_out_all_three(self) -> None:
        # Arrange
        covered = ("6502", "2a03", "65c02", "r65c02", "w65c02", "65816")

        # Act
        found = {MODELS[name].pins for name in covered}

        # Assert
        self.assertEqual(found, {("irq", "nmi", "rdy")})


if __name__ == "__main__":
    unittest.main(verbosity=2)
