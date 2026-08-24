"""That every sentence these records call a quote is one a pinned document carries.

Nothing here needs a document. The documents are not redistributable, so a run on
a machine without them checks nothing, and the part worth pinning is that such a
run says so rather than reporting a pass it did not earn.
"""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conformance import quotes  # noqa: E402

PRINTED = "the quick brown fox jumps over the lazy dog and then keeps running for a while"


class FlattenTest(unittest.TestCase):
    def test_punctuation_and_spacing_stop_mattering(self) -> None:
        self.assertEqual(quotes.flatten("A, b.  C!"), "abc")

    def test_a_typographic_dash_reads_as_a_plain_one(self) -> None:
        self.assertEqual(quotes.flatten(f"a{chr(0x2014)}b"), "ab")

    def test_a_curly_quote_reads_as_a_straight_one(self) -> None:
        self.assertEqual(quotes.flatten(f"it{chr(0x2019)}s"), "its")

    def test_and_a_typographic_double_quote_does_too(self) -> None:
        self.assertEqual(quotes.flatten(f"{chr(0x201C)}x{chr(0x201D)}"), "x")


class WindowTest(unittest.TestCase):
    def test_a_quote_shorter_than_the_window_is_one_window(self) -> None:
        self.assertEqual(quotes.windows("a b c"), [quotes.flatten("a b c")])

    def test_a_longer_one_is_scored_on_overlapping_runs(self) -> None:
        found = quotes.windows(PRINTED)

        self.assertEqual(len(found), len(PRINTED.split()) - quotes.WINDOW + 1)


class ReadingTest(unittest.TestCase):
    def test_a_quote_is_found_where_it_sits(self) -> None:
        found = quotes.said({"quote": "hello"}, "here")

        self.assertEqual(found, [("here.quote", "hello")])

    def test_a_key_that_merely_ends_in_quote_is_read_too(self) -> None:
        found = quotes.said({"unusedBitsQuote": "hello"})

        self.assertEqual(found, [("unusedBitsQuote", "hello")])

    def test_a_list_of_quotes_is_read_item_by_item(self) -> None:
        found = quotes.said({"quotes": ["one", "two"]})

        self.assertEqual([where for where, _ in found], ["quotes[0]", "quotes[1]"])

    def test_a_list_entry_that_is_not_a_sentence_is_left_alone(self) -> None:
        found = quotes.said({"quotes": ["one", 2]})

        self.assertEqual(len(found), 1)

    def test_a_quote_inside_a_list_of_objects_is_reached(self) -> None:
        found = quotes.said([{"quote": "hello"}])

        self.assertEqual(found, [("[0].quote", "hello")])

    def test_a_table_flattened_into_prose_is_left_out(self) -> None:
        found = quotes.said({"quote": "Table 21", "assembled": True})

        self.assertEqual(found, [])

    def test_the_records_hold_quotes_to_look_for(self) -> None:
        self.assertGreater(len(quotes.quoted()), 0)

    def test_a_quote_the_recording_made_is_not_one_to_look_for(self) -> None:
        found = quotes.quoted([("made-up.json", {"suiteSays": {"quote": "hello"}})])

        self.assertEqual(found, [])

    def test_but_one_the_manufacturer_made_is(self) -> None:
        found = quotes.quoted([("made-up.json", {"documentSays": {"quote": "hello"}})])

        self.assertEqual(found, [("made-up.json.documentSays.quote", "hello")])

    def test_and_none_of_them_comes_from_the_recording(self) -> None:
        stray = [where for where, _ in quotes.quoted() if "suiteSays" in where]

        self.assertEqual(stray, [])


class LibraryTest(unittest.TestCase):
    def test_a_machine_with_no_documents_has_an_empty_library(self) -> None:
        self.assertEqual(quotes.library(ROOT / "no such folder"), {})

    def test_a_folder_of_documents_is_read_once_each(self) -> None:
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (folder / "one.pdf").write_bytes(b"not really a pdf")

        self.assertEqual(list(quotes.library(folder)), ["one.pdf"])

    def test_something_that_cannot_be_read_yields_no_text(self) -> None:
        self.assertEqual(quotes.readable(ROOT / "no such file.pdf"), "")

    def test_and_a_machine_with_no_reader_installed_checks_nothing(self) -> None:
        found = quotes.readable(ROOT / "anything.pdf", self.refuse)

        self.assertEqual(found, "")

    def test_a_reader_that_answers_gives_back_what_it_read(self) -> None:
        found = quotes.readable(ROOT / "anything.pdf", self.answering("Hello, World."))

        self.assertEqual(found, "helloworld")

    def test_a_reading_left_beside_the_document_is_pooled_with_it(self) -> None:
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (folder / "one.pdf").write_bytes(b"")
        (folder / "one.txt").write_text("from the pages")

        found = quotes.readable(folder / "one.pdf", self.answering("from the layer"))

        self.assertEqual(found, "fromthelayerfromthepages")

    def test_and_nothing_is_pooled_when_nobody_has_read_the_pages(self) -> None:
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (folder / "one.pdf").write_bytes(b"")

        found = quotes.readable(folder / "one.pdf", self.answering("only the layer"))

        self.assertEqual(found, "onlythelayer")

    @staticmethod
    def answering(text: str) -> Any:
        class Answered:
            stdout = text

        def reader(*rest: object, **named: object) -> Answered:
            return Answered()

        return reader

    @staticmethod
    def refuse(*rest: object, **named: object) -> None:
        raise FileNotFoundError("pdftotext")


class VerdictTest(unittest.TestCase):
    def test_a_quote_that_places_enough_windows_is_found(self) -> None:
        self.assertTrue(quotes.Verdict("a", "b", "doc", 5, 10).found)

    def test_one_that_places_too_few_is_not(self) -> None:
        self.assertFalse(quotes.Verdict("a", "b", "doc", 1, 10).found)

    def test_and_a_quote_with_no_windows_at_all_is_not(self) -> None:
        self.assertFalse(quotes.Verdict("a", "b", None, 0, 0).found)


class VerifyTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.books = {"real.pdf": quotes.flatten(PRINTED)}

    def test_a_sentence_the_document_carries_is_located(self) -> None:
        found = quotes.verify([("here", PRINTED)], self.books)

        self.assertEqual((found[0].found, found[0].document), (True, "real.pdf"))

    def test_a_sentence_it_does_not_is_reported(self) -> None:
        found = quotes.verify([("here", "nothing at all like the printed page here")], self.books)

        self.assertEqual((found[0].found, found[0].document), (False, None))

    def test_the_best_of_several_documents_is_the_one_named(self) -> None:
        books = {"poor.pdf": quotes.flatten("the quick brown"), **self.books}

        found = quotes.verify([("here", PRINTED)], books)

        self.assertEqual(found[0].document, "real.pdf")


class ReportTest(unittest.TestCase):
    def test_a_run_with_no_documents_says_it_checked_nothing(self) -> None:
        said = quotes.report([quotes.Verdict("a", "b", None, 0, 3)], 0)

        self.assertIn("none was checked", said)

    def test_a_clean_run_still_says_how_much_it_checked(self) -> None:
        said = quotes.report([quotes.Verdict("a", "b", "doc", 3, 3)], 1)

        self.assertIn("1 quotes against 1 documents, 1 located, 0 not", said)

    def test_a_missing_quote_is_named_with_its_score(self) -> None:
        said = quotes.report([quotes.Verdict("here", "text", "doc", 1, 9)], 1)

        self.assertIn("placed 1 of 9 windows (best in doc)", said)

    def test_and_one_no_document_could_place_names_none(self) -> None:
        said = quotes.report([quotes.Verdict("here", "text", None, 0, 9)], 1)

        self.assertIn("placed 0 of 9 windows", said)


class EntryPointTest(unittest.TestCase):
    def run_with(self, books: dict[str, str], held: list[tuple[str, str]]) -> tuple[int, str]:
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            status = quotes.main(books, held)
        return status, printed.getvalue()

    def test_with_no_documents_it_asks_for_nothing(self) -> None:
        status, said = self.run_with({}, [("here", PRINTED)])

        self.assertEqual((status, "none was checked" in said), (0, True))

    def test_with_documents_and_every_quote_placed_it_passes(self) -> None:
        status, said = self.run_with({"real.pdf": quotes.flatten(PRINTED)}, [("here", PRINTED)])

        self.assertEqual((status, "0 not" in said), (0, True))

    def test_a_sentence_no_document_carries_asks_for_a_person(self) -> None:
        status, said = self.run_with({"real.pdf": quotes.flatten(PRINTED)}, [("here", "absent")])

        self.assertEqual((status, "1 not" in said), (1, True))


class CitationTest(unittest.TestCase):
    """That a reader can look up every sentence the manufacturer is quoted saying."""

    def test_every_manufacturer_quote_names_a_page(self) -> None:
        self.assertEqual(quotes.unpaged(), [])

    def test_a_record_that_quotes_without_a_page_is_reported(self) -> None:
        found = quotes.unpaged([("made-up.json", {"facts": {"one": {"quote": "hello"}}})])

        self.assertEqual(found, ["made-up.json.facts.one.quote"])

    def test_but_not_when_the_quote_is_the_recording_speaking(self) -> None:
        found = quotes.unpaged([("made-up.json", {"suiteSays": {"quote": "hello"}})])

        self.assertEqual(found, [])

    def test_the_records_beside_this_file_are_the_ones_read(self) -> None:
        names = [name for name, _ in quotes.loaded()]

        self.assertIn("hardware.json", names)

    def test_a_page_key_says_where_the_quote_is(self) -> None:
        self.assertTrue(quotes.pointed({"page": 7}))

    def test_a_document_naming_a_section_says_it_too(self) -> None:
        self.assertTrue(quotes.pointed({"document": "W65C816S Data Sheet, 8.11.2"}))

    def test_but_naming_only_the_document_does_not(self) -> None:
        self.assertFalse(quotes.pointed({"document": "W65C816S Data Sheet"}))

    def test_a_quote_with_no_page_anywhere_above_it_is_reported(self) -> None:
        found = quotes.uncited({"quote": "hello"})

        self.assertEqual(found, ["quote"])

    def test_a_page_beside_it_is_enough(self) -> None:
        found = quotes.uncited({"quote": "hello", "page": 7})

        self.assertEqual(found, [])

    def test_and_a_page_on_the_object_above_counts_for_the_quotes_below(self) -> None:
        found = quotes.uncited({"page": 7, "inner": {"quote": "hello"}})

        self.assertEqual(found, [])

    def test_a_quote_inside_a_list_is_reached(self) -> None:
        found = quotes.uncited([{"quote": "hello"}])

        self.assertEqual(found, ["[0].quote"])

    def test_and_a_key_that_merely_ends_in_quote_is_held_to_the_same_rule(self) -> None:
        found = quotes.uncited({"vectorQuote": "hello"})

        self.assertEqual(found, ["vectorQuote"])


if __name__ == "__main__":
    unittest.main()
