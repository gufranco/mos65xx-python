"""What the watcher surveys, and what it refuses to leave out."""

import importlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "conformance"))

watch: Any = importlib.import_module("watch")

ONE = "https://example.invalid/one.git"
TWO = "https://example.invalid/two.git"


def _suites(*rows: tuple[str, str, str]) -> list[dict[str, Any]]:
    return [
        {"name": name, "repository": repository, "commit": commit, "path": f"{name}/v1"}
        for name, repository, commit in rows
    ]


class GroupingTest(unittest.TestCase):
    def test_suites_that_share_a_repository_are_surveyed_once(self) -> None:
        suites = _suites(("a", ONE, "aaa"), ("b", ONE, "aaa"), ("c", TWO, "bbb"))

        found = watch.by_repository(suites)

        self.assertEqual([group["repository"] for group in found], [ONE, TWO])

    def test_and_each_group_carries_every_suite_that_uses_it(self) -> None:
        suites = _suites(("a", ONE, "aaa"), ("b", ONE, "aaa"), ("c", TWO, "bbb"))

        found = watch.by_repository(suites)

        self.assertEqual([group["suites"] for group in found], [["a", "b"], ["c"]])

    def test_the_pinned_commit_travels_with_the_group(self) -> None:
        suites = _suites(("a", ONE, "aaa"), ("c", TWO, "bbb"))

        found = watch.by_repository(suites)

        self.assertEqual([group["pinned"] for group in found], ["aaa", "bbb"])

    def test_a_repository_pinned_two_ways_is_refused_rather_than_guessed_at(self) -> None:
        suites = _suites(("a", ONE, "aaa"), ("b", ONE, "ccc"))

        with self.assertRaises(watch.Disagreement):
            watch.by_repository(suites)

    def test_every_suite_reaches_a_group(self) -> None:
        suites = _suites(("a", ONE, "aaa"), ("b", ONE, "aaa"), ("c", TWO, "bbb"))

        counted = sum(len(group["suites"]) for group in watch.by_repository(suites))

        self.assertEqual(counted, len(suites))


class SurveyTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.suites = _suites(("a", ONE, "aaa"), ("b", ONE, "aaa"), ("c", TWO, "bbb"))

    def test_a_repository_that_moved_is_marked_as_moved(self) -> None:
        found = watch.survey(self.suites, ask=lambda group: "zzz")

        self.assertEqual([group["moved"] for group in found], [True, True])

    def test_a_repository_that_did_not_move_is_not(self) -> None:
        found = watch.survey(self.suites, ask=lambda group: group["pinned"])

        self.assertEqual([group["moved"] for group in found], [False, False])

    def test_a_repository_that_cannot_be_reached_is_neither(self) -> None:
        found = watch.survey(self.suites, ask=lambda group: None)

        self.assertEqual(
            [(group["moved"], group["latest"]) for group in found], [(False, ""), (False, "")]
        )

    def test_one_repository_moving_does_not_mark_the_other(self) -> None:
        found = watch.survey(
            self.suites, ask=lambda group: "zzz" if group["repository"] == TWO else group["pinned"]
        )

        self.assertEqual([group["moved"] for group in found], [False, True])


class ReportTest(unittest.TestCase):
    def _said(self, argv: list[str], suites: list[dict[str, Any]]) -> str:
        with tempfile.TemporaryDirectory() as folder:
            where = Path(folder) / "suites.json"
            where.write_text(json.dumps({"suites": suites}))
            captured = io.StringIO()
            with redirect_stdout(captured):
                watch.main([*argv, str(where)], ask=lambda group: group["pinned"])
            return captured.getvalue()

    def test_the_survey_prints_one_line_of_json(self) -> None:
        suites = _suites(("a", ONE, "aaa"), ("c", TWO, "bbb"))

        said = self._said([], suites)

        self.assertEqual(len(json.loads(said)), 2)

    def test_and_it_is_a_matrix_a_workflow_can_consume(self) -> None:
        suites = _suites(("a", ONE, "aaa"), ("b", ONE, "aaa"))

        found = json.loads(self._said([], suites))

        self.assertEqual(sorted(found[0]), ["latest", "moved", "pinned", "repository", "suites"])

    def test_only_what_moved_is_listed_when_asked_for_that(self) -> None:
        suites = _suites(("a", ONE, "aaa"), ("c", TWO, "bbb"))

        found = json.loads(self._said(["--moved"], suites))

        self.assertEqual(found, [])

    def test_an_unreadable_definition_is_reported_rather_than_raised(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = watch.main([str(Path(folder) / "absent.json")])

            self.assertEqual(code, 1)

    def test_a_repository_pinned_two_ways_is_reported_rather_than_raised(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            where = Path(folder) / "suites.json"
            where.write_text(json.dumps({"suites": _suites(("a", ONE, "aaa"), ("b", ONE, "ccc"))}))
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = watch.main([str(where)])

            self.assertEqual((code, "pinned" in captured.getvalue()), (1, True))


class UpstreamTest(unittest.TestCase):
    """The one path that reaches the network, asked about somewhere that is not there.

    `.invalid` is reserved by RFC 2606 and resolves nowhere, so this exercises
    the real fetcher and the real failure path without depending on anything
    being reachable. A machine with no network at all fails faster and answers
    the same.
    """

    def test_a_repository_that_does_not_exist_answers_nothing(self) -> None:
        group = {"repository": "https://example.invalid/nothing.git", "pinned": "aaa"}

        found = watch._upstream(group)

        self.assertIsNone(found)

    def test_and_the_survey_reports_that_as_not_moved(self) -> None:
        suites = _suites(("a", "https://example.invalid/nothing.git", "aaa"))

        found = watch.survey(suites)

        self.assertEqual((found[0]["moved"], found[0]["latest"]), (False, ""))


class RealDefinitionTest(unittest.TestCase):
    """The file this repository actually ships, which is the point of all this."""

    @override
    def setUp(self) -> None:
        self.groups = watch.by_repository(watch.declared())

    def test_the_suites_come_from_more_than_one_repository(self) -> None:
        self.assertGreater(len(self.groups), 1)

    def test_and_every_one_of_them_is_surveyed(self) -> None:
        watched = {name for group in self.groups for name in group["suites"]}

        self.assertEqual(watched, {suite["name"] for suite in watch.declared()})

    def test_the_repository_holding_most_of_them_is_not_the_first(self) -> None:
        biggest = max(self.groups, key=lambda group: len(group["suites"]))

        self.assertIsNot(biggest, self.groups[0])


if __name__ == "__main__":
    unittest.main(verbosity=1)
