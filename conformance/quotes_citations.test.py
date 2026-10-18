import builtins
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conformance import quotes  # noqa: E402


class CitationTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
