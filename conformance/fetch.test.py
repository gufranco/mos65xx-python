import contextlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "conformance"))

fetch = importlib.import_module("fetch")

A_SUITE = {
    "name": "65816",
    "repository": "https://example.invalid/suite.git",
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "sparse": ["65816"],
    "path": "65816/v1",
}


class DefinitionTest(unittest.TestCase):
    def test_the_repository_declares_at_least_one_suite(self):
        self.assertTrue(fetch.definitions())

    def test_every_suite_names_where_it_comes_from_and_which_commit(self):
        for suite in fetch.definitions():
            self.assertTrue(suite["repository"].startswith("https://"))
            self.assertEqual(len(suite["commit"]), 40)
            self.assertTrue(suite["sparse"])
            self.assertTrue(suite["path"])

    def test_a_definition_file_is_read_from_where_it_is_asked_for(self):
        with tempfile.TemporaryDirectory() as where:
            path = Path(where) / "suites.json"
            path.write_text(json.dumps({"suites": [A_SUITE]}))

            self.assertEqual(fetch.definitions(path)[0]["name"], "65816")


class CheckoutTest(unittest.TestCase):
    def test_the_clone_takes_neither_history_nor_blobs(self):
        steps = fetch.checkout_command(A_SUITE, Path("/tmp/x"))
        joined = [" ".join(step) for step in steps]

        self.assertTrue(
            any("--depth=1" in step and "--filter=blob:none" in step for step in joined)
        )

    def test_only_the_directories_the_suite_names_are_checked_out(self):
        steps = fetch.checkout_command(A_SUITE, Path("/tmp/x"))

        self.assertTrue(any(step[-1] == "65816" and "sparse-checkout" in step for step in steps))

    def test_the_pinned_commit_is_what_gets_fetched(self):
        steps = fetch.checkout_command(A_SUITE, Path("/tmp/x"))

        self.assertTrue(any(A_SUITE["commit"] in step for step in steps))

    def test_a_commit_can_be_overridden_for_the_weekly_check(self):
        other = "f" * 40
        steps = fetch.checkout_command(A_SUITE, Path("/tmp/x"), other)

        self.assertTrue(any(other in step for step in steps))
        self.assertFalse(any(A_SUITE["commit"] in step for step in steps))


class LatestTest(unittest.TestCase):
    def test_an_unreachable_repository_reports_nothing_rather_than_raising(self):
        self.assertIsNone(fetch.latest_commit(A_SUITE))


def build_upstream(root):
    """A real repository on disk, shaped like the suite this core is held to.

    Nothing here is stubbed. The fetch path is git for its whole length, so a
    stand-in for git would only prove the stand-in works. A repository in a
    temporary directory is the same software the real fetch talks to, reached
    over a path instead of over the network.
    """
    upstream = Path(root) / "upstream"
    suite = upstream / "65816" / "v1"
    suite.mkdir(parents=True)
    (suite / "00.n.json").write_text("[]")
    (upstream / "unrelated").mkdir()
    (upstream / "unrelated" / "big.bin").write_text("not wanted")

    subprocess.run(["git", "init", "-q", "-b", "main", str(upstream)], check=True)
    for key, value in (("user.email", "suite@example.invalid"), ("user.name", "Suite")):
        subprocess.run(["git", "-C", str(upstream), "config", key, value], check=True)
    subprocess.run(["git", "-C", str(upstream), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(upstream), "commit", "-q", "-m", "suite"],
        check=True,
        env={**os.environ, "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"},
    )
    found = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return upstream, found.stdout.strip()


class FetchTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fetch-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.upstream, self.head = build_upstream(self.root)
        self.suite = {
            "name": "65816",
            "repository": str(self.upstream),
            "commit": self.head,
            "sparse": ["65816"],
            "path": "65816/v1",
        }

    def test_a_reachable_repository_reports_where_its_head_is(self):
        self.assertEqual(fetch.latest_commit(self.suite), self.head)

    def test_fetching_returns_the_directory_the_tests_live_in(self):
        where = fetch.fetch(self.suite, Path(self.root) / "down")

        self.assertTrue((where / "00.n.json").is_file())

    def test_fetching_takes_only_the_directories_that_were_asked_for(self):
        fetch.fetch(self.suite, Path(self.root) / "down")

        self.assertFalse((Path(self.root) / "down" / "unrelated").exists())

    def test_fetching_into_a_directory_that_already_exists_is_not_an_error(self):
        (Path(self.root) / "down").mkdir()

        where = fetch.fetch(self.suite, Path(self.root) / "down")

        self.assertTrue(where.is_dir())

    def test_a_commit_that_is_not_there_stops_the_run(self):
        missing = {**self.suite, "commit": "f" * 40}

        with self.assertRaises(SystemExit):
            fetch.fetch(missing, Path(self.root) / "down")

    def test_a_failure_names_the_step_that_failed(self):
        missing = {**self.suite, "commit": "f" * 40}

        with self.assertRaises(SystemExit) as raised:
            fetch.fetch(missing, Path(self.root) / "down", quiet=True)

        self.assertIn("65816", str(raised.exception))

    def test_a_probe_that_runs_out_of_time_reports_nothing(self):
        self.assertIsNone(fetch.latest_commit(self.suite, timeout=0))

    def test_a_transfer_that_runs_out_of_time_gives_up_and_says_so(self):
        with self.assertRaises(SystemExit) as raised:
            fetch.fetch(self.suite, Path(self.root) / "down", timeout=0)

        self.assertIn("gave up", str(raised.exception))

    def test_git_is_told_never_to_stop_and_ask(self):
        self.assertEqual(fetch._git_environment()["GIT_TERMINAL_PROMPT"], "0")


class MainTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fetch-main-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.upstream, self.head = build_upstream(self.root)
        self.definition = Path(self.root) / "suites.json"
        self.write_definition(str(self.upstream), self.head)

    def write_definition(self, repository, commit):
        self.definition.write_text(
            json.dumps(
                {
                    "suites": [
                        {
                            "name": "65816",
                            "repository": repository,
                            "commit": commit,
                            "sparse": ["65816"],
                            "path": "65816/v1",
                        }
                    ]
                }
            )
        )

    def run_main(self, argv):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = fetch.main(argv, self.definition)
        return code, captured.getvalue()

    def test_fetching_every_suite_reports_where_each_one_landed(self):
        code, output = self.run_main([str(Path(self.root) / "down")])

        self.assertEqual(code, 0)
        self.assertIn(self.head, output)

    def test_the_latest_flag_resolves_upstream_rather_than_the_pin(self):
        code, output = self.run_main([str(Path(self.root) / "down"), "--latest"])

        self.assertEqual(code, 0)
        self.assertIn(self.head, output)

    def test_a_suite_that_cannot_be_reached_is_reported_and_stops_the_run(self):
        self.write_definition(str(Path(self.root) / "nowhere"), "0" * 40)

        code, output = self.run_main([str(Path(self.root) / "down"), "--latest"])

        self.assertEqual(code, 1)
        self.assertIn("cannot reach", output)

    def test_no_directory_falls_back_to_a_cache_below_the_home_directory(self):
        chosen = {}
        original = fetch.fetch
        fetch.fetch = lambda suite, directory, commit=None, quiet=True: (
            chosen.setdefault("directory", directory) or Path(directory) / suite["path"]
        )
        self.addCleanup(setattr, fetch, "fetch", original)

        code, _ = self.run_main([])

        self.assertEqual(code, 0)
        self.assertIn(".cache", str(chosen["directory"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
