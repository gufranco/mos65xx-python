import importlib
import re
import sys
import tempfile
import unittest
import unittest.mock
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn, override

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import doctor


class Complaint(Exception):
    pass


DECLARED: dict[str, Any] = {
    "suites": [{"name": "6502", "path": "6502/v1", "files": 4, "commit": "2f6980a1b2c3d4"}]
}


def a_finding(
    name: str = "something", ok: bool = True, detail: str = "detail", advice: str | None = None
) -> "doctor.Finding":
    return doctor.Finding(name, ok, detail, advice)


def a_definition() -> dict[str, Any]:
    return DECLARED


def a_cache(files: int) -> tempfile.TemporaryDirectory[str]:
    """A suite directory holding that many case files, and nothing else."""
    held = tempfile.TemporaryDirectory()
    where = Path(held.name) / "6502" / "6502" / "v1"
    where.mkdir(parents=True)
    for number in range(files):
        (where / f"{number:02d}.json").write_text("[]")
    return held


class FindingTest(unittest.TestCase):
    def test_a_finding_says_what_was_checked(self) -> None:
        self.assertEqual(a_finding(name="the suite").name, "the suite")

    def test_and_whether_it_was_well(self) -> None:
        self.assertTrue(a_finding(ok=True).ok)
        self.assertFalse(a_finding(ok=False).ok)

    def test_a_healthy_finding_prints_with_a_mark_that_says_so(self) -> None:
        self.assertIn("ok", a_finding(ok=True).line)

    def test_and_an_unhealthy_one_prints_differently(self) -> None:
        self.assertNotIn("ok", a_finding(ok=False).line)

    def test_every_finding_carries_what_it_actually_saw(self) -> None:
        self.assertIn("1604 files", a_finding(detail="1604 files").line)

    def test_an_unhealthy_finding_says_what_to_do_about_it(self) -> None:
        self.assertIn("go and look", a_finding(ok=False, advice="go and look").report)

    def test_a_healthy_one_does_not_repeat_advice_nobody_needs(self) -> None:
        self.assertEqual(a_finding(ok=True, advice="go and look").report, a_finding(ok=True).line)

    def test_an_unhealthy_one_with_nothing_to_advise_says_only_what_it_saw(self) -> None:
        found = a_finding(ok=False, advice=None)

        self.assertEqual(found.report, found.line)

    def test_a_finding_describes_itself_when_printed(self) -> None:
        self.assertIn("something", repr(a_finding()))
        self.assertIn("not ok", repr(a_finding(ok=False)))


class ExaminationTest(unittest.TestCase):
    def test_the_examination_looks_at_the_runtime(self) -> None:
        self.assertIn("python", [one.name for one in doctor.examine()])

    def test_and_the_package(self) -> None:
        found = [one for one in doctor.examine() if one.name == "package"]

        self.assertIn("mos65xx", found[0].detail)

    def test_and_every_part_it_can_build(self) -> None:
        from mos65xx import models

        names = [one.name for one in doctor.examine()]

        for model in models.MODELS:
            self.assertIn(model, names, model)

    def test_and_where_it_looks_for_suites(self) -> None:
        self.assertIn("looking in", [one.name for one in doctor.examine()])

    def test_and_what_the_definition_declares(self) -> None:
        self.assertIn("declared", [one.name for one in doctor.examine()])

    def test_every_finding_carries_a_detail(self) -> None:
        for one in doctor.examine():
            self.assertTrue(one.detail, one.name)

    def test_a_part_that_will_not_build_is_reported_rather_than_hidden(self) -> None:
        def boom(_name: str) -> NoReturn:
            raise Complaint("the core exploded")

        found = [one for one in doctor.examine(build=boom) if one.name == "6502"]

        self.assertFalse(found[0].ok)
        self.assertIn("Complaint: the core exploded", found[0].detail)

    def test_a_part_that_builds_reports_what_makes_it_that_part(self) -> None:
        found = [one for one in doctor.examine() if one.name == "6507"]

        self.assertTrue(found[0].ok)
        self.assertIn("13-bit address", found[0].detail)

    def test_and_the_pins_that_part_actually_brings_out(self) -> None:
        found = [one for one in doctor.examine() if one.name == "6507"]

        self.assertIn("pins rdy", found[0].detail)
        self.assertNotIn("irq", found[0].detail)

    def test_a_part_with_no_decimal_adder_says_so(self) -> None:
        found = [one for one in doctor.examine() if one.name == "2a03"]

        self.assertIn("no decimal", found[0].detail)


class DeclaredTest(unittest.TestCase):
    def test_what_the_definition_names_is_reported(self) -> None:
        found = doctor._declared(a_definition)

        self.assertTrue(found.ok)
        self.assertIn("1 suites: 6502", found.detail)

    def test_an_absent_definition_is_reported_rather_than_raised(self) -> None:
        def missing() -> NoReturn:
            raise FileNotFoundError(2, "No such file or directory")

        found = doctor._declared(missing)

        self.assertTrue(found.ok)
        self.assertIn("normal state of an install", found.detail)

    def test_a_definition_that_will_not_parse_is_reported_rather_than_hidden(self) -> None:
        def broken() -> NoReturn:
            raise Complaint("the definition exploded")

        found = doctor._declared(broken)

        self.assertFalse(found.ok)
        self.assertIn("Complaint: the definition exploded", found.detail)

    def test_a_definition_naming_nothing_is_not_well(self) -> None:
        found = doctor._declared(lambda: {"suites": []})

        self.assertFalse(found.ok)


class SuiteTest(unittest.TestCase):
    def test_a_complete_suite_is_well(self) -> None:
        with a_cache(4) as where:
            found = doctor._suites(a_definition, Path(where))

        self.assertTrue(found[0].ok)
        self.assertIn("4 files", found[0].detail)

    def test_and_names_the_commit_it_is_pinned_at(self) -> None:
        with a_cache(4) as where:
            found = doctor._suites(a_definition, Path(where))

        self.assertIn("2f6980a", found[0].detail)

    def test_a_partial_fetch_is_not_well(self) -> None:
        with a_cache(2) as where:
            found = doctor._suites(a_definition, Path(where))

        self.assertFalse(found[0].ok)
        self.assertIn("the definition names 4", found[0].detail)

    def test_and_says_why_that_matters(self) -> None:
        with a_cache(2) as where:
            found = doctor._suites(a_definition, Path(where))

        self.assertIn("reports a pass", str(found[0].advice))

    def test_a_suite_nobody_fetched_is_the_ordinary_case(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            found = doctor._suites(a_definition, Path(where))

        self.assertTrue(found[0].ok)
        self.assertIn("fresh checkout", found[0].detail)

    def test_a_definition_that_is_absent_leaves_nothing_to_report(self) -> None:
        def missing() -> NoReturn:
            raise FileNotFoundError(2, "No such file or directory")

        self.assertEqual(doctor._suites(missing, Path("/nowhere")), [])

    def test_a_definition_that_will_not_parse_is_reported_here_too(self) -> None:
        def broken() -> NoReturn:
            raise Complaint("the definition exploded")

        found = doctor._suites(broken, Path("/nowhere"))

        self.assertFalse(found[0].ok)
        self.assertIn("Complaint", found[0].detail)

    def test_a_suite_directory_that_cannot_be_read_is_reported(self) -> None:
        class Refuses(Path):
            @override
            def glob(self, *_args: Any, **_kwargs: Any) -> NoReturn:
                raise PermissionError(13, "Permission denied")

            @override
            def __truediv__(self, _other: Any) -> "Refuses":
                return self

        found = doctor._suite(DECLARED["suites"][0], Refuses("/nowhere"))

        self.assertFalse(found.ok)
        self.assertIn("could not be read", found.detail)

    def test_a_suite_with_no_stated_file_count_is_taken_as_it_is(self) -> None:
        with a_cache(2) as where:
            found = doctor._suite({"name": "6502", "path": "6502/v1"}, Path(where))

        self.assertTrue(found.ok)


class DefinitionTest(unittest.TestCase):
    def test_the_definition_is_read_from_the_conformance_directory(self) -> None:
        held = doctor._read_definition()

        self.assertIn("suites", held)


class ReportTest(unittest.TestCase):
    def test_the_report_opens_with_what_is_running(self) -> None:
        lines = doctor.report([a_finding()])

        self.assertIn("mos65xx", lines[0])

    def test_a_clean_report_says_there_is_nothing_to_report(self) -> None:
        lines = doctor.report([a_finding(ok=True), a_finding(ok=True)])

        self.assertIn("2 checks, nothing to report", lines[-1])

    def test_and_one_with_faults_counts_them(self) -> None:
        lines = doctor.report([a_finding(ok=True), a_finding(ok=False)])

        self.assertIn("1 of 2 checks did not pass", lines[-1])

    def test_every_finding_reaches_the_report(self) -> None:
        lines = doctor.report([a_finding(name="one"), a_finding(name="two")])

        self.assertTrue(any("one" in line for line in lines))
        self.assertTrue(any("two" in line for line in lines))


class CommandTest(unittest.TestCase):
    def test_a_clean_machine_exits_zero(self) -> None:
        said: list[str] = []

        code = doctor.main((), lambda: [a_finding(ok=True)], said.append)

        self.assertEqual(code, 0)

    def test_a_machine_with_a_fault_exits_non_zero(self) -> None:
        code = doctor.main((), lambda: [a_finding(ok=False)], lambda _line: None)

        self.assertEqual(code, 1)

    def test_the_report_is_said_rather_than_kept(self) -> None:
        said: list[str] = []

        doctor.main((), lambda: [a_finding(name="the suite")], said.append)

        self.assertTrue(any("the suite" in line for line in said))

    def test_the_default_examination_is_the_real_one(self) -> None:
        checked: list[Callable[..., Sequence[doctor.Finding]]] = []

        def noting() -> list[doctor.Finding]:
            checked.append(doctor.examine)
            return [a_finding()]

        doctor.main((), noting, lambda _line: None)

        self.assertEqual(checked, [doctor.examine])


class PathTest(unittest.TestCase):
    """That the doctor puts the repository on the path when nothing else has.

    Run as a file it has no package to be relative to, so it inserts the
    repository itself. Under the test suite the path is already set, so the line
    never runs and nothing would report it broken.
    """

    def test_the_repository_is_put_on_the_path_when_it_is_not_already_there(self) -> None:
        held = [one for one in sys.path if one != str(doctor.ROOT)]

        with unittest.mock.patch.object(sys, "path", held):
            importlib.reload(doctor)

            self.assertIn(str(doctor.ROOT), held)

    def test_the_version_is_read_out_of_the_file_rather_than_imported(self) -> None:
        found = re.search(
            r'VERSION[^"\']*"([^"]+)"', (doctor.ROOT / "mos65xx" / "version.py").read_text()
        )
        assert found is not None

        self.assertEqual(doctor.VERSION, found.group(1))

    def test_a_version_file_naming_nothing_reads_as_unknown(self) -> None:
        where = Path(tempfile.mkdtemp()) / "version.py"
        where.write_text("NOTHING = 1\n")

        self.assertEqual(doctor._version(where), "unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
