"""Holds the CMOS reserved opcodes to the length and timing the data sheet gives.

The NMOS parts leave these forty-four undefined, and some of them stop the part
until it is reset, so nothing can be asserted about them. The CMOS parts turned
every one into a no-operation of a stated length, which turns a row of a caveats
table into forty-four checkable claims.

Forty-three hold. The one that does not is 5C, where the data sheet and the
recorded cycles disagree about the count and no source states the addresses, so
it is recorded rather than guessed at.
"""

import json
import sys
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import Cpu, SparseMemory  # noqa: E402

HELD = json.loads((Path(__file__).resolve().parent / "cmos-reserved.json").read_text())

GROUPS = HELD["groups"]

START = 0x0200

CMOS = ("w65c02", "65c02", "r65c02")


def run(opcode: int, model: str = "w65c02") -> tuple[int, int]:
    """How many bytes an opcode consumes and how many cycles it spends."""
    space = SparseMemory()
    for offset, byte in enumerate((opcode, 0x11, 0x22, 0xEA)):
        space.write8(START + offset, byte)
    cpu = Cpu(space, model=model, reset=False)
    cpu.pc, cpu.s = START, 0x80
    cpu.set_status(0x24)
    cpu.trace = []
    cpu.step()
    return cpu.pc - START, len(cpu.trace)


def disputed() -> set[int]:
    return {0x5C}


class RecordTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.opcodes = [code for group in GROUPS for code in group["opcodes"]]

    def test_the_row_names_forty_four_opcodes(self) -> None:
        self.assertEqual(len(self.opcodes), 44)

    def test_none_of_them_twice(self) -> None:
        self.assertEqual(len(set(self.opcodes)), 44)

    def test_which_is_what_the_stated_opcode_count_leaves(self) -> None:
        self.assertEqual(256 - HELD["crossCheck"]["statedOpcodes"], len(self.opcodes))

    def test_and_what_the_opcode_matrix_leaves_blank(self) -> None:
        self.assertEqual(HELD["crossCheck"]["matrixBlanks"], len(self.opcodes))

    def test_the_reading_says_why_the_layout_alone_does_not_settle_it(self) -> None:
        self.assertIn("columns break", HELD["howTheListWasRead"])


class LengthTest(unittest.TestCase):
    """Every reserved opcode consumes the bytes the data sheet says it does."""

    def rows(self) -> list[tuple[str, int, int]]:
        return [
            (f"{code:02X}", run(code)[0], group["bytes"])
            for group in GROUPS
            for code in group["opcodes"]
        ]

    def test_every_one_of_the_forty_four(self) -> None:
        wrong = [code for code, took, printed in self.rows() if took != printed]

        self.assertEqual(wrong, [])

    def test_including_the_one_whose_timing_is_disputed(self) -> None:
        self.assertEqual(run(0x5C)[0], 3)


class TimingTest(unittest.TestCase):
    """Every reserved opcode spends the cycles the data sheet says it does."""

    def rows(self) -> list[tuple[str, int, int]]:
        return [
            (f"{code:02X}", run(code)[1], group["cycles"])
            for group in GROUPS
            for code in group["opcodes"]
            if code not in disputed()
        ]

    def test_forty_three_of_the_forty_four_agree(self) -> None:
        wrong = [code for code, took, printed in self.rows() if took != printed]

        self.assertEqual((wrong, len(self.rows())), ([], 43))

    def test_and_all_three_cmos_parts_agree_with_each_other(self) -> None:
        found = {
            model: [run(code, model)[1] for group in GROUPS for code in group["opcodes"]]
            for model in CMOS
        }

        self.assertEqual(len(set(map(tuple, found.values()))), 1)


class DisputedTest(unittest.TestCase):
    """5C, where the data sheet says eight cycles and every recording says four."""

    def entry(self) -> dict[str, Any]:
        return next(group for group in GROUPS if 0x5C in group["opcodes"])

    def test_the_data_sheet_says_eight(self) -> None:
        self.assertEqual(self.entry()["cycles"], 8)

    def test_the_part_as_modelled_here_takes_four(self) -> None:
        self.assertEqual(run(0x5C)[1], 4)

    def test_and_takes_four_on_every_cmos_part(self) -> None:
        self.assertEqual([run(0x5C, model)[1] for model in CMOS], [4, 4, 4])

    def test_the_four_it_takes_are_the_three_bytes_and_the_last_one_again(self) -> None:
        space = SparseMemory()
        for offset, byte in enumerate((0x5C, 0x11, 0x22, 0xEA)):
            space.write8(START + offset, byte)
        cpu = Cpu(space, model="w65c02", reset=False)
        cpu.pc, cpu.s = START, 0x80
        cpu.set_status(0x24)
        cpu.trace = []

        cpu.step()

        self.assertEqual(
            [address for address, _, _ in cpu.trace],
            [START, START + 1, START + 2, START + 2],
        )


if __name__ == "__main__":
    unittest.main()
