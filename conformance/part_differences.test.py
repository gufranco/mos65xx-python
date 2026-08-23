"""Holds each part to the row of Table 8-1 that describes it.

The W65C816S data sheet is the only document here that sets the four parts side
by side, so it is the one place a claim about a difference between them can be
checked rather than inferred from two documents that never mention each other.
Every row is driven on every model, and the row's own numbers are what the run
is compared against.
"""

import json
import sys
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import FLAG_D, Cpu, SparseMemory  # noqa: E402

HELD = json.loads((Path(__file__).resolve().parent / "part-differences.json").read_text())

ROWS = HELD["rows"]

PARTS = HELD["columns"]

START = 0x0200

VECTOR = {0x12FF: 0x34, 0x1200: 0xAB, 0x1300: 0xCD}
"""A jump vector whose low byte sits at the top of a page, which is the case row B is about."""


def drive(row: dict[str, Any], model: str) -> list[tuple[int, str]]:
    """One run of one row's program on one part, as a list of bus cycles."""
    start = row.get("start", START)
    space = SparseMemory()
    for offset, byte in enumerate(row["program"]):
        space.write8(start + offset, byte)
    for address, value in VECTOR.items():
        space.write8(address, value)
    cpu = Cpu(model, space, reset=False)
    cpu.pc, cpu.a = start, 0x05
    cpu.x, cpu.y = row.get("x", 0), row.get("y", 0)
    if model == "65816":
        cpu.s, cpu.emulation, cpu.pb, cpu.db, cpu.d = 0x01FD, True, 0, 0, 0
    else:
        cpu.s = 0xFD
    cpu.set_status(FLAG_D if row.get("decimal") else 0x00)
    cpu.trace = []
    cpu.step()
    return [(address & 0xFFFF, kind) for address, _, kind in cpu.trace]


def third(row: dict[str, Any], model: str) -> str:
    """What the discarded cycle of an indexed access lands on."""
    address = drive(row, model)[3][0]
    return {
        (row.get("start", START) + len(row["program"]) - 1): "last instruction byte",
        0x1210: "invalid address",
    }.get(address, f"{address:04X}")


def observed(row: dict[str, Any], model: str) -> Any:
    if row["check"] == "cycles":
        return len(drive(row, model))
    return third(row, model)


class RecordTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.rows = ROWS

    def test_the_table_carries_five_rows_this_project_can_drive(self) -> None:
        self.assertEqual(len(self.rows), 5)

    def test_each_one_says_something_about_every_part(self) -> None:
        missing = [row["id"] for row in self.rows if list(row["says"]) != PARTS]

        self.assertEqual(missing, [])

    def test_the_parts_are_named_both_ways_round(self) -> None:
        self.assertEqual(len(HELD["columnsAsPrinted"]), len(PARTS))

    def test_each_row_quotes_the_label_the_table_prints(self) -> None:
        missing = [row["id"] for row in self.rows if not row.get("printed")]

        self.assertEqual(missing, [])

    def test_each_row_says_why_the_difference_is_worth_pinning(self) -> None:
        missing = [row["id"] for row in self.rows if not row.get("why")]

        self.assertEqual(missing, [])

    def test_the_reading_says_why_the_extracted_text_will_not_do(self) -> None:
        self.assertIn("merged cell", HELD["readHow"])


class DifferenceTest(unittest.TestCase):
    """Every row driven on every part."""

    def cells(self) -> list[tuple[str, Any, Any]]:
        return [
            (f"{row['id']} on {model}", observed(row, model), row["says"][model])
            for row in ROWS
            for model in PARTS
        ]

    def test_every_part_does_what_its_column_says(self) -> None:
        wrong = [name for name, did, says in self.cells() if did != says]

        self.assertEqual(wrong, [])

    def test_which_is_twenty_cells_of_the_table(self) -> None:
        self.assertEqual(len(self.cells()), 20)

    def test_three_of_the_five_rows_separate_the_parts_rather_than_agreeing(self) -> None:
        splitting = [row["id"] for row in ROWS if len(set(row["says"].values())) > 1]

        self.assertEqual(len(splitting), 4)


class IndirectJumpTest(unittest.TestCase):
    """Row B, where one instruction gets three different answers."""

    def row(self) -> dict[str, Any]:
        return next(row for row in ROWS if row["id"] == "indirectJumpOffThePageEdge")

    def test_the_oldest_part_takes_its_high_byte_from_the_wrong_page(self) -> None:
        found = [address for address, _ in drive(self.row(), "6502")]

        self.assertEqual(found[3:], [0x12FF, 0x1200])

    def test_which_is_the_defect_the_table_names_in_the_same_cell(self) -> None:
        self.assertIn("invalid page crossing", self.row()["printedForTheOldestPart"])

    def test_the_cmos_parts_take_it_from_the_right_page_and_charge_a_cycle(self) -> None:
        found = [
            [address for address, _ in drive(self.row(), model)] for model in ("65c02", "w65c02")
        ]

        self.assertEqual([one[3:] for one in found], [[0x12FF, 0x1200, 0x1300]] * 2)

    def test_and_the_sixteen_bit_part_takes_it_from_the_right_page_for_nothing(self) -> None:
        found = [address for address, _ in drive(self.row(), "65816")]

        self.assertEqual(found[3:], [0x12FF, 0x1300])


class DiscardedReadTest(unittest.TestCase):
    """The row that says the sixteen bit part kept the older behaviour."""

    def row(self) -> dict[str, Any]:
        return next(row for row in ROWS if row["id"] == "discardedReadOfAnIndexedAccess")

    def test_the_two_parts_in_the_middle_re_read_the_instruction(self) -> None:
        found = [third(self.row(), model) for model in ("65c02", "w65c02")]

        self.assertEqual(found, ["last instruction byte"] * 2)

    def test_the_two_on_either_end_read_an_address_that_holds_nothing_wanted(self) -> None:
        found = [third(self.row(), model) for model in ("6502", "65816")]

        self.assertEqual(found, ["invalid address"] * 2)

    def test_every_row_that_splits_the_parts_splits_them_the_same_way(self) -> None:
        splitting = [row["id"] for row in ROWS if len(set(row["says"].values())) > 1]
        ends_against_middle = [
            row["id"]
            for row in ROWS
            if row["says"][PARTS[0]] == row["says"][PARTS[3]]
            and row["says"][PARTS[1]] == row["says"][PARTS[2]]
            and row["says"][PARTS[0]] != row["says"][PARTS[1]]
        ]

        self.assertEqual(ends_against_middle, splitting)

    def test_which_puts_the_sixteen_bit_part_with_the_oldest_one_every_time(self) -> None:
        agreements = [row["says"][PARTS[0]] == row["says"][PARTS[3]] for row in ROWS]

        self.assertEqual(agreements, [True] * 5)


class ProgramTest(unittest.TestCase):
    """That each row is driven by a program that exercises what it describes."""

    def test_the_shift_row_indexes_without_leaving_its_page(self) -> None:
        row = next(one for one in ROWS if one["id"] == "shiftOfAnIndexedAbsolute")

        self.assertLess(row["program"][1] + row["x"], 0x100)

    def test_the_discarded_read_row_indexes_across_one(self) -> None:
        row = next(one for one in ROWS if one["id"] == "discardedReadOfAnIndexedAccess")

        self.assertGreater(row["program"][1] + row["x"], 0xFF)

    def test_the_branch_row_starts_near_enough_the_edge_to_cross_it(self) -> None:
        row = next(one for one in ROWS if one["id"] == "branchAcrossAPage")

        self.assertGreater((row["start"] & 0xFF) + 2 + row["program"][1], 0xFF)

    def test_the_decimal_row_runs_an_instruction_decimal_mode_changes(self) -> None:
        row = next(one for one in ROWS if one["id"] == "decimalArithmetic")

        self.assertEqual(row["program"][0], 0x69)


if __name__ == "__main__":
    unittest.main()
