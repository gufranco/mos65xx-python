import sys
import types
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance import netlist


def answering(addresses: list[int]) -> Any:
    """A stand-in for the simulation that drives those addresses and nothing else."""

    def run(argv: Any, **_kwargs: Any) -> Any:
        lines = "".join(f" {step} {one:04X} EA r\n" for step, one in enumerate(addresses))
        return types.SimpleNamespace(stdout=lines)

    return run


def agreeing() -> Any:
    """A stand-in that answers whatever the model answers, for every case."""

    def run(argv: Any, **_kwargs: Any) -> Any:
        case = next(one for one in netlist.CASES if one.program.hex() == argv[1])
        held = netlist.modelled(case)
        return types.SimpleNamespace(
            stdout="".join(f" {step} {one:04X} EA r\n" for step, one in enumerate(held))
        )

    return run


class ModelTest(unittest.TestCase):
    def test_the_discarded_read_of_a_page_crossing_index_is_not_fixed_up(self) -> None:
        """The high byte is still the base's when the discarded read happens.

        This is the case the appendix gives two different answers for, and the
        one a simulation of the die settles: the read lands at the base plus the
        index with the carry not yet applied.
        """
        found = netlist.modelled(netlist.CASES[0])

        self.assertIn(0x1200, found)
        self.assertIn(0x1300, found)
        self.assertLess(found.index(0x1200), found.index(0x1300))

    def test_a_branch_crossing_a_page_reads_the_unfixed_target_first(self) -> None:
        found = netlist.modelled(netlist.CASES[2])

        self.assertIn(0x02E4, found)

    def test_every_case_drives_at_least_its_own_program(self) -> None:
        for case in netlist.CASES:
            self.assertGreaterEqual(len(netlist.modelled(case)), len(case.program))


class ComparisonTest(unittest.TestCase):
    def test_a_die_that_agrees_reports_nothing(self) -> None:
        self.assertEqual(netlist.compare(Path("/made-up"), netlist.CASES, agreeing()), [])

    def test_a_die_that_disagrees_names_the_case_and_both_answers(self) -> None:
        found = netlist.compare(Path("/made-up"), netlist.CASES[:1], answering([0xDEAD, 0xBEEF]))

        self.assertEqual(len(found), 1)
        self.assertIn("DEAD", found[0])
        self.assertIn(netlist.CASES[0].why, found[0])

    def test_only_the_cycles_both_answered_are_compared(self) -> None:
        """A short answer is not a disagreement about the cycles it does carry."""
        case = netlist.CASES[0]
        head = netlist.modelled(case)[:3]

        self.assertEqual(netlist.compare(Path("/made-up"), (case,), answering(head)), [])


class SkipTest(unittest.TestCase):
    """That a machine without the simulation says so rather than reporting a pass."""

    def test_it_says_it_could_not_run(self) -> None:
        said: list[str] = []
        original = print
        import builtins

        builtins.print = lambda *args, **_k: said.append(" ".join(str(one) for one in args))
        try:
            code = netlist.main((), lambda: None)
        finally:
            builtins.print = original

        self.assertEqual(code, 0)
        self.assertIn("skipped", " ".join(said))

    def test_and_names_the_variable_that_would_let_it(self) -> None:
        said: list[str] = []
        import builtins

        original = print
        builtins.print = lambda *args, **_k: said.append(" ".join(str(one) for one in args))
        try:
            netlist.main((), lambda: None)
        finally:
            builtins.print = original

        self.assertIn(netlist.VARIABLE, " ".join(said))

    def test_an_absent_path_is_the_same_as_none(self) -> None:
        import os

        os.environ[netlist.VARIABLE] = "/nothing/here/at/all"
        try:
            self.assertIsNone(netlist.probe())
        finally:
            del os.environ[netlist.VARIABLE]

    def test_and_no_variable_at_all_is_too(self) -> None:
        """Set first, then cleared, so the restore is the same on every machine.

        Popping a variable that may or may not be there leaves a branch that only
        runs for whoever happens to have it set, which is a check nobody else's
        run reaches.
        """
        import os

        os.environ[netlist.VARIABLE] = __file__
        del os.environ[netlist.VARIABLE]

        self.assertIsNone(netlist.probe())

    def test_a_path_that_is_a_file_is_taken(self) -> None:
        import os

        os.environ[netlist.VARIABLE] = __file__
        try:
            self.assertEqual(netlist.probe(), Path(__file__))
        finally:
            del os.environ[netlist.VARIABLE]


class RunTest(unittest.TestCase):
    def test_a_run_that_agrees_exits_zero(self) -> None:
        import builtins

        original = print
        builtins.print = lambda *_a, **_k: None
        try:
            code = netlist.main((), lambda: Path("/made-up"), agreeing())
        finally:
            builtins.print = original

        self.assertEqual(code, 0)

    def test_a_run_that_disagrees_exits_non_zero(self) -> None:
        import builtins

        original = print
        builtins.print = lambda *_a, **_k: None
        try:
            code = netlist.main((), lambda: Path("/made-up"), answering([0xDEAD]))
        finally:
            builtins.print = original

        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
