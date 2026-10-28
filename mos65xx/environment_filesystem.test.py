import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

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

    def test_a_checkout_kept_under_external_is_not_sampled(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        (where / "external" / "upstream").mkdir(parents=True)
        (where / "external" / "upstream" / "readme.txt").write_bytes(b"one\r\n")
        (where / "a.md").write_bytes(b"one\n")

        # Act
        found = environment.line_endings(where)

        # Assert
        self.assertEqual((found.ok, found.detail), (True, "line feeds in 1 sampled files"))

    def test_notes_kept_under_docs_are_not_sampled(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        (where / "docs").mkdir()
        (where / "docs" / "notes.txt").write_bytes(b"one\r\n")
        (where / "a.md").write_bytes(b"one\n")

        # Act
        found = environment.line_endings(where)

        # Assert
        self.assertEqual((found.ok, found.detail), (True, "line feeds in 1 sampled files"))

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


if __name__ == "__main__":
    unittest.main()
