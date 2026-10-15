import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import contextlib  # noqa: E402
import io  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import zipfile  # noqa: E402

from conformance import package  # noqa: E402


def wheel(where: Path, names: list[str]) -> Path:
    path = where / "mos65xx-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "")
    return path


def complete() -> list[str]:
    return [f"mos65xx/{one}" for one in package.modules()]


def run_main(argv: list[str]) -> tuple[int, str]:
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = package.main(argv)
    return code, said.getvalue()


class ModulesTest(unittest.TestCase):
    def test_it_finds_every_module_the_package_carries(self) -> None:
        # Arrange
        expected = {"__init__.py", "doctor.py", "environment.py"}

        # Act
        found = package.modules()

        # Assert
        self.assertTrue(expected.issubset(found), found)

    def test_it_never_counts_a_test_file_as_a_module(self) -> None:
        # Arrange
        suffix = ".test.py"

        # Act
        found = package.modules()

        # Assert
        self.assertEqual([one for one in found if one.endswith(suffix)], [])

    def test_the_package_carries_test_files_for_there_to_be_any_to_exclude(self) -> None:
        # Arrange
        directory = ROOT / "mos65xx"

        # Act
        tests = sorted(directory.glob("*.test.py"))

        # Assert
        self.assertGreater(len(tests), 0)


class AuditTest(unittest.TestCase):
    def test_a_wheel_holding_every_module_and_no_test_is_clean(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        path = wheel(where, complete())

        # Act
        found = package.audit(path)

        # Assert
        self.assertEqual(found, [])

    def test_a_test_file_in_the_wheel_is_named(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        path = wheel(where, [*complete(), "mos65xx/doctor.test.py"])

        # Act
        found = package.audit(path)

        # Assert
        self.assertEqual(found, ["ships a test: mos65xx/doctor.test.py"])

    def test_a_module_missing_from_the_wheel_is_named(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        path = wheel(where, [one for one in complete() if not one.endswith("/doctor.py")])

        # Act
        found = package.audit(path)

        # Assert
        self.assertEqual(found, ["missing a module: mos65xx/doctor.py"])

    def test_a_wheel_holding_nothing_of_the_package_names_every_module(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        path = wheel(where, ["other/thing.py"])

        # Act
        found = package.audit(path)

        # Assert
        self.assertEqual(len(found), len(package.modules()))


class MainTest(unittest.TestCase):
    def test_naming_no_wheel_explains_how_to_call_it(self) -> None:
        # Arrange
        argv: list[str] = []

        # Act
        code, said = run_main(argv)

        # Assert
        self.assertEqual(code, 2)
        self.assertIn("usage", said)

    def test_a_wheel_that_is_not_there_fails_rather_than_passing(self) -> None:
        # Arrange
        absent = Path(tempfile.mkdtemp()) / "absent.whl"

        # Act
        code, said = run_main([str(absent)])

        # Assert
        self.assertEqual(code, 1)
        self.assertIn("absent", said)

    def test_a_clean_wheel_reports_what_it_examined(self) -> None:
        # Arrange
        path = wheel(Path(tempfile.mkdtemp()), complete())

        # Act
        code, said = run_main([str(path)])

        # Assert
        self.assertEqual(code, 0)
        self.assertIn(f"{len(package.modules())} modules present, no test shipped", said)

    def test_a_faulty_wheel_names_each_fault_and_fails(self) -> None:
        # Arrange
        path = wheel(Path(tempfile.mkdtemp()), [*complete(), "mos65xx/environment.test.py"])

        # Act
        code, said = run_main([str(path)])

        # Assert
        self.assertEqual(code, 1)
        self.assertIn("ships a test: mos65xx/environment.test.py", said)


if __name__ == "__main__":
    unittest.main()
