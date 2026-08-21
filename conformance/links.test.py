"""That the link survey reads the readme correctly and judges an answer honestly.

Nothing here touches the network. A watcher that only worked against live hosts
could not be tested at all, and the judgement it makes, which refusals mean a
dead link and which mean weather, is the part worth pinning.
"""

import contextlib
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conformance import links  # noqa: E402


class Refusal(urllib.error.HTTPError):
    def __init__(self, code: int) -> None:
        super().__init__("https://example.invalid", code, "no", {}, None)  # type: ignore[arg-type]


class Answered:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "Answered":
        return self

    def __exit__(self, *rest: object) -> None:
        return None


def answering(status: int = 200) -> Any:
    def opener(request: Any, timeout: int = 0) -> Answered:
        return Answered(status)

    return opener


def refusing(code: int) -> Any:
    def opener(request: Any, timeout: int = 0) -> Answered:
        raise Refusal(code)

    return opener


def failing(trouble: type[Exception]) -> Any:
    def opener(request: Any, timeout: int = 0) -> Answered:
        raise trouble("no route")

    return opener


def head_refuses_get_answers() -> Any:
    def opener(request: Any, timeout: int = 0) -> Answered:
        if request.get_method() == "HEAD":
            raise Refusal(500)
        return Answered(206)

    return opener


class ReadingTest(unittest.TestCase):
    """What the survey takes from the readme."""

    def test_it_finds_the_addresses_in_a_line(self) -> None:
        found = links.addresses("see https://example.com/a and <https://example.com/b>")

        self.assertEqual(found, ["https://example.com/a", "https://example.com/b"])

    def test_it_names_each_address_once(self) -> None:
        found = links.addresses("https://example.com/a https://example.com/a")

        self.assertEqual(found, ["https://example.com/a"])

    def test_it_keeps_the_order_the_readme_uses(self) -> None:
        found = links.addresses("https://b.example https://a.example")

        self.assertEqual(found, ["https://b.example", "https://a.example"])

    def test_it_drops_the_punctuation_a_sentence_leaves_behind(self) -> None:
        found = links.addresses("fetched from https://example.com/a.pdf.")

        self.assertEqual(found, ["https://example.com/a.pdf"])

    def test_it_does_not_follow_a_markdown_close_bracket(self) -> None:
        found = links.addresses("[title](https://example.com/a) and text")

        self.assertEqual(found, ["https://example.com/a"])

    def test_it_leaves_badges_alone(self) -> None:
        found = links.addresses("![b](https://img.shields.io/x) [c](https://example.com/c)")

        self.assertEqual(found, ["https://example.com/c"])

    def test_the_readme_of_this_project_names_addresses_to_check(self) -> None:
        self.assertGreater(len(links.addresses()), 10)

    def test_and_every_one_of_them_is_an_address(self) -> None:
        wrong = [one for one in links.addresses() if not one.startswith("https://")]

        self.assertEqual(wrong, [])


class JudgementTest(unittest.TestCase):
    """Which answers count as a broken link and which do not."""

    def test_an_address_that_answers_is_fine(self) -> None:
        found = links.probe("https://example.com/a", answering(200))

        self.assertEqual((found.verdict, found.broken), ("ok", False))

    def test_a_not_found_is_a_broken_link(self) -> None:
        found = links.probe("https://example.com/a", refusing(404))

        self.assertEqual((found.verdict, found.broken), ("gone", True))

    def test_so_is_a_gone(self) -> None:
        found = links.probe("https://example.com/a", refusing(410))

        self.assertEqual((found.verdict, found.broken), ("gone", True))

    def test_a_door_held_shut_is_not_a_broken_link(self) -> None:
        found = links.probe("https://example.com/a", refusing(403))

        self.assertEqual((found.verdict, found.broken), ("unreachable", False))

    def test_neither_is_a_host_having_a_bad_day(self) -> None:
        found = links.probe("https://example.com/a", refusing(503))

        self.assertEqual((found.verdict, found.broken), ("unreachable", False))

    def test_nor_is_a_timeout(self) -> None:
        found = links.probe("https://example.com/a", failing(TimeoutError))

        self.assertEqual((found.verdict, found.broken), ("unreachable", False))

    def test_a_host_that_refuses_the_cheap_question_is_asked_the_other_one(self) -> None:
        found = links.probe("https://example.com/a", head_refuses_get_answers())

        self.assertEqual((found.verdict, found.detail), ("ok", "206"))

    def test_the_detail_says_what_the_last_refusal_was(self) -> None:
        found = links.probe("https://example.com/a", refusing(503))

        self.assertEqual(found.detail, "GET 503")


class ReportTest(unittest.TestCase):
    """The shape the workflow reads."""

    @override
    def setUp(self) -> None:
        self.answers = [
            links.Answer("https://a.example", "ok", "200"),
            links.Answer("https://b.example", "gone", "404"),
            links.Answer("https://c.example", "unreachable", "GET 503"),
        ]

    def test_it_counts_everything_it_asked(self) -> None:
        held = json.loads(links.report(self.answers))

        self.assertEqual(held["checked"], 3)

    def test_it_names_the_broken_ones_on_their_own(self) -> None:
        held = json.loads(links.report(self.answers))

        self.assertEqual(held["gone"], ["https://b.example"])

    def test_it_keeps_the_ones_that_only_went_quiet_apart(self) -> None:
        held = json.loads(links.report(self.answers))

        self.assertEqual(held["unreachable"], ["https://c.example"])

    def test_and_carries_every_answer_for_a_reader(self) -> None:
        held = json.loads(links.report(self.answers))

        self.assertEqual(len(held["answers"]), 3)

    def test_a_survey_with_nothing_wrong_says_so_plainly(self) -> None:
        held = json.loads(links.report(self.answers[:1]))

        self.assertEqual((held["gone"], held["unreachable"]), ([], []))


class SurveyTest(unittest.TestCase):
    """Driving the whole thing without a network."""

    def test_it_asks_every_address_it_is_given(self) -> None:
        found = links.survey(["https://a.example", "https://b.example"], answering(200))

        self.assertEqual([one.address for one in found], ["https://a.example", "https://b.example"])

    def test_it_reports_a_dead_address_among_live_ones(self) -> None:
        def opener(request: Any, timeout: int = 0) -> Answered:
            if "dead" in request.full_url:
                raise Refusal(404)
            return Answered(200)

        found = links.survey(["https://a.example", "https://dead.example"], opener)

        self.assertEqual([one.verdict for one in found], ["ok", "gone"])

    def test_it_reads_the_readme_when_given_nothing(self) -> None:
        found = links.survey(None, answering(200))

        self.assertEqual(len(found), len(links.addresses()))


class ExitTest(unittest.TestCase):
    """What the command line says to a workflow."""

    def run_with(self, answers: list[links.Answer]) -> tuple[int, str]:
        original, printed = links.survey, io.StringIO()
        links.survey = lambda *rest, **named: answers
        try:
            with contextlib.redirect_stdout(printed):
                code = links.main([])
        finally:
            links.survey = original
        return code, printed.getvalue()

    def test_a_survey_with_nothing_gone_succeeds(self) -> None:
        code, _ = self.run_with([links.Answer("https://a.example", "ok", "200")])

        self.assertEqual(code, 0)

    def test_a_quiet_host_does_not_fail_the_run(self) -> None:
        code, _ = self.run_with([links.Answer("https://a.example", "unreachable", "GET 503")])

        self.assertEqual(code, 0)

    def test_but_a_broken_link_does(self) -> None:
        code, _ = self.run_with([links.Answer("https://a.example", "gone", "404")])

        self.assertEqual(code, 1)

    def test_and_it_prints_the_survey_for_the_workflow_to_read(self) -> None:
        _, printed = self.run_with([links.Answer("https://a.example", "gone", "404")])

        self.assertEqual(json.loads(printed)["gone"], ["https://a.example"])


if __name__ == "__main__":
    unittest.main()
