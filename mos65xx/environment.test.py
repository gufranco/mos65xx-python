import importlib.util
import sys
import tempfile
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


def nested(where: Path, top: str, leaf: str) -> None:
    deep = where.joinpath(*filter(None, (top, "a" * 120, "b" * 120)))
    deep.mkdir(parents=True)
    (deep / leaf).write_bytes(b"")


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


class LineEndingTest(unittest.TestCase):
    def test_a_tree_whose_text_files_use_line_feeds_is_fine(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        (where / "a.md").write_bytes(b"one\ntwo\n")

        # Act
        found = environment.line_endings(where)

        # Assert
        self.assertTrue(found.ok)

    def test_a_tree_that_git_converted_to_carriage_returns_is_not(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        (where / "a.md").write_bytes(b"one\r\ntwo\r\n")

        # Act
        found = environment.line_endings(where)

        # Assert
        self.assertFalse(found.ok)

    def test_and_the_advice_names_the_setting_that_caused_it(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        (where / "a.md").write_bytes(b"one\r\n")

        # Act
        found = environment.line_endings(where)

        # Assert
        self.assertIn("autocrlf", found.advice)

    def test_a_tree_with_nothing_to_read_says_so_rather_than_passing(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())

        # Act
        found = environment.line_endings(where)

        # Assert
        self.assertIn("nothing", found.detail)

    def test_a_sample_that_fills_up_stops_reading(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        for n in range(3):
            (where / f"{n}.md").write_bytes(b"one\n")

        # Act
        found = environment.line_endings(where, sample=1)

        # Assert
        self.assertIn("1 sampled", found.detail)

    def test_a_file_it_cannot_read_is_passed_over_rather_than_counted(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        (where / "a.md").write_bytes(b"one\n")
        bad = where / "b.md"
        bad.write_bytes(b"two\r\n")
        bad.chmod(0o000)
        self.addCleanup(bad.chmod, 0o600)

        # Act
        found = environment.line_endings(where)

        # Assert
        self.assertTrue(found.ok)


class CaseTest(unittest.TestCase):
    def test_a_case_sensitive_filesystem_is_reported_as_such(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())

        # Act
        found = environment.filesystem_case(where)

        # Assert
        self.assertIn("sensitive", found.detail)

    def test_the_check_never_fails_a_machine_for_its_filesystem(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())

        # Act
        found = environment.filesystem_case(where)

        # Assert
        self.assertTrue(found.ok)


class PathBudgetTest(unittest.TestCase):
    def test_a_short_path_on_windows_is_fine(self) -> None:
        # Arrange
        root = Path("C:/a")

        # Act
        found = environment.path_budget(root, windows=True, longest=80)

        # Assert
        self.assertTrue(found.ok)

    def test_a_path_past_the_windows_limit_is_not(self) -> None:
        # Arrange
        root = Path("C:/a")

        # Act
        found = environment.path_budget(root, windows=True, longest=300)

        # Assert
        self.assertFalse(found.ok)

    def test_and_the_advice_names_the_setting_that_lifts_it(self) -> None:
        # Arrange
        root = Path("C:/a")

        # Act
        found = environment.path_budget(root, windows=True, longest=300)

        # Assert
        self.assertIn("LongPathsEnabled", found.advice)

    def test_the_same_length_elsewhere_is_still_reported(self) -> None:
        # Arrange
        root = Path("/a")

        # Act
        found = environment.path_budget(root, windows=False, longest=300)

        # Assert
        self.assertFalse(found.ok)

    def test_because_the_tree_is_shared_rather_than_local_to_one_machine(self) -> None:
        # Arrange
        roots = ((Path("/a"), False), (Path("C:/a"), True))

        # Act
        found = [environment.path_budget(root, windows=on, longest=300).ok for root, on in roots]

        # Assert
        self.assertEqual(found, [False, False])

    def test_the_headroom_a_windows_checkout_would_have_is_reported(self) -> None:
        # Arrange
        root = Path("/a")

        # Act
        found = environment.path_budget(root, windows=False, longest=100)

        # Assert
        self.assertIn("160", found.detail)

    def test_a_tree_that_leaves_no_room_for_a_checkout_path_is_flagged_anywhere(self) -> None:
        # Arrange
        root = Path("/a")

        # Act
        found = environment.path_budget(root, windows=False, longest=250)

        # Assert
        self.assertFalse(found.ok)

    def test_and_the_advice_says_it_is_about_windows_rather_than_here(self) -> None:
        # Arrange
        root = Path("/a")

        # Act
        found = environment.path_budget(root, windows=False, longest=250)

        # Assert
        self.assertIn("Windows", found.advice)

    def test_a_tree_with_room_to_spare_passes_on_every_system(self) -> None:
        # Arrange
        systems = (True, False)

        # Act
        found = [environment.path_budget(Path("/a"), windows=on, longest=100).ok for on in systems]

        # Assert
        self.assertEqual(found, [True, True])

    def test_a_generated_directory_is_reported_without_failing_the_check(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        nested(where, "node_modules", "c.js")

        # Act
        found = environment.path_budget(where)

        # Assert
        self.assertTrue(found.ok)

    def test_but_the_same_depth_in_tracked_content_does_fail_it(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        nested(where, "", "c.py")

        # Act
        found = environment.path_budget(where)

        # Assert
        self.assertFalse(found.ok)

    def test_and_a_generated_one_is_still_named_so_it_is_not_a_surprise(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        nested(where, "node_modules", "c.js")

        # Act
        found = environment.path_budget(where)

        # Assert
        self.assertIn("node_modules", found.detail)


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


class SpaceTest(unittest.TestCase):
    def test_plenty_of_room_is_fine(self) -> None:
        # Arrange
        def measure(_path: Path) -> int:
            return 40 * 1024**3

        # Act
        found = environment.free_space(ROOT, measure=measure)

        # Assert
        self.assertTrue(found.ok)

    def test_a_nearly_full_disk_is_not(self) -> None:
        # Arrange
        def measure(_path: Path) -> int:
            return 100 * 1024**2

        # Act
        found = environment.free_space(ROOT, measure=measure)

        # Assert
        self.assertFalse(found.ok)

    def test_a_disk_it_cannot_measure_is_reported_rather_than_assumed(self) -> None:
        # Arrange
        def refuse(_path: Path) -> int:
            raise OSError("no")

        # Act
        found = environment.free_space(ROOT, measure=refuse)

        # Assert
        self.assertFalse(found.ok)

    def test_a_case_insensitive_answer_is_reported_and_is_not_a_fault(self) -> None:
        # Arrange
        insensitive = True

        # Act
        found = environment.filesystem_case(ROOT, insensitive=insensitive)

        # Assert
        self.assertEqual((found.ok, "insensitive" in found.detail), (True, True))

    def test_a_case_sensitive_answer_is_reported_the_same_way(self) -> None:
        # Arrange
        insensitive = False

        # Act
        found = environment.filesystem_case(ROOT, insensitive=insensitive)

        # Assert
        self.assertEqual((found.ok, found.detail), (True, "case sensitive"))

    def test_a_root_it_cannot_write_to_is_reported_rather_than_raised(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        where.chmod(0o500)
        self.addCleanup(where.chmod, 0o700)

        # Act
        found = environment.filesystem_case(where)

        # Assert
        self.assertEqual((found.ok, "could not probe" in found.detail), (True, True))


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
