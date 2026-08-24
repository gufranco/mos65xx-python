"""That the adopter survey reads the page correctly and judges the record honestly.

Nothing here touches the network. The part worth pinning is the judgement: a
selector that stopped matching must read as unread rather than as an ecosystem
that emptied overnight, and a pointer file must be held to pointing at AGENTS.md
rather than to holding rules of its own.
"""

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conformance import agents_support  # noqa: E402


def marquee(*names: str) -> str:
    return "".join(
        f'<span class="text-xl font-semibold leading-tight">{name}</span>' for name in names
    )


class Answered:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "Answered":
        return self

    def __exit__(self, *rest: object) -> None:
        return None


def answering(body: str) -> Any:
    def opener(request: Any, timeout: int = 0) -> Answered:
        return Answered(body.encode())

    return opener


def failing(trouble: type[Exception]) -> Any:
    def opener(request: Any, timeout: int = 0) -> Answered:
        raise trouble("no route")

    return opener


def reached(pointer: Path) -> Path:
    """Where the link inside a pointer file actually lands.

    Checking that the text names AGENTS.md is not the same as checking that a
    reader clicking it arrives somewhere, and the two part company the moment a
    pointer moves into a directory and keeps its old relative address.
    """
    found = re.search(r"\]\(([^)]+)\)", pointer.read_text())
    if found is None:
        return pointer.parent / "there is no link here"
    return (pointer.parent / found.group(1)).resolve()


class ReadingTest(unittest.TestCase):
    def test_a_name_is_taken_out_of_the_span_that_prints_it(self) -> None:
        found = agents_support.names_in(marquee("Codex"))

        self.assertEqual(found, ["Codex"])

    def test_an_entity_is_turned_back_into_the_character_it_stands_for(self) -> None:
        found = agents_support.names_in(marquee("Autopilot &amp; Coded Agents"))

        self.assertEqual(found, ["Autopilot & Coded Agents"])

    def test_a_name_printed_twice_is_counted_once(self) -> None:
        found = agents_support.names_in(marquee("Zed", "Zed"))

        self.assertEqual(found, ["Zed"])

    def test_and_the_order_the_page_prints_them_in_is_kept(self) -> None:
        found = agents_support.names_in(marquee("Warp", "Aider"))

        self.assertEqual(found, ["Warp", "Aider"])

    def test_an_empty_span_names_nothing(self) -> None:
        found = agents_support.names_in('<span class="text-xl font-semibold">  </span>')

        self.assertEqual(found, [])

    def test_markup_with_no_such_span_names_nothing(self) -> None:
        found = agents_support.names_in("<p>Codex</p>")

        self.assertEqual(found, [])


class FetchTest(unittest.TestCase):
    def test_a_page_that_answers_is_returned(self) -> None:
        self.assertEqual(agents_support.fetch(opener=answering("hello")), "hello")

    def test_a_host_that_never_answers_gives_nothing_back(self) -> None:
        self.assertEqual(agents_support.fetch(opener=failing(urllib.error.URLError)), "")

    def test_an_operating_system_refusal_is_treated_the_same_way(self) -> None:
        self.assertEqual(agents_support.fetch(opener=failing(OSError)), "")


class ComparisonTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.record: dict[str, Any] = {
            "readsAgentsFile": {"names": [f"Agent {n}" for n in range(agents_support.FEWEST)]}
        }
        self.page = marquee(*self.record["readsAgentsFile"]["names"])

    def test_a_page_that_matches_the_record_reports_nothing(self) -> None:
        result = agents_support.compare(self.page, self.record)

        self.assertEqual((result["read"], result["new"], result["gone"]), (True, [], []))

    def test_a_name_the_record_does_not_hold_is_reported_as_new(self) -> None:
        result = agents_support.compare(self.page + marquee("Newcomer"), self.record)

        self.assertEqual(result["new"], ["Newcomer"])

    def test_a_name_the_page_dropped_is_reported_as_gone(self) -> None:
        self.record["readsAgentsFile"]["names"].append("Retired")

        result = agents_support.compare(self.page, self.record)

        self.assertEqual(result["gone"], ["Retired"])

    def test_too_few_names_reads_as_a_page_that_was_not_read(self) -> None:
        result = agents_support.compare(marquee("Codex"), self.record)

        self.assertEqual((result["read"], result["found"]), (False, 1))

    def test_and_such_a_page_reports_nothing_gone(self) -> None:
        result = agents_support.compare("", self.record)

        self.assertEqual((result["new"], result["gone"]), ([], []))


class ReportTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.names = [f"Agent {n}" for n in range(agents_support.FEWEST)]
        self.record: dict[str, Any] = {"readsAgentsFile": {"names": list(self.names)}}

    def serving(self, *extra: str) -> Any:
        return answering(marquee(*self.names, *extra))

    def test_a_page_that_matches_asks_for_nothing(self) -> None:
        result, status = agents_support.report(self.serving(), self.record)

        self.assertEqual((result["new"], status), ([], 0))

    def test_a_new_name_is_worth_a_person_reading(self) -> None:
        result, status = agents_support.report(self.serving("Newcomer"), self.record)

        self.assertEqual((result["new"], status), (["Newcomer"], 1))

    def test_a_host_that_went_quiet_is_not_an_alarm(self) -> None:
        result, status = agents_support.report(failing(urllib.error.URLError), self.record)

        self.assertEqual((result["read"], status), (False, 0))

    def test_the_entry_point_prints_the_report_and_returns_its_status(self) -> None:
        printed = io.StringIO()

        with contextlib.redirect_stdout(printed):
            status = agents_support.main(self.serving("Newcomer"), self.record)

        self.assertEqual((json.loads(printed.getvalue())["new"], status), (["Newcomer"], 1))

    def test_and_it_reads_the_record_beside_it_when_none_is_given(self) -> None:
        result, _ = agents_support.report(self.serving())

        self.assertEqual(result["read"], True)


class RecordTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.record = agents_support.held()

    def test_the_record_is_the_one_beside_this_file(self) -> None:
        self.assertTrue(agents_support.RECORD.exists())

    def test_every_pointer_names_a_file_that_is_here(self) -> None:
        missing = [
            tool["pointer"]
            for tool in self.record["tools"]
            if not (ROOT / tool["pointer"]).exists()
        ]

        self.assertEqual(missing, [])

    def test_every_pointer_sends_the_reader_to_the_one_instruction_file(self) -> None:
        silent = [
            tool["pointer"]
            for tool in self.record["tools"]
            if "AGENTS.md" not in (ROOT / tool["pointer"]).read_text()
        ]

        self.assertEqual(silent, [])

    def test_no_pointer_carries_instructions_of_its_own(self) -> None:
        fat = [
            tool["pointer"]
            for tool in self.record["tools"]
            if len((ROOT / tool["pointer"]).read_text().split()) > 60
        ]

        self.assertEqual(fat, [])

    def test_the_link_in_each_pointer_lands_on_the_instruction_file(self) -> None:
        astray = [
            tool["pointer"]
            for tool in self.record["tools"]
            if reached(ROOT / tool["pointer"]) != (ROOT / "AGENTS.md").resolve()
        ]

        self.assertEqual(astray, [])

    def test_and_a_pointer_with_no_link_at_all_is_caught_rather_than_passed(self) -> None:
        bare = Path(self.enterContext(tempfile.TemporaryDirectory())) / "bare.md"
        bare.write_text("go and read the other file")

        self.assertFalse(reached(bare).exists())

    def test_every_tool_says_where_its_path_was_documented(self) -> None:
        silent = [tool["name"] for tool in self.record["tools"] if not tool.get("documented")]

        self.assertEqual(silent, [])

    def test_the_adopter_list_is_kept_as_the_page_prints_it(self) -> None:
        names = self.record["readsAgentsFile"]["names"]

        self.assertEqual(names, sorted(names, key=str.casefold))

    def test_an_agent_on_both_lists_says_so_rather_than_looking_like_a_duplicate(self) -> None:
        quiet = [
            tool["name"]
            for tool in self.record["tools"]
            if tool["name"] in self.record["readsAgentsFile"]["names"]
            and not tool.get("alsoOnTheAdopterList")
        ]

        self.assertEqual(quiet, [])

    def test_and_nothing_claims_to_be_on_the_adopter_list_without_being_on_it(self) -> None:
        wrong = [
            tool["name"]
            for tool in self.record["tools"]
            if tool.get("alsoOnTheAdopterList")
            and tool["name"] not in self.record["readsAgentsFile"]["names"]
        ]

        self.assertEqual(wrong, [])


if __name__ == "__main__":
    unittest.main()
