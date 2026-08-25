"""That every worked example in the readme still does what it says.

A readme example is a promise a reader tests by pasting it, so an example that
has stopped working is worse than an absent one: it is the first thing a new
reader runs and the first impression they get. Nothing else in the suite touches
these lines, because they live in prose rather than in a module, which is exactly
why they rot quietly.

Each example runs in a fresh interpreter rather than in this one. An example that
only works because a test already imported something is not an example a reader
can paste, and running it here in-process would hide that.

An example that cannot run at all here is reported as skipped rather than as
broken, and only when the member itself says why. Two members model a part that
runs a program their repository is not allowed to carry, so on a machine without
one every example that builds a part refuses. That refusal is the package working
correctly, and counting it as a broken example would make a bare checkout look
like a defect while hiding real ones behind it.

What decides is the member's own `why_not`, which is the same sentence its doctor
prints. A member that publishes none skips nothing, and on a machine that has the
files nothing is skipped either, so the check keeps its teeth exactly where it
had them.
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent

README = ROOT / "README.md"


def packages() -> list[str]:
    """The importable package in this repository, which is the member itself.

    The conformance directory is one too and is not the member, so it is left
    out by name rather than by position.
    """
    return sorted(
        found.name
        for found in ROOT.iterdir()
        if (found / "__init__.py").is_file() and found.name != "conformance"
    )


def cannot_run_here(named: list[str] | None = None) -> str | None:
    """Why this member cannot build its part on this machine, or nothing.

    Read off the package rather than guessed from a traceback, so the sentence
    an example is excused by is the sentence the member itself publishes.

    The names are a parameter so this can be driven against a member that
    publishes a reason from a member that does not, and the other way round.
    Nine of the sixteen publish nothing, and a branch only two of them reach is
    a branch nobody has seen work.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    for name in packages() if named is None else named:
        asked = getattr(importlib.import_module(name), "why_not", None)
        if callable(asked):
            answer = asked()
            return str(answer) if answer else None
    return None


def excused(failure: str, reason: str | None = None) -> bool:
    """Whether that failure is the member saying it has no file to run.

    Matched on a run of the member's own sentence rather than on an exception
    name, because the name differs per member and the sentence is the thing the
    member publishes for exactly this purpose.
    """
    said = cannot_run_here() if reason is None else reason
    return bool(said) and str(said)[:40] in failure


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


def broken(found: list[tuple[str, str | None]], reason: str | None = None) -> list[str]:
    """The last line of the traceback of every example that will not run.

    A process can exit non-zero and print nothing, so the reason falls back to
    the exit code rather than indexing an empty list. A checker that raises
    while collecting a fault reports neither that fault nor any after it.
    """
    failed = []
    reason = cannot_run_here() if reason is None else reason
    for source, _ in found:
        finished = ran(source)
        if finished.returncode == 0:
            continue
        if excused(finished.stderr, reason):
            continue
        said = finished.stderr.strip().splitlines()
        failed.append(said[-1] if said else f"exited {finished.returncode} in silence")
    return failed


def mismatched(
    found: list[tuple[str, str | None]], reason: str | None = None
) -> list[tuple[str, str]]:
    """What the readme claims each example prints, beside what it printed."""
    wrong = []
    reason = cannot_run_here() if reason is None else reason
    for source, expected in found:
        if expected is None:
            continue
        finished = ran(source)
        if finished.returncode != 0 and excused(finished.stderr, reason):
            continue
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

    def test_an_example_that_runs_is_not_reported(self) -> None:
        """Driven rather than inherited from whichever readme this member has.

        On a member whose every example needs a file it may not ship, no example
        succeeds on a runner, so this arc was covered here and uncovered there.
        """
        readme = "```python\nprint(1)\n```\n"

        self.assertEqual(broken(examples(readme)), [])

    def test_an_example_that_raises_is_reported(self) -> None:
        readme = '```python\nraise ValueError("nope")\n```\n'

        self.assertEqual(broken(examples(readme)), ["ValueError: nope"])

    def test_an_example_that_fails_in_silence_is_still_reported(self) -> None:
        readme = "```python\nraise SystemExit(3)\n```\n"

        self.assertEqual(broken(examples(readme)), ["exited 3 in silence"])

    def test_an_example_that_prints_the_wrong_thing_is_reported(self) -> None:
        readme = "```python\nprint(1)\n```\n\n```\n2\n```\n"

        self.assertEqual(mismatched(examples(readme)), [("2", "1")])

    def test_and_a_later_example_is_still_checked_after_an_earlier_one_failed(self) -> None:
        """The loop has to keep going, and one crafted example cannot show that.

        A single mismatching example proves the report is produced and nothing
        about what happens next. Two of them, with the failure first, is the only
        arrangement where continuing after a failure is observable.
        """
        readme = (
            "```python\nprint(1)\n```\n\n```\n2\n```\n\n```python\nprint(3)\n```\n\n```\n3\n```\n"
        )

        self.assertEqual(mismatched(examples(readme)), [("2", "1")])

    def test_a_member_that_can_run_everything_excuses_nothing(self) -> None:
        """The teeth stay where they were on every member that ships its own part."""
        self.assertFalse(excused("anything at all", None if cannot_run_here() else "x" * 60))

    def test_a_failure_the_member_says_it_expects_is_excused(self) -> None:
        reason = "no firmware image was found: this backend runs the part's own microcode"

        self.assertTrue(excused(f"Traceback\nNoFirmware: {reason}", reason))

    def test_and_any_other_failure_is_not(self) -> None:
        """Driven against the shape that would otherwise slip through."""
        reason = "no firmware image was found: this backend runs the part's own microcode"

        self.assertFalse(excused("Traceback\nZeroDivisionError: division by zero", reason))

    def test_and_a_member_that_publishes_no_reason_excuses_nothing(self) -> None:
        self.assertFalse(excused("Traceback\nNoFirmware: anything", ""))

    def test_an_example_that_only_this_machine_can_run_is_reported_as_broken(self) -> None:
        """So the excuse cannot be claimed by an example that simply does not work."""
        readme = "```python\nraise ValueError('nope')\n```\n"

        self.assertEqual(broken(examples(readme)), ["ValueError: nope"])

    def test_an_example_the_member_says_it_cannot_run_is_not_reported_as_broken(self) -> None:
        readme = "```python\nraise SystemExit('no image is here')\n```\n"

        self.assertEqual(broken(examples(readme), "no image is here"), [])

    def test_and_its_stated_output_is_not_compared_either(self) -> None:
        """An example that never ran produced no output to compare."""
        readme = "```python\nraise SystemExit('no image is here')\n```\n\n```\n7\n```\n"

        self.assertEqual(mismatched(examples(readme), "no image is here"), [])

    def test_a_member_that_publishes_a_reason_is_read(self) -> None:
        """Driven against a stand-in, because nine of the sixteen publish none."""
        speaking = ModuleType("speaking")
        speaking.why_not = lambda: "no image is here"  # type: ignore[attr-defined]
        sys.modules["speaking"] = speaking
        try:
            self.assertEqual(cannot_run_here(["speaking"]), "no image is here")
        finally:
            del sys.modules["speaking"]

    def test_and_one_that_publishes_nothing_to_say_says_nothing(self) -> None:
        quiet = ModuleType("quiet")
        quiet.why_not = lambda: None  # type: ignore[attr-defined]
        sys.modules["quiet"] = quiet
        try:
            self.assertIsNone(cannot_run_here(["quiet"]))
        finally:
            del sys.modules["quiet"]

    def test_and_one_that_publishes_no_such_call_is_passed_over(self) -> None:
        silent = ModuleType("silent")
        sys.modules["silent"] = silent
        try:
            self.assertIsNone(cannot_run_here(["silent"]))
        finally:
            del sys.modules["silent"]

    def test_the_member_this_repository_holds_is_found_by_name(self) -> None:
        """So the sweep cannot start reading the conformance directory instead."""
        self.assertNotIn("conformance", packages())

    def test_an_example_with_no_stated_output_is_only_run(self) -> None:
        readme = "```python\nprint(1)\n```\n"

        self.assertEqual(mismatched(examples(readme)), [])

    def test_every_example_is_run_and_none_is_skipped(self) -> None:
        found = examples()

        self.assertEqual(len([body for body, _ in found if body.strip()]), len(found))


if __name__ == "__main__":
    unittest.main(verbosity=2)
