from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import MACHINES, PACKAGE, ROOT, SOLD_AS_A_COMPONENT
from conformance.family_shared import a_folder_holding

DOCUMENT_SUFFIXES = frozenset({".pdf", ".djvu", ".epub", ".rom", ".bin", ".img"})


def unignored(where: Path, run: Any = None) -> list[str]:
    runner = subprocess.run if run is None else run
    done = runner(
        ["git", "-c", "core.excludesFile=/dev/null", "status", "--porcelain", "-uall"],
        cwd=where,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(
            f"git could not read the tree: {done.stderr.strip() or 'no reason given'}"
        )
    return sorted(line[3:] for line in done.stdout.splitlines() if line.startswith("??"))


def tracked_files() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return listed.stdout.split()


def saying(text: str) -> Any:
    def run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout=text, stderr="")

    return run


def refusing(code: int, said: str) -> Any:
    def run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], code, stdout="", stderr=said)

    return run


class CarriesNobodyElsesWorkTest(unittest.TestCase):
    def test_no_document_is_committed(self) -> None:
        # Arrange
        tracked = tracked_files()

        # Act
        carried = sorted(rel for rel in tracked if Path(rel).suffix.lower() in DOCUMENT_SUFFIXES)

        # Assert
        self.assertEqual(carried, [])

    def test_nor_is_anything_from_the_folder_they_live_in(self) -> None:
        # Arrange
        tracked = tracked_files()

        # Act
        carried = [rel for rel in tracked if rel.startswith("docs/")]

        # Assert
        self.assertEqual(carried, [])

    def test_there_are_tracked_files_to_look_through(self) -> None:
        # Arrange
        smallest = 20

        # Act
        tracked = tracked_files()

        # Assert
        self.assertGreater(len(tracked), smallest)

    def test_the_ignore_file_here_covers_everything_on_its_own(self) -> None:
        # Arrange
        where = ROOT

        # Act
        found = unignored(where)

        # Assert
        self.assertEqual(found, [])

    def test_the_reader_of_that_names_an_untracked_file(self) -> None:
        # Arrange
        run = saying("?? left/behind.txt\n M edited.py\n")

        # Act
        found = unignored(ROOT, run)

        # Assert
        self.assertEqual(found, ["left/behind.txt"])

    def test_and_steps_over_one_that_is_merely_edited(self) -> None:
        # Arrange
        run = saying(" M edited.py\nA  added.py\n")

        # Act
        found = unignored(ROOT, run)

        # Assert
        self.assertEqual(found, [])

    def test_a_run_that_failed_is_not_read_as_a_clean_tree(self) -> None:
        # Arrange
        run = refusing(128, "not a repository")

        # Act
        attempt = lambda: unignored(ROOT, run)  # noqa: E731

        # Assert
        self.assertRaisesRegex(RuntimeError, "not a repository", attempt)

    def test_and_a_failure_with_nothing_to_say_still_raises(self) -> None:
        # Arrange
        run = refusing(1, "")

        # Act
        attempt = lambda: unignored(ROOT, run)  # noqa: E731

        # Assert
        self.assertRaises(RuntimeError, attempt)


NOT_THIS_PACKAGES_WORDS = (
    "FAMILY.md",
    "conformance/family_carried.test.py",
    "conformance/family_documents.test.py",
    "conformance/family_end_to_end.test.py",
    "conformance/family_imports.test.py",
    "conformance/family_interface.test.py",
    "conformance/family_member.py",
    "conformance/family_package.test.py",
    "conformance/family_printed_facts.test.py",
    "conformance/family_published.test.py",
    "conformance/family_record.test.py",
    "conformance/family_shared.py",
    "conformance/family_sizes.test.py",
    "conformance/family_test_roms.test.py",
    "conformance/family_tools.test.py",
    "conformance/family_translations.test.py",
    "conformance/family_writing.test.py",
)


def unquoted(text: str, suffix: str) -> str:
    if suffix != ".json":
        return text
    try:
        record = json.loads(text)
    except json.JSONDecodeError:
        return text
    blanked = text
    for passage in _passages(record):
        if len(passage) > 8:
            blanked = blanked.replace(
                json.dumps(passage)[1:-1], " " * len(json.dumps(passage)[1:-1])
            )
    return blanked


def _passages(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key.endswith(("quote", "Quote")) and isinstance(value, str):
                found.append(value)
            elif key.endswith(("quotes", "Quotes")) and isinstance(value, list):
                found.extend(one for one in value if isinstance(one, str))
            elif key.endswith(("quotes", "Quotes")) and isinstance(value, dict):
                found.extend(one for one in value.values() if isinstance(one, str))
            else:
                found.extend(_passages(value))
    elif isinstance(node, list):
        for one in node:
            found.extend(_passages(one))
    return found


def machine_mentions(where: Path, names: tuple[str, ...], run: Any = None) -> list[str]:
    runner = subprocess.run if run is None else run
    listed = runner(
        ["git", "ls-files"], cwd=where, capture_output=True, text=True, check=False
    ).stdout.split()
    found = []
    for rel in listed:
        if rel in NOT_THIS_PACKAGES_WORDS:
            continue
        path = where / rel
        if path.suffix in {".png", ".jpg", ".ico", ".pdf"} or not path.is_file():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        searched = unquoted(text, path.suffix)
        for name in names:
            for hit in re.finditer(rf"(?<![\w-]){re.escape(name)}(?![\w-])", searched):
                found.append(f"{rel}:{text[: hit.start()].count(chr(10)) + 1} names {name}")
    return found


class QuotedPassageTest(unittest.TestCase):
    def test_a_quote_is_blanked_and_the_line_numbers_survive(self) -> None:
        # Arrange
        held = '{"quote": "the SNES is named here", "note": "and here too"}'

        # Act
        found = unquoted(held, ".json")

        # Assert
        self.assertEqual(len(found), len(held))
        self.assertNotIn("SNES", found[: found.index("note")])
        self.assertIn("and here too", found)

    def test_a_plural_key_holding_a_list_is_blanked_as_well(self) -> None:
        # Arrange
        held = '{"aboutQuotes": ["the SNES is named here", "and so it is here"]}'

        # Act
        found = unquoted(held, ".json")

        # Assert
        self.assertNotIn("SNES", found)

    def test_and_one_holding_a_map_of_numbered_notes(self) -> None:
        # Arrange
        held = '{"noteQuotes": {"1": "the SNES is named here"}}'

        # Act
        found = unquoted(held, ".json")

        # Assert
        self.assertNotIn("SNES", found)

    def test_a_short_passage_is_left_alone(self) -> None:
        # Arrange
        held = '{"quote": "SNES", "note": "SNES"}'

        # Act
        found = unquoted(held, ".json")

        # Assert
        self.assertEqual(found, held)

    def test_a_file_that_is_not_a_record_is_read_as_it_stands(self) -> None:
        # Arrange
        held = "the SNES is named here"

        # Act
        found = unquoted(held, ".md")

        # Assert
        self.assertEqual(found, held)

    def test_and_so_is_one_that_claims_to_be_and_is_not(self) -> None:
        # Arrange
        held = "{this is not json at all, and it names the SNES"

        # Act
        found = unquoted(held, ".json")

        # Assert
        self.assertEqual(found, held)

    def test_a_value_that_is_not_a_passage_is_stepped_over(self) -> None:
        # Arrange
        held = '{"quote": 5, "quotes": [1, 2], "noteQuotes": {"1": 3}, "cycles": [1]}'

        # Act
        found = _passages(json.loads(held))

        # Assert
        self.assertEqual(found, [])


def listing(*names: str) -> Any:
    def run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout="\n".join(names), stderr="")

    return run


@unittest.skipUnless(SOLD_AS_A_COMPONENT, "this part only existed inside one machine")
class NamesNoMachineTest(unittest.TestCase):
    def names(self) -> tuple[str, ...]:
        return MACHINES[PACKAGE.__name__ if PACKAGE.__name__ in MACHINES else ROOT.name]

    def test_no_tracked_file_names_one(self) -> None:
        # Arrange
        names = self.names()

        # Act
        found = machine_mentions(ROOT, names)

        # Assert
        self.assertEqual(found, [])

    def test_the_sweep_would_report_one_if_it_were_there(self) -> None:
        # Arrange
        names = ("README",)

        # Act
        found = machine_mentions(ROOT, names)

        # Assert
        self.assertNotEqual(found, [])

    def test_a_name_inside_a_longer_word_is_not_a_mention(self) -> None:
        # Arrange
        folder = a_folder_holding("a.md", "SNESLIKE and pre-SNES-era are not mentions\n")

        # Act
        found = machine_mentions(folder, ("SNES",), listing("a.md"))

        # Assert
        self.assertEqual(found, [])

    def test_but_the_bare_name_is(self) -> None:
        # Arrange
        folder = a_folder_holding("a.md", "first\nthis one names the SNES outright\n")

        # Act
        found = machine_mentions(folder, ("SNES",), listing("a.md"))

        # Assert
        self.assertEqual(found, ["a.md:2 names SNES"])

    def test_a_file_that_is_not_text_is_stepped_over(self) -> None:
        # Arrange
        folder = Path(tempfile.mkdtemp())
        (folder / "a.bin").write_bytes(b"\xff\xfe\x00SNES")

        # Act
        found = machine_mentions(folder, ("SNES",), listing("a.bin"))

        # Assert
        self.assertEqual(found, [])

    def test_and_so_is_one_git_lists_that_is_not_on_disk(self) -> None:
        # Arrange
        folder = Path(tempfile.mkdtemp())

        # Act
        found = machine_mentions(folder, ("SNES",), listing("gone.md"))

        # Assert
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
