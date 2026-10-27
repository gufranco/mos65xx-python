from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import ROOT

FOLDER = "external"

HOME = re.compile("(?:^|[\\s\"'`(=])(?:" + "~" + "/|\\$" + "HOME/|/" + "Users/)")


def tracked_files(where: Path, run: Any = None) -> list[str]:
    runner = subprocess.run if run is None else run
    listed = runner(
        ["git", "-c", "submodule.recurse=false", "ls-files"],
        cwd=where,
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:
        raise RuntimeError(listed.stderr.strip() or "git ls-files failed")
    return [rel for rel in listed.stdout.split("\n") if rel]


def naming_a_home_folder(where: Path, listed: list[str]) -> list[str]:
    found = []
    for rel in listed:
        path = where / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        found += [
            f"{rel}:{number}"
            for number, line in enumerate(text.splitlines(), 1)
            if HOME.search(line)
        ]
    return found


def ignores_the_folder(gitignore: Path) -> bool:
    if not gitignore.is_file():
        return False
    lines = {line.strip() for line in gitignore.read_text().splitlines()}
    return bool(lines & {f"{FOLDER}/", f"/{FOLDER}/"})


def a_folder_holding(files: dict[str, str | bytes]) -> Path:
    where = Path(tempfile.mkdtemp())
    for rel, body in files.items():
        path = where / rel
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(body)
    return where


class EveryMemberKeepsItsFilesInsideTest(unittest.TestCase):
    def test_git_ignores_the_folder_the_artifacts_live_in(self) -> None:
        # Arrange
        gitignore = ROOT / ".gitignore"

        # Act
        ignored = ignores_the_folder(gitignore)

        # Assert
        self.assertTrue(ignored)

    def test_no_tracked_file_points_at_a_folder_outside_the_repository(self) -> None:
        # Arrange
        listed = tracked_files(ROOT)

        # Act
        found = naming_a_home_folder(ROOT, listed)

        # Assert
        self.assertEqual(found, [])


class TheGitignoreReaderTest(unittest.TestCase):
    def test_a_gitignore_naming_the_folder_from_the_root_passes(self) -> None:
        # Arrange
        where = a_folder_holding({".gitignore": "build/\n/external/\n"})

        # Act
        ignored = ignores_the_folder(where / ".gitignore")

        # Assert
        self.assertTrue(ignored)

    def test_a_gitignore_that_never_names_the_folder_fails(self) -> None:
        # Arrange
        where = a_folder_holding({".gitignore": "build/\n"})

        # Act
        ignored = ignores_the_folder(where / ".gitignore")

        # Assert
        self.assertFalse(ignored)

    def test_a_repository_with_no_gitignore_fails(self) -> None:
        # Arrange
        where = a_folder_holding({})

        # Act
        ignored = ignores_the_folder(where / ".gitignore")

        # Assert
        self.assertFalse(ignored)


class TheHomeFolderSweepTest(unittest.TestCase):
    def test_each_way_of_naming_a_home_folder_is_found_by_line(self) -> None:
        # Arrange
        lines = ["ok", "cat ~" + "/lib", "cd $" + "HOME/lib", 'p = "/' + 'Users/me"', "a~/b"]
        where = a_folder_holding({"notes.md": "\n".join(lines)})

        # Act
        found = naming_a_home_folder(where, ["notes.md"])

        # Assert
        self.assertEqual(found, ["notes.md:2", "notes.md:3", "notes.md:4"])

    def test_a_binary_file_and_a_listed_file_that_is_gone_are_passed_over(self) -> None:
        # Arrange
        where = a_folder_holding({"image.bin": b"\xff\xfe~/x"})

        # Act
        found = naming_a_home_folder(where, ["image.bin", "gone.md"])

        # Assert
        self.assertEqual(found, [])


class Listed:
    def __init__(self, code: int, out: str, err: str) -> None:
        self.returncode = code
        self.stdout = out
        self.stderr = err


class TheTrackedFileListTest(unittest.TestCase):
    def test_the_listing_is_split_into_paths(self) -> None:
        # Arrange
        run = lambda *_args, **_kwargs: Listed(0, "a.py\nb.md\n", "")  # noqa: E731

        # Act
        listed = tracked_files(ROOT, run)

        # Assert
        self.assertEqual(listed, ["a.py", "b.md"])

    def test_a_listing_that_fails_raises_what_git_said(self) -> None:
        # Arrange
        run = lambda *_args, **_kwargs: Listed(128, "", "not a repository")  # noqa: E731

        # Act
        with self.assertRaises(RuntimeError) as raised:
            tracked_files(ROOT, run)

        # Assert
        self.assertEqual(str(raised.exception), "not a repository")

    def test_a_listing_that_fails_silently_still_raises(self) -> None:
        # Arrange
        run = lambda *_args, **_kwargs: Listed(1, "", "")  # noqa: E731

        # Act
        with self.assertRaises(RuntimeError) as raised:
            tracked_files(ROOT, run)

        # Assert
        self.assertEqual(str(raised.exception), "git ls-files failed")


if __name__ == "__main__":
    unittest.main()
