"""That every worked example in the readme still does what it says.

A readme example is a promise a reader tests by pasting it, so an example that
has stopped working is worse than an absent one: it is the first thing a new
reader runs and the first impression they get. Nothing else in the suite touches
these lines, because they live in prose rather than in a module, which is exactly
why they rot quietly.

Each example runs in a fresh interpreter rather than in this one. An example that
only works because a test already imported something is not an example a reader
can paste, and running it here in-process would hide that.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

README = ROOT / "README.md"

BLOCK = re.compile(r"^```(\w*)\n(.*?)^```$", re.M | re.S)


def blocks(text: str | None = None) -> list[tuple[str, str]]:
    return [
        (lang, body)
        for lang, body in BLOCK.findall(text if text is not None else README.read_text())
    ]


def examples(text: str | None = None) -> list[tuple[str, str | None]]:
    """Each python block, paired with the output block that follows it.

    `text` is here so the collectors below can be driven against a readme that
    is deliberately wrong. A checker nothing has ever seen fail is a checker
    nobody knows the failure path of.
    """
    found = blocks(text)
    paired: list[tuple[str, str | None]] = []
    for index, (lang, body) in enumerate(found):
        if lang != "python":
            continue
        after = found[index + 1] if index + 1 < len(found) else None
        paired.append((body, after[1] if after and after[0] == "" else None))
    return paired


def ran(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        check=False,
        text=True,
        cwd=ROOT,
        timeout=120,
    )


def broken(found: list[tuple[str, str | None]]) -> list[str]:
    """The last line of the traceback of every example that will not run.

    A process can exit non-zero and print nothing, so the reason falls back to
    the exit code rather than indexing an empty list. A checker that raises
    while collecting a fault reports neither that fault nor any after it.
    """
    failed = []
    for source, _ in found:
        finished = ran(source)
        if finished.returncode != 0:
            said = finished.stderr.strip().splitlines()
            failed.append(said[-1] if said else f"exited {finished.returncode} in silence")
    return failed


def mismatched(found: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
    """What the readme claims each example prints, beside what it printed."""
    wrong = []
    for source, expected in found:
        if expected is None:
            continue
        finished = ran(source)
        if finished.stdout != expected:
            wrong.append((expected.strip(), finished.stdout.strip()))
    return wrong


class WorkedExampleTest(unittest.TestCase):
    def test_there_are_examples_to_check(self) -> None:
        found = examples()

        self.assertGreaterEqual(len(found), 4)

    def test_every_example_that_can_run_here_runs(self) -> None:
        self.assertEqual(broken(examples()), [])

    def test_every_example_prints_what_the_readme_says_it_prints(self) -> None:
        self.assertEqual(mismatched(examples()), [])


class CheckerTest(unittest.TestCase):
    """That the two collectors above report a fault rather than sailing past one.

    They are the only thing standing between a rotted example and a reader, so a
    run in which they have never been seen to fail says nothing about them.
    """

    def test_an_example_that_raises_is_reported(self) -> None:
        readme = '```python\nraise ValueError("nope")\n```\n'

        self.assertEqual(broken(examples(readme)), ["ValueError: nope"])

    def test_an_example_that_fails_in_silence_is_still_reported(self) -> None:
        readme = "```python\nraise SystemExit(3)\n```\n"

        self.assertEqual(broken(examples(readme)), ["exited 3 in silence"])

    def test_an_example_that_prints_the_wrong_thing_is_reported(self) -> None:
        readme = "```python\nprint(1)\n```\n\n```\n2\n```\n"

        self.assertEqual(mismatched(examples(readme)), [("2", "1")])

    def test_an_example_with_no_stated_output_is_only_run(self) -> None:
        readme = "```python\nprint(1)\n```\n"

        self.assertEqual(mismatched(examples(readme)), [])

    def test_every_example_is_run_and_none_is_skipped(self) -> None:
        found = examples()

        self.assertEqual(len([body for body, _ in found if body.strip()]), len(found))


if __name__ == "__main__":
    unittest.main(verbosity=2)
