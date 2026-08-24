"""Holds the sixteen bit part's bus to Table 6-7 of its data sheet.

The table prints all eight output lines for every cycle of every addressing
mode. Nothing else here states that at rung one, so without it the 65816's
timing rests entirely on a recording. Each group is driven with one
representative instruction and the table's own address expressions are resolved
against that run, so a row that stops matching names the page it came from.

Rows whose cycle label carries a letter are the conditional ones the notes add,
for a sixteen bit register, a direct register with a low byte, an index that
crosses a page. The runs below take the base path, so those rows are expected to
be absent and their absence is checked rather than assumed.
"""

import json
import sys
import unittest
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import Memory  # noqa: E402
from mos65xx import wdc65816 as core  # noqa: E402

HELD = json.loads((Path(__file__).resolve().parent / "bus-operation.json").read_text())

GROUPS = {group["id"]: group for group in HELD["groups"]}

START = 0x000200

HALTS = ("19c", "19d")
"""Stop the clock and wait for an interrupt, which never finish a step."""

BY_PIN = ("22a",)
"""The hardware interrupts, which a pin drives rather than an opcode."""


class Scene:
    """One run of one group, with the quantities the table's expressions name."""

    def __init__(self, group: str, program: tuple[int, ...], **named: Any) -> None:
        self.group = group
        self.program = program
        self.seed: dict[int, int] = named.pop("seed", {})
        self.named = named

    def run(self) -> tuple[list[tuple[int | None, int | None, str]], dict[str, int]]:
        memory = Memory(0x1000000)
        for offset, byte in enumerate(self.program):
            memory.write8(START + offset, byte)
        for address, value in self.seed.items():
            memory.write8(address, value)
        cpu = core.Cpu(memory)
        cpu.emulation = False
        cpu.m8 = cpu.x8 = True
        cpu.pb, cpu.pc = 0x00, START & 0xFFFF
        cpu.db, cpu.d = self.named.get("DBR", 0x00), self.named.get("D", 0x0000)
        cpu.s = self.named.get("S", 0x01F0)
        cpu.x, cpu.y = self.named.get("X", 0x00), self.named.get("Y", 0x00)
        cpu.a = self.named.get("A", 0x5A)
        cpu.set_status(self.named.get("P", 0x00) | (core.FLAG_M | core.FLAG_X))
        cpu.trace = []
        cpu.step()
        values = dict(self.named)
        values.setdefault("PBR", 0x00)
        values.setdefault("DBR", 0x00)
        values.setdefault("D", 0x0000)
        values.setdefault("S", 0x01F0)
        values.setdefault("X", 0x00)
        values.setdefault("Y", 0x00)
        values["PC"] = START & 0xFFFF
        values["NewPC"] = cpu.pc
        values["NewPBR"] = cpu.pb
        return list(cpu.trace), values


def bank(name: str, values: Mapping[str, int]) -> int:
    return {
        "0": 0,
        "PBR": values["PBR"],
        "DBR": values["DBR"],
        "AAB": values.get("AAB", 0),
        "DBA": values.get("DBA", 0),
        "SBA": values.get("SBA", 0),
        "New PBR": values["NewPBR"],
    }[name] << 16


def offsets() -> dict[str, Callable[[Mapping[str, int]], int]]:
    """Every offset expression the table prints, one function each."""
    return {
        "PC": lambda v: v["PC"],
        "PC+1": lambda v: v["PC"] + 1,
        "PC+2": lambda v: v["PC"] + 2,
        "PC+3": lambda v: v["PC"] + 3,
        "PC+Offset": lambda v: (v["PC"] + 2 + v["Offset"]) & 0xFFFF,
        "New PC": lambda v: v["NewPC"],
        "AA": lambda v: v["AA"],
        "AA+1": lambda v: v["AA"] + 1,
        "AA+2": lambda v: v["AA"] + 2,
        "AA+X": lambda v: (v["AA"] + v["X"]) & 0xFFFF,
        "AA+X+1": lambda v: (v["AA"] + v["X"] + 1) & 0xFFFF,
        "AA+Y": lambda v: (v["AA"] + v["Y"]) & 0xFFFF,
        "AA+Y+1": lambda v: (v["AA"] + v["Y"] + 1) & 0xFFFF,
        "AAH,AAL+XL": lambda v: (v["AA"] & 0xFF00) | ((v["AA"] + v["X"]) & 0xFF),
        "AAH,AAL+YL": lambda v: (v["AA"] & 0xFF00) | ((v["AA"] + v["Y"]) & 0xFF),
        "AA+X+2": lambda v: (v["AA"] + v["X"] + 2) & 0xFFFF,
        "AAV": lambda v: v["AAV"],
        "VA": lambda v: v["VA"],
        "VA+1": lambda v: v["VA"] + 1,
        "D+DO": lambda v: (v["D"] + v["DO"]) & 0xFFFF,
        "D+DO+1": lambda v: (v["D"] + v["DO"] + 1) & 0xFFFF,
        "D+DO+2": lambda v: (v["D"] + v["DO"] + 2) & 0xFFFF,
        "D+DO+X": lambda v: (v["D"] + v["DO"] + v["X"]) & 0xFFFF,
        "D+DO+X+1": lambda v: (v["D"] + v["DO"] + v["X"] + 1) & 0xFFFF,
        "D+DO+Y": lambda v: (v["D"] + v["DO"] + v["Y"]) & 0xFFFF,
        "D+DO+Y+1": lambda v: (v["D"] + v["DO"] + v["Y"] + 1) & 0xFFFF,
        "S": lambda v: v["S"],
        "S+1": lambda v: v["S"] + 1,
        "S+2": lambda v: v["S"] + 2,
        "S+3": lambda v: v["S"] + 3,
        "S+4": lambda v: v["S"] + 4,
        "S-1": lambda v: v["S"] - 1,
        "S-2": lambda v: v["S"] - 2,
        "S-3": lambda v: v["S"] - 3,
        "S+SO": lambda v: (v["S"] + v["SO"]) & 0xFFFF,
        "S+SO+1": lambda v: (v["S"] + v["SO"] + 1) & 0xFFFF,
        "X": lambda v: v["X"],
        "X+1": lambda v: v["X"] + 1,
        "X+2": lambda v: v["X"] + 2,
        "X-1": lambda v: v["X"] - 1,
        "X-2": lambda v: v["X"] - 2,
        "Y": lambda v: v["Y"],
        "Y+1": lambda v: v["Y"] + 1,
        "Y+2": lambda v: v["Y"] + 2,
        "Y-1": lambda v: v["Y"] - 1,
        "Y-2": lambda v: v["Y"] - 2,
    }


def resolve(printed: str, values: Mapping[str, int]) -> int:
    """One of the table's address cells, as a full twenty-four bit address.

    Two cells name the bank and both halves of the offset, DBR,AAH,AAL+XL, so
    the split is on the first comma only and the rest is one expression.
    """
    head, _, tail = printed.partition(",")
    return (bank(head, values) | offsets()[tail](values)) & 0xFFFFFF


def base(group: str) -> list[dict[str, Any]]:
    """The rows a run in the configuration below should produce.

    Eight bit registers, a direct register with no low byte, no index crossing a
    page and no branch taken, which is the one configuration where every note
    the table carries is inactive. That matters because the Note column is a
    merged cell whose row alignment the extracted text cannot recover, so any
    configuration that switched a note on would be relying on a guess about
    which row the note belongs to. Here every lettered row is off, and a lettered
    row is exactly a row the notes add.

    The block moves print three consecutive executions of one instruction; one
    step runs the first.
    """
    rows = [
        row
        for row in GROUPS[group]["bus"]
        if not row.get("isNextOpcodeFetch") and row["cycle"].isdigit()
    ]
    return rows[:7] if group in ("9a", "9b") else rows


def pins(row: Mapping[str, Any]) -> tuple[int, int, int, int]:
    return row["vda"], row["vpa"], row["vpb"], row["mlb"]


def observed(pin: str) -> tuple[int, int, int, int]:
    return (
        1 if pin[0] == "d" else 0,
        1 if pin[1] == "p" else 0,
        0 if pin[2] == "v" else 1,
        0 if pin[7] == "l" else 1,
    )


POINTER = 0x0010

TARGET = 0x1234


def scenes() -> list[Scene]:
    """One run per group, with the quantities its rows name."""
    vector = {TARGET: 0x78, TARGET + 1: 0x56, TARGET + 2: 0x7E}
    direct = {POINTER: 0x34, POINTER + 1: 0x12, POINTER + 2: 0x7E}
    stack = {0x01F1: 0x24, 0x01F2: 0x34, 0x01F3: 0x12, 0x01F4: 0x7E}
    return [
        Scene("1a", (0xAD, 0x34, 0x12), AA=TARGET),
        Scene("1b", (0x4C, 0x34, 0x12), AA=TARGET),
        Scene("1c", (0x20, 0x34, 0x12), AA=TARGET),
        Scene("1d", (0x0E, 0x34, 0x12), AA=TARGET),
        Scene("2a", (0x7C, 0x34, 0x12), AA=TARGET, X=0x02, seed=vector),
        Scene("2b", (0xFC, 0x34, 0x12), AA=TARGET, X=0x02, seed=vector),
        Scene("3a", (0xDC, 0x34, 0x12), AA=TARGET, seed=vector),
        Scene("3b", (0x6C, 0x34, 0x12), AA=TARGET, seed=vector),
        Scene("4a", (0xAF, 0x34, 0x12, 0x7E), AA=TARGET, AAB=0x7E),
        Scene("4b", (0x5C, 0x34, 0x12, 0x7E), AA=TARGET, AAB=0x7E),
        Scene("4c", (0x22, 0x34, 0x12, 0x7E), AA=TARGET, AAB=0x7E),
        Scene("5", (0xBF, 0x34, 0x12, 0x7E), AA=TARGET, AAB=0x7E, X=0x02),
        Scene("6a", (0xBD, 0x34, 0x12), AA=TARGET, X=0x02),
        Scene("6b", (0x1E, 0x34, 0x12), AA=TARGET, X=0x02),
        Scene("7", (0xB9, 0x34, 0x12), AA=TARGET, Y=0x02),
        Scene("8", (0x0A,)),
        Scene("10a", (0xA5, 0x10), DO=POINTER),
        Scene("10b", (0x06, 0x10), DO=POINTER),
        Scene(
            "11",
            (0xA1, 0x10),
            DO=POINTER,
            X=0x02,
            seed={POINTER + 2: 0x34, POINTER + 3: 0x12},
            AA=TARGET,
        ),
        Scene("12", (0xB2, 0x10), DO=POINTER, seed=direct, AA=TARGET),
        Scene("13", (0xB1, 0x10), DO=POINTER, Y=0x02, seed=direct, AA=TARGET),
        Scene("14", (0xB7, 0x10), DO=POINTER, Y=0x02, seed=direct, AA=TARGET, AAB=0x7E),
        Scene("15", (0xA7, 0x10), DO=POINTER, seed=direct, AA=TARGET, AAB=0x7E),
        Scene("16a", (0xB5, 0x10), DO=POINTER, X=0x02),
        Scene("16b", (0x16, 0x10), DO=POINTER, X=0x02),
        Scene("17", (0xB6, 0x10), DO=POINTER, Y=0x02),
        Scene("18", (0xA9, 0x42)),
        Scene("19a", (0xEA,)),
        Scene("19b", (0xEB,)),
        Scene("20", (0xD0, 0x10), Offset=0x10, P=core.FLAG_Z),
        Scene("21", (0x82, 0x10, 0x00), Offset=0x10),
        Scene("22b", (0x68,), seed=stack),
        Scene("22c", (0x48,)),
        Scene("22d", (0xF4, 0x34, 0x12), AA=TARGET),
        Scene("22e", (0xD4, 0x10), DO=POINTER, seed=direct, AA=TARGET),
        Scene("22f", (0x62, 0x10, 0x00), Offset=0x10),
        Scene("22g", (0x40,), seed=stack),
        Scene("22h", (0x60,), seed=stack),
        Scene("22i", (0x6B,), seed=stack),
        Scene(
            "22j", (0x00, 0xEA), VA=0x00FFE6, AAV=0x00FFE6, seed={0x00FFE6: 0x34, 0x00FFE7: 0x12}
        ),
        Scene("23", (0xA3, 0x10), SO=0x10),
        Scene(
            "24",
            (0xB3, 0x10),
            SO=0x10,
            Y=0x02,
            S=0x0140,
            seed={0x0150: 0x34, 0x0151: 0x12},
            AA=TARGET,
        ),
        Scene("9a", (0x54, 0x7E, 0x7F), X=0x0010, Y=0x0020, DBA=0x7E, SBA=0x7F, A=0x0000),
        Scene("9b", (0x44, 0x7E, 0x7F), X=0x0010, Y=0x0020, DBA=0x7E, SBA=0x7F, A=0x0000),
    ]


class RecordTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.groups = HELD["groups"]

    def test_the_table_covers_forty_seven_addressing_mode_groups(self) -> None:
        self.assertEqual(len(self.groups), 47)

    def test_and_three_hundred_and_twenty_eight_cycles_between_them(self) -> None:
        self.assertEqual(sum(len(group["bus"]) for group in self.groups), 328)

    def test_every_note_the_rows_cite_is_written_down(self) -> None:
        cited = {
            note for group in self.groups for row in group["bus"] for note in row.get("notes", ())
        }

        self.assertLessEqual(cited, set(HELD["noteQuotes"]))

    def test_every_row_says_what_all_four_qualifying_lines_did(self) -> None:
        missing = [
            group["id"]
            for group in self.groups
            for row in group["bus"]
            if not all(key in row for key in ("vpb", "mlb", "vda", "vpa"))
        ]

        self.assertEqual(missing, [])

    def test_the_cells_the_page_spells_differently_are_kept_as_printed(self) -> None:
        slips = [
            row["asPrinted"] for group in self.groups for row in group["bus"] if "asPrinted" in row
        ]

        self.assertEqual(len(slips), 18)

    def test_and_each_kind_of_slip_says_what_the_page_did(self) -> None:
        self.assertEqual(len(HELD["printingSlips"]["kinds"]), 6)

    def test_the_pages_were_read_rather_than_only_parsed(self) -> None:
        self.assertIn("read as printed", HELD["readHow"])


class BusTest(unittest.TestCase):
    """Every drivable group run, and every line of every cycle checked."""

    def rows(self) -> list[tuple[str, str, str]]:
        found = []
        for scene in scenes():
            trace, values = scene.run()
            wanted = base(scene.group)
            found.append((f"{scene.group} length", str(len(trace)), str(len(wanted))))
            found.extend(
                (
                    f"{scene.group} cycle {row['cycle']}",
                    f"{address:06X} {observed(pin)}",
                    f"{resolve(row['address'], values):06X} {pins(row)}",
                )
                for (address, _, pin), row in zip(trace, wanted, strict=False)
            )
        return found

    def test_the_model_puts_the_table_on_the_bus(self) -> None:
        wrong = [name for name, did, says in self.rows() if did != says]
        recorded = HELD["disagreements"]

        self.assertEqual(
            sorted(wrong),
            sorted(
                recorded["widthDependentAddress"]["rows"]
                + recorded["qualifierOnAnIndexedIndirectJump"]["rows"]
            ),
        )

    def test_which_is_nine_rows_of_two_hundred_and_sixty_six(self) -> None:
        rows = self.rows()

        self.assertEqual((len(rows), sum(1 for _, d, s in rows if d != s)), (266, 9))

    def test_the_five_that_differ_by_a_byte_are_the_ones_a_wide_register_lengthens(
        self,
    ) -> None:
        rows = {name: (did, says) for name, did, says in self.rows() if did != says}
        found = [
            int(says.split()[0], 16) - int(did.split()[0], 16)
            for name, (did, says) in rows.items()
            if name in HELD["disagreements"]["widthDependentAddress"]["rows"]
        ]

        self.assertEqual([abs(one) for one in found], [1] * 5)

    def test_four_of_them_are_a_byte_higher_and_the_push_a_byte_lower(self) -> None:
        rows = {name: (did, says) for name, did, says in self.rows() if did != says}
        found = {
            name: int(says.split()[0], 16) - int(did.split()[0], 16)
            for name, (did, says) in rows.items()
            if name in HELD["disagreements"]["widthDependentAddress"]["rows"]
        }

        self.assertEqual((sorted(found.values()), found["22c cycle 3"]), ([-1, 1, 1, 1, 1], -1))

    def test_and_the_four_that_differ_by_a_pin_agree_on_the_address(self) -> None:
        rows = {name: (did, says) for name, did, says in self.rows() if did != says}
        found = [
            did.split()[0] == says.split()[0]
            for name, (did, says) in rows.items()
            if name in HELD["disagreements"]["qualifierOnAnIndexedIndirectJump"]["rows"]
        ]

        self.assertEqual(found, [True] * 4)

    def test_the_table_marks_the_same_operation_the_other_way_two_groups_later(self) -> None:
        indexed = [row for row in base("2a") if row["data"].startswith("New PC")]
        direct = [row for row in base("3b") if row["data"].startswith("New PC")]

        self.assertEqual(
            (
                [(row["vda"], row["vpa"]) for row in indexed],
                [(row["vda"], row["vpa"]) for row in direct],
            ),
            ([(0, 1), (0, 1)], [(1, 0), (1, 0)]),
        )

    def test_every_group_but_the_three_that_cannot_be_driven(self) -> None:
        driven = {scene.group for scene in scenes()}

        self.assertEqual(set(GROUPS) - driven, set(HALTS) | set(BY_PIN))

    def test_the_three_are_the_two_halts_and_the_pin_driven_one(self) -> None:
        self.assertEqual(
            [GROUPS[name]["title"] for name in (*HALTS, *BY_PIN)],
            ["Stop the Clock", "Wait for Interrupt                  (9)RDY=1", "Stack s"],
        )


class QualifierTest(unittest.TestCase):
    """The two lines the eight bit parts do not have, which this table is for."""

    def test_exactly_one_cycle_of_each_group_is_an_opcode_fetch(self) -> None:
        counts = {
            group["id"]: sum(1 for row in base(group["id"]) if (row["vda"], row["vpa"]) == (1, 1))
            for group in HELD["groups"]
        }

        self.assertEqual(set(counts.values()), {1})

    def test_an_internal_cycle_is_the_one_with_both_lines_low(self) -> None:
        internal = [
            row
            for group in HELD["groups"]
            for row in group["bus"]
            if (row["vda"], row["vpa"]) == (0, 0)
        ]

        self.assertGreater([row["data"] for row in internal].count("IO"), 60)

    def test_the_model_reports_no_value_on_an_internal_cycle(self) -> None:
        scene = next(one for one in scenes() if one.group == "22h")
        trace, _ = scene.run()
        internal = [value for _, value, pin in trace if pin[0] == "-" and pin[1] == "-"]

        self.assertEqual(internal, [None, None, None])

    def test_the_vector_pull_line_falls_only_on_an_interrupt(self) -> None:
        pulling = {
            group["id"] for group in HELD["groups"] for row in group["bus"] if row["vpb"] == 0
        }

        self.assertEqual(pulling, {"22a", "22j"})

    def test_and_memory_lock_only_on_a_read_modify_write(self) -> None:
        locked = {
            group["id"] for group in HELD["groups"] for row in group["bus"] if row["mlb"] == 0
        }

        self.assertEqual(locked, {"1d", "6b", "10b", "16b"})


if __name__ == "__main__":
    unittest.main()
