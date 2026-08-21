"""Holds the opcode table, the cycle counts and the flag rules to Appendix B.

The Programming Manual gives every instruction its own page: the flags it
touches, and per addressing mode the opcode, the byte count and the cycle count.
That is a hundred and fifty-one opcodes stated by the manufacturer, which makes
it a check on the table this project decodes with and on the timing it runs at,
neither of which needs a suite on the machine to verify.

Two rows are misprinted. Their instructions are run in the page-crossing case
anyway, and the extra cycle the part takes is asserted rather than the page.
"""

import json
import random
import sys
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import SparseMemory, opcodes6502  # noqa: E402
from mos65xx import mos6502 as core  # noqa: E402

HELD = json.loads((Path(__file__).resolve().parent / "instruction-set.json").read_text())

INSTRUCTIONS = HELD["instructions"]

FLAGS = {
    "N": core.FLAG_N,
    "Z": core.FLAG_Z,
    "C": core.FLAG_C,
    "I": core.FLAG_I,
    "D": core.FLAG_D,
    "V": core.FLAG_V,
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
"""The manual's name for each addressing mode beside the table's own."""

START = 0x0200

NEAR_THE_EDGE = 0x02F0
"""Where a branch has to sit for a forward offset to leave the page."""

SEEDS = 24
"""How many states each flag rule is tried against."""

POINTER = 0x10

BASE = 0x12


def operand(mode: str, crossing: bool) -> tuple[int, ...]:
    """The bytes that follow the opcode, chosen to cross a page or not."""
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


def machine(opcode: int, mode: str, crossing: bool, seed: int) -> core.Cpu:
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
    cpu = core.Cpu(space, reset=False)
    cpu.pc, cpu.s = start, 0x80
    cpu.a, cpu.x, cpu.y = generator.randrange(256), 0x20, 0x20
    cpu.set_status(generator.randrange(256))
    return cpu


def spent(opcode: int, mode: str, crossing: bool) -> int:
    """How many bus cycles one run of an instruction takes."""
    cpu = machine(opcode, mode, crossing, seed=1)
    cpu.trace = []
    cpu.step()
    return len(cpu.trace)


def branch_always(opcode: int) -> int:
    """A status byte under which the named branch is taken."""
    taken = {
        0x90: 0x00,
        0xB0: core.FLAG_C,
        0xF0: core.FLAG_Z,
        0x30: core.FLAG_N,
        0xD0: 0x00,
        0x10: 0x00,
        0x50: 0x00,
        0x70: core.FLAG_V,
    }
    return taken[opcode]


def branch_cycles(opcode: int, crossing: bool, taken: bool) -> int:
    cpu = machine(opcode, "relative", crossing, seed=1)
    cpu.set_status(branch_always(opcode) if taken else ~branch_always(opcode) & 0xFF)
    cpu.trace = []
    cpu.step()
    return len(cpu.trace)


class RecordTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.instructions = INSTRUCTIONS

    def test_the_appendix_gives_a_page_to_every_documented_instruction(self) -> None:
        self.assertEqual(len(self.instructions), 56)

    def test_which_between_them_name_a_hundred_and_fifty_one_opcodes(self) -> None:
        found = [mode["opcode"] for held in self.instructions.values() for mode in held["modes"]]

        self.assertEqual((len(found), len(set(found))), (151, 151))

    def test_every_flag_row_has_one_entry_for_each_of_the_six(self) -> None:
        wrong = [
            name
            for name, held in self.instructions.items()
            if list(held["flags"]) != list("NZCIDV")
        ]

        self.assertEqual(wrong, [])

    def test_every_entry_is_a_notation_the_appendix_defines(self) -> None:
        used = {value for held in self.instructions.values() for value in held["flags"].values()}

        self.assertLessEqual(used, set(HELD["notation"]))

    def test_every_mode_is_one_the_table_also_names(self) -> None:
        used = {mode["mode"] for held in self.instructions.values() for mode in held["modes"]}

        self.assertLessEqual(used, set(NAMED))

    def test_the_two_misprinted_rows_are_recorded(self) -> None:
        self.assertEqual(HELD["misprints"]["missingPageCrossingMark"], ["AND", "ORA"])


class OpcodeTest(unittest.TestCase):
    """Every opcode the appendix prints, against the table this project decodes with."""

    def rows(self) -> list[tuple[str, str, str]]:
        found = []
        for name, held in INSTRUCTIONS.items():
            for mode in held["modes"]:
                printed = f"{name.lower()} {NAMED[mode['mode']]} {mode['bytes']}"
                decoded = opcodes6502.NMOS[mode["opcode"]]
                size = opcodes6502.MODE_SIZE[decoded[1]] + 1
                found.append(
                    (f"{mode['opcode']:02X}", printed, f"{decoded[0]} {decoded[1]} {size}")
                )
        return found

    def test_the_table_decodes_every_one_as_the_appendix_prints_it(self) -> None:
        wrong = [code for code, printed, decoded in self.rows() if printed != decoded]

        self.assertEqual(wrong, [])

    def test_which_is_every_documented_opcode(self) -> None:
        self.assertEqual(len(self.rows()), 151)

    def test_and_the_table_carries_more_than_the_appendix_does(self) -> None:
        documented = {mode["opcode"] for held in INSTRUCTIONS.values() for mode in held["modes"]}

        self.assertEqual(len(set(range(256)) - documented), 256 - 151)


class CycleTest(unittest.TestCase):
    """Every cycle count the appendix prints, against a run of the instruction."""

    def rows(self) -> list[tuple[str, int, int]]:
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

    def test_every_instruction_takes_the_cycles_the_appendix_prints(self) -> None:
        wrong = [name for name, took, printed in self.rows() if took != printed]

        self.assertEqual(wrong, [])

    def test_which_is_every_row_but_the_branches(self) -> None:
        self.assertEqual(len(self.rows()), 151 - 8)

    def test_a_page_crossing_adds_one_wherever_the_appendix_marks_it(self) -> None:
        marked = [
            (name, mode)
            for name, held in INSTRUCTIONS.items()
            for mode in held["modes"]
            if mode.get("addOneWhenCrossing") and mode["mode"] != "relative"
        ]
        wrong = [
            f"{name} {mode['mode']}"
            for name, mode in marked
            if spent(mode["opcode"], mode["mode"], True) != mode["cycles"] + 1
        ]

        self.assertEqual((wrong, len(marked)), ([], 21))


class MisprintTest(unittest.TestCase):
    """The two indirect indexed rows printed without the page-crossing mark."""

    def rows(self) -> list[dict[str, Any]]:
        return [
            mode
            for name in HELD["misprints"]["missingPageCrossingMark"]
            for mode in INSTRUCTIONS[name]["modes"]
            if mode["mode"] == "(indirect),Y"
        ]

    def test_neither_row_carries_the_mark(self) -> None:
        self.assertEqual([mode.get("addOneWhenCrossing") for mode in self.rows()], [None, None])

    def test_but_both_take_the_extra_cycle_anyway(self) -> None:
        found = [spent(mode["opcode"], mode["mode"], True) for mode in self.rows()]

        self.assertEqual(found, [6, 6])

    def test_and_the_ones_that_do_carry_it_take_the_same_six(self) -> None:
        found = [
            spent(mode["opcode"], "(indirect),Y", True)
            for name in HELD["misprints"]["carryIt"]
            for mode in INSTRUCTIONS[name]["modes"]
            if mode["mode"] == "(indirect),Y"
        ]

        self.assertEqual(found, [6] * 5)

    def test_the_same_two_do_carry_the_mark_on_their_absolute_rows(self) -> None:
        found = [
            mode.get("addOneWhenCrossing")
            for name in HELD["misprints"]["missingPageCrossingMark"]
            for mode in INSTRUCTIONS[name]["modes"]
            if mode["mode"] in ("absolute,X", "absolute,Y")
        ]

        self.assertEqual(found, [True] * 4)


class BranchCycleTest(unittest.TestCase):
    """The branch rows, whose count depends on whether the branch is taken."""

    def branches(self) -> list[dict[str, Any]]:
        return [
            mode
            for held in INSTRUCTIONS.values()
            for mode in held["modes"]
            if mode["mode"] == "relative"
        ]

    def test_a_branch_not_taken_takes_the_two_the_appendix_prints(self) -> None:
        found = [branch_cycles(mode["opcode"], False, taken=False) for mode in self.branches()]

        self.assertEqual(found, [2] * 8)

    def test_one_taken_inside_a_page_adds_the_one_the_footnote_names(self) -> None:
        found = [branch_cycles(mode["opcode"], False, taken=True) for mode in self.branches()]

        self.assertEqual(found, [3] * 8)

    def test_and_one_crossing_a_page_adds_the_two(self) -> None:
        found = [branch_cycles(mode["opcode"], True, taken=True) for mode in self.branches()]

        self.assertEqual(found, [4] * 8)


class FlagTest(unittest.TestCase):
    """Every flag rule the appendix prints, tried against twenty-four states."""

    def either_side(self, name: str, seed: int) -> tuple[int, int]:
        """The status byte before and after one run of an instruction."""
        mode = INSTRUCTIONS[name]["modes"][0]
        cpu = machine(mode["opcode"], mode["mode"], False, seed)
        before = cpu.status()
        cpu.step()
        return before, cpu.status()

    def kept(self, rule: str, before: int, after: int, mask: int) -> bool:
        """Whether one run kept the promise the appendix printed for one flag."""
        return {
            "unchanged": (before & mask) == (after & mask),
            "0": not after & mask,
            "1": bool(after & mask),
        }[rule]

    def holds(self, name: str, flag: str, rule: str) -> bool:
        mask = FLAGS[flag]
        return all(self.kept(rule, *self.either_side(name, seed), mask) for seed in range(SEEDS))

    def broken(self) -> list[str]:
        return [
            f"{name} {flag}"
            for name, held in INSTRUCTIONS.items()
            for flag, rule in held["flags"].items()
            if rule in ("unchanged", "0", "1") and not self.holds(name, flag, rule)
        ]

    def test_every_absolute_the_appendix_prints_holds(self) -> None:
        self.assertEqual(self.broken(), [])

    def test_which_is_two_hundred_and_fifty_seven_rules(self) -> None:
        absolute = [
            rule
            for held in INSTRUCTIONS.values()
            for rule in held["flags"].values()
            if rule in ("unchanged", "0", "1")
        ]

        self.assertEqual(len(absolute), 257)

    def test_the_flags_it_says_change_are_not_claimed_to_hold_still(self) -> None:
        changing = {
            rule
            for held in INSTRUCTIONS.values()
            for rule in held["flags"].values()
            if rule not in ("unchanged", "0", "1")
        }

        self.assertEqual(changing, {"changes", "from stack", "bit 7 of memory", "bit 6 of memory"})


if __name__ == "__main__":
    unittest.main()
