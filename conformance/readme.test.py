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
    return sorted(
        found.name
        for found in ROOT.iterdir()
        if (found / "__init__.py").is_file() and found.name != "conformance"
    )


def cannot_run_here(named: list[str] | None = None) -> str | None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    for name in packages() if named is None else named:
        asked = getattr(importlib.import_module(name), "why_not", None)
        if callable(asked):
            answer = asked()
            return str(answer) if answer else None
    return None


def excused(failure: str, reason: str | None = None) -> bool:
    said = cannot_run_here() if reason is None else reason
    return bool(said) and str(said)[:40] in failure


BLOCK = re.compile(r"^```(\w*)\n(.*?)^```$", re.M | re.S)


def blocks(text: str | None = None) -> list[tuple[str, str]]:
    return [
        (lang, body)
        for lang, body in BLOCK.findall(text if text is not None else README.read_text())
    ]


def examples(text: str | None = None) -> list[tuple[str, str | None]]:
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
    def test_an_example_that_runs_is_not_reported(self) -> None:
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
        readme = (
            "```python\nprint(1)\n```\n\n```\n2\n```\n\n```python\nprint(3)\n```\n\n```\n3\n```\n"
        )

        self.assertEqual(mismatched(examples(readme)), [("2", "1")])

    def test_a_member_that_can_run_everything_excuses_nothing(self) -> None:
        self.assertFalse(excused("anything at all", None if cannot_run_here() else "x" * 60))

    def test_a_failure_the_member_says_it_expects_is_excused(self) -> None:
        reason = "no firmware image was found: this backend runs the part's own microcode"

        self.assertTrue(excused(f"Traceback\nNoFirmware: {reason}", reason))

    def test_and_any_other_failure_is_not(self) -> None:
        reason = "no firmware image was found: this backend runs the part's own microcode"

        self.assertFalse(excused("Traceback\nZeroDivisionError: division by zero", reason))

    def test_and_a_member_that_publishes_no_reason_excuses_nothing(self) -> None:
        self.assertFalse(excused("Traceback\nNoFirmware: anything", ""))

    def test_an_example_that_only_this_machine_can_run_is_reported_as_broken(self) -> None:
        readme = "```python\nraise ValueError('nope')\n```\n"

        self.assertEqual(broken(examples(readme)), ["ValueError: nope"])

    def test_an_example_the_member_says_it_cannot_run_is_not_reported_as_broken(self) -> None:
        readme = "```python\nraise SystemExit('no image is here')\n```\n"

        self.assertEqual(broken(examples(readme), "no image is here"), [])

    def test_and_its_stated_output_is_not_compared_either(self) -> None:
        readme = "```python\nraise SystemExit('no image is here')\n```\n\n```\n7\n```\n"

        self.assertEqual(mismatched(examples(readme), "no image is here"), [])

    def test_a_member_that_publishes_a_reason_is_read(self) -> None:
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
        self.assertNotIn("conformance", packages())

    def test_an_example_with_no_stated_output_is_only_run(self) -> None:
        readme = "```python\nprint(1)\n```\n"

        self.assertEqual(mismatched(examples(readme)), [])

    def test_every_example_is_run_and_none_is_skipped(self) -> None:
        found = examples()

        self.assertEqual(len([body for body, _ in found if body.strip()]), len(found))


if __name__ == "__main__":
    unittest.main(verbosity=2)
