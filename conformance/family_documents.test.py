from __future__ import annotations

import posixpath
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import FAMILY, ROOT


class EveryLinkResolvesTest(unittest.TestCase):
    LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

    def documents(self) -> list[Path]:
        held = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return [ROOT / one for one in held.stdout.split()]

    def tracked(self) -> set[str]:
        held = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        found: set[str] = set()
        for one in held.stdout.split():
            found.add(one)
            for parent in PurePosixPath(one).parents:
                if str(parent) != ".":
                    found.add(str(parent))
        return found

    def targets(self, where: Path) -> list[str]:
        found = []
        for target in self.LINK.findall(where.read_text()):
            held = target.split("#", 1)[0].split(" ", 1)[0]
            if not held or "://" in held or held.startswith(("mailto:", "#")):
                continue
            found.append(held)
        return found

    def said_from_the_root(self, inside: PurePosixPath, target: str) -> str:
        return posixpath.normpath(str(inside / target)).rstrip("/")

    def unresolved(self, where: Path, known: set[str]) -> list[str]:
        inside = PurePosixPath(where.parent.relative_to(ROOT))
        return [
            f"{where.relative_to(ROOT)} -> {one}"
            for one in self.targets(where)
            if self.said_from_the_root(inside, one) not in known
        ]

    def a_page(self, text: str) -> Path:
        where = Path(tempfile.mkdtemp()) / "one.md"
        where.write_text(text)
        return where

    def test_every_markdown_file_here_is_checked(self) -> None:
        # Arrange
        expected = {"README.md", "AGENTS.md", "FAMILY.md"}

        # Act
        named = {one.name for one in self.documents()}

        # Assert
        self.assertLessEqual(expected, named, named)

    def test_and_every_link_into_this_repository_resolves(self) -> None:
        # Arrange
        known = self.tracked()

        # Act
        missing = sorted(one for held in self.documents() for one in self.unresolved(held, known))

        # Assert
        self.assertEqual(missing, [])

    def test_a_link_to_something_the_repository_does_not_track_is_reported(self) -> None:
        # Arrange
        held = ROOT / "README.md"

        # Act
        unresolved = self.unresolved(held, set())

        # Assert
        self.assertEqual(len(unresolved), len(self.targets(held)))

    def test_a_link_to_something_it_does_track_is_not(self) -> None:
        # Arrange
        held = ROOT / "README.md"

        # Act
        unresolved = self.unresolved(held, self.tracked())

        # Assert
        self.assertEqual(unresolved, [])

    def test_a_link_out_of_a_subdirectory_resolves_to_what_it_names(self) -> None:
        # Arrange
        inside = PurePosixPath("cartridges")

        # Act
        held = self.said_from_the_root(inside, "../manifest.json")

        # Assert
        self.assertEqual(held, "manifest.json")

    def test_and_one_that_climbs_past_the_root_still_resolves_to_nothing(self) -> None:
        # Arrange
        inside = PurePosixPath(".")

        # Act
        held = self.said_from_the_root(inside, "../outside.json")

        # Assert
        self.assertEqual(held, "../outside.json")

    def test_an_anchor_is_dropped_before_the_file_is_looked_for(self) -> None:
        # Arrange
        where = self.a_page("see [a section](FAMILY.md#somewhere)\n")

        # Act
        found = self.targets(where)

        # Assert
        self.assertEqual(found, ["FAMILY.md"])

    def test_and_a_link_within_one_document_is_left_alone(self) -> None:
        # Arrange
        where = self.a_page("see [above](#somewhere)\n")

        # Act
        found = self.targets(where)

        # Assert
        self.assertEqual(found, [])

    def test_an_address_on_the_network_is_not_this_check_s_business(self) -> None:
        # Arrange
        where = self.a_page("see [a site](https://example.com/page)\n")

        # Act
        found = self.targets(where)

        # Assert
        self.assertEqual(found, [])

    def test_a_path_this_repository_ignores_does_not_count_as_resolved(self) -> None:
        # Arrange
        ignored = "docs/PROMPT.md"

        # Act
        known = self.tracked()

        # Assert
        self.assertNotIn(ignored, known)


class SharedFileTest(unittest.TestCase):
    NAMED = re.compile(r"^\| `([^`]+)` \|", re.M)

    FILE = re.compile(r"[./]")

    def promised(self) -> list[str]:
        return [row for row in self.NAMED.findall(FAMILY) if self.FILE.search(row)]

    def test_the_standard_names_every_file_this_repository_must_carry(self) -> None:
        # Arrange
        promised = self.promised()

        # Act
        missing = [row for row in promised if not (ROOT / row).exists()]

        # Assert
        self.assertEqual(missing, [])

    def test_and_there_is_something_to_check(self) -> None:
        # Arrange
        smallest = 6

        # Act
        promised = self.promised()

        # Assert
        self.assertGreater(len(promised), smallest)

    def test_a_file_named_with_no_directory_in_it_is_still_required(self) -> None:
        # Arrange
        citation = "CITATION.cff"

        # Act
        promised = self.promised()

        # Assert
        self.assertIn(citation, promised)


AGENTS_SECTIONS = (
    "What this project is, in one paragraph",
    "The interface a caller drives",
    "The authority ladder",
    "What is settled and what is not",
    "Every gate, in the order to run them",
    "Conventions that are not negotiable",
    "Layout",
    "Things that will bite you",
    "Before calling anything finished",
    "What a change is expected to leave behind",
)


SETTLED_SECTIONS = ("What is not in question", "What is deliberately not modelled")


def open_questions(where: Path | None = None) -> list[str]:
    held = ((ROOT if where is None else where) / "OPEN-QUESTIONS.md").read_text()
    found: list[str] = []
    section = ""
    for line in held.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("### ") and section not in SETTLED_SECTIONS:
            found.append(line[4:].strip())
    return found


class BriefedTheSameWayTest(unittest.TestCase):
    def agents(self) -> str:
        return (ROOT / "AGENTS.md").read_text()

    def held(self) -> list[str]:
        return re.findall(r"^## (.+)$", self.agents(), re.M)

    def test_it_carries_the_sections_the_family_carries(self) -> None:
        # Arrange
        held = self.held()

        # Act
        missing = [one for one in AGENTS_SECTIONS if one not in held]

        # Assert
        self.assertEqual(missing, [])

    def test_and_in_the_order_the_family_carries_them(self) -> None:
        # Arrange
        held = self.held()

        # Act
        kept = [one for one in held if one in AGENTS_SECTIONS]

        # Assert
        self.assertEqual(kept, list(AGENTS_SECTIONS))

    def test_anything_it_adds_of_its_own_sits_in_one_place(self) -> None:
        # Arrange
        held = self.held()
        gates = held.index("Every gate, in the order to run them")
        settled = held.index("What is settled and what is not")

        # Act
        stray = [
            one
            for one in held
            if one not in AGENTS_SECTIONS and not settled < held.index(one) < gates
        ]

        # Assert
        self.assertEqual(stray, [])

    def test_the_count_of_open_questions_is_the_count_there_is(self) -> None:
        # Arrange
        listed = open_questions()

        # Act
        claimed = re.search(r"\*\*Not settled: (\d+) things\*\*", self.agents())

        # Assert
        assert claimed is not None
        self.assertEqual(int(claimed.group(1)), len(listed))

    def test_and_counts_questions_rather_than_headings(self) -> None:
        # Arrange
        held = (ROOT / "OPEN-QUESTIONS.md").read_text()

        # Act
        listed = open_questions()

        # Assert
        self.assertLessEqual(len(listed), len(re.findall(r"^### ", held, re.M)))


if __name__ == "__main__":
    unittest.main()
