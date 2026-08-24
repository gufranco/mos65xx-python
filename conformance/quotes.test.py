"""That every sentence these records call a quote is one a pinned document carries.

Nothing here needs a document. The documents are not redistributable, so a run on
a machine without them checks nothing, and the part worth pinning is that such a
run says so rather than reporting a pass it did not earn.
"""

import builtins
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar, override

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


class SectionTest(unittest.TestCase):
    """That a fact from a book covering many parts names which part's pages it came from.

    This is the one thing searching the document cannot answer. The flattened
    text holds every section at once, so a table lifted from a sibling part
    matches just as well as the right one, and the sibling in this particular
    book prints the same six flag bits under the same names.
    """

    def a_record(self, page: object, span: object = None) -> tuple[str, object]:
        document: dict[str, object] = {"title": "a book"}
        if span is not None:
            document["sectionPages"] = span
        fact: dict[str, object] = {"document": "book", "quote": "words"}
        if page is not None:
            fact["filePage"] = page
        return ("held.json", {"book": document, "facts": {"a": fact}})

    def test_a_page_inside_the_section_is_accepted(self) -> None:
        found = quotes.sections([self.a_record(82, {"from": 76, "to": 99})])

        self.assertEqual(found, [])

    def test_a_page_outside_it_is_reported(self) -> None:
        found = quotes.sections([self.a_record(105, {"from": 76, "to": 99})])

        self.assertEqual(len(found), 1)
        self.assertIn("outside the 76-99", found[0])

    def test_a_page_below_it_is_reported_too(self) -> None:
        found = quotes.sections([self.a_record(12, {"from": 76, "to": 99})])

        self.assertIn("outside the 76-99", found[0])

    def test_the_first_and_last_pages_are_inside(self) -> None:
        self.assertEqual(quotes.sections([self.a_record(76, {"from": 76, "to": 99})]), [])
        self.assertEqual(quotes.sections([self.a_record(99, {"from": 76, "to": 99})]), [])

    def test_a_fact_naming_no_page_is_reported(self) -> None:
        found = quotes.sections([self.a_record(None, {"from": 76, "to": 99})])

        self.assertIn("names no filePage", found[0])

    def test_a_document_declaring_no_range_is_single_part_and_exempt(self) -> None:
        found = quotes.sections([self.a_record(None)])

        self.assertEqual(found, [])

    def test_several_ranges_are_accepted_for_a_part_the_book_returns_to(self) -> None:
        spans = [{"from": 416, "to": 419}, {"from": 424, "to": 424}]

        self.assertEqual(quotes.sections([self.a_record(417, spans)]), [])
        self.assertEqual(quotes.sections([self.a_record(424, spans)]), [])

    def test_and_a_page_between_them_belongs_to_another_part(self) -> None:
        spans = [{"from": 416, "to": 419}, {"from": 424, "to": 424}]

        found = quotes.sections([self.a_record(421, spans)])

        self.assertIn("outside the 416-419, 424-424", found[0])

    def test_a_range_in_a_list_that_is_not_a_mapping_declares_nothing(self) -> None:
        found = quotes.sections([self.a_record(None, ["416-419"])])

        self.assertEqual(found, [])

    def test_a_range_that_is_not_two_numbers_declares_nothing(self) -> None:
        found = quotes.sections([self.a_record(None, {"from": "76", "to": 99})])

        self.assertEqual(found, [])

    def test_a_fact_citing_a_document_with_no_range_is_left_alone(self) -> None:
        held = {
            "book": {"sectionPages": {"from": 76, "to": 99}},
            "other": {"title": "single part"},
            "facts": {"a": {"document": "other", "quote": "words"}},
        }

        self.assertEqual(quotes.sections([("held.json", held)]), [])

    def test_a_record_carrying_no_ranges_at_all_is_skipped(self) -> None:
        held = {"facts": {"a": {"document": "book", "quote": "words"}}}

        self.assertEqual(quotes.sections([("held.json", held)]), [])

    def test_a_row_table_counts_as_a_fact_even_with_no_quote(self) -> None:
        held = {
            "book": {"sectionPages": {"from": 76, "to": 99}},
            "facts": {"a": {"document": "book", "rows": [], "filePage": 105}},
        }

        found = quotes.sections([("held.json", held)])

        self.assertIn("outside", found[0])

    def test_ranges_are_found_inside_a_list(self) -> None:
        held = {
            "parts": [{"book": {"sectionPages": {"from": 1, "to": 2}}}],
            "facts": {"a": {"document": "book", "quote": "w", "filePage": 9}},
        }

        self.assertIn("outside the 1-2", quotes.sections([("held.json", held)])[0])

    def test_the_records_on_disk_all_land_in_their_own_section(self) -> None:
        self.assertEqual(quotes.sections(), [])

    def test_a_fact_in_the_wrong_section_fails_the_run(self) -> None:
        code = quotes.main({}, [], ["a.json.facts.x: names file page 105, outside 76-99"])

        self.assertEqual(code, 1)

    def test_and_the_run_says_which_fact_it_was(self) -> None:
        said: list[str] = []
        original = builtins.print
        builtins.print = lambda *args, **kwargs: said.append(" ".join(str(one) for one in args))
        try:
            quotes.main({}, [], ["a.json.facts.x: names file page 105"])
        finally:
            builtins.print = original

        self.assertTrue(any("names file page 105" in line for line in said))


class DeclaredDocumentTest(unittest.TestCase):
    """That every citation names a document the record declares.

    The field held three vocabularies at once here: a declared key, a bare file
    name, and a prose title with the section glued on the end. Nothing could
    check any of them, because a check written against keys skipped the other two
    in silence and reported a clean run over the third.
    """

    def a_record(self, cited: str, declared: object = None) -> tuple[str, object]:
        held: dict[str, object] = {"facts": {"a": {"document": cited, "quote": "words"}}}
        if declared is not None:
            held["documents"] = declared
        return ("held.json", held)

    def test_a_declared_key_is_accepted(self) -> None:
        found = quotes.undeclared([self.a_record("book", {"book": {}})])

        self.assertEqual(found, [])

    def test_a_prose_title_is_reported(self) -> None:
        found = quotes.undeclared([self.a_record("Some Data Sheet, 8.2", {"book": {}})])

        self.assertEqual(len(found), 1)
        self.assertIn("not a declared document", found[0])

    def test_a_bare_file_name_is_reported(self) -> None:
        found = quotes.undeclared([self.a_record("manual.pdf", {"book": {}})])

        self.assertIn("not a declared document", found[0])

    def test_a_record_declaring_nothing_is_left_alone(self) -> None:
        found = quotes.undeclared([self.a_record("anything at all")])

        self.assertEqual(found, [])

    def test_a_documents_block_nested_in_a_part_is_found(self) -> None:
        held = {
            "parts": [{"documents": {"book": {}}}],
            "facts": {"a": {"document": "elsewhere", "quote": "w"}},
        }

        self.assertIn("not a declared document", quotes.undeclared([("held.json", held)])[0])

    def test_a_documents_block_that_is_not_a_mapping_declares_nothing(self) -> None:
        found = quotes.undeclared([self.a_record("anything", ["book"])])

        self.assertEqual(found, [])

    def test_the_records_on_disk_all_cite_declared_documents(self) -> None:
        self.assertEqual(quotes.undeclared(), [])


class AttributionTest(unittest.TestCase):
    """That a quote is in the document its own record names.

    Scoring a quote against whichever document places it best answers "did
    somebody publish this sentence" and not "did the document this record cites
    publish it". The two come apart exactly when a fact is filed under the wrong
    source, and then the words are real, the run is green, and the citation sends
    a reader somewhere the sentence is not.
    """

    def a_record(self, cited: str, quote: str) -> tuple[str, object]:
        return (
            "held.json",
            {
                "documents": {
                    "right": {"file": "right.pdf"},
                    "wrong": {"file": "wrong.pdf"},
                },
                "facts": {"a": {"document": cited, "quote": quote}},
            },
        )

    BOOKS: ClassVar[dict[str, str]] = {
        "right.pdf": quotes.flatten(
            "the quick brown fox jumps over the lazy dog and keeps running"
        ),
        "wrong.pdf": quotes.flatten("nothing here resembles the sentence above in any way at all"),
    }

    def test_a_quote_in_the_document_it_names_is_accepted(self) -> None:
        found = quotes.misattributed(
            [self.a_record("right", "the quick brown fox jumps over the lazy dog")], self.BOOKS
        )

        self.assertEqual(found, [])

    def test_a_quote_that_lives_in_another_document_is_reported(self) -> None:
        found = quotes.misattributed(
            [self.a_record("wrong", "the quick brown fox jumps over the lazy dog")], self.BOOKS
        )

        self.assertEqual(len(found), 1)
        self.assertIn("right.pdf", found[0])

    def test_a_quote_in_no_document_at_all_is_left_to_the_other_check(self) -> None:
        found = quotes.misattributed(
            [self.a_record("right", "a sentence that appears in neither of them anywhere")],
            self.BOOKS,
        )

        self.assertEqual(found, [])

    def test_a_document_with_no_file_on_this_machine_is_skipped(self) -> None:
        held = (
            "held.json",
            {
                "documents": {"right": {"file": "absent.pdf"}},
                "facts": {"a": {"document": "right", "quote": "the quick brown fox jumps"}},
            },
        )

        self.assertEqual(quotes.misattributed([held], self.BOOKS), [])

    def test_a_record_declaring_no_files_is_left_alone(self) -> None:
        held = ("held.json", {"facts": {"a": {"document": "x", "quote": "the quick brown fox"}}})

        self.assertEqual(quotes.misattributed([held], self.BOOKS), [])

    def test_an_entry_saying_nothing_has_no_quote_to_place(self) -> None:
        held = (
            "held.json",
            {
                "documents": {"right": {"file": "right.pdf"}},
                "facts": {
                    "a": {"document": "right", "quote": "nothing at all", "saysNothing": True}
                },
            },
        )

        self.assertEqual(quotes.misattributed([held], self.BOOKS), [])

    def test_a_declared_document_naming_no_file_cannot_be_checked(self) -> None:
        """The block may hold an entry with no file, and it is simply skipped.

        A record can declare a document it has never had a copy of. There is
        nothing to search, so there is nothing to say about a quote citing it.
        """
        held = (
            "held.json",
            {
                "documents": {"right": {"file": "right.pdf"}, "paperOnly": {"title": "no file"}},
                "facts": {"a": {"document": "paperOnly", "quote": "the quick brown fox jumps"}},
            },
        )

        self.assertEqual(quotes.misattributed([held], self.BOOKS), [])

    def test_the_records_on_disk_are_all_where_they_say_they_are(self) -> None:
        self.assertEqual(quotes.misattributed(), [])


class PhantomTableTest(unittest.TestCase):
    """That a section naming a table is held to the document beside it.

    The words of a quote were checked and the table pointed at was not, so a
    citation could name the right document, quote it correctly, and send a
    reader to a table only a different sheet has.
    """

    TABLES: ClassVar[dict[str, set[str]]] = {
        "right.pdf": {"4-1", "7-1"},
        "other.pdf": {"6-5", "6-76"},
    }

    def a_record(self, document: str, section: str) -> tuple[str, dict[str, Any]]:
        return (
            "held.json",
            {
                "documents": {"right": {"file": "right.pdf"}, "other": {"file": "other.pdf"}},
                "facts": {"a": {"document": document, "section": section}},
            },
        )

    def test_a_table_the_named_document_has_is_accepted(self) -> None:
        found = quotes.phantom([self.a_record("right", "Table 4-1 Addressing Mode")], self.TABLES)

        self.assertEqual(found, [])

    def test_a_table_only_another_document_has_is_reported(self) -> None:
        found = quotes.phantom([self.a_record("right", "Table 6-5 note 6")], self.TABLES)

        self.assertEqual(len(found), 1)
        self.assertIn("other.pdf", found[0])

    def test_a_table_no_document_has_is_reported_without_a_destination(self) -> None:
        found = quotes.phantom([self.a_record("right", "Table 9-9")], self.TABLES)

        self.assertEqual(len(found), 1)
        self.assertNotIn("and it is in", found[0])

    def test_a_section_naming_two_tables_is_checked_on_both(self) -> None:
        found = quotes.phantom(
            [self.a_record("right", "Table 7-1, with Table 6-5 for the cycle counts")], self.TABLES
        )

        self.assertEqual(len(found), 1)
        self.assertIn("Table 6-5", found[0])

    def test_a_section_named_in_prose_is_left_alone(self) -> None:
        found = quotes.phantom([self.a_record("right", "3.13 Reset (RESB)")], self.TABLES)

        self.assertEqual(found, [])

    def test_a_longer_table_number_does_not_pass_off_as_a_shorter_one(self) -> None:
        """`Table 6-7` is absent from a document whose only near name is `Table 6-76`."""
        found = quotes.phantom([self.a_record("other", "Table 6-7")], self.TABLES)

        self.assertEqual(len(found), 1)

    def test_a_bare_table_number_is_not_satisfied_by_a_subdivided_one(self) -> None:
        """NEC numbers a table `6`. A document whose only six is `6-5` has no `6`."""
        found = quotes.phantom([self.a_record("other", "Table 6. ALU Field")], self.TABLES)

        self.assertEqual(len(found), 1)
        self.assertIn("Table 6,", found[0])

    def test_a_document_whose_reading_names_no_table_is_skipped(self) -> None:
        """A scan whose text layer lost the labels says nothing about the record."""
        found = quotes.phantom(
            [self.a_record("right", "Table 6-5")], {"right.pdf": set(), "other.pdf": {"6-5"}}
        )

        self.assertEqual(found, [])

    def test_a_document_with_no_file_on_this_machine_is_skipped(self) -> None:
        held = (
            "held.json",
            {
                "documents": {"gone": {"file": "absent.pdf"}},
                "facts": {"a": {"document": "gone", "section": "Table 6-5"}},
            },
        )

        self.assertEqual(quotes.phantom([held], self.TABLES), [])

    def test_a_record_declaring_no_files_is_left_alone(self) -> None:
        held = ("held.json", {"facts": {"a": {"document": "right", "section": "Table 6-5"}}})

        self.assertEqual(quotes.phantom([held], self.TABLES), [])

    def test_a_document_the_record_never_declared_is_skipped(self) -> None:
        found = quotes.phantom([self.a_record("unheard-of", "Table 6-5")], self.TABLES)

        self.assertEqual(found, [])

    def test_the_walk_reaches_a_section_inside_a_list(self) -> None:
        held = (
            "held.json",
            {
                "documents": {"right": {"file": "right.pdf"}},
                "facts": {"a": {"alsoSays": [{"document": "right", "section": "Table 6-5"}]}},
            },
        )

        found = quotes.phantom([held], self.TABLES)

        self.assertEqual(len(found), 1)
        self.assertIn("alsoSays[0]", found[0])

    def test_the_records_on_disk_name_no_table_their_document_lacks(self) -> None:
        self.assertEqual(quotes.phantom(), [])


class TableCatalogueTest(unittest.TestCase):
    """That the table names come off the page rather than off the flattened body."""

    def answering(self, text: str) -> Any:
        def run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 0, stdout=text, stderr="")

        return run

    def refuse(self, *_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        raise OSError("no pdftotext here")

    def test_the_tables_a_document_names_are_collected(self) -> None:
        found = quotes.labelled(ROOT / "one.pdf", self.answering("see Table 4-1 and Table 7-1"))

        self.assertEqual(found, {"4-1", "7-1"})

    def test_a_machine_without_the_reader_reports_nothing_rather_than_raising(self) -> None:
        self.assertEqual(quotes.labelled(ROOT / "one.pdf", self.refuse), set())

    def test_a_second_reading_beside_the_document_is_pooled_in(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            folder = Path(where)
            (folder / "one.pdf").write_bytes(b"")
            (folder / "one.txt").write_text("and Table 9-9 from the scanned pages")

            found = quotes.labelled(folder / "one.pdf", self.answering("Table 4-1"))

        self.assertEqual(found, {"4-1", "9-9"})

    def test_a_folder_that_is_not_there_yields_no_catalogue(self) -> None:
        self.assertEqual(quotes.catalogue(ROOT / "no such folder"), {})

    def test_every_pinned_document_is_catalogued(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            folder = Path(where)
            (folder / "one.pdf").write_bytes(b"")
            (folder / "two.pdf").write_bytes(b"")

            found = quotes.catalogue(folder, self.answering("Table 1-1"))

        self.assertEqual(found, {"one.pdf": {"1-1"}, "two.pdf": {"1-1"}})


if __name__ == "__main__":
    unittest.main()
