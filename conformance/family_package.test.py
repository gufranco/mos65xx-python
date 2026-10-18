from __future__ import annotations

import ast
import importlib
import sys
import types
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import PACKAGE
from conformance.family_shared import a_folder_holding


class OneDefinitionTest(unittest.TestCase):
    def modules(self) -> list[Any]:
        found = []
        for path in sorted(Path(PACKAGE.__file__ or "").resolve().parent.glob("*.py")):
            if path.name.endswith(".test.py") or path.name == "__init__.py":
                continue
            found.append(importlib.import_module(f"{PACKAGE.__name__}.{path.stem}"))
        return found

    def defined(self, package: Any = None) -> dict[str, list[str]]:
        held = self.modules() if package is None else [getattr(package, n) for n in dir(package)]
        found: dict[str, list[str]] = {}
        for module in held:
            if not isinstance(module, types.ModuleType):
                continue
            for one in vars(module).values():
                if not isinstance(one, type) or not issubclass(one, BaseException):
                    continue
                if one.__module__ != module.__name__:
                    continue
                found.setdefault(one.__qualname__, []).append(module.__name__)
        return {name: sorted(set(where)) for name, where in found.items()}

    def test_no_exception_name_is_defined_twice(self) -> None:
        # Arrange
        defined = self.defined()

        # Act
        twice = {name: where for name, where in defined.items() if len(where) > 1}

        # Assert
        self.assertEqual(twice, {})

    def test_every_exception_a_caller_can_meet_is_published(self) -> None:
        # Arrange
        defined = self.defined()

        # Act
        hidden = [
            name for name in defined if not name.startswith("_") and name not in PACKAGE.__all__
        ]

        # Assert
        self.assertEqual(hidden, [])

    def test_there_are_exceptions_to_check(self) -> None:
        # Arrange
        modules = self.modules()

        # Act
        defined = self.defined()

        # Assert
        self.assertGreater(len(modules), 0)
        self.assertGreater(len(defined), 0)

    def test_an_exception_imported_into_a_module_is_not_counted_as_defined_there(
        self,
    ) -> None:
        # Arrange
        home: Any = types.ModuleType("home")
        borrower: Any = types.ModuleType("borrower")
        held = type("Borrowed", (Exception,), {"__module__": "home"})
        home.Borrowed = held
        borrower.Borrowed = held
        package: Any = types.ModuleType("package")
        package.home = home
        package.borrower = borrower

        # Act
        found = self.defined(package)

        # Assert
        self.assertEqual(found, {"Borrowed": ["home"]})


def still_holding(classes: Any) -> list[str]:
    return [
        one.__qualname__
        for one in classes
        if any("__dict__" in vars(base) for base in one.__mro__[:-1])
    ]


class NoStrayAttributeTest(unittest.TestCase):
    def published(self) -> list[type]:
        found = []
        for name in dir(PACKAGE):
            held = getattr(PACKAGE, name)
            if (
                isinstance(held, type)
                and not issubclass(held, BaseException)
                and held.__module__.startswith(PACKAGE.__name__)
            ):
                found.append(held)
            elif isinstance(held, types.ModuleType) and held.__name__.startswith(PACKAGE.__name__):
                for attr, one in vars(held).items():
                    if attr.startswith("_"):
                        continue
                    if (
                        isinstance(one, type)
                        and one.__module__ == held.__name__
                        and not issubclass(one, BaseException)
                        and not getattr(one, "_is_protocol", False)
                    ):
                        found.append(one)
        return sorted(set(found), key=lambda one: one.__qualname__)

    def test_every_published_class_declares_what_it_holds(self) -> None:
        # Arrange
        published = self.published()

        # Act
        loose = [
            f"{one.__module__.split('.')[-1]}.{one.__qualname__}"
            for one in published
            if "__slots__" not in vars(one)
        ]

        # Assert
        self.assertEqual(loose, [])

    def test_and_none_of_them_kept_a_dict_anyway(self) -> None:
        # Arrange
        published = self.published()

        # Act
        holding = still_holding(published)

        # Assert
        self.assertEqual(holding, [])

    def test_and_one_that_did_would_be_named(self) -> None:
        # Arrange
        loose = type("Loose", (), {})
        slotted = type("Slotted", (loose,), {"__slots__": ()})

        # Act
        found = still_holding([slotted])

        # Assert
        self.assertEqual(len(found), 1)
        self.assertRegex(found[0], r"Slotted$")

    def test_there_are_classes_to_check(self) -> None:
        # Arrange
        smallest = 0

        # Act
        published = self.published()

        # Assert
        self.assertGreater(len(published), smallest)


def imported_by(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add("." * node.level + (node.module or ""))
    return found


def reaching_inside(names: Iterable[str], package: str) -> list[str]:
    return sorted(
        name
        for name in names
        if name.startswith(".") or name == package or name.startswith(package + ".")
    )


class ErrorsCloseNoCycleTest(unittest.TestCase):
    def errors(self) -> Path:
        return Path(PACKAGE.__file__ or "").resolve().parent / "errors.py"

    def test_it_imports_nothing_from_this_package(self) -> None:
        # Arrange
        held = imported_by(self.errors())

        # Act
        inside = reaching_inside(held, PACKAGE.__name__)

        # Assert
        self.assertEqual(inside, [])

    def test_the_reader_of_that_tells_the_package_from_the_standard_library(self) -> None:
        # Arrange
        held = {"__future__", "re", "typing", PACKAGE.__name__, f"{PACKAGE.__name__}.core", "."}

        # Act
        inside = reaching_inside(held, PACKAGE.__name__)

        # Assert
        self.assertEqual(inside, [".", PACKAGE.__name__, f"{PACKAGE.__name__}.core"])

    def test_and_a_package_whose_name_merely_starts_the_same_is_not_inside(self) -> None:
        # Arrange
        held = {f"{PACKAGE.__name__}asm", f"{PACKAGE.__name__}_tools"}

        # Act
        inside = reaching_inside(held, PACKAGE.__name__)

        # Assert
        self.assertEqual(inside, [])

    def test_the_reader_of_that_sees_the_imports_that_are_there(self) -> None:
        # Arrange
        where = a_folder_holding(
            "sample.py", "from __future__ import annotations\nimport re\nfrom . import core\n"
        )

        # Act
        found = imported_by(where / "sample.py")

        # Assert
        self.assertEqual(found, {"__future__", "re", "."})

    def test_and_would_name_one_reaching_back_into_the_package(self) -> None:
        # Arrange
        where = a_folder_holding("sample.py", f"from {PACKAGE.__name__}.core import Cpu\n")

        # Act
        found = imported_by(where / "sample.py")

        # Assert
        self.assertIn(f"{PACKAGE.__name__}.core", found)


class PublishesNamesNotModulesTest(unittest.TestCase):
    def test_no_module_is_published_as_a_name(self) -> None:
        # Arrange
        names = PACKAGE.__all__

        # Act
        published = sorted(
            name for name in names if isinstance(getattr(PACKAGE, name, None), types.ModuleType)
        )

        # Assert
        self.assertEqual(published, [])

    def test_a_module_is_still_reachable_without_being_published(self) -> None:
        # Arrange
        name = "errors"

        # Act
        published = PACKAGE.__all__

        # Assert
        self.assertTrue(hasattr(PACKAGE, name))
        self.assertNotIn(name, published)

    def test_there_are_names_published(self) -> None:
        # Arrange
        smallest = 0

        # Act
        published = len(PACKAGE.__all__)

        # Assert
        self.assertGreater(published, smallest)


if __name__ == "__main__":
    unittest.main()
