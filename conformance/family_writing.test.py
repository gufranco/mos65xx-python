from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
import tokenize
import tomllib
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import CLOCKED, PACKAGE, ROOT
from conformance.family_shared import a_folder_holding

SECTIONS = (
    "Install",
    "The interface",
    "Is it right",
    "Working on it",
    "References",
    "Citing this",
    "License",
)


CLOCKED_SECTIONS = (
    "Running it at a real speed",
    "Models",
    "Nothing starts clean",
)


DIRECTIVE = ("noqa", "type:", "pragma", "ruff:", "mypy:", "isort:", "fmt:")


TEST_MARKERS = ("Arrange", "Act", "Assert")


def prose_comments(where: Path) -> list[str]:
    found = []
    for path in sorted(where.glob("**/*.py")):
        with path.open("rb") as opened:
            for token in tokenize.tokenize(opened.readline):
                if token.type != tokenize.COMMENT:
                    continue
                body = token.string.lstrip("#").strip()
                if body and not body.startswith(DIRECTIVE) and body not in TEST_MARKERS:
                    found.append(f"{path.name}:{token.start[0]}")
    return found


CONFIGURATION = ("pyproject.toml", "setup.cfg", ".gitignore")


def configuration_comments(where: Path) -> list[str]:
    found = []
    for name in CONFIGURATION:
        path = where / name
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                found.append(f"{name}:{number}")
    return found


def mute_names(where: Path) -> list[str]:
    found = []
    for path in sorted(where.glob("**/*.test.py")):
        for name in re.findall(r"^    def test_(\w+)", path.read_text(), re.M):
            if len(name.split("_")) < 2:
                found.append(f"{path.name}:test_{name}")
    return found


class WrittenTheSameWayTest(unittest.TestCase):
    def readme(self) -> str:
        return (ROOT / "README.md").read_text()

    def headings(self) -> list[str]:
        return re.findall(r"^## (.+)$", self.readme(), re.M)

    def opening(self) -> str:
        return self.readme().split("## ")[0]

    def tool(self) -> Any:
        return tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]

    def test_the_readme_carries_the_sections_the_family_carries(self) -> None:
        # Arrange
        headings = self.headings()

        # Act
        missing = [one for one in SECTIONS if one not in headings]

        # Assert
        self.assertEqual(missing, [])

    def test_and_in_the_order_the_family_carries_them(self) -> None:
        # Arrange
        headings = self.headings()

        # Act
        held = [one for one in headings if one in SECTIONS]

        # Assert
        self.assertEqual(held, list(SECTIONS))

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_a_clocked_part_also_carries_the_three_a_clock_needs(self) -> None:
        # Arrange
        headings = self.headings()

        # Act
        missing = [one for one in CLOCKED_SECTIONS if one not in headings]

        # Assert
        self.assertEqual(missing, [])

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_and_a_section_on_driving_it_a_cycle_at_a_time(self) -> None:
        # Arrange
        headings = self.headings()

        # Act
        found = any(one.startswith("Driving it one") for one in headings)

        # Assert
        self.assertTrue(found)

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_and_one_on_reading_a_program_without_running_it(self) -> None:
        # Arrange
        heading = "Reading without running"

        # Act
        headings = self.headings()

        # Assert
        self.assertIn(heading, headings)

    def test_anything_it_adds_sits_between_the_interface_and_the_evidence(self) -> None:
        # Arrange
        held = self.headings()
        added = [one for one in held if one not in SECTIONS and one not in CLOCKED_SECTIONS]
        interface = held.index("The interface")
        evidence = held.index("Is it right")

        # Act
        stray = [one for one in added if not interface < held.index(one) < evidence]

        # Assert
        self.assertEqual(stray, [])

    def test_the_readme_opens_with_what_was_measured(self) -> None:
        # Arrange
        held = self.opening()

        # Act
        found = re.search(r"^\*\*[0-9,]+\*\* [a-z]", held, re.M)

        # Assert
        self.assertIsNotNone(found, held[:400])

    def test_and_says_how_much_of_it_failed(self) -> None:
        # Arrange
        held = self.opening()

        # Act
        found = re.search(r"\*\*0\*\* (?:\w+ )?(?:failures|disagreements)", held)

        # Assert
        self.assertIsNotNone(found, held[:400])

    def test_and_what_it_costs_to_install(self) -> None:
        # Arrange
        phrase = "no dependencies"

        # Act
        held = self.opening()

        # Assert
        self.assertIn(phrase, held)

    def test_no_source_file_carries_a_comment_a_tool_does_not_read(self) -> None:
        # Arrange
        package = Path(PACKAGE.__file__ or "").resolve().parent

        # Act
        found = prose_comments(package)

        # Assert
        self.assertEqual(found, [])

    def test_a_bare_test_marker_is_not_prose(self) -> None:
        # Arrange
        where = a_folder_holding("sample.py", "# Arrange\nx = 1\n# Act now\n# Assert\n")

        # Act
        found = prose_comments(where)

        # Assert
        self.assertEqual(found, ["sample.py:3"])

    def test_nor_does_any_conformance_file(self) -> None:
        # Arrange
        where = ROOT / "conformance"

        # Act
        found = prose_comments(where)

        # Assert
        self.assertEqual(found, [])

    def test_no_configuration_file_carries_a_comment(self) -> None:
        # Arrange
        where = ROOT

        # Act
        found = configuration_comments(where)

        # Assert
        self.assertEqual(found, [])

    def test_the_reader_of_configuration_finds_a_comment_line(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        (where / "pyproject.toml").write_text('[tool.x]\n# why\nname = "a#b"\n')

        # Act
        found = configuration_comments(where)

        # Assert
        self.assertEqual(found, ["pyproject.toml:2"])

    def test_the_reader_of_that_tells_a_directive_from_prose(self) -> None:
        # Arrange
        where = a_folder_holding(
            "sample.py",
            "# ruff: noqa: E501\n"
            "# noqa: E743 -- the register really is called l\n"
            "x = 1  # type: ignore[assignment]\n"
            "#\n"
            "# the accumulator is eight bits wide\n"
            "def f() -> None:\n"
            '    """One worked line, with the answer beside it.\n'
            "\n"
            "        resolve(address).region\n"
            "        # 'work-ram', not cartridge\n"
            '    """\n',
        )

        # Act
        found = prose_comments(where)

        # Assert
        self.assertEqual(found, ["sample.py:5"])

    def test_and_the_reader_of_names_tells_a_sentence_from_a_function(self) -> None:
        # Arrange
        where = a_folder_holding(
            "sample.test.py",
            "class T:\n"
            "    def test_step(self) -> None:\n"
            "        pass\n"
            "\n"
            "    def test_a_step_costs_what_the_sheet_says(self) -> None:\n"
            "        pass\n",
        )

        # Act
        found = mute_names(where)

        # Assert
        self.assertEqual(found, ["sample.test.py:test_step"])

    def test_every_test_is_named_as_a_sentence_about_behaviour(self) -> None:
        # Arrange
        where = ROOT

        # Act
        found = mute_names(where)

        # Assert
        self.assertEqual(found, [])

    def test_the_checker_is_strict_everywhere_the_family_is(self) -> None:
        # Arrange
        floor = 100
        width = 100

        # Act
        held = self.tool()

        # Assert
        self.assertIs(held["mypy"]["strict"], True)
        self.assertEqual(held["coverage"]["report"]["fail_under"], floor)
        self.assertEqual(held["ruff"]["line-length"], width)

    def test_a_protocol_stub_is_excluded_from_the_count_both_ways(self) -> None:
        # Arrange
        patterns = self.tool()["coverage"]["report"].get("exclude_also", [])

        # Act
        inline = [one for one in patterns if re.search(one, "    def step(self) -> int: ...")]
        alone = [one for one in patterns if re.search(one, "        ...")]

        # Assert
        self.assertGreater(len(inline), 0, patterns)
        self.assertGreater(len(alone), 0, patterns)

    def test_and_a_pattern_that_matches_neither_would_be_reported(self) -> None:
        # Arrange
        doubled = r"^\\s*\\.\\.\\.$"

        # Act
        found = re.search(doubled, "        ...")

        # Assert
        self.assertIsNone(found)


DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def is_bare_string(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def documents_its_holder(body: list[ast.stmt], index: int) -> bool:
    opens_the_body = index == 0
    follows_an_assignment = index > 0 and isinstance(body[index - 1], (ast.Assign, ast.AnnAssign))
    return is_bare_string(body[index]) and (opens_the_body or follows_an_assignment)


def documentation_strings(text: str) -> list[int]:
    holders = [node for node in ast.walk(ast.parse(text)) if isinstance(node, DOCUMENTED)]
    return sorted(
        holder.body[index].lineno
        for holder in holders
        for index in range(len(holder.body))
        if documents_its_holder(holder.body, index)
    )


def tracked_python_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [ROOT / one for one in listed]


class NoDocumentationStringTest(unittest.TestCase):
    def test_no_tracked_file_carries_a_documentation_string(self) -> None:
        # Arrange
        files = tracked_python_files()

        # Act
        found = [
            f"{path.relative_to(ROOT)}:{line}"
            for path in files
            for line in documentation_strings(path.read_text())
        ]

        # Assert
        self.assertEqual(found, [])

    def test_and_there_are_files_to_check(self) -> None:
        # Arrange
        minimum = 5

        # Act
        files = tracked_python_files()

        # Assert
        self.assertGreater(len(files), minimum)

    def test_a_module_class_and_function_string_are_each_found(self) -> None:
        # Arrange
        text = '"""M."""\n\n\nclass A:\n    """C."""\n\n\ndef f() -> None:\n    """F."""\n'

        # Act
        found = documentation_strings(text)

        # Assert
        self.assertEqual(found, [1, 5, 9])

    def test_a_string_after_an_assignment_is_found(self) -> None:
        # Arrange
        text = 'LIMIT = 3\n"""What the limit is."""\n'

        # Act
        found = documentation_strings(text)

        # Assert
        self.assertEqual(found, [2])

    def test_a_string_used_as_a_value_is_not_one(self) -> None:
        # Arrange
        text = 'NAME = "a value"\nprint("a call")\n'

        # Act
        found = documentation_strings(text)

        # Assert
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
