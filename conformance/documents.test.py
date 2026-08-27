import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT))

from conformance import documents as _documents  # noqa: E402

documents: Any = _documents

HELD = json.loads((ROOT / "conformance" / "documents.json").read_text())

PRESENT = all((ROOT / "docs" / entry["file"]).is_file() for entry in HELD["documents"])


def a_file(where: Path, name: str, body: bytes) -> dict[str, Any]:
    path = where / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {
        "file": name,
        "rung": 1,
        "retrievedFrom": path.resolve().as_uri(),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }


class ManifestTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.entries = HELD["documents"]

    def test_the_repository_declares_the_documents_it_was_read_from(self) -> None:
        self.assertTrue(self.entries)

    def test_every_document_carries_a_digest_of_the_full_width(self) -> None:
        short = [entry["file"] for entry in self.entries if len(entry["sha256"]) != 64]

        self.assertEqual(short, [])

    def test_every_document_says_where_it_came_from(self) -> None:
        missing = [
            entry["file"]
            for entry in self.entries
            if not str(entry.get("retrievedFrom", "")).startswith("http")
        ]

        self.assertEqual(missing, [])

    def test_every_document_says_which_rung_it_sits_on(self) -> None:
        rungs = {entry["rung"] for entry in self.entries}

        self.assertLessEqual(rungs, {1, 3, 4})

    def test_the_ladder_says_why_the_second_rung_is_empty_here(self) -> None:
        self.assertIn("suites.json", HELD["authority"]["2"])

    def test_every_part_either_has_a_document_or_says_why_it_has_none(self) -> None:
        from mos65xx import MODELS

        covered: set[str] = set()
        for entry in self.entries:
            covered |= set(entry["covers"])
        covered |= set(HELD["partsWithNoDocument"])

        self.assertEqual(set(MODELS) - covered, set())

    def test_a_part_with_no_document_says_what_is_known_about_it_instead(self) -> None:
        missing = [name for name, why in HELD["partsWithNoDocument"].items() if len(why) < 80]

        self.assertEqual(missing, [])

    def test_no_independent_document_claims_to_settle_anything(self) -> None:
        claiming = [
            entry["file"]
            for entry in self.entries
            if entry["rung"] != 1 and not str(entry["settles"]).startswith("Nothing")
        ]

        self.assertEqual(claiming, [])

    def test_no_two_documents_are_the_same_file(self) -> None:
        digests = [entry["sha256"] for entry in self.entries]

        self.assertEqual(len(digests), len(set(digests)))

    def test_no_document_here_was_printed_from_a_page(self) -> None:
        printed = [entry["file"] for entry in self.entries if entry.get("printedFromPage")]

        self.assertEqual(printed, [])


class VerifyTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_a_file_that_is_what_the_record_says_is_accepted(self) -> None:
        entry = a_file(self.root, "held.pdf", b"a document")

        documents.verify(entry, self.root)

    def test_a_file_that_is_not_there_is_refused(self) -> None:
        entry = a_file(self.root, "held.pdf", b"a document")
        (self.root / "held.pdf").unlink()

        with self.assertRaises(documents.Refused):
            documents.verify(entry, self.root)

    def test_a_file_with_a_different_digest_is_refused(self) -> None:
        entry = a_file(self.root, "held.pdf", b"a document")
        (self.root / "held.pdf").write_bytes(b"a different one")

        with self.assertRaises(documents.Refused):
            documents.verify(entry, self.root)

    def test_a_file_of_the_wrong_length_is_refused_even_if_the_digest_agrees(self) -> None:
        entry = a_file(self.root, "held.pdf", b"a document")
        entry["bytes"] = 1

        with self.assertRaises(documents.Refused):
            documents.verify(entry, self.root)


class DownloadTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.source = Path(tempfile.mkdtemp())

    def test_a_document_is_brought_down_where_the_record_names(self) -> None:
        entry = a_file(self.source, "held.pdf", b"a document")
        entry["file"] = "manufacturer/held.pdf"

        documents.download(entry, self.root)

        self.assertTrue((self.root / "manufacturer" / "held.pdf").is_file())

    def test_an_address_nobody_answers_is_refused(self) -> None:
        entry = {
            "file": "gone.pdf",
            "rung": 1,
            "retrievedFrom": (self.source / "absent.pdf").resolve().as_uri(),
            "sha256": "0" * 64,
            "bytes": 0,
        }

        with self.assertRaises(documents.Refused):
            documents.download(entry, self.root)

    def test_a_fetch_that_never_answers_is_refused_rather_than_waited_on(self) -> None:
        held = documents.subprocess.run

        def stall(*_args: object, **_kwargs: object) -> None:
            raise subprocess.TimeoutExpired("curl", documents.TIMEOUT)

        documents.subprocess.run = stall
        self.addCleanup(setattr, documents.subprocess, "run", held)
        entry = a_file(self.source, "held.pdf", b"a document")

        with self.assertRaises(subprocess.TimeoutExpired):
            documents.download(entry, self.root)


class OptionTest(unittest.TestCase):
    def test_a_run_fetches_unless_it_is_told_only_to_check(self) -> None:
        self.assertEqual(documents.options([])[0], False)

    def test_checking_alone_can_be_asked_for(self) -> None:
        self.assertEqual(documents.options(["--check"])[0], True)

    def test_one_document_can_be_named(self) -> None:
        self.assertEqual(documents.options(["--only", "w65c02s"])[1], "w65c02s")

    def test_naming_nothing_after_only_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            documents.options(["--only"])

    def test_an_option_the_tool_does_not_know_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            documents.options(["--everything"])

    def test_naming_no_document_selects_all_of_them(self) -> None:
        self.assertEqual(len(documents.wanted(HELD["documents"], None)), len(HELD["documents"]))

    def test_naming_one_selects_only_it(self) -> None:
        self.assertEqual(len(documents.wanted(HELD["documents"], "w65c02s")), 1)


class EntryTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def held(self, entries: list[dict[str, Any]]) -> Path:
        path = self.root / "documents.json"
        path.write_text(json.dumps({"documents": entries}))
        return path

    def test_naming_a_document_nobody_has_is_reported_rather_than_passing(self) -> None:
        self.assertEqual(documents.main(["--check", "--only", "nothing-like-this"], self.root), 1)

    def test_a_check_of_a_folder_that_holds_what_it_should_passes(self) -> None:
        entry = a_file(self.root, "held.pdf", b"a document")
        held = documents.documents
        documents.documents = lambda *_args: [entry]
        self.addCleanup(setattr, documents, "documents", held)

        self.assertEqual(documents.main(["--check"], self.root), 0)

    def test_a_check_of_a_folder_that_does_not_fails(self) -> None:
        entry = a_file(self.root, "held.pdf", b"a document")
        (self.root / "held.pdf").write_bytes(b"something else")
        held = documents.documents
        documents.documents = lambda *_args: [entry]
        self.addCleanup(setattr, documents, "documents", held)

        self.assertEqual(documents.main(["--check"], self.root), 1)

    def test_a_print_of_a_page_is_verified_and_never_fetched(self) -> None:
        entry = a_file(self.root, "held.pdf", b"a document")
        entry["printedFromPage"] = True
        entry["retrievedFrom"] = "https://example.invalid/page.html"
        held = documents.documents
        documents.documents = lambda *_args: [entry]
        self.addCleanup(setattr, documents, "documents", held)

        self.assertEqual(documents.main([], self.root), 0)

    def test_a_document_rendered_into_another_form_names_it(self) -> None:
        entry = a_file(self.root, "held.txt", b"a document")
        entry["renderedAs"] = "held.pdf"
        held = documents.documents
        documents.documents = lambda *_args: [entry]
        self.addCleanup(setattr, documents, "documents", held)

        self.assertEqual(documents.main(["--check"], self.root), 0)

    def test_a_run_that_is_not_only_checking_brings_the_document_down(self) -> None:
        source = Path(tempfile.mkdtemp())
        entry = a_file(source, "held.pdf", b"a document")
        held = documents.documents
        documents.documents = lambda *_args: [entry]
        self.addCleanup(setattr, documents, "documents", held)

        code = documents.main([], self.root)

        self.assertEqual((code, (self.root / "held.pdf").read_bytes()), (0, b"a document"))

    def test_a_document_read_from_a_named_file_is_read_from_there(self) -> None:
        entry = a_file(self.root, "held.pdf", b"a document")

        self.assertEqual(documents.documents(self.held([entry]))[0]["file"], "held.pdf")


@unittest.skipUnless(PRESENT, "the documents are not on this machine")
class OnDiskTest(unittest.TestCase):  # pragma: no cover
    """The documents this machine actually holds, if it holds any.

    Outside the coverage gate, and the only thing here that is. A check whose
    subject is a file the repository does not carry runs on one machine and not
    another, so the gate would measure which machine ran it rather than the code.
    """

    def test_every_document_on_disk_is_the_one_that_was_read(self) -> None:
        self.assertEqual(documents.main(["--check"], ROOT / "docs"), 0)


if __name__ == "__main__":
    unittest.main()
