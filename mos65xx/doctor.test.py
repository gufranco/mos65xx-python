import importlib
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import MODELS, doctor


class Complaint(Exception):
    pass


class WillNotReset:
    pc = 0

    def reset(self) -> NoReturn:
        raise Complaint("the pin did nothing")


def a_finding(
    name: str = "something", ok: bool = True, detail: str = "detail", advice: str | None = None
) -> "doctor.Finding":
    return doctor.Finding(name, ok, detail, advice)


def named(found: Sequence["doctor.Finding"], name: str) -> "doctor.Finding":
    return next(one for one in found if one.name == name)


class FindingTest(unittest.TestCase):
    def test_a_finding_says_what_was_checked(self) -> None:
        # Arrange
        name = "the suite"

        # Act
        found = a_finding(name=name)

        # Assert
        self.assertEqual(found.name, "the suite")

    def test_and_whether_it_was_well(self) -> None:
        # Arrange
        states = (True, False)

        # Act
        found = [a_finding(ok=state).ok for state in states]

        # Assert
        self.assertEqual(found, [True, False])

    def test_a_healthy_finding_prints_with_a_mark_that_says_so(self) -> None:
        # Arrange
        found = a_finding(ok=True)

        # Act
        line = found.line

        # Assert
        self.assertIn("ok", line)

    def test_and_an_unhealthy_one_prints_differently(self) -> None:
        # Arrange
        found = a_finding(ok=False)

        # Act
        line = found.line

        # Assert
        self.assertNotIn("ok", line)

    def test_every_finding_carries_what_it_actually_saw(self) -> None:
        # Arrange
        found = a_finding(detail="1604 files")

        # Act
        line = found.line

        # Assert
        self.assertIn("1604 files", line)

    def test_an_unhealthy_finding_says_what_to_do_about_it(self) -> None:
        # Arrange
        found = a_finding(ok=False, advice="go and look")

        # Act
        report = found.report

        # Assert
        self.assertIn("go and look", report)

    def test_a_healthy_one_does_not_repeat_advice_nobody_needs(self) -> None:
        # Arrange
        found = a_finding(ok=True, advice="go and look")

        # Act
        report = found.report

        # Assert
        self.assertEqual(report, a_finding(ok=True).line)

    def test_an_unhealthy_one_with_nothing_to_advise_says_only_what_it_saw(self) -> None:
        # Arrange
        found = a_finding(ok=False, advice=None)

        # Act
        report = found.report

        # Assert
        self.assertEqual(report, found.line)

    def test_a_finding_describes_itself_when_printed(self) -> None:
        # Arrange
        found = a_finding(ok=False)

        # Act
        described = repr(found)

        # Assert
        self.assertEqual(described, "<Finding something not ok>")


class ExaminationTest(unittest.TestCase):
    def test_the_examination_looks_at_the_runtime(self) -> None:
        # Arrange
        examine = doctor.examine

        # Act
        found = examine()

        # Assert
        self.assertIn("python", [one.name for one in found])

    def test_and_the_package(self) -> None:
        # Arrange
        examine = doctor.examine

        # Act
        found = examine()

        # Assert
        self.assertIn("mos65xx", named(found, "package").detail)

    def test_and_every_part_it_can_build(self) -> None:
        # Arrange
        expected = sorted(MODELS)

        # Act
        found = doctor.examine()

        # Assert
        self.assertEqual([name for name in expected if name not in {o.name for o in found}], [])

    def test_and_where_it_looks_for_suites(self) -> None:
        # Arrange
        examine = doctor.examine

        # Act
        found = examine()

        # Assert
        self.assertIn("looking in", [one.name for one in found])

    def test_and_what_the_definition_declares(self) -> None:
        # Arrange
        examine = doctor.examine

        # Act
        found = examine()

        # Assert
        self.assertIn("declared", [one.name for one in found])

    def test_every_finding_carries_a_detail(self) -> None:
        # Arrange
        examine = doctor.examine

        # Act
        found = examine()

        # Assert
        self.assertEqual([one.name for one in found if not one.detail], [])

    def test_a_part_that_will_not_build_is_reported_rather_than_hidden(self) -> None:
        # Arrange
        def boom(_name: str) -> NoReturn:
            raise Complaint("the core exploded")

        # Act
        found = named(doctor.examine(build=boom), "6502")

        # Assert
        self.assertEqual((found.ok, found.detail), (False, "Complaint: the core exploded"))

    def test_a_part_that_builds_and_will_not_reset_is_reported_as_broken(self) -> None:
        # Arrange
        def build(_name: str) -> Any:
            return WillNotReset()

        # Act
        found = named(doctor.examine(build=build), "6502")

        # Assert
        self.assertEqual((found.ok, found.detail), (False, "Complaint: the pin did nothing"))

    def test_a_part_that_builds_reports_where_the_reset_left_it(self) -> None:
        # Arrange
        examine = doctor.examine

        # Act
        found = named(examine(), "6502")

        # Assert
        self.assertIn("resets to $", found.detail)

    def test_a_part_that_builds_reports_what_makes_it_that_part(self) -> None:
        # Arrange
        examine = doctor.examine

        # Act
        found = named(examine(), "6507")

        # Assert
        self.assertEqual((found.ok, "13-bit address" in found.detail), (True, True))

    def test_and_the_pins_that_part_actually_brings_out(self) -> None:
        # Arrange
        examine = doctor.examine

        # Act
        found = named(examine(), "6507")

        # Assert
        self.assertEqual(("pins rdy" in found.detail, "irq" in found.detail), (True, False))

    def test_a_part_with_no_decimal_adder_says_so(self) -> None:
        # Arrange
        examine = doctor.examine

        # Act
        found = named(examine(), "2a03")

        # Assert
        self.assertIn("no decimal", found.detail)


class ReportTest(unittest.TestCase):
    def test_the_report_opens_with_what_is_running(self) -> None:
        # Arrange
        found = [a_finding()]

        # Act
        lines = doctor.report(found)

        # Assert
        self.assertTrue(lines[0].startswith(f"mos65xx {doctor.VERSION} on "))

    def test_a_clean_report_says_there_is_nothing_to_report(self) -> None:
        # Arrange
        found = [a_finding(ok=True), a_finding(ok=True)]

        # Act
        lines = doctor.report(found)

        # Assert
        self.assertEqual(lines[-1], "  2 checks, nothing to report")

    def test_and_one_with_faults_counts_them(self) -> None:
        # Arrange
        found = [a_finding(ok=True), a_finding(ok=False)]

        # Act
        lines = doctor.report(found)

        # Assert
        self.assertEqual(lines[-1], "  1 of 2 checks did not pass")

    def test_every_finding_reaches_the_report(self) -> None:
        # Arrange
        found = [a_finding(name="one"), a_finding(name="two")]

        # Act
        lines = doctor.report(found)

        # Assert
        self.assertEqual(
            [one.line in lines for one in found],
            [True, True],
        )


class CommandTest(unittest.TestCase):
    def test_a_clean_machine_exits_zero(self) -> None:
        # Arrange
        said: list[str] = []

        # Act
        code = doctor.main((), lambda: [a_finding(ok=True)], said.append)

        # Assert
        self.assertEqual(code, 0)

    def test_a_machine_with_a_fault_exits_non_zero(self) -> None:
        # Arrange
        said: list[str] = []

        # Act
        code = doctor.main((), lambda: [a_finding(ok=False)], said.append)

        # Assert
        self.assertEqual(code, 1)

    def test_the_report_is_said_rather_than_kept(self) -> None:
        # Arrange
        said: list[str] = []

        # Act
        doctor.main((), lambda: [a_finding(name="the suite")], said.append)

        # Assert
        self.assertIn(a_finding(name="the suite").line, said)

    def test_the_default_examination_is_the_real_one(self) -> None:
        # Arrange
        checked: list[Callable[..., Sequence[doctor.Finding]]] = []

        def noting() -> list[doctor.Finding]:
            checked.append(doctor.examine)
            return [a_finding()]

        # Act
        doctor.main((), noting, lambda _line: None)

        # Assert
        self.assertEqual(checked, [doctor.examine])


class PathTest(unittest.TestCase):
    def test_the_repository_is_put_on_the_path_when_it_is_not_already_there(self) -> None:
        # Arrange
        held = [one for one in sys.path if one != str(doctor.ROOT)]

        # Act
        with unittest.mock.patch.object(sys, "path", held):
            importlib.reload(doctor)

        # Assert
        self.assertIn(str(doctor.ROOT), held)

    def test_the_version_is_read_out_of_the_file_rather_than_imported(self) -> None:
        # Arrange
        found = re.search(
            r'VERSION[^"\']*"([^"]+)"', (doctor.ROOT / "mos65xx" / "version.py").read_text()
        )
        assert found is not None

        # Act
        read = doctor.installed_version()

        # Assert
        self.assertEqual((read, doctor.VERSION), (found.group(1), found.group(1)))

    def test_run_as_the_readme_says_from_outside_the_repository_it_reports(self) -> None:
        # Arrange
        script = doctor.ROOT / "mos65xx" / "doctor.py"
        elsewhere = tempfile.mkdtemp()

        # Act
        finished = subprocess.run(
            [sys.executable, str(script)],
            cwd=elsewhere,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        # Assert
        self.assertEqual(finished.stderr, "")
        self.assertRegex(finished.stdout.splitlines()[-1], r"^  \d+ (checks|of \d+ checks)")

    def test_a_version_file_naming_nothing_reads_as_unknown(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp()) / "version.py"
        where.write_text("NOTHING = 1\n")

        # Act
        read = doctor.installed_version(where)

        # Assert
        self.assertEqual(read, "unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
