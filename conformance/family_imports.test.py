from __future__ import annotations

import ast
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import PACKAGE, ROOT


class EveryModuleIsReachedTest(unittest.TestCase):
    def an_entry_point(self, path: Path) -> bool:
        return any(
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            for node in ast.walk(ast.parse(path.read_text()))
        )

    def entry_points(self) -> set[str]:
        return {
            path.stem
            for path in Path(PACKAGE.__file__ or "").resolve().parent.glob("*.py")
            if not path.name.endswith(".test.py") and self.an_entry_point(path)
        }

    def modules(self) -> set[str]:
        return {
            path.stem
            for path in Path(PACKAGE.__file__ or "").resolve().parent.glob("*.py")
            if not path.name.endswith(".test.py") and path.stem != "__init__"
        }

    def imported(self, where: Path | None = None) -> set[str]:
        held = ROOT if where is None else where
        name = PACKAGE.__name__
        found: set[str] = set()
        for path in sorted(held.glob("**/*.py")):
            if "node_modules" in path.parts or path.name.endswith(".test.py"):
                continue
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if not (node.level or (node.module or "").split(".")[0] == name):
                        continue
                    if node.module:
                        found.add(node.module.rsplit(".", 1)[-1])
                    found.update(one.name for one in node.names)
                elif isinstance(node, ast.Import):
                    for one in node.names:
                        if one.name.split(".")[0] == name:
                            found.add(one.name.rsplit(".", 1)[-1])
        return found

    def a_tree_holding(self, name: str, text: str) -> Path:
        where = Path(tempfile.mkdtemp())
        (where / name).write_text(text)
        return where

    def test_every_module_in_the_package_is_reached_by_something(self) -> None:
        # Arrange
        published = set(PACKAGE.__all__) | {
            name for name in dir(PACKAGE) if isinstance(getattr(PACKAGE, name), types.ModuleType)
        }

        # Act
        stranded = sorted(self.modules() - published - self.imported() - self.entry_points())

        # Assert
        self.assertEqual(stranded, [])

    def test_the_doctor_is_reached_by_being_run_rather_than_imported(self) -> None:
        # Arrange
        name = "doctor"

        # Act
        points = self.entry_points()

        # Assert
        self.assertIn(name, points)

    def test_a_module_with_no_main_guard_is_not_an_entry_point(self) -> None:
        # Arrange
        where = self.a_tree_holding("quiet.py", "VALUE = 1\n") / "quiet.py"

        # Act
        found = self.an_entry_point(where)

        # Assert
        self.assertFalse(found)

    def test_the_reader_of_that_counts_a_module_a_sibling_imports(self) -> None:
        # Arrange
        where = self.a_tree_holding("one.py", f"from {PACKAGE.__name__} import held\n")

        # Act
        found = self.imported(where)

        # Assert
        self.assertIn("held", found)

    def test_and_one_reached_only_by_a_relative_import(self) -> None:
        # Arrange
        where = self.a_tree_holding("one.py", "from . import sibling\n")

        # Act
        found = self.imported(where)

        # Assert
        self.assertIn("sibling", found)

    def test_and_does_not_count_a_module_reached_only_by_its_own_test(self) -> None:
        # Arrange
        where = self.a_tree_holding("stranded.test.py", "from . import stranded\n")

        # Act
        found = self.imported(where)

        # Assert
        self.assertNotIn("stranded", found)

    def test_and_a_module_reached_by_its_full_dotted_name(self) -> None:
        # Arrange
        where = self.a_tree_holding("one.py", f"import {PACKAGE.__name__}.reached\n")

        # Act
        found = self.imported(where)

        # Assert
        self.assertIn("reached", found)

    def test_and_ignores_a_module_from_somewhere_else_entirely(self) -> None:
        # Arrange
        where = self.a_tree_holding("one.py", "from json import loads\n")

        # Act
        found = self.imported(where)

        # Assert
        self.assertNotIn("loads", found)


class NothingOutsideTheStandardLibraryTest(unittest.TestCase):
    def declared_submodules(self, root: Path | None = None) -> set[str]:
        where = ROOT if root is None else root
        held = where / ".gitmodules"
        if not held.is_file():
            return set()
        found = set()
        for line in held.read_text().splitlines():
            if not line.strip().startswith("path = "):
                continue
            name = line.strip().removeprefix("path = ").strip()
            for path in sorted((where / name).glob("*/__init__.py")):
                found.add(path.parent.name)
        return found

    def imports(self, where: Path) -> set[str]:
        found: set[str] = set()
        for node in ast.walk(ast.parse(where.read_text())):
            if isinstance(node, ast.Import):
                found.update(one.name.split(".")[0] for one in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                found.add(node.module.split(".")[0])
        return found

    def a_file(self, text: str) -> Path:
        where = Path(tempfile.mkdtemp()) / "one.py"
        where.write_text(text)
        return where

    def test_the_package_imports_nothing_it_does_not_ship(self) -> None:
        # Arrange
        allowed = (
            set(sys.stdlib_module_names)
            | {PACKAGE.__name__, "conformance"}
            | self.declared_submodules()
        )

        # Act
        outside = sorted(
            f"{path.name}: {name}"
            for path in Path(PACKAGE.__file__ or "").resolve().parent.glob("*.py")
            if not path.name.endswith(".test.py")
            for name in self.imports(path)
            if name not in allowed
        )

        # Assert
        self.assertEqual(outside, [])

    def test_and_the_readme_says_so(self) -> None:
        # Arrange
        phrase = "no dependencies"

        # Act
        readme = (ROOT / "README.md").read_text()

        # Assert
        self.assertIn(phrase, readme)

    def test_a_submodule_is_allowed_because_it_is_carried_rather_than_fetched(
        self,
    ) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        (where / ".gitmodules").write_text(
            '[submodule "sibling-python"]\n\tpath = sibling-python\n'
            "\turl = https://example.invalid/sibling.git\n"
        )
        (where / "sibling-python" / "sibling").mkdir(parents=True)
        (where / "sibling-python" / "sibling" / "__init__.py").write_text("")

        # Act
        found = self.declared_submodules(where)

        # Assert
        self.assertEqual(found, {"sibling"})

    def test_and_a_repository_with_none_declares_none(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())

        # Act
        found = self.declared_submodules(where)

        # Assert
        self.assertEqual(found, set())

    def test_the_reader_of_that_sees_an_import_from_outside(self) -> None:
        # Arrange
        where = self.a_file("import json\nimport numpy\nfrom yaml import safe_load\n")

        # Act
        held = self.imports(where)

        # Assert
        self.assertEqual(sorted(held - set(sys.stdlib_module_names)), ["numpy", "yaml"])

    def test_and_reads_a_relative_import_as_the_package_itself(self) -> None:
        # Arrange
        where = self.a_file("from . import sibling\nfrom .errors import Refused\n")

        # Act
        found = self.imports(where)

        # Assert
        self.assertEqual(found, set())


if __name__ == "__main__":
    unittest.main()
