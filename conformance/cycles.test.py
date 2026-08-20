"""That the cycle comparison compares, and refuses where it cannot.

Two things are easy to get wrong in a runner like this and both are checked here.
A comparison that quietly treats an absent suite, an unsupported model or a halted
part as agreement is worse than no comparison. And a comparison that only counts
cycles rather than reading their addresses would pass a model that spends the
right number of cycles on the wrong bus activity.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conformance import cycles  # noqa: E402
from conformance.singlestep import Usage  # noqa: E402
from mos65xx import UnknownModelError  # noqa: E402

LDA_ZERO_PAGE = 0xA5
INC_ZERO_PAGE = 0xE6
JAM = 0x02


def a_case(
    program: dict[int, int], cycled: list[list[Any]], name: str = "made up", **state: Any
) -> dict[str, Any]:
    """One test in the shape the suites use, with only the fields the runner reads."""
    initial: dict[str, Any] = {"pc": 0x8000, "s": 0xFD, "a": 0x00, "x": 0x00, "y": 0x00, "p": 0x24}
    initial.update(state)
    initial["ram"] = sorted(program.items())
    return {"name": name, "initial": initial, "final": dict(initial), "cycles": cycled}


LOADING = a_case(
    {0x8000: LDA_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x7B},
    [[0x8000, LDA_ZERO_PAGE, "read"], [0x8001, 0x40, "read"], [0x0040, 0x7B, "read"]],
)


class ComparisonTest(unittest.TestCase):
    """That a matching sequence passes and any change to it does not."""

    def test_a_case_the_model_reproduces_exactly_agrees(self) -> None:
        self.assertIsNone(cycles.check(LOADING, "6502"))

    def test_a_recording_one_cycle_short_disagrees(self) -> None:
        short = a_case(
            {0x8000: LDA_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x7B},
            [[0x8000, LDA_ZERO_PAGE, "read"], [0x8001, 0x40, "read"]],
        )

        self.assertIsNotNone(cycles.check(short, "6502"))

    def test_a_recording_with_the_right_count_and_a_wrong_address_disagrees(self) -> None:
        moved = a_case(
            {0x8000: LDA_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x7B},
            [[0x8000, LDA_ZERO_PAGE, "read"], [0x8001, 0x40, "read"], [0x0041, 0x7B, "read"]],
        )

        self.assertIsNotNone(cycles.check(moved, "6502"))

    def test_and_the_disagreement_carries_the_model_s_own_sequence(self) -> None:
        moved = a_case(
            {0x8000: LDA_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x7B},
            [[0x8000, LDA_ZERO_PAGE, "read"], [0x8001, 0x40, "read"], [0x0041, 0x7B, "read"]],
        )

        self.assertEqual(cycles.check(moved, "6502"), cycles.recorded(LOADING))

    def test_a_read_where_a_write_was_recorded_disagrees(self) -> None:
        mislabelled = a_case(
            {0x8000: LDA_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x7B},
            [[0x8000, LDA_ZERO_PAGE, "read"], [0x8001, 0x40, "read"], [0x0040, 0x7B, "write"]],
        )

        self.assertIsNotNone(cycles.check(mislabelled, "6502"))

    def test_the_double_write_of_a_read_modify_write_is_part_of_the_comparison(self) -> None:
        bumping = a_case(
            {0x8000: INC_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x10},
            [
                [0x8000, INC_ZERO_PAGE, "read"],
                [0x8001, 0x40, "read"],
                [0x0040, 0x10, "read"],
                [0x0040, 0x10, "write"],
                [0x0040, 0x11, "write"],
            ],
        )

        self.assertIsNone(cycles.check(bumping, "6502"))

    def test_and_a_recording_with_only_one_write_disagrees(self) -> None:
        collapsed = a_case(
            {0x8000: INC_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x10},
            [
                [0x8000, INC_ZERO_PAGE, "read"],
                [0x8001, 0x40, "read"],
                [0x0040, 0x10, "read"],
                [0x0040, 0x11, "write"],
            ],
        )

        self.assertIsNotNone(cycles.check(collapsed, "6502"))

    def test_a_case_the_model_cannot_run_reports_what_it_raised(self) -> None:
        held = cycles.check(a_case({0x8000: LDA_ZERO_PAGE}, []), "not-a-part-at-all")

        assert held is not None
        self.assertIn("raised", held[0][2])


class HaltTest(unittest.TestCase):
    """That a halted part is left out rather than counted either way."""

    def test_a_jam_opcode_is_recognised_as_a_halt(self) -> None:
        self.assertTrue(cycles.halted(a_case({0x8000: JAM}, []), "6502"))

    def test_an_ordinary_opcode_is_not(self) -> None:
        self.assertFalse(cycles.halted(LOADING, "6502"))

    def test_a_case_whose_opcode_byte_is_absent_is_not_treated_as_a_halt(self) -> None:
        self.assertFalse(cycles.halted(a_case({0x9000: JAM}, []), "6502"))

    def test_a_part_with_no_opcode_table_is_not_treated_as_a_halt(self) -> None:
        self.assertFalse(cycles.halted(a_case({0x8000: JAM}, []), "65816"))

    def test_a_part_that_does_not_record_its_bus_is_refused_by_the_comparison(self) -> None:
        class Deaf:
            table = None

        with (
            unittest.mock.patch.object(cycles, "machine_for", lambda *_: (Deaf(), None)),
            self.assertRaises(cycles.Unsupported),
        ):
            cycles.check(LOADING, "6502")

    def test_halts_are_counted_apart_from_agreements(self) -> None:
        agreed, differed, skipped, _ = cycles.run_tests(
            [LOADING, a_case({0x8000: JAM}, [])], "6502"
        )

        self.assertEqual((agreed, differed, skipped), (1, 0, 1))


class RefusalTest(unittest.TestCase):
    """That the runner refuses rather than reporting an agreement it cannot check."""

    def test_a_part_nobody_has_held_to_a_recording_is_refused(self) -> None:
        with (
            unittest.mock.patch.object(cycles, "VERIFIED", frozenset({"6502"})),
            self.assertRaises(cycles.Unsupported),
        ):
            cycles.options(["somewhere", "--model", "65816"])

    def test_every_part_this_core_records_is_accepted(self) -> None:
        for named in sorted(cycles.VERIFIED):
            self.assertEqual(cycles.options(["somewhere", "--model", named])[1], named)

    def test_a_model_nobody_has_is_refused_too(self) -> None:
        with self.assertRaises(UnknownModelError):
            cycles.options(["somewhere", "--model", "6503-with-wings"])

    def test_a_missing_suite_directory_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            output = io.StringIO()
            with redirect_stdout(output):
                code = cycles.main([empty, "--model", "6502"])

        self.assertEqual((code, "no suite at" in output.getvalue()), (0, True))

    def test_the_model_flag_needs_a_name_after_it(self) -> None:
        with self.assertRaises(Usage):
            cycles.options(["somewhere", "--model"])

    def test_a_directory_is_required(self) -> None:
        with self.assertRaises(Usage):
            cycles.options(["--model", "6502"])

    def test_a_refusal_exits_two_rather_than_zero(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cycles.main(["--model", "6502"])

        self.assertEqual(code, 2)


class BudgetTest(unittest.TestCase):
    """That a part with an interruptible instruction is given the window."""

    MOVE = 0x54

    def test_the_recorded_length_bounds_a_block_move(self) -> None:
        held = {
            "name": "a move with nowhere near enough time",
            "initial": {
                "pc": 0x8000,
                "s": 0x01FF,
                "a": 0xFFFF,
                "x": 0x0000,
                "y": 0x0100,
                "p": 0x30,
                "e": 0,
                "dbr": 0x00,
                "pbr": 0x00,
                "d": 0x0000,
                "ram": [[0x8000, self.MOVE], [0x8001, 0x7E], [0x8002, 0x7F]],
            },
            "final": {},
            "cycles": [[0, 0, "dp-r-mx-"]] * 7,
        }

        seen = cycles.check(held, "65816")

        self.assertEqual(len(seen or []), 7)


class PlaceholderTest(unittest.TestCase):
    """That the one cycle with no address to compute is counted apart, narrowly."""

    ADC_IMMEDIATE = 0x69

    def decimal_add(self, third: int) -> dict[str, Any]:
        return a_case(
            {0x8000: self.ADC_IMMEDIATE, 0x8001: 0x11},
            [[0x8000, self.ADC_IMMEDIATE, "read"], [0x8001, 0x11, "read"], [third, 0x11, "read"]],
            p=0x2C,
        )

    def test_a_case_differing_only_at_that_cycle_is_not_a_disagreement(self) -> None:
        agreed, differed, skipped, _ = cycles.run_tests([self.decimal_add(0x7F)], "w65c02")

        self.assertEqual((agreed, differed, skipped), (0, 0, 1))

    def test_the_same_case_with_the_address_the_model_reads_agrees_outright(self) -> None:
        agreed, differed, skipped, _ = cycles.run_tests([self.decimal_add(0x8001)], "w65c02")

        self.assertEqual((agreed, differed, skipped), (1, 0, 0))

    def test_an_opcode_outside_the_pair_is_never_excused(self) -> None:
        moved = a_case(
            {0x8000: LDA_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x7B},
            [[0x8000, LDA_ZERO_PAGE, "read"], [0x8001, 0x40, "read"], [0x0041, 0x7B, "read"]],
        )

        self.assertFalse(cycles.only_placeholder(moved, cycles.recorded(LOADING)))

    def test_a_difference_in_length_is_never_excused(self) -> None:
        short = a_case(
            {0x8000: self.ADC_IMMEDIATE, 0x8001: 0x11},
            [[0x8000, self.ADC_IMMEDIATE, "read"], [0x8001, 0x11, "read"]],
            p=0x2C,
        )

        self.assertFalse(cycles.only_placeholder(short, [(0, 0, "read")]))

    def test_two_cycles_apart_is_never_excused(self) -> None:
        held = self.decimal_add(0x7F)

        self.assertFalse(
            cycles.only_placeholder(held, [(1, 1, "read"), (2, 2, "read"), (3, 3, "read")])
        )

    def test_a_write_where_a_read_was_recorded_is_never_excused(self) -> None:
        held = self.decimal_add(0x7F)
        seen = cycles.recorded(held)
        seen[2] = (0x8001, 0x11, "write")

        self.assertFalse(cycles.only_placeholder(held, seen))


class SuiteTest(unittest.TestCase):
    """That a directory of files is walked, reported, and answered for."""

    def written(self, directory: Path, name: str, tests: list[dict[str, Any]]) -> None:
        (directory / name).write_text(json.dumps(tests))

    def test_a_suite_that_agrees_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            self.written(Path(where), "a5.json", [LOADING])
            output = io.StringIO()
            with redirect_stdout(output):
                code = cycles.main([where, "--model", "6502"])

        self.assertEqual((code, "1 agreed" in output.getvalue()), (0, True))

    def test_a_suite_that_disagrees_exits_one_and_shows_both_sequences(self) -> None:
        moved = a_case(
            {0x8000: LDA_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x7B},
            [[0x8000, LDA_ZERO_PAGE, "read"], [0x8001, 0x40, "read"], [0x0041, 0x7B, "read"]],
        )
        with tempfile.TemporaryDirectory() as where:
            self.written(Path(where), "a5.json", [moved])
            output = io.StringIO()
            with redirect_stdout(output):
                code = cycles.main([where, "--model", "6502"])

        self.assertEqual((code, "recorded" in output.getvalue()), (1, True))

    def test_more_disagreements_than_the_example_limit_are_still_counted(self) -> None:
        moved = a_case(
            {0x8000: LDA_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x7B},
            [[0x8000, LDA_ZERO_PAGE, "read"], [0x8001, 0x40, "read"], [0x0041, 0x7B, "read"]],
        )
        many = [moved] * (cycles.EXAMPLE_LIMIT + 2)

        agreed, differed, skipped, examples = cycles.run_tests(many, "6502")

        self.assertEqual(
            (agreed, differed, skipped, len(examples)),
            (0, cycles.EXAMPLE_LIMIT + 2, 0, cycles.EXAMPLE_LIMIT),
        )

    def test_an_empty_file_is_no_cases_rather_than_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            (Path(where) / "cb.json").write_text("")

            held = cycles.run_file(Path(where) / "cb.json", model="6502")

        self.assertEqual(held, (0, 0, 0, []))

    def test_a_limit_stops_reading_a_file_early(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            self.written(Path(where), "a5.json", [LOADING, LOADING, LOADING])

            agreed, _, _, _ = cycles.run_file(Path(where) / "a5.json", limit=2, model="6502")

        self.assertEqual(agreed, 2)

    def test_a_filter_picks_which_files_run(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            self.written(Path(where), "a5.json", [LOADING])
            self.written(Path(where), "e6.json", [LOADING])
            output = io.StringIO()
            with redirect_stdout(output):
                cycles.main([where, "1", "a5", "--model", "6502"])

        self.assertIn("1 files", output.getvalue())

    def test_more_broken_files_than_the_example_limit_are_counted(self) -> None:
        moved = a_case(
            {0x8000: LDA_ZERO_PAGE, 0x8001: 0x40, 0x0040: 0x7B},
            [[0x8000, LDA_ZERO_PAGE, "read"], [0x8001, 0x40, "read"], [0x0041, 0x7B, "read"]],
        )
        with tempfile.TemporaryDirectory() as where:
            for index in range(cycles.EXAMPLE_LIMIT + 2):
                self.written(Path(where), f"{index:02x}.json", [moved])
            output = io.StringIO()
            with redirect_stdout(output):
                cycles.main([where, "--model", "6502"])

        self.assertIn("more files with disagreements", output.getvalue())


if __name__ == "__main__":
    unittest.main()
