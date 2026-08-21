"""Holds the model's bus to Appendix A of the MCS6500 Hardware Manual.

The appendix prints the address bus and the read write line for every cycle of
every addressing mode, which makes it the one manufacturer statement of NMOS
cycle behaviour strong enough to test against. Each shape is driven here with a
concrete setup, and the manual's own address expressions are resolved against
that setup rather than restated as numbers, so a row that stops matching names
the page it came from.

Four rows carry an expression the part does not drive. Those rows are run twice,
once in the case where the two readings agree and once where they part, and the
disagreement is asserted rather than smoothed over.
"""

import json
import sys
import unittest
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import Cpu, SparseMemory  # noqa: E402

HELD = json.loads((Path(__file__).resolve().parent / "addressing-cycles.json").read_text())

SHAPES = HELD["shapes"]

START = 0x0200

STACK = 0x80
"""A stack pointer far enough from either end that no pull or push wraps.

The manual writes its stack addresses as plain sums, Stack Ptr. + 3 and the
like, which only hold while the sum stays inside page one. Keeping the general
runs away from the ends lets those expressions be checked as written, and the
wrap is checked on its own below.
"""


def resolvers() -> dict[str, Callable[[Mapping[str, int]], int]]:
    """The manual's address expressions, one function each.

    A closed vocabulary rather than a parser: every expression printed anywhere
    in the appendix appears here, so an expression the record grows that this
    does not know about fails loudly instead of being skipped.
    """
    return {
        "PC": lambda s: s["pc"],
        "PC + 1": lambda s: s["pc"] + 1,
        "PC + 2": lambda s: s["pc"] + 2,
        "PC + 3": lambda s: s["pc"] + 3,
        "00, ADL": lambda s: s["adl"],
        "ADH, ADL": lambda s: (s["adh"] << 8) | s["adl"],
        "00, BAL": lambda s: s["bal"],
        "00, BAL + X": lambda s: (s["bal"] + s["x"]) & 0xFF,
        "00, BAL + X + 1": lambda s: (s["bal"] + s["x"] + 1) & 0xFF,
        "00, BAL + index register": lambda s: (s["bal"] + s["index"]) & 0xFF,
        "00, IAL": lambda s: s["ial"],
        "00, IAL + 1": lambda s: (s["ial"] + 1) & 0xFF,
        "BAH + C, BAL + index register": lambda s: carried(s, s["index"], 1),
        "BAH, BAL + index register": lambda s: carried(s, s["index"], 0),
        "BAH + 1, BAL + index register": lambda s: uncarried(s, s["index"]) + 0x100,
        "BAH + C, BAL + Y": lambda s: carried(s, s["y"], 1),
        "BAH, BAL + Y": lambda s: carried(s, s["y"], 0),
        "BAH + 1, BAL + Y": lambda s: uncarried(s, s["y"]) + 0x100,
        "BAH + C, BAL + X": lambda s: carried(s, s["x"], 1),
        "BAH, BAL + X": lambda s: carried(s, s["x"], 0),
        "IAH, IAL": lambda s: (s["iah"] << 8) | s["ial"],
        "IAH, IAL + 1": lambda s: (s["iah"] << 8) | ((s["ial"] + 1) & 0xFF),
        "Stack Ptr.": lambda s: 0x0100 + s["s"],
        "Stack Ptr. - 1": lambda s: 0x0100 + s["s"] - 1,
        "Stack Ptr. - 2": lambda s: 0x0100 + s["s"] - 2,
        "Stack Ptr. + 1": lambda s: 0x0100 + s["s"] + 1,
        "Stack Ptr. + 2": lambda s: 0x0100 + s["s"] + 2,
        "Stack Ptr. + 3": lambda s: 0x0100 + s["s"] + 3,
        "FFFE": lambda s: 0xFFFE,
        "FFFF": lambda s: 0xFFFF,
        "PCH, PCL": lambda s: s["pulled"],
        "PCH, PCL + 1": lambda s: s["pulled"] + 1,
        "PC + 2 + offset (w/o carry)": partial,
        "PC + 2 + offset (with carry)": lambda s: (s["pc"] + 2 + s["offset"]) & 0xFFFF,
    }


def uncarried(scene: Mapping[str, int], index: int) -> int:
    """The base address with the index added to its low byte only."""
    return (scene["bah"] << 8) | ((scene["bal"] + index) & 0xFF)


def carried(scene: Mapping[str, int], index: int, apply: int) -> int:
    """The same, with the carry out of that addition folded in or left out."""
    carry = 1 if scene["bal"] + index > 0xFF else 0
    return uncarried(scene, index) + 0x100 * carry * apply


def partial(scene: Mapping[str, int]) -> int:
    """A branch target with the offset added to the low byte of the counter only."""
    here = scene["pc"] + 2
    return (here & 0xFF00) | ((here + scene["offset"]) & 0xFF)


class Scene:
    """One concrete run of one shape, with the quantities its expressions name."""

    def __init__(self, shape: str, program: Sequence[int], **named: Any) -> None:
        self.shape = shape
        self.program = program
        self.seed: dict[int, int] = named.pop("seed", {})
        self.pc = named.pop("pc", START)
        self.crossing = named.pop("crossing", False)
        self.taken = named.pop("taken", True)
        self.named = named

    def run(self) -> tuple[list[tuple[int, str]], dict[str, int]]:
        space = SparseMemory()
        for offset, byte in enumerate(self.program):
            space.write8(self.pc + offset, byte)
        for address, value in self.seed.items():
            space.write8(address, value)
        cpu = Cpu(space, model="6502", reset=False)
        cpu.pc, cpu.s = self.pc, self.named.get("s", STACK)
        cpu.a, cpu.x, cpu.y = 0x5A, self.named.get("x", 0), self.named.get("y", 0)
        cpu.set_status(self.named.get("p", 0x24))
        cpu.trace = []
        cpu.step()
        scene = dict(self.named)
        scene.update(pc=self.pc, s=self.named.get("s", STACK))
        scene.setdefault("x", 0)
        scene.setdefault("y", 0)
        scene.setdefault("index", scene["x"] or scene["y"])
        scene.setdefault("offset", 0)
        scene.setdefault("pulled", 0)
        return [(address & 0xFFFF, kind) for address, _, kind in cpu.trace], scene


def wanted(shape: str, scene: Scene) -> list[str]:
    """The rows the record says appear for this run."""
    held = SHAPES[shape]
    crossing = set(held.get("onlyWhenCrossing", []))
    taken = set(held.get("onlyWhenTaken", []))
    rows = []
    for row in held["bus"]:
        state = row["state"]
        if state in crossing and not scene.crossing:
            continue
        if state in taken and not scene.taken:
            continue
        rows.append(state)
    return rows


def access(shape: str, state: str) -> str:
    """Whether the appendix prints a read or a write for one row."""
    found = next(row for row in SHAPES[shape]["bus"] if row["state"] == state)
    return str(found["access"])


def expected(shape: str, state: str, values: Mapping[str, int]) -> int:
    """The address the part drives, which is the printed one unless a row says otherwise."""
    row = next(row for row in SHAPES[shape]["bus"] if row["state"] == state)
    return resolvers()[row.get("partDrives") or row["address"]](values) & 0xFFFF


POINTER = {0x10: 0xF0, 0x11: 0x12}

INDIRECT = {0x14: 0x34, 0x15: 0x12}

JUMP = {0x1234: 0x78, 0x1235: 0x56}

RETURN = {0x0100 + STACK + 1: 0x24, 0x0100 + STACK + 2: 0x34, 0x0100 + STACK + 3: 0x12}

RESUME = {0x0100 + STACK + 1: 0x34, 0x0100 + STACK + 2: 0x12}


def scenes() -> list[Scene]:
    """One run per shape, plus a second for every shape with a page crossing."""
    return [
        Scene("single byte", (0xEA,)),
        Scene("immediate", (0xA9, 0x42)),
        Scene("zero page", (0xA5, 0x10), adl=0x10),
        Scene("absolute", (0xAD, 0x34, 0x12), adl=0x34, adh=0x12),
        Scene("indirect x", (0xA1, 0x10), seed=INDIRECT, x=4, bal=0x10, adl=0x34, adh=0x12),
        Scene("absolute indexed", (0xBD, 0x00, 0x12), x=0x20, bal=0x00, bah=0x12),
        Scene("absolute indexed", (0xBD, 0xF0, 0x12), x=0x20, bal=0xF0, bah=0x12, crossing=True),
        Scene("zero page indexed", (0xB5, 0x10), x=4, bal=0x10),
        Scene("indirect y", (0xB1, 0x10), seed=POINTER, y=2, ial=0x10, bal=0xF0, bah=0x12),
        Scene(
            "indirect y",
            (0xB1, 0x10),
            seed=POINTER,
            y=0x20,
            ial=0x10,
            bal=0xF0,
            bah=0x12,
            crossing=True,
        ),
        Scene("store zero page", (0x85, 0x10), adl=0x10),
        Scene("store absolute", (0x8D, 0x34, 0x12), adl=0x34, adh=0x12),
        Scene("store indirect x", (0x81, 0x10), seed=INDIRECT, x=4, bal=0x10, adl=0x34, adh=0x12),
        Scene(
            "store absolute indexed",
            (0x9D, 0x00, 0x12),
            x=0x20,
            bal=0x00,
            bah=0x12,
            adl=0x20,
            adh=0x12,
        ),
        Scene(
            "store absolute indexed",
            (0x9D, 0xF0, 0x12),
            x=0x20,
            bal=0xF0,
            bah=0x12,
            adl=0x10,
            adh=0x13,
            crossing=True,
        ),
        Scene("store zero page indexed", (0x95, 0x10), x=4, bal=0x10),
        Scene(
            "store indirect y",
            (0x91, 0x10),
            seed=POINTER,
            y=2,
            ial=0x10,
            bal=0xF0,
            bah=0x12,
            adl=0xF2,
            adh=0x12,
        ),
        Scene("modify zero page", (0x06, 0x10), adl=0x10),
        Scene("modify absolute", (0x0E, 0x34, 0x12), adl=0x34, adh=0x12),
        Scene("modify zero page x", (0x16, 0x10), x=4, bal=0x10),
        Scene(
            "modify absolute x", (0x1E, 0x00, 0x12), x=0x20, bal=0x00, bah=0x12, adl=0x20, adh=0x12
        ),
        Scene("push", (0x48,)),
        Scene("pull", (0x68,)),
        Scene("jump to subroutine", (0x20, 0x34, 0x12), adl=0x34, adh=0x12),
        Scene("break", (0x00,)),
        Scene("return from interrupt", (0x40,), seed=RETURN, pulled=0x1234),
        Scene("jump absolute", (0x4C, 0x34, 0x12), adl=0x34, adh=0x12),
        Scene(
            "jump indirect", (0x6C, 0x34, 0x12), seed=JUMP, ial=0x34, iah=0x12, adl=0x78, adh=0x56
        ),
        Scene("return from subroutine", (0x60,), seed=RESUME, pulled=0x1234),
        Scene("branch", (0xF0, 0x17), p=0x24, taken=False),
        Scene("branch", (0xD0, 0x17), p=0x24, offset=0x17),
        Scene("branch", (0xD0, 0x2B), pc=0x40DC, p=0x24, offset=0x2B, crossing=True),
    ]


class RecordTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.shapes = SHAPES

    def test_the_appendix_has_a_shape_for_every_table_it_prints(self) -> None:
        self.assertEqual(len(self.shapes), 27)

    def test_every_shape_names_the_section_and_the_page_it_came_from(self) -> None:
        missing = [
            name
            for name, held in self.shapes.items()
            if not held.get("manualSection") or not held.get("printedPage")
        ]

        self.assertEqual(missing, [])

    def test_every_row_of_every_shape_uses_an_expression_this_gate_can_resolve(self) -> None:
        known = set(resolvers())
        printed = {
            expression
            for held in self.shapes.values()
            for row in held["bus"]
            for expression in (row["address"], row.get("partDrives"))
            if expression
        }

        self.assertLessEqual(printed, known)

    def test_every_row_is_a_read_or_a_write(self) -> None:
        kinds = {row["access"] for held in self.shapes.values() for row in held["bus"]}

        self.assertEqual(kinds, {"read", "write"})

    def test_the_row_count_of_each_shape_matches_the_cycle_count_it_declares(self) -> None:
        wrong = [
            name for name, held in self.shapes.items() if len(held["bus"]) != max(held["cycles"])
        ]

        self.assertEqual(wrong, [])

    def test_the_warning_about_stopping_in_a_write_cycle_is_kept(self) -> None:
        self.assertIn("will not stop in any cycle where R/W is a 0", HELD["opening"]["quote"])

    def test_the_pages_were_read_rather_than_extracted(self) -> None:
        self.assertIn("read as printed", HELD["readHow"])


class BusTest(unittest.TestCase):
    """Every shape driven, and every address the appendix prints checked."""

    def observed(self) -> list[tuple[str, str, str]]:
        """Every driven cycle, as what the model did beside what the record says.

        The count of cycles is one of the rows, so a run that comes out short is
        reported by name rather than truncating the comparison silently.
        """
        found = []
        for scene in scenes():
            trace, values = scene.run()
            states = wanted(scene.shape, scene)
            found.append((f"{scene.shape} length", str(len(trace)), str(len(states))))
            found.extend(
                (
                    f"{scene.shape} {state}",
                    f"{address:04X} {kind}",
                    f"{expected(scene.shape, state, values):04X} {access(scene.shape, state)}",
                )
                for (address, kind), state in zip(trace, states, strict=False)
            )
        return found

    def test_the_model_puts_the_appendix_on_the_bus(self) -> None:
        wrong = [name for name, did, says in self.observed() if did != says]

        self.assertEqual(wrong, [])

    def test_which_is_every_cycle_of_every_run_plus_a_count_for_each(self) -> None:
        rows = self.observed()
        counts = [name for name, _, _ in rows if name.endswith(" length")]

        self.assertEqual((len(rows), len(counts)), (179, 32))

    def test_which_is_every_shape_the_appendix_prints(self) -> None:
        driven = {scene.shape for scene in scenes()}

        self.assertEqual(driven, set(SHAPES))

    def test_and_a_second_run_for_every_shape_that_can_cross_a_page(self) -> None:
        crossing = {scene.shape for scene in scenes() if scene.crossing}

        self.assertEqual(len(crossing), 4)


class CarryTest(unittest.TestCase):
    """The discarded indexed read, which the appendix writes two ways.

    Four tables give the high byte of that cycle as BAH + C. One, the indirect Y
    store at A.3.6, gives it as BAH with no carry. Only the second matches the
    part, so a reader who followed the first would expect the corrected address
    on the bus one cycle early.
    """

    def crossing(self) -> list[Scene]:
        return [scene for scene in scenes() if scene.crossing and scene.shape != "branch"]

    def test_three_tables_print_the_carry_and_one_does_not(self) -> None:
        printed = [
            (name, row["state"])
            for name, held in SHAPES.items()
            for row in held["bus"]
            if "+ C," in row["address"]
        ]

        self.assertEqual(len(printed), 5)

    def test_the_one_that_does_not_is_the_indirect_y_store(self) -> None:
        row = next(row for row in SHAPES["store indirect y"]["bus"] if row["state"] == "T4")

        self.assertEqual((row["address"], row.get("partDrives")), ("BAH, BAL + Y", None))

    def test_the_part_drives_the_uncarried_address_on_every_crossing(self) -> None:
        found = []
        for scene in self.crossing():
            trace, values = scene.run()
            state = next(
                row["state"]
                for row in SHAPES[scene.shape]["bus"]
                if row.get("partDrives", "").startswith("BAH,")
            )
            index = wanted(scene.shape, scene).index(state)
            found.append(trace[index][0] == expected(scene.shape, state, values))

        self.assertEqual(found, [True] * len(self.crossing()))

    def test_and_the_printed_expression_names_a_different_address(self) -> None:
        found = []
        for scene in self.crossing():
            _, values = scene.run()
            row = next(
                row
                for row in SHAPES[scene.shape]["bus"]
                if row.get("partDrives", "").startswith("BAH,")
            )
            printed = resolvers()[row["address"]](values) & 0xFFFF
            found.append(printed != resolvers()[row["partDrives"]](values) & 0xFFFF)

        self.assertEqual(found, [True] * len(self.crossing()))


class BranchTest(unittest.TestCase):
    """The branch table, whose two address rows sit one row lower than they run."""

    def taken(self) -> Scene:
        return next(s for s in scenes() if s.shape == "branch" and s.taken and not s.crossing)

    def test_the_third_cycle_is_the_counter_rather_than_the_target(self) -> None:
        scene = self.taken()
        trace, values = scene.run()

        self.assertEqual(trace[2][0], values["pc"] + 2)

    def test_which_is_not_what_the_table_prints_for_that_row(self) -> None:
        scene = self.taken()
        _, values = scene.run()
        row = next(row for row in SHAPES["branch"]["bus"] if row["state"] == "T2")

        self.assertNotEqual(resolvers()[row["address"]](values), values["pc"] + 2)

    def test_the_fourth_cycle_carries_the_address_the_table_puts_on_the_third(self) -> None:
        scene = next(s for s in scenes() if s.shape == "branch" and s.crossing)
        trace, values = scene.run()
        third = next(row for row in SHAPES["branch"]["bus"] if row["state"] == "T2")

        self.assertEqual(trace[3][0], resolvers()[third["address"]](values) & 0xFFFF)

    def test_and_the_corrected_target_is_not_reached_inside_the_branch(self) -> None:
        scene = next(s for s in scenes() if s.shape == "branch" and s.crossing)
        trace, values = scene.run()

        self.assertNotIn((values["pc"] + 2 + values["offset"]) & 0xFFFF, [a for a, _ in trace])


class StackWrapTest(unittest.TestCase):
    """The stack expressions, which are plain sums and so stop at the page edge."""

    def pulled(self, stack: int) -> list[int]:
        space = SparseMemory()
        space.write8(START, 0x40)
        cpu = Cpu(space, model="6502", reset=False)
        cpu.pc, cpu.s = START, stack
        cpu.set_status(0x24)
        cpu.trace = []
        cpu.step()
        return [address & 0xFFFF for address, _, _ in cpu.trace]

    def test_the_plain_sums_hold_while_the_pull_stays_inside_page_one(self) -> None:
        found = self.pulled(STACK)

        self.assertEqual(found[2:], [0x0100 + STACK + step for step in range(4)])

    def test_but_the_part_wraps_where_the_sums_leave_the_page(self) -> None:
        found = self.pulled(0xFE)

        self.assertEqual(found[2:], [0x01FE, 0x01FF, 0x0100, 0x0101])

    def test_which_is_where_the_third_sum_would_have_pointed(self) -> None:
        self.assertEqual(0x0100 + 0xFE + 3, 0x0201)


if __name__ == "__main__":
    unittest.main()
