import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, override

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance import routines

PASSING = bytes((0xA2, 0xFF, 0x86, 0x75, 0x80, 0xFE))

COPYING = bytes(
    (0xC2, 0x30, 0xA9, 0x03, 0x00, 0xA2, 0x20, 0x80, 0xA0, 0x00, 0x00, 0x54, 0x7F, 0x00)
) + bytes((0xE2, 0x30, 0xA2, 0xFF, 0x86, 0x75, 0x80, 0xFE))

SPINNING = bytes((0x80, 0xFE))


def an_image(code: bytes) -> bytes:
    body = bytearray(0x8000)
    body[: len(code)] = code
    body[0x20:0x24] = b"\x0a\x0b\x0c\x0d"
    return bytes(body)


def an_entry(image: bytes, **fields: Any) -> dict[str, Any]:
    return {
        "id": "tiny",
        "sha256": hashlib.sha256(image).hexdigest(),
        "layout": "lorom",
        "start": "008000",
        "flag": "000075",
        "copies": [],
        "measured": {},
        **fields,
    }


def recorded(name: str) -> dict[str, Any]:
    held: list[dict[str, Any]] = routines.declared()["routines"]
    return next(one for one in held if one["id"] == name)


def passed(name: str) -> tuple[str, list[bool]]:
    run = recorded(name)["measured"]
    return run["flag"], run["copiesMatch"]


class TheRecordedRoutinesTest(unittest.TestCase):
    def test_the_burn_in_cpu_test_passes_and_its_unchecked_copies_hold(self) -> None:
        # Arrange
        name = "burn-in-rev-d-cpu"

        # Act
        held = passed(name)

        # Assert
        self.assertEqual(held, ("ff", [True, True]))

    def test_the_snsp_aging_65c816_test_passes_with_its_copies_and_relocations(self) -> None:
        # Arrange
        name = "snsp-aging-1-02-65c816"

        # Act
        held = passed(name)

        # Assert
        self.assertEqual(held, ("ff", [True, True]))

    def test_the_control_deck_tester_cpu_test_passes(self) -> None:
        # Arrange
        name = "control-deck-tester-rev-1-cpu"

        # Act
        held = passed(name)

        # Assert
        self.assertEqual(held, ("ff", [True, True]))

    def test_the_ntf_2_5_cpu_test_passes(self) -> None:
        # Arrange
        name = "ntf-2-5-rev-a-cpu"

        # Act
        held = passed(name)

        # Assert
        self.assertEqual(held, ("ff", [True, True]))

    def test_the_overdumped_test_program_runs_the_same_cpu_test_and_passes(self) -> None:
        # Arrange
        name = "test-program-overdump-cpu"

        # Act
        held = passed(name)

        # Assert
        self.assertEqual(held, ("ff", [True, True]))

    def test_the_aging_1_00_work_ram_mirror_routine_passes(self) -> None:
        # Arrange
        name = "aging-1-00-work-ram-mirror"

        # Act
        held = passed(name)

        # Assert
        self.assertEqual(held, ("ff", []))


class RunTest(unittest.TestCase):
    def test_a_routine_that_sets_its_flag_is_measured(self) -> None:
        # Arrange
        entry = an_entry(an_image(PASSING))

        # Act
        run = routines.run(an_image(PASSING), entry, limit=50)

        # Assert
        self.assertEqual(run, {"flag": "ff", "steps": 14, "copiesMatch": []})

    def test_a_block_move_is_compared_with_where_it_came_from(self) -> None:
        # Arrange
        image = an_image(COPYING)
        entry = an_entry(image, copies=[{"to": "7F0000", "from": "008020", "length": 4}])

        # Act
        run = routines.run(image, entry, limit=50)

        # Assert
        self.assertEqual((run["flag"], run["copiesMatch"]), ("ff", [True]))

    def test_a_copy_that_does_not_match_is_measured_as_such(self) -> None:
        # Arrange
        image = an_image(PASSING)
        entry = an_entry(image, copies=[{"to": "7F0000", "from": "008020", "length": 4}])

        # Act
        run = routines.run(image, entry, limit=50)

        # Assert
        self.assertEqual(run["copiesMatch"], [False])

    def test_a_routine_that_never_sets_its_flag_is_measured_as_such(self) -> None:
        # Arrange
        image = an_image(SPINNING)

        # Act
        run = routines.run(image, an_entry(image), limit=20)

        # Assert
        self.assertEqual(run, {"flag": None, "steps": 20, "copiesMatch": []})


class MainTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.said: list[str] = []
        self.folder = Path(tempfile.mkdtemp())
        self.image = an_image(PASSING)

    def run_main(self, held: dict[str, Any] | None, **options: Any) -> int:
        settings: dict[str, Any] = {
            "say": self.said.append,
            "environment": {routines.VARIABLE: str(self.folder)},
            "held": held,
            "limit": 50,
        }
        return routines.main((), **{**settings, **options})

    def test_no_directory_runs_nothing_and_says_so(self) -> None:
        # Arrange
        held = {"routines": [an_entry(self.image)]}

        # Act
        status = self.run_main(held, environment={})

        # Assert
        self.assertEqual(status, routines.NOTHING_RAN)
        self.assertIn("skipped", self.said[0])

    def test_an_image_that_is_not_there_runs_nothing(self) -> None:
        # Arrange
        held = {"routines": [an_entry(self.image)]}

        # Act
        status = self.run_main(held)

        # Assert
        self.assertEqual(status, routines.NOTHING_RAN)
        self.assertEqual(self.said[0], "  tiny: not on this machine, so nothing was run")

    def test_files_that_are_not_the_image_are_passed_over(self) -> None:
        # Arrange
        (self.folder / "notes.txt").write_bytes(self.image)
        (self.folder / "another.sfc").write_bytes(b"another")

        # Act
        found = routines.located(hashlib.sha256(self.image).hexdigest(), [self.folder])

        # Assert
        self.assertIsNone(found)

    def test_a_run_matching_the_record_passes(self) -> None:
        # Arrange
        (self.folder / "any name.sfc").write_bytes(self.image)
        measured = {"flag": "ff", "steps": 14, "copiesMatch": []}

        # Act
        status = self.run_main({"routines": [an_entry(self.image, measured=measured)]})

        # Assert
        self.assertEqual(
            (status, self.said), (0, ["  tiny: flag ff after 14 steps", "1 runs, 0 wrong"])
        )

    def test_a_flag_left_clear_or_a_copy_astray_or_a_changed_run_is_wrong(self) -> None:
        # Arrange
        image = an_image(SPINNING)
        (self.folder / "any name.sfc").write_bytes(image)
        copies = [{"to": "7F0000", "from": "008020", "length": 4}]

        # Act
        status = self.run_main({"routines": [an_entry(image, copies=copies)]})

        # Assert
        self.assertEqual(status, 1)
        self.assertEqual(
            self.said[1:4],
            [
                "  tiny: the routine never set its flag to ff",
                "  tiny: a block move does not match its source",
                "  tiny: differs from the recorded run",
            ],
        )

    def test_writing_keeps_what_the_run_measured(self) -> None:
        # Arrange
        (self.folder / "any name.sfc").write_bytes(self.image)
        target = self.folder / "record.json"

        # Act
        self.run_main({"routines": [an_entry(self.image)]}, record_path=target)

        # Assert
        written = json.loads(target.read_text())["routines"][0]["measured"]
        self.assertEqual(written, {"flag": "ff", "steps": 14, "copiesMatch": []})

    def test_the_committed_record_is_read_when_none_is_given(self) -> None:
        # Arrange
        environment: dict[str, str] = {}

        # Act
        status = self.run_main(None, environment=environment)

        # Assert
        self.assertEqual(status, routines.NOTHING_RAN)

    def test_the_process_environment_is_read_when_none_is_given(self) -> None:
        # Arrange
        held = {"routines": [an_entry(self.image)], "variable": "NEVER_SET_ANYWHERE"}

        # Act
        status = self.run_main(held, environment=None)

        # Assert
        self.assertEqual(status, routines.NOTHING_RAN)


if __name__ == "__main__":
    unittest.main()
