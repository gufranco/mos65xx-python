from __future__ import annotations

import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import PACKAGE, ROOT, TOOL_MODULES


def is_private(name: str) -> bool:
    return name.startswith("_") and not name.startswith("__")


def project_modules(tree: ast.Module, package: str) -> set[str]:
    roots = {package, "conformance"}
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in roots:
            bound.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Import):
            bound.update(
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
                if alias.name.split(".")[0] in roots
            )
    return bound


def import_problems(node: ast.AST, package: str, exported: set[str], tools: set[str]) -> list[str]:
    if isinstance(node, ast.Import):
        return [
            f"imports {alias.name}"
            for alias in node.names
            if alias.name.startswith(f"{package}.") and alias.name.split(".")[1] not in tools
        ]
    if not isinstance(node, ast.ImportFrom) or node.module is None:
        return []
    if node.module.startswith(f"{package}."):
        return [] if node.module.split(".")[1] in tools else [f"imports from {node.module}"]
    if node.module == package:
        allowed = exported | tools
        return [
            f"imports {alias.name} from {package}"
            for alias in node.names
            if alias.name not in allowed
        ]
    return []


LOADERS = frozenset(
    {"import_module", "spec_from_file_location", "SourceFileLoader", "run_path", "run_module"}
)


def loaded_inner(text: str, package: str) -> str | None:
    if text.startswith(f"{package}."):
        return text.split(".")[1]
    if f"{package}/" in text:
        return text.split(f"{package}/", 1)[1].split("/", maxsplit=1)[0].removesuffix(".py")
    return None


def load_problems(node: ast.AST, package: str, tools: set[str]) -> list[str]:
    if not isinstance(node, ast.Call):
        return []
    called = (
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
    )
    if called not in LOADERS:
        return []
    pieces = sorted(
        (one.lineno, one.col_offset, one.value)
        for argument in node.args
        for one in ast.walk(argument)
        if isinstance(one, ast.Constant) and isinstance(one.value, str)
    )
    words = [value for _, _, value in pieces]
    candidates = [*words, "/".join(words)]
    return sorted(
        {
            f"loads {inner} from {package}"
            for text in candidates
            if (inner := loaded_inner(text, package)) and inner not in tools | {"__init__"}
        }
    )


def reaches_inside(source: str, package: str, exported: set[str], tools: set[str]) -> list[str]:
    tree = ast.parse(source)
    roots = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == package
    }
    modules = project_modules(tree, package)
    found: list[str] = []
    for node in ast.walk(tree):
        found.extend(import_problems(node, package, exported, tools))
        found.extend(load_problems(node, package, tools))
        if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
            continue
        owner, name = node.value.id, node.attr
        if owner in roots and name not in exported | tools and not name.startswith("__"):
            found.append(f"reaches {package}.{name}")
        elif owner in modules and is_private(name):
            found.append(f"reaches {owner}.{name}")
    return found


def realiased_modules(init_source: str) -> set[str]:
    return {
        alias.name
        for node in ast.walk(ast.parse(init_source))
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None
        for alias in node.names
        if alias.asname == alias.name
    }


def documented_modules(init_source: str, readme: str, package: str) -> set[str]:
    return {
        name
        for name in realiased_modules(init_source)
        if re.search(rf"\b{package}[./]{name}\b(?!\.test)", readme)
        or re.search(rf"from {package} import [^\n]*\b{name}\b", readme)
    }


def public_names() -> set[str]:
    init_source = (ROOT / PACKAGE.__name__ / "__init__.py").read_text()
    readme = (ROOT / "README.md").read_text()
    return set(PACKAGE.__all__) | documented_modules(init_source, readme, PACKAGE.__name__)


def repository_test_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "-c", "submodule.recurse=false", "ls-files", "*.test.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    homes = {PACKAGE.__name__, "conformance"}
    return [ROOT / one for one in listed if Path(one).parts[0] in homes]


class EveryTestUsesThePublicInterfaceTest(unittest.TestCase):
    def test_no_test_reaches_past_what_the_package_exports(self) -> None:
        # Arrange
        exported = public_names()

        # Act
        found = {
            str(path.relative_to(ROOT)): problems
            for path in repository_test_files()
            if (
                problems := reaches_inside(
                    path.read_text(), PACKAGE.__name__, exported, TOOL_MODULES
                )
            )
        }

        # Assert
        self.assertEqual(found, {})

    def test_there_are_package_tests_to_look_at(self) -> None:
        # Arrange
        package = PACKAGE.__name__

        # Act
        found = [path for path in repository_test_files() if path.parts[-2] == package]

        # Assert
        self.assertGreater(len(found), 0)

    def test_an_exported_name_passes(self) -> None:
        # Arrange
        source = "import part\n\nchip = part.Chip('a')\nnames = part.__all__\n"

        # Act
        found = reaches_inside(source, "part", {"Chip"}, set())

        # Assert
        self.assertEqual(found, [])

    def test_a_name_the_package_does_not_export_is_reported(self) -> None:
        # Arrange
        source = "import part as p\n\nwidth = p.tone\n"

        # Act
        found = reaches_inside(source, "part", {"Chip"}, set())

        # Assert
        self.assertEqual(found, ["reaches part.tone"])

    def test_importing_an_inner_module_is_reported(self) -> None:
        # Arrange
        source = "import part.tone\nfrom part.noise import shifted\nfrom part import tone, Chip\n"

        # Act
        found = reaches_inside(source, "part", {"Chip"}, set())

        # Assert
        self.assertEqual(
            found, ["imports part.tone", "imports from part.noise", "imports tone from part"]
        )

    def test_a_tool_module_may_be_imported_and_driven(self) -> None:
        # Arrange
        source = "import part.doctor\nfrom part.doctor import main\nfrom part import doctor\n"

        # Act
        found = reaches_inside(source, "part", {"Chip"}, {"doctor"})

        # Assert
        self.assertEqual(found, [])

    def test_a_private_name_of_any_project_module_is_reported(self) -> None:
        # Arrange
        source = (
            "from conformance import census\nfrom part import doctor\n\n"
            "census._tally\ndoctor._load\n"
        )

        # Act
        found = reaches_inside(source, "part", {"Chip"}, {"doctor"})

        # Assert
        self.assertEqual(found, ["reaches census._tally", "reaches doctor._load"])

    def test_a_private_name_of_something_else_is_left_alone(self) -> None:
        # Arrange
        source = "import json\n\nhandle = json._default_decoder\n"

        # Act
        found = reaches_inside(source, "part", {"Chip"}, set())

        # Assert
        self.assertEqual(found, [])

    def test_a_relative_import_is_left_to_the_other_checks(self) -> None:
        # Arrange
        source = "from . import helper\n"

        # Act
        found = reaches_inside(source, "part", {"Chip"}, set())

        # Assert
        self.assertEqual(found, [])

    def test_loading_an_inner_module_by_name_is_reported(self) -> None:
        # Arrange
        source = "import importlib\n\ntone = importlib.import_module('part.tone')\n"

        # Act
        found = reaches_inside(source, "part", {"Chip"}, set())

        # Assert
        self.assertEqual(found, ["loads tone from part"])

    def test_loading_an_inner_module_by_path_is_reported(self) -> None:
        # Arrange
        source = "spec = spec_from_file_location('t', ROOT / 'part' / 'tone.py')\n"

        # Act
        found = reaches_inside(source, "part", {"Chip"}, set())

        # Assert
        self.assertEqual(found, ["loads tone from part"])

    def test_loading_a_tool_or_something_outside_the_package_passes(self) -> None:
        # Arrange
        source = (
            "import runpy\n\nrunpy.run_path(str(ROOT / 'setup.py'))\n"
            "importlib.import_module('part.doctor')\nloader = make(ROOT / 'part.py')\n"
        )

        # Act
        found = reaches_inside(source, "part", {"Chip"}, {"doctor"})

        # Assert
        self.assertEqual(found, [])

    def test_a_module_reexported_and_documented_for_callers_is_public(self) -> None:
        # Arrange
        init_source = "from . import tiles as tiles\nfrom . import core as core\n"

        # Act
        found = documented_modules(init_source, "Call `from part import tiles` first.", "part")

        # Assert
        self.assertEqual(found, {"tiles"})

    def test_a_module_documented_by_its_path_is_public_too(self) -> None:
        # Arrange
        init_source = "from . import tiles as tiles\n"

        # Act
        found = documented_modules(init_source, "| [`part/tiles.py`](part/tiles.py) |", "part")

        # Assert
        self.assertEqual(found, {"tiles"})

    def test_a_command_running_a_modules_tests_is_not_documentation(self) -> None:
        # Arrange
        init_source = "from . import core as core\n"

        # Act
        found = documented_modules(init_source, "python3 part/core.test.py", "part")

        # Assert
        self.assertEqual(found, set())

    def test_a_module_imported_without_the_alias_stays_private(self) -> None:
        # Arrange
        init_source = "from . import tiles\nfrom .core import Chip\n"

        # Act
        found = realiased_modules(init_source)

        # Assert
        self.assertEqual(found, set())

    def test_this_package_publishes_its_names_and_its_documented_modules(self) -> None:
        # Arrange
        listed = set(PACKAGE.__all__)

        # Act
        found = public_names()

        # Assert
        self.assertGreaterEqual(found, listed)

    def test_an_import_of_another_library_is_left_alone(self) -> None:
        # Arrange
        source = "from json import loads\nimport conformance.census as census\n"

        # Act
        found = reaches_inside(source, "part", {"Chip"}, set())

        # Assert
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
