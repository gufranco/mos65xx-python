import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance import speed


def ticking(*seconds: float) -> Any:
    """A clock that advances by each of those in turn, so a run is exactly timed."""
    held = [0.0]
    steps = list(seconds)

    def clock() -> float:
        if not steps:
            return held[0]
        at = held[0]
        held[0] = at + steps.pop(0)
        return at

    return clock


class MeasurementTest(unittest.TestCase):
    """What a run reports, on a clock that does not vary."""

    def _timed(self, seconds: Sequence[float]) -> speed.Timed:
        return speed.Timed("6502", instructions=1000, seconds=seconds)

    def test_the_median_is_the_middle_of_the_runs(self) -> None:
        self.assertEqual(self._timed([0.1, 0.2, 0.9]).median, 0.2)

    def test_and_a_single_run_is_its_own_median(self) -> None:
        self.assertEqual(self._timed([0.5]).median, 0.5)

    def test_the_rate_is_cycles_over_the_median(self) -> None:
        self.assertEqual(self._timed([0.1, 0.2, 0.9]).rate, 5000)

    def test_one_slow_run_moves_the_median_less_than_it_moves_a_mean(self) -> None:
        steady = self._timed([0.1, 0.1, 0.1])
        hiccup = self._timed([0.1, 0.1, 9.9])

        self.assertEqual(steady.median, hiccup.median)

    def test_a_run_faster_than_the_floor_beats_it(self) -> None:
        self.assertTrue(self._timed([0.001]).beats(100))

    def test_and_one_slower_does_not(self) -> None:
        self.assertFalse(self._timed([10.0]).beats(1000))

    def test_a_run_exactly_at_the_floor_beats_it(self) -> None:
        found = speed.Timed("6502", instructions=1000, seconds=[1.0])

        self.assertTrue(found.beats(1000))

    def test_a_measurement_prints_as_the_rate_it_found(self) -> None:
        self.assertIn("cycles per second", repr(self._timed([0.1])))


class RunTest(unittest.TestCase):
    """That the runner actually drives the model, on a clock it is given."""

    def test_a_run_records_one_duration_per_repeat(self) -> None:
        found = speed.timed(instructions=10, repeats=3, clock=ticking(0.1, 0.1, 0.1))

        self.assertEqual(len(found.seconds), 3)

    def test_and_reports_the_part_it_ran(self) -> None:
        found = speed.timed(instructions=10, repeats=1, clock=ticking(0.1))

        self.assertEqual(found.part, "6502")

    def test_and_the_number_of_instructions_it_was_asked_for(self) -> None:
        found = speed.timed(instructions=10, repeats=1, clock=ticking(0.1))

        self.assertEqual(found.instructions, 10)

    def test_a_run_really_executes_the_instructions(self) -> None:
        found = speed.timed(instructions=64, repeats=1, clock=ticking(0.1))

        self.assertEqual(found.rate, 640)


class ReportTest(unittest.TestCase):
    def test_a_report_gives_the_rate_and_the_runtime(self) -> None:
        found = speed.Timed("6502", instructions=1000, seconds=[0.001])

        lines = " ".join(speed.lines_for(found, floor=100))

        self.assertIn("cycles per second", lines)
        self.assertIn("Python", lines)

    def test_and_the_fastest_and_slowest_run(self) -> None:
        found = speed.Timed("6502", instructions=1000, seconds=[0.001, 0.002, 0.003])

        lines = " ".join(speed.lines_for(found, floor=100))

        self.assertIn("fastest", lines)
        self.assertIn("slowest", lines)

    def test_it_does_not_claim_a_share_of_the_silicon(self) -> None:
        """This part has no one clock rate, so there is no share to report.

        The sibling package reports one, because its data sheet quotes a single
        rate for a single part. This one shipped in speed grades over two
        decades, so any divider would be a choice dressed as a measurement.
        """
        found = speed.Timed("6502", instructions=1000, seconds=[0.001])

        self.assertNotIn("% of the", " ".join(speed.lines_for(found, floor=100)))
        self.assertFalse(hasattr(found, "of_real_time"))

    def test_a_run_below_the_floor_says_so(self) -> None:
        found = speed.Timed("6502", instructions=1000, seconds=[10.0])

        self.assertIn("below the floor", " ".join(speed.lines_for(found, floor=1000)))

    def test_a_run_above_it_does_not(self) -> None:
        found = speed.Timed("6502", instructions=1000, seconds=[0.001])

        self.assertNotIn("below the floor", " ".join(speed.lines_for(found, floor=100)))


class OptionTest(unittest.TestCase):
    def test_a_run_with_no_options_takes_the_defaults(self) -> None:
        self.assertEqual(speed.options([]), (speed.INSTRUCTIONS, speed.REPEATS))

    def test_a_count_of_instructions_can_be_named(self) -> None:
        self.assertEqual(speed.options(["--instructions", "5"])[0], 5)

    def test_and_a_number_of_repeats(self) -> None:
        self.assertEqual(speed.options(["--repeats", "3"])[1], 3)

    def test_an_unknown_option_is_refused_by_name(self) -> None:
        with self.assertRaises(speed.Usage) as raised:
            speed.options(["--nonsense"])

        self.assertIn("--nonsense", str(raised.exception))

    def test_an_option_with_no_value_is_refused(self) -> None:
        with self.assertRaises(speed.Usage) as raised:
            speed.options(["--repeats"])

        self.assertIn("--repeats", str(raised.exception))


class EntryTest(unittest.TestCase):
    def _run(self, argv: Sequence[str], **held: Any) -> tuple[int, str]:
        said: list[str] = []
        code = speed.main(argv, say=said.append, **held)
        return code, " ".join(said)

    def test_a_run_that_beats_the_floor_passes(self) -> None:
        code, said = self._run(
            [],
            floor=100,
            run=lambda **_options: speed.Timed("6502", 1000, [0.001]),
        )

        self.assertEqual(code, 0)
        self.assertNotIn("below the floor", said)

    def test_a_run_that_does_not_fails_and_says_so(self) -> None:
        code, said = self._run(
            [],
            floor=1_000_000,
            run=lambda **_options: speed.Timed("6502", 1000, [1.0]),
        )

        self.assertEqual(code, 1)
        self.assertIn("below the floor", said)

    def test_an_unusable_option_is_reported_rather_than_raised(self) -> None:
        code, said = self._run(["--nonsense"])

        self.assertEqual(code, 2)
        self.assertIn("--nonsense", said)


if __name__ == "__main__":
    unittest.main()
