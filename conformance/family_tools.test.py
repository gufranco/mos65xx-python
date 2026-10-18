from __future__ import annotations

import importlib
import json
import re
import sys
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import PACKAGE, ROOT, TESTED_DIRECTORIES
from conformance.family_shared import a_folder_holding


def counted_tests() -> int:
    return sum(
        len(re.findall(r"^\s+def test_", found.read_text(), re.M))
        for directory in TESTED_DIRECTORIES
        for found in sorted((ROOT / directory).glob("**/*.test.py"))
    )


class ClaimedCountTest(unittest.TestCase):
    def test_the_readme_advertises_the_number_of_tests_there_are(self) -> None:
        # Arrange
        readme = (ROOT / "README.md").read_text()

        # Act
        claimed = re.search(r"\*\*([\d,]+)\*\* tests", readme)

        # Assert
        assert claimed is not None
        self.assertEqual(int(claimed.group(1).replace(",", "")), counted_tests())


def as_a_script(text: str) -> list[int]:
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if re.search(r"python3? conformance/[a-z_]+\.py", line)
    ]


class StandardIsKeptTest(unittest.TestCase):
    def test_the_standard_names_the_errors_module_as_the_one_home(self) -> None:
        # Arrange
        name = "errors.py"

        # Act
        standard = (ROOT / "FAMILY.md").read_text()

        # Assert
        self.assertIn(name, standard)

    def test_and_this_repository_has_one(self) -> None:
        # Arrange
        package = Path(PACKAGE.__file__ or "").resolve().parent

        # Act
        present = (package / "errors.py").exists()

        # Assert
        self.assertTrue(present)

    def test_the_standard_says_a_tool_runs_as_a_module(self) -> None:
        # Arrange
        phrase = "python3 -m conformance.name"

        # Act
        standard = (ROOT / "FAMILY.md").read_text()

        # Assert
        self.assertIn(phrase, standard)

    def test_and_no_workflow_runs_one_as_a_script(self) -> None:
        # Arrange
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

        # Act
        astray = [
            f"{path.name}:{number}"
            for path in workflows
            for number in as_a_script(path.read_text())
        ]

        # Assert
        self.assertEqual(astray, [])

    def test_and_no_document_tells_a_reader_to(self) -> None:
        # Arrange
        names = ("README.md", "AGENTS.md", "CONTRIBUTING.md")

        # Act
        astray = [
            name
            for name in names
            if (ROOT / name).exists() and as_a_script((ROOT / name).read_text())
        ]

        # Assert
        self.assertEqual(astray, [])

    def test_the_reader_of_those_two_finds_a_script_invocation(self) -> None:
        # Arrange
        texts = (
            "run: python conformance/speed.py\n",
            "run: python3 -m conformance.speed\n",
            "a\nb\npython conformance/links.py\n",
        )

        # Act
        found = [as_a_script(text) for text in texts]

        # Assert
        self.assertEqual(found, [[1], [], [3]])

    def test_the_standard_promises_a_throughput_floor(self) -> None:
        # Arrange
        phrase = "throughput floor"

        # Act
        standard = (ROOT / "FAMILY.md").read_text()

        # Assert
        self.assertIn(phrase, standard)

    def test_and_this_repository_has_one_with_a_floor_to_beat(self) -> None:
        # Arrange
        speed = importlib.import_module("conformance.speed")

        # Act
        floor = speed.FLOOR

        # Assert
        self.assertGreater(floor, 0)

    def test_and_it_is_this_repository_s_floor(self) -> None:
        # Arrange
        speed = importlib.import_module("conformance.speed")

        # Act
        held = Path(speed.__file__ or "").resolve()

        # Assert
        self.assertEqual(held, ROOT / "conformance" / "speed.py", held)

    def test_the_floor_is_checked_outside_the_coverage_step(self) -> None:
        # Arrange
        run = "python -m conformance.speed"
        covered = "coverage run -a conformance/speed.py"

        # Act
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        # Assert
        self.assertIn(run, workflow)
        self.assertNotIn(covered, workflow)


def stamped_paths(script: Path) -> list[str]:
    if not script.is_file():
        return []
    return sorted(set(re.findall(r"\$\{root\}/([^\"'\s]+)", script.read_text())))


def released_assets(config: Path) -> list[str]:
    if not config.is_file():
        return []
    document = json.loads(config.read_text())
    for plugin in document.get("plugins", []):
        if isinstance(plugin, list) and plugin and plugin[0] == "@semantic-release/git":
            return [str(asset) for asset in plugin[1].get("assets", [])]
    return []


def unreleased(stamped: Iterable[str], released: Iterable[str]) -> list[str]:
    committed = set(released)
    return [path for path in stamped if path not in committed]


class EveryStampedFileIsReleasedTest(unittest.TestCase):
    SCRIPT = "scripts/set-version.sh"

    CONFIG = ".releaserc.json"

    def test_the_release_commits_every_file_the_script_stamps(self) -> None:
        # Arrange
        stamped = stamped_paths(ROOT / self.SCRIPT)
        released = released_assets(ROOT / self.CONFIG)

        # Act
        left_out = unreleased(stamped, released)

        # Assert
        self.assertEqual(left_out, [])

    def test_and_there_is_something_to_check(self) -> None:
        # Arrange
        script = ROOT / self.SCRIPT

        # Act
        stamped = stamped_paths(script)

        # Assert
        self.assertGreaterEqual(len(stamped), 2)

    def test_a_path_the_release_leaves_out_is_reported(self) -> None:
        # Arrange
        stamped = ["pkg/version.py", "CITATION.cff"]

        # Act
        found = unreleased(stamped, ["pkg/version.py"])

        # Assert
        self.assertEqual(found, ["CITATION.cff"])

    def test_a_script_that_is_not_here_stamps_nothing(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp()) / "set-version.sh"

        # Act
        found = stamped_paths(where)

        # Assert
        self.assertEqual(found, [])

    def test_a_script_that_names_no_target_stamps_nothing(self) -> None:
        # Arrange
        where = a_folder_holding(
            "set-version.sh", "#!/usr/bin/env bash\nprintf 'nothing to do\\n'\n"
        )

        # Act
        found = stamped_paths(where / "set-version.sh")

        # Assert
        self.assertEqual(found, [])

    def test_a_release_config_that_is_not_here_releases_nothing(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp()) / ".releaserc.json"

        # Act
        found = released_assets(where)

        # Assert
        self.assertEqual(found, [])

    def test_a_config_with_no_git_plugin_releases_nothing(self) -> None:
        # Arrange
        where = a_folder_holding(
            ".releaserc.json", '{"plugins": ["@semantic-release/github", [], ["@other", {}]]}'
        )

        # Act
        found = released_assets(where / ".releaserc.json")

        # Assert
        self.assertEqual(found, [])

    def test_a_git_plugin_naming_no_asset_releases_nothing(self) -> None:
        # Arrange
        where = a_folder_holding(".releaserc.json", '{"plugins": [["@semantic-release/git", {}]]}')

        # Act
        found = released_assets(where / ".releaserc.json")

        # Assert
        self.assertEqual(found, [])


def recorded_version(module: Path) -> str | None:
    if not module.is_file():
        return None
    found = re.search(r'^VERSION = "([^"]*)"$', module.read_text(), re.M)
    return found.group(1) if found else None


def cited_version(citation: Path) -> str | None:
    if not citation.is_file():
        return None
    found = re.search(r"^version: (.*)$", citation.read_text(), re.M)
    return found.group(1).strip() if found else None


class TheVersionAndTheCitationAgreeTest(unittest.TestCase):
    def stamped(self) -> list[str]:
        return stamped_paths(ROOT / "scripts" / "set-version.sh")

    def module(self) -> Path:
        named = [one for one in self.stamped() if one.endswith("version.py")]
        return ROOT / named[0] if named else ROOT / "version.py"

    def test_the_script_stamps_exactly_one_version_module(self) -> None:
        # Arrange
        stamped = self.stamped()

        # Act
        named = [one for one in stamped if one.endswith("version.py")]

        # Assert
        self.assertEqual(len(named), 1, named)

    def test_the_package_reports_a_version(self) -> None:
        # Arrange
        module = self.module()

        # Act
        found = recorded_version(module)

        # Assert
        self.assertIsNotNone(found)

    def test_the_citation_publishes_a_version(self) -> None:
        # Arrange
        citation = ROOT / "CITATION.cff"

        # Act
        found = cited_version(citation)

        # Assert
        self.assertIsNotNone(found)

    def test_the_two_say_the_same_thing(self) -> None:
        # Arrange
        module = self.module()

        # Act
        found = (recorded_version(module), cited_version(ROOT / "CITATION.cff"))

        # Assert
        self.assertEqual(found[0], found[1])

    def test_a_module_that_is_not_here_reports_no_version(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp()) / "version.py"

        # Act
        found = recorded_version(where)

        # Assert
        self.assertIsNone(found)

    def test_a_module_with_no_assignment_reports_no_version(self) -> None:
        # Arrange
        where = a_folder_holding("version.py", "RELEASE = '1.2.3'\n")

        # Act
        found = recorded_version(where / "version.py")

        # Assert
        self.assertIsNone(found)

    def test_a_citation_that_is_not_here_publishes_no_version(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp()) / "CITATION.cff"

        # Act
        found = cited_version(where)

        # Assert
        self.assertIsNone(found)

    def test_a_citation_with_no_version_line_publishes_none(self) -> None:
        # Arrange
        where = a_folder_holding("CITATION.cff", "cff-version: 1.2.0\ntitle: something\n")

        # Act
        found = cited_version(where / "CITATION.cff")

        # Assert
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
