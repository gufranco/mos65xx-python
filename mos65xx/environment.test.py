import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import NoReturn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_module(name: str, where: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


environment = load_module("environment", Path(__file__).resolve().parent / "environment.py")


class ObservationTest(unittest.TestCase):
    def test_an_observation_carries_what_was_looked_at(self) -> None:
        # Arrange
        name = "thing"

        # Act
        one = environment.Observation(name, True, "found", None)

        # Assert
        self.assertEqual(one.name, "thing")

    def test_a_failing_one_may_carry_what_to_do_about_it(self) -> None:
        # Arrange
        advice = "install it"

        # Act
        one = environment.Observation("thing", False, "missing", advice)

        # Assert
        self.assertEqual(one.advice, "install it")


class InterpreterTest(unittest.TestCase):
    def test_the_command_that_runs_is_the_one_reported(self) -> None:
        # Arrange
        def look(name: str) -> bool:
            return name == "python3"

        # Act
        found = environment.interpreter(look=look)

        # Assert
        self.assertIn("python3", found.detail)

    def test_a_machine_with_only_python_says_to_use_python(self) -> None:
        # Arrange
        def look(name: str) -> bool:
            return name == "python"

        # Act
        found = environment.interpreter(look=look)

        # Assert
        self.assertEqual(("python" in found.detail, "python3" in found.detail), (True, False))

    def test_windows_py_launcher_is_reported_when_it_is_all_there_is(self) -> None:
        # Arrange
        def look(name: str) -> bool:
            return name == "py"

        # Act
        found = environment.interpreter(look=look)

        # Assert
        self.assertIn("py -3", found.detail)

    def test_a_machine_where_none_of_them_resolve_is_not_ok(self) -> None:
        # Arrange
        def look(_name: str) -> bool:
            return False

        # Act
        found = environment.interpreter(look=look)

        # Assert
        self.assertFalse(found.ok)

    def test_and_says_what_to_do_about_it(self) -> None:
        # Arrange
        def look(_name: str) -> bool:
            return False

        # Act
        found = environment.interpreter(look=look)

        # Assert
        self.assertIsInstance(found.advice, str)
        self.assertNotEqual(found.advice, "")


class EncodingTest(unittest.TestCase):
    def test_utf8_output_is_fine(self) -> None:
        # Arrange
        encoding = "utf-8"

        # Act
        found = environment.output_encoding(encoding=encoding)

        # Assert
        self.assertTrue(found.ok)

    def test_a_legacy_windows_codepage_is_not(self) -> None:
        # Arrange
        encoding = "cp1252"

        # Act
        found = environment.output_encoding(encoding=encoding)

        # Assert
        self.assertFalse(found.ok)

    def test_and_the_advice_names_the_switch_that_fixes_it(self) -> None:
        # Arrange
        encoding = "cp1252"

        # Act
        found = environment.output_encoding(encoding=encoding)

        # Assert
        self.assertIn("PYTHONUTF8", found.advice)

    def test_an_unknown_encoding_is_reported_rather_than_guessed(self) -> None:
        # Arrange
        encoding = None

        # Act
        found = environment.output_encoding(encoding=encoding)

        # Assert
        self.assertFalse(found.ok)


class ToolTest(unittest.TestCase):
    def test_a_tool_that_is_present_is_reported_with_where(self) -> None:
        # Arrange
        def look(_name: str) -> str | None:
            return "/usr/bin/git"

        # Act
        found = environment.tool("git", look=look)

        # Assert
        self.assertTrue(found.ok)

    def test_one_that_is_absent_is_not_ok(self) -> None:
        # Arrange
        def look(_name: str) -> str | None:
            return None

        # Act
        found = environment.tool("git", look=look)

        # Assert
        self.assertFalse(found.ok)

    def test_an_optional_tool_that_is_absent_is_still_ok(self) -> None:
        # Arrange
        def look(_name: str) -> str | None:
            return None

        # Act
        found = environment.tool("docker", look=look, required=False)

        # Assert
        self.assertTrue(found.ok)

    def test_but_says_it_was_not_found(self) -> None:
        # Arrange
        def look(_name: str) -> str | None:
            return None

        # Act
        found = environment.tool("docker", look=look, required=False)

        # Assert
        self.assertIn("not found", found.detail)


class LocaleTest(unittest.TestCase):
    def test_utf8_mode_on_is_fine_whatever_the_locale_says(self) -> None:
        # Arrange
        preferred = "cp1252"

        # Act
        found = environment.locale_setting(preferred=preferred, utf8=1)

        # Assert
        self.assertTrue(found.ok)

    def test_a_utf8_locale_is_fine_with_the_mode_off(self) -> None:
        # Arrange
        preferred = "UTF-8"

        # Act
        found = environment.locale_setting(preferred=preferred, utf8=0)

        # Assert
        self.assertTrue(found.ok)

    def test_a_legacy_locale_with_the_mode_off_is_not(self) -> None:
        # Arrange
        preferred = "cp1252"

        # Act
        found = environment.locale_setting(preferred=preferred, utf8=0)

        # Assert
        self.assertFalse(found.ok)

    def test_and_the_advice_names_the_switch(self) -> None:
        # Arrange
        preferred = "cp1252"

        # Act
        found = environment.locale_setting(preferred=preferred, utf8=0)

        # Assert
        self.assertIn("PYTHONUTF8", found.advice)


class ReportTest(unittest.TestCase):
    def test_every_observation_becomes_a_line(self) -> None:
        # Arrange
        observed = len(environment.observations(ROOT))

        # Act
        found = environment.lines(ROOT)

        # Assert
        self.assertGreaterEqual(len(found), observed)

    def test_a_line_says_whether_its_check_passed(self) -> None:
        # Arrange
        openings = ("  ok  ", "     !", "       ")

        # Act
        found = environment.lines(ROOT)

        # Assert
        self.assertEqual([line for line in found if not line.startswith(openings)], [])

    def test_advice_is_printed_under_the_checks_that_failed(self) -> None:
        # Arrange
        unwell = [one for one in environment.observations(ROOT) if not one.ok and one.advice]

        # Act
        found = environment.lines(ROOT)

        # Assert
        self.assertEqual(len([x for x in found if x.startswith("         ")]), len(unwell))

    def test_a_failing_check_prints_its_advice_underneath(self) -> None:
        # Arrange
        unwell = [environment.Observation("thing", False, "not well", "do this")]

        # Act
        found = environment.lines(ROOT, unwell)

        # Assert
        self.assertEqual(found[1].strip(), "thing: do this")

    def test_a_failing_check_with_no_advice_prints_only_its_line(self) -> None:
        # Arrange
        unwell = [environment.Observation("thing", False, "not well", None)]

        # Act
        found = environment.lines(ROOT, unwell)

        # Assert
        self.assertEqual(len(found), 1)

    def test_a_run_from_the_command_line_reports_what_it_found(self) -> None:
        # Arrange
        outcomes = (0, 1)

        # Act
        code = environment.main()

        # Assert
        self.assertIn(code, outcomes)


class SurveyTest(unittest.TestCase):
    def test_every_check_produces_an_observation_on_this_machine(self) -> None:
        # Arrange
        fewest = 8

        # Act
        found = environment.observations(ROOT)

        # Assert
        self.assertGreaterEqual(len(found), fewest)

    def test_none_of_them_raise_whatever_they_find(self) -> None:
        # Arrange
        root = ROOT

        # Act
        found = environment.observations(root)

        # Assert
        self.assertEqual([one.name for one in found if not isinstance(one.detail, str)], [])

    def test_every_one_that_did_not_pass_says_what_to_do(self) -> None:
        # Arrange
        root = ROOT

        # Act
        found = environment.observations(root)

        # Assert
        self.assertEqual([one.name for one in found if not one.ok and not one.advice], [])

    def test_every_observation_has_a_name_of_its_own(self) -> None:
        # Arrange
        root = ROOT

        # Act
        names = [one.name for one in environment.observations(root)]

        # Assert
        self.assertEqual(len(names), len(set(names)))

    def test_a_check_that_throws_is_caught_and_reported_rather_than_lost(self) -> None:
        # Arrange
        def explode(_root: Path) -> NoReturn:
            raise RuntimeError("boom")

        # Act
        found = environment.guarded("thing", explode, ROOT)

        # Assert
        self.assertEqual((found.ok, "RuntimeError" in found.detail), (False, True))

    def test_and_a_check_that_works_is_passed_through_untouched(self) -> None:
        # Arrange
        fine = environment.Observation("thing", True, "fine", None)

        # Act
        found = environment.guarded("thing", lambda _root: fine, ROOT)

        # Assert
        self.assertEqual(found.detail, "fine")


if __name__ == "__main__":
    unittest.main()
