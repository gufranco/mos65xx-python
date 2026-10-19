import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, override

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance import exercisers

PASSING = bytes(0x400) + bytes((0xA9, 0x01, 0x4C, 0x02, 0x04))

LOOPING = bytes(0x400) + bytes((0xE8, 0x4C, 0x00, 0x04))

ERRANT = bytes(0x400) + bytes((0x4C, 0x00, 0x04))


def a_program(raw: bytes = PASSING, **fields: Any) -> dict[str, Any]:
    return {
        "id": "tiny",
        "file": "tiny.bin",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "loadAt": "0000",
        "start": "0400",
        "passedAt": "0402",
        "runs": [{"model": "6502"}],
        **fields,
    }


def a_record(*programs: dict[str, Any]) -> dict[str, Any]:
    return {
        "variable": "EXERCISERS_UNDER_TEST",
        "repository": "a repository",
        "commit": "a commit",
        "programs": list(programs),
    }


def a_folder_holding(raw: bytes | None) -> dict[str, str]:
    folder = Path(tempfile.mkdtemp())
    if raw is not None:
        (folder / "tiny.bin").write_bytes(raw)
    return {"EXERCISERS_UNDER_TEST": str(folder)}


def recorded(name: str) -> dict[str, Any]:
    programs: list[dict[str, Any]] = exercisers.declared()["programs"]
    return next(one for one in programs if one["id"] == name)


class TheRecordedVerdictsTest(unittest.TestCase):
    def test_the_6502_functional_test_reported_passed(self) -> None:
        # Arrange
        program = recorded("dormann-6502-functional")

        # Act
        trapped = [one["trappedAt"] for one in program["runs"]]

        # Assert
        self.assertEqual(trapped, ["3469"])
        self.assertIn(f"{program['passedAt']} : 4c6934", program["passedListing"])

    def test_the_65c02_extended_test_reported_passed_on_both_parts_with_its_opcodes(self) -> None:
        # Arrange
        program = recorded("dormann-65c02-extended")

        # Act
        trapped = {one["model"]: one["trappedAt"] for one in program["runs"]}

        # Assert
        self.assertEqual(trapped, {"r65c02": "24f1", "w65c02": "24f1"})
        self.assertIn(f"{program['passedAt']} : 4cf124", program["passedListing"])


class TrapTest(unittest.TestCase):
    def test_a_jump_to_itself_is_where_the_program_stopped(self) -> None:
        # Arrange
        cpu = exercisers.loaded(PASSING, "6502", 0, 0x400)

        # Act
        verdict = exercisers.trap(cpu)

        # Assert
        self.assertEqual((verdict.at(), verdict.steps, verdict.cycles), ("0402", 2, 5))

    def test_a_program_that_never_stops_reports_nowhere(self) -> None:
        # Arrange
        cpu = exercisers.loaded(LOOPING, "6502", 0, 0x400)

        # Act
        verdict = exercisers.trap(cpu, 10)

        # Assert
        self.assertEqual((verdict.at(), verdict.steps), ("nowhere", 10))


class MainTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.said: list[str] = []

    def test_no_directory_runs_nothing_and_says_so(self) -> None:
        # Arrange
        held = a_record(a_program())

        # Act
        status = exercisers.main({}, held, self.said.append)

        # Assert
        self.assertEqual(status, exercisers.NOTHING_RAN)
        self.assertIn("skipped: nothing was run", self.said[0])

    def test_a_directory_that_is_not_there_is_no_directory(self) -> None:
        # Arrange
        environment = {"EXERCISERS_UNDER_TEST": "/nowhere/at/all"}

        # Act
        status = exercisers.main(environment, a_record(a_program()), self.said.append)

        # Assert
        self.assertEqual(status, exercisers.NOTHING_RAN)

    def test_a_program_that_passes_exits_zero(self) -> None:
        # Arrange
        environment = a_folder_holding(PASSING)

        # Act
        status = exercisers.main(environment, a_record(a_program()), self.said.append)

        # Assert
        self.assertEqual(status, 0)
        self.assertEqual(self.said, ["  tiny as a 6502: passed, 2 steps", "1 runs, 0 wrong"])

    def test_a_program_that_stops_elsewhere_exits_one(self) -> None:
        # Arrange
        environment = a_folder_holding(ERRANT)

        # Act
        status = exercisers.main(environment, a_record(a_program(ERRANT)), self.said.append)

        # Assert
        self.assertEqual(status, 1)
        self.assertEqual(self.said[0], "  tiny as a 6502: stopped at 0400, not 0402, 1 steps")

    def test_a_program_that_never_stops_exits_one(self) -> None:
        # Arrange
        environment = a_folder_holding(LOOPING)

        # Act
        status = exercisers.main(
            environment, a_record(a_program(LOOPING)), self.said.append, limit=6
        )

        # Assert
        self.assertEqual(status, 1)
        self.assertEqual(self.said[0], "  tiny as a 6502: stopped at nowhere, not 0402, 6 steps")

    def test_an_image_with_another_digest_is_refused(self) -> None:
        # Arrange
        environment = a_folder_holding(ERRANT)

        # Act
        status = exercisers.main(environment, a_record(a_program()), self.said.append)

        # Assert
        self.assertEqual(status, 1)
        self.assertEqual(self.said[0], "  tiny: does not match its published sha256")

    def test_a_directory_without_the_image_runs_nothing(self) -> None:
        # Arrange
        environment = a_folder_holding(None)

        # Act
        status = exercisers.main(environment, a_record(a_program()), self.said.append)

        # Assert
        self.assertEqual(status, exercisers.NOTHING_RAN)
        self.assertEqual(self.said[0], "  tiny: not on this machine, so nothing was run")

    def test_the_variable_is_read_from_the_process_when_none_is_given(self) -> None:
        # Arrange
        held = a_record(a_program()) | {"variable": "EXERCISERS_NEVER_SET_ANYWHERE"}

        # Act
        status = exercisers.main(None, held, self.said.append)

        # Assert
        self.assertEqual(status, exercisers.NOTHING_RAN)

    def test_the_committed_record_is_read_when_none_is_given(self) -> None:
        # Arrange
        environment: dict[str, str] = {}

        # Act
        status = exercisers.main(environment, None, self.said.append)

        # Assert
        self.assertEqual(status, exercisers.NOTHING_RAN)
        self.assertIn("MOS65XX_EXERCISERS", self.said[1])


if __name__ == "__main__":
    unittest.main()
