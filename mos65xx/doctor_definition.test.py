import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, NoReturn, override

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import doctor


class Complaint(Exception):
    pass


DECLARED: dict[str, Any] = {
    "suites": [{"name": "6502", "path": "6502/v1", "files": 4, "commit": "2f6980a1b2c3d4"}]
}


def a_definition() -> dict[str, Any]:
    return DECLARED


def a_cache(files: int) -> tempfile.TemporaryDirectory[str]:
    held = tempfile.TemporaryDirectory()
    where = Path(held.name) / "6502" / "6502" / "v1"
    where.mkdir(parents=True)
    for number in range(files):
        (where / f"{number:02d}.json").write_text("[]")
    return held


def missing() -> NoReturn:
    raise FileNotFoundError(2, "No such file or directory")


def broken() -> NoReturn:
    raise Complaint("the definition exploded")


class DeclaredTest(unittest.TestCase):
    def test_what_the_definition_names_is_reported(self) -> None:
        # Arrange
        read = a_definition

        # Act
        found = doctor.check_declared(read)

        # Assert
        self.assertEqual((found.ok, found.detail), (True, "1 suites: 6502"))

    def test_an_absent_definition_is_reported_rather_than_raised(self) -> None:
        # Arrange
        read = missing

        # Act
        found = doctor.check_declared(read)

        # Assert
        self.assertEqual((found.ok, "normal state of an install" in found.detail), (True, True))

    def test_a_definition_that_will_not_parse_is_reported_rather_than_hidden(self) -> None:
        # Arrange
        read = broken

        # Act
        found = doctor.check_declared(read)

        # Assert
        self.assertEqual((found.ok, found.detail), (False, "Complaint: the definition exploded"))

    def test_a_definition_naming_nothing_is_not_well(self) -> None:
        # Arrange
        def empty() -> dict[str, Any]:
            return {"suites": []}

        # Act
        found = doctor.check_declared(empty)

        # Assert
        self.assertFalse(found.ok)


class SuiteTest(unittest.TestCase):
    def test_a_complete_suite_is_well(self) -> None:
        # Arrange
        held = a_cache(4)
        self.addCleanup(held.cleanup)

        # Act
        found = doctor.check_suites(a_definition, Path(held.name))

        # Assert
        self.assertEqual((found[0].ok, "4 files" in found[0].detail), (True, True))

    def test_and_names_the_commit_it_is_pinned_at(self) -> None:
        # Arrange
        held = a_cache(4)
        self.addCleanup(held.cleanup)

        # Act
        found = doctor.check_suites(a_definition, Path(held.name))

        # Assert
        self.assertIn("pinned at 2f6980a", found[0].detail)

    def test_a_partial_fetch_is_not_well(self) -> None:
        # Arrange
        held = a_cache(2)
        self.addCleanup(held.cleanup)

        # Act
        found = doctor.check_suites(a_definition, Path(held.name))

        # Assert
        self.assertEqual((found[0].ok, "the definition names 4" in found[0].detail), (False, True))

    def test_and_says_why_that_matters(self) -> None:
        # Arrange
        held = a_cache(2)
        self.addCleanup(held.cleanup)

        # Act
        found = doctor.check_suites(a_definition, Path(held.name))

        # Assert
        self.assertIn("reports a pass", str(found[0].advice))

    def test_a_suite_nobody_fetched_is_the_ordinary_case(self) -> None:
        # Arrange
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)

        # Act
        found = doctor.check_suites(a_definition, Path(held.name))

        # Assert
        self.assertEqual((found[0].ok, "fresh checkout" in found[0].detail), (True, True))

    def test_a_definition_that_is_absent_leaves_nothing_to_report(self) -> None:
        # Arrange
        read = missing

        # Act
        found = doctor.check_suites(read, Path("/nowhere"))

        # Assert
        self.assertEqual(found, [])

    def test_a_definition_that_will_not_parse_is_reported_here_too(self) -> None:
        # Arrange
        read = broken

        # Act
        found = doctor.check_suites(read, Path("/nowhere"))

        # Assert
        self.assertEqual(
            (found[0].ok, found[0].detail), (False, "Complaint: the definition exploded")
        )

    def test_a_suite_directory_that_cannot_be_read_is_reported(self) -> None:
        # Arrange
        class Refuses(Path):
            @override
            def glob(self, *_args: Any, **_kwargs: Any) -> NoReturn:
                raise PermissionError(13, "Permission denied")

            @override
            def __truediv__(self, _other: Any) -> "Refuses":
                return self

        # Act
        found = doctor.check_suite(DECLARED["suites"][0], Refuses("/nowhere"))

        # Assert
        self.assertEqual((found.ok, "could not be read" in found.detail), (False, True))

    def test_a_suite_with_no_stated_file_count_is_taken_as_it_is(self) -> None:
        # Arrange
        held = a_cache(2)
        self.addCleanup(held.cleanup)

        # Act
        found = doctor.check_suite({"name": "6502", "path": "6502/v1"}, Path(held.name))

        # Assert
        self.assertTrue(found.ok)


class DefinitionTest(unittest.TestCase):
    def test_the_definition_is_read_from_the_conformance_directory(self) -> None:
        # Arrange
        where = doctor.DEFINITION

        # Act
        held = doctor.read_definition(where)

        # Assert
        self.assertEqual(where.parent.name, "conformance")
        self.assertIn("suites", held)

    def test_by_default_too(self) -> None:
        # Arrange
        expected = doctor.read_definition(doctor.DEFINITION)

        # Act
        held = doctor.read_definition()

        # Assert
        self.assertEqual(held, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
