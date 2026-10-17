import json
import random
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mos65xx  # noqa: E402
from mos65xx import SparseMemory, decode8  # noqa: E402

HELD = json.loads((Path(__file__).resolve().parent / "instruction-set.json").read_text())

INSTRUCTIONS = HELD["instructions"]

FLAGS = {
    "N": mos65xx.FLAG_N,
    "Z": mos65xx.FLAG_Z,
    "C": mos65xx.FLAG_C,
    "I": mos65xx.FLAG_I,
    "D": mos65xx.FLAG_D,
    "V": mos65xx.FLAG_V,
}

NAMED = {
    "immediate": "immediate",
    "zero page": "zeroPage",
    "zero page,X": "zeroPageX",
    "zero page,Y": "zeroPageY",
    "absolute": "absolute",
    "absolute,X": "absoluteX",
    "absolute,Y": "absoluteY",
    "(indirect,X)": "indexedIndirectX",
    "(indirect),Y": "indirectIndexedY",
    "relative": "relative",
    "implied": "implied",
    "accumulator": "accumulator",
    "indirect": "indirect",
}

START = 0x0200

NEAR_THE_EDGE = 0x02F0

SEEDS = 24

POINTER = 0x10

BASE = 0x12


def operand(mode: str, crossing: bool) -> tuple[int, ...]:
    low = 0xF0 if crossing else 0x10
    if mode in ("implied", "accumulator"):
        return ()
    if mode in (
        "zero page",
        "zero page,X",
        "zero page,Y",
        "immediate",
        "(indirect,X)",
        "(indirect),Y",
    ):
        return (POINTER,)
    if mode == "relative":
        return (0x7F if crossing else 0x10,)
    return (low, BASE)


def machine(opcode: int, mode: str, crossing: bool, seed: int) -> Any:
    generator = random.Random(seed)
    space = SparseMemory()
    program = (opcode, *operand(mode, crossing))
    start = NEAR_THE_EDGE if mode == "relative" and crossing else START
    for offset, byte in enumerate(program):
        space.write8(start + offset, byte)
    space.write8(POINTER, 0xF0 if crossing else 0x10)
    space.write8(POINTER + 1, BASE)
    for address in range(0x1200, 0x1400):
        space.write8(address, generator.randrange(256))
    cpu = mos65xx.Cpu("6502", space)
    cpu.pc, cpu.s = start, 0x80
    cpu.a, cpu.x, cpu.y = generator.randrange(256), 0x20, 0x20
    cpu.set_status(generator.randrange(256))
    return cpu


def spent(opcode: int, mode: str, crossing: bool) -> int:
    cpu = machine(opcode, mode, crossing, seed=1)
    cpu.trace = []
    cpu.step()
    return len(cpu.trace)


def branch_always(opcode: int) -> int:
    taken = {
        0x90: 0x00,
        0xB0: mos65xx.FLAG_C,
        0xF0: mos65xx.FLAG_Z,
        0x30: mos65xx.FLAG_N,
        0xD0: 0x00,
        0x10: 0x00,
        0x50: 0x00,
        0x70: mos65xx.FLAG_V,
    }
    return taken[opcode]


def branch_cycles(opcode: int, crossing: bool, taken: bool) -> int:
    cpu = machine(opcode, "relative", crossing, seed=1)
    cpu.set_status(branch_always(opcode) if taken else ~branch_always(opcode) & 0xFF)
    cpu.trace = []
    cpu.step()
    return len(cpu.trace)


class RecordTest(unittest.TestCase):
    def test_the_appendix_gives_a_page_to_every_documented_instruction(self) -> None:
        # Arrange
        held = INSTRUCTIONS

        # Act
        pages = len(held)

        # Assert
        self.assertEqual(pages, 56)

    def test_which_between_them_name_a_hundred_and_fifty_one_opcodes(self) -> None:
        # Arrange
        held = INSTRUCTIONS

        # Act
        found = [mode["opcode"] for one in held.values() for mode in one["modes"]]

        # Assert
        self.assertEqual((len(found), len(set(found))), (151, 151))

    def test_every_flag_row_has_one_entry_for_each_of_the_six(self) -> None:
        # Arrange
        held = INSTRUCTIONS

        # Act
        wrong = [name for name, one in held.items() if list(one["flags"]) != list("NZCIDV")]

        # Assert
        self.assertEqual(wrong, [])

    def test_every_entry_is_a_notation_the_appendix_defines(self) -> None:
        # Arrange
        held = INSTRUCTIONS

        # Act
        used = {value for one in held.values() for value in one["flags"].values()}

        # Assert
        self.assertLessEqual(used, set(HELD["notation"]))

    def test_every_mode_is_one_the_table_also_names(self) -> None:
        # Arrange
        held = INSTRUCTIONS

        # Act
        used = {mode["mode"] for one in held.values() for mode in one["modes"]}

        # Assert
        self.assertLessEqual(used, set(NAMED))

    def test_the_two_misprinted_rows_are_recorded(self) -> None:
        # Arrange
        misprints = HELD["misprints"]

        # Act
        rows = misprints["missingPageCrossingMark"]

        # Assert
        self.assertEqual(rows, ["AND", "ORA"])


def decoded_rows() -> list[tuple[str, str, str]]:
    found = []
    for name, held in INSTRUCTIONS.items():
        for mode in held["modes"]:
            printed = f"{name.lower()} {NAMED[mode['mode']]} {mode['bytes']}"
            one = decode8(bytes([mode["opcode"], 0x00, 0x00]), 0, START)
            found.append(
                (f"{mode['opcode']:02X}", printed, f"{one.mnemonic} {one.mode} {one.size}")
            )
    return found


class OpcodeTest(unittest.TestCase):
    def test_the_table_decodes_every_one_as_the_appendix_prints_it(self) -> None:
        # Arrange
        rows = decoded_rows()

        # Act
        wrong = [code for code, printed, decoded in rows if printed != decoded]

        # Assert
        self.assertEqual(wrong, [])

    def test_which_is_every_documented_opcode(self) -> None:
        # Arrange
        held = INSTRUCTIONS

        # Act
        rows = decoded_rows()

        # Assert
        self.assertEqual(len(rows), sum(len(one["modes"]) for one in held.values()))

    def test_and_the_table_carries_more_than_the_appendix_does(self) -> None:
        # Arrange
        documented = {mode["opcode"] for held in INSTRUCTIONS.values() for mode in held["modes"]}

        # Act
        beyond = set(range(256)) - documented

        # Assert
        self.assertEqual(len(beyond), 256 - 151)


def cycle_rows() -> list[tuple[str, int, int]]:
    found = []
    for name, held in INSTRUCTIONS.items():
        for mode in held["modes"]:
            if mode["mode"] == "relative":
                continue
            printed = mode["cycles"]
            found.append(
                (f"{name} {mode['mode']}", spent(mode["opcode"], mode["mode"], False), printed)
            )
    return found


class CycleTest(unittest.TestCase):
    def test_every_instruction_takes_the_cycles_the_appendix_prints(self) -> None:
        # Arrange
        rows = cycle_rows()

        # Act
        wrong = [name for name, took, printed in rows if took != printed]

        # Assert
        self.assertEqual(wrong, [])

    def test_which_is_every_row_but_the_branches(self) -> None:
        # Arrange
        branches = 8

        # Act
        rows = cycle_rows()

        # Assert
        self.assertEqual(len(rows), 151 - branches)

    def test_a_page_crossing_adds_one_wherever_the_appendix_marks_it(self) -> None:
        # Arrange
        marked = [
            (name, mode)
            for name, held in INSTRUCTIONS.items()
            for mode in held["modes"]
            if mode.get("addOneWhenCrossing") and mode["mode"] != "relative"
        ]

        # Act
        wrong = [
            f"{name} {mode['mode']}"
            for name, mode in marked
            if spent(mode["opcode"], mode["mode"], True) != mode["cycles"] + 1
        ]

        # Assert
        self.assertEqual((wrong, len(marked)), ([], 21))


def misprinted_rows() -> list[dict[str, Any]]:
    return [
        mode
        for name in HELD["misprints"]["missingPageCrossingMark"]
        for mode in INSTRUCTIONS[name]["modes"]
        if mode["mode"] == "(indirect),Y"
    ]


class MisprintTest(unittest.TestCase):
    def test_neither_row_carries_the_mark(self) -> None:
        # Arrange
        rows = misprinted_rows()

        # Act
        marks = [mode.get("addOneWhenCrossing") for mode in rows]

        # Assert
        self.assertEqual(marks, [None, None])

    def test_but_both_take_the_extra_cycle_anyway(self) -> None:
        # Arrange
        rows = misprinted_rows()

        # Act
        found = [spent(mode["opcode"], mode["mode"], True) for mode in rows]

        # Assert
        self.assertEqual(found, [6, 6])

    def test_and_the_ones_that_do_carry_it_take_the_same_six(self) -> None:
        # Arrange
        rows = [
            mode
            for name in HELD["misprints"]["carryIt"]
            for mode in INSTRUCTIONS[name]["modes"]
            if mode["mode"] == "(indirect),Y"
        ]

        # Act
        found = [spent(mode["opcode"], "(indirect),Y", True) for mode in rows]

        # Assert
        self.assertEqual(found, [6] * 5)

    def test_the_same_two_do_carry_the_mark_on_their_absolute_rows(self) -> None:
        # Arrange
        names = HELD["misprints"]["missingPageCrossingMark"]

        # Act
        found = [
            mode.get("addOneWhenCrossing")
            for name in names
            for mode in INSTRUCTIONS[name]["modes"]
            if mode["mode"] in ("absolute,X", "absolute,Y")
        ]

        # Assert
        self.assertEqual(found, [True] * 4)


def branch_rows() -> list[dict[str, Any]]:
    return [
        mode
        for held in INSTRUCTIONS.values()
        for mode in held["modes"]
        if mode["mode"] == "relative"
    ]


class BranchCycleTest(unittest.TestCase):
    def test_a_branch_not_taken_takes_the_two_the_appendix_prints(self) -> None:
        # Arrange
        rows = branch_rows()

        # Act
        found = [branch_cycles(mode["opcode"], False, taken=False) for mode in rows]

        # Assert
        self.assertEqual(found, [2] * 8)

    def test_one_taken_inside_a_page_adds_the_one_the_footnote_names(self) -> None:
        # Arrange
        rows = branch_rows()

        # Act
        found = [branch_cycles(mode["opcode"], False, taken=True) for mode in rows]

        # Assert
        self.assertEqual(found, [3] * 8)

    def test_and_one_crossing_a_page_adds_the_two(self) -> None:
        # Arrange
        rows = branch_rows()

        # Act
        found = [branch_cycles(mode["opcode"], True, taken=True) for mode in rows]

        # Assert
        self.assertEqual(found, [4] * 8)


def either_side(name: str, seed: int) -> tuple[int, int]:
    mode = INSTRUCTIONS[name]["modes"][0]
    cpu = machine(mode["opcode"], mode["mode"], False, seed)
    before = cpu.status()
    cpu.step()
    return before, cpu.status()


def kept(rule: str, before: int, after: int, mask: int) -> bool:
    return {
        "unchanged": (before & mask) == (after & mask),
        "0": not after & mask,
        "1": bool(after & mask),
    }[rule]


def holds(name: str, flag: str, rule: str) -> bool:
    mask = FLAGS[flag]
    return all(kept(rule, *either_side(name, seed), mask) for seed in range(SEEDS))


class FlagTest(unittest.TestCase):
    def test_every_absolute_the_appendix_prints_holds(self) -> None:
        # Arrange
        rules = [
            (name, flag, rule)
            for name, held in INSTRUCTIONS.items()
            for flag, rule in held["flags"].items()
            if rule in ("unchanged", "0", "1")
        ]

        # Act
        broken = [f"{name} {flag}" for name, flag, rule in rules if not holds(name, flag, rule)]

        # Assert
        self.assertEqual(broken, [])

    def test_which_is_two_hundred_and_fifty_seven_rules(self) -> None:
        # Arrange
        held = INSTRUCTIONS

        # Act
        absolute = [
            rule
            for one in held.values()
            for rule in one["flags"].values()
            if rule in ("unchanged", "0", "1")
        ]

        # Assert
        self.assertEqual(len(absolute), 257)

    def test_the_flags_it_says_change_are_not_claimed_to_hold_still(self) -> None:
        # Arrange
        held = INSTRUCTIONS

        # Act
        changing = {
            rule
            for one in held.values()
            for rule in one["flags"].values()
            if rule not in ("unchanged", "0", "1")
        }

        # Assert
        self.assertEqual(changing, {"changes", "from stack", "bit 7 of memory", "bit 6 of memory"})


class ReadmeCountTest(unittest.TestCase):
    def test_the_readme_reports_the_split_the_appendix_gives(self) -> None:
        # Arrange
        record = json.loads((ROOT / "conformance" / "instruction-set.json").read_text())
        readme = (ROOT / "README.md").read_text()
        stated = ("hundred and fifty one", "hundred and five")

        # Act
        documented = sum(len(one["modes"]) for one in record["instructions"].values())

        # Assert
        self.assertEqual(
            (documented, 256 - documented, all(word in readme for word in stated)),
            (151, 105, True),
        )


if __name__ == "__main__":
    unittest.main()
