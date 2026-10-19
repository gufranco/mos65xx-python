from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance import family_member
from conformance.family_member import ROOT

LIMIT = 500

LONG_FILES: dict[str, str] = getattr(family_member, "LONG_FILES", {})


def tracked_sources(where: Path, run: Any = None) -> list[str]:
    runner = subprocess.run if run is None else run
    listed = runner(
        ["git", "-c", "submodule.recurse=false", "ls-files", "--", "*.py"],
        cwd=where,
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:
        raise RuntimeError(listed.stderr.strip() or "git ls-files failed")
    return [rel for rel in listed.stdout.split("\n") if rel]


def line_count(path: Path) -> int:
    return len(path.read_text().splitlines())


def oversized(where: Path, listed: list[str], allowed: dict[str, str]) -> list[str]:
    problems = []
    for rel in listed:
        path = where / rel
        if not path.is_file():
            continue
        lines = line_count(path)
        if lines > LIMIT and not allowed.get(rel, "").strip():
            problems.append(f"{rel}: {lines} lines, over {LIMIT} with no reason recorded")
    problems.extend(
        f"{rel}: excused but not tracked" for rel in sorted(allowed) if rel not in listed
    )
    return problems


def a_folder_holding(files: dict[str, int]) -> Path:
    where = Path(tempfile.mkdtemp())
    for rel, lines in files.items():
        (where / rel).write_text("x = 1\n" * lines)
    return where


class NoFileOutgrowsTheLimitTest(unittest.TestCase):
    def test_every_tracked_source_is_short_or_excused_by_name(self) -> None:
        # Arrange
        listed = tracked_sources(ROOT)

        # Act
        problems = oversized(ROOT, listed, LONG_FILES)

        # Assert
        self.assertEqual(problems, [])


class TheSizeReaderTest(unittest.TestCase):
    def test_a_file_at_the_limit_passes(self) -> None:
        # Arrange
        where = a_folder_holding({"a.py": LIMIT})

        # Act
        problems = oversized(where, ["a.py"], {})

        # Assert
        self.assertEqual(problems, [])

    def test_a_file_one_line_over_is_reported(self) -> None:
        # Arrange
        where = a_folder_holding({"a.py": LIMIT + 1})

        # Act
        problems = oversized(where, ["a.py"], {})

        # Assert
        self.assertEqual(problems, ["a.py: 501 lines, over 500 with no reason recorded"])

    def test_a_long_file_excused_with_a_reason_passes(self) -> None:
        # Arrange
        where = a_folder_holding({"core.py": LIMIT + 40})

        # Act
        problems = oversized(where, ["core.py"], {"core.py": "one calculation engine"})

        # Assert
        self.assertEqual(problems, [])

    def test_an_excuse_with_an_empty_reason_does_not_count(self) -> None:
        # Arrange
        where = a_folder_holding({"core.py": LIMIT + 40})

        # Act
        problems = oversized(where, ["core.py"], {"core.py": " "})

        # Assert
        self.assertEqual(problems, ["core.py: 540 lines, over 500 with no reason recorded"])

    def test_an_excuse_for_a_file_no_longer_tracked_is_reported(self) -> None:
        # Arrange
        where = a_folder_holding({})

        # Act
        problems = oversized(where, [], {"gone.py": "one calculation engine"})

        # Assert
        self.assertEqual(problems, ["gone.py: excused but not tracked"])

    def test_a_listed_file_missing_from_the_tree_is_skipped(self) -> None:
        # Arrange
        where = a_folder_holding({})

        # Act
        problems = oversized(where, ["deleted.py"], {})

        # Assert
        self.assertEqual(problems, [])

    def test_a_listing_that_fails_raises(self) -> None:
        # Arrange
        def refusing(*_: Any, **__: Any) -> Any:
            return subprocess.CompletedProcess([], 128, "", "not a repository")

        # Act
        attempt = lambda: tracked_sources(ROOT, refusing)  # noqa: E731

        # Assert
        self.assertRaisesRegex(RuntimeError, "not a repository", attempt)

    def test_a_failed_listing_with_nothing_to_say_still_raises(self) -> None:
        # Arrange
        def silent(*_: Any, **__: Any) -> Any:
            return subprocess.CompletedProcess([], 1, "", "")

        # Act
        attempt = lambda: tracked_sources(ROOT, silent)  # noqa: E731

        # Assert
        self.assertRaisesRegex(RuntimeError, "git ls-files failed", attempt)


if __name__ == "__main__":
    unittest.main()
