import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, override

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance import screens

PRINTING = (
    bytes((0x18, 0xFB, 0xE2, 0x30, 0x9C, 0x15, 0x21, 0x9C, 0x16, 0x21, 0x9C, 0x17, 0x21))
    + b"".join(bytes((0xA9, letter, 0x8D, 0x18, 0x21)) for letter in b"PASS PASS ok")
    + bytes((0x80, 0xFE))
)

FAILING = (
    bytes((0x18, 0xFB, 0xE2, 0x30))
    + b"".join(bytes((0xA9, letter, 0x8D, 0x18, 0x21)) for letter in b"FAIL")
    + bytes((0x80, 0xFE))
)

WAITING = bytes((0x18, 0xFB, 0xE2, 0x30, 0xAD, 0x18, 0x42, 0x80, 0xFB))


def an_image(code: bytes) -> bytes:
    body = bytearray(0x8000)
    body[: len(code)] = code
    body[0x7FFC:0x7FFE] = b"\x00\x80"
    return bytes(body)


def an_entry(image: bytes, **fields: Any) -> dict[str, Any]:
    return {
        "id": "tiny",
        "sha256": hashlib.sha256(image).hexdigest(),
        "layout": "lorom",
        "limit": 4_000,
        "until": {"passes": 2},
        "passes": 2,
        "measured": {},
        **fields,
    }


def recorded(name: str) -> dict[str, Any]:
    held: list[dict[str, Any]] = screens.declared()["programs"]
    return next(one for one in held if one["id"] == name)


def lemon(names: list[str]) -> list[tuple[int, int, int]]:
    held = [recorded(name) for name in names]
    return [
        (one["measured"]["printed"]["PASS"], one["passes"], one["measured"]["printed"]["FAIL"])
        for one in held
    ]


class TheRecordedProgramsTest(unittest.TestCase):
    def test_peter_lemons_arithmetic_and_logic_tests_print_every_pass_their_source_prints(
        self,
    ) -> None:
        # Arrange
        names = [
            "peterlemon-cpu-adc",
            "peterlemon-cpu-and",
            "peterlemon-cpu-bit",
            "peterlemon-cpu-cmp",
            "peterlemon-cpu-eor",
            "peterlemon-cpu-ora",
            "peterlemon-cpu-sbc",
        ]

        # Act
        held = lemon(names)

        # Assert
        self.assertEqual(held, [(one[1], one[1], 0) for one in held])

    def test_peter_lemons_shift_step_and_branch_tests_print_every_pass(self) -> None:
        # Arrange
        names = [
            "peterlemon-cpu-asl",
            "peterlemon-cpu-bra",
            "peterlemon-cpu-dec",
            "peterlemon-cpu-inc",
            "peterlemon-cpu-jmp",
            "peterlemon-cpu-lsr",
            "peterlemon-cpu-rol",
            "peterlemon-cpu-ror",
            "peterlemon-cpu-ret",
        ]

        # Act
        held = lemon(names)

        # Assert
        self.assertEqual(held, [(one[1], one[1], 0) for one in held])

    def test_peter_lemons_load_store_move_and_stack_tests_print_every_pass(self) -> None:
        # Arrange
        names = [
            "peterlemon-cpu-ldr",
            "peterlemon-cpu-str",
            "peterlemon-cpu-mov",
            "peterlemon-cpu-msc",
            "peterlemon-cpu-phl",
            "peterlemon-cpu-psr",
            "peterlemon-cpu-trn",
        ]

        # Act
        held = lemon(names)

        # Assert
        self.assertEqual(held, [(one[1], one[1], 0) for one in held])

    def test_gilyon_cputest_reaches_success_after_thirteen_failures_it_names(self) -> None:
        # Arrange
        entry = recorded("gilyon-cputest")

        # Act
        run = entry["measured"]

        # Assert
        self.assertIn("Success", run["screen"])
        self.assertEqual(
            run["failed"],
            [
                "0027",
                "0074",
                "015F",
                "0194",
                "0216",
                "02CC",
                "0397",
                "03D9",
                "046F",
                "04E0",
                "0518",
                "05D2",
                "0621",
            ],
        )

    def test_shay_greens_adc_and_sbc_tests_each_print_passed(self) -> None:
        # Arrange
        names = [
            "blargg-adc-8",
            "blargg-sbc-8",
            "blargg-adc",
            "blargg-adc-16",
            "blargg-sbc",
            "blargg-sbc-16",
        ]

        # Act
        last = [recorded(name)["measured"]["screen"].split("\n")[-1] for name in names]

        # Assert
        self.assertEqual(last, [" Passed"] * 6)


class RunTest(unittest.TestCase):
    def test_a_program_that_prints_its_passes_is_counted(self) -> None:
        # Arrange
        image = an_image(PRINTING)

        # Act
        run = screens.run(image, an_entry(image), chunk=1_000)

        # Assert
        self.assertEqual(
            (run["printed"], run["screen"], run["failed"]),
            ({"PASS": 2, "FAIL": 0}, "PASS PASS ok", []),
        )

    def test_a_failure_stops_the_run(self) -> None:
        # Arrange
        image = an_image(FAILING)

        # Act
        run = screens.run(image, an_entry(image), chunk=1_000)

        # Assert
        self.assertEqual(run["printed"], {"PASS": 0, "FAIL": 1})

    def test_a_screen_it_waits_for_stops_the_run(self) -> None:
        # Arrange
        image = an_image(PRINTING)

        # Act
        run = screens.run(image, an_entry(image, until={"screen": "ok"}), chunk=1_000)

        # Assert
        self.assertLess(run["cycles"], 2_000)

    def test_each_wait_for_a_key_is_kept_with_the_test_number_on_screen(self) -> None:
        # Arrange
        image = an_image(WAITING)

        # Act
        run = screens.run(image, an_entry(image, limit=2_000, until={}), chunk=1_000)

        # Assert
        self.assertGreater(len(run["failed"]), 0)
        self.assertEqual(set(run["failed"]), {""})


class ProblemsTest(unittest.TestCase):
    def test_a_fail_a_wait_and_too_few_passes_are_each_named(self) -> None:
        # Arrange
        run = {"printed": {"PASS": 1, "FAIL": 2}, "failed": ["0027"], "screen": ""}

        # Act
        found = screens.problems({"passes": 3, "until": {"screen": "Success"}}, run)

        # Assert
        self.assertEqual(
            found,
            [
                "printed FAIL 2 times",
                "stopped on a failure at 0027",
                "printed PASS 1 times, its source prints it 3",
                "never showed Success",
            ],
        )


class MainTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.said: list[str] = []
        self.folder = Path(tempfile.mkdtemp())
        self.image = an_image(PRINTING)

    def run_main(self, held: dict[str, Any] | None, **options: Any) -> int:
        settings: dict[str, Any] = {
            "say": self.said.append,
            "environment": {screens.VARIABLE: str(self.folder)},
            "held": held,
            "chunk": 1_000,
        }
        return screens.main((), **{**settings, **options})

    def test_no_directory_runs_nothing(self) -> None:
        # Arrange
        held = {"programs": [an_entry(self.image)]}

        # Act
        status = self.run_main(held, environment={})

        # Assert
        self.assertEqual(status, screens.NOTHING_RAN)

    def test_an_image_that_is_not_there_runs_nothing(self) -> None:
        # Arrange
        held = {"programs": [an_entry(self.image)]}

        # Act
        status = self.run_main(held)

        # Assert
        self.assertEqual(
            (status, self.said[0]), (2, "  tiny: not on this machine, so nothing was run")
        )

    def test_a_run_matching_the_record_passes(self) -> None:
        # Arrange
        (self.folder / "any.sfc").write_bytes(self.image)
        measured = screens.run(self.image, an_entry(self.image), chunk=1_000)

        # Act
        status = self.run_main({"programs": [an_entry(self.image, measured=measured)]})

        # Assert
        self.assertEqual(
            (status, self.said), (0, ["  tiny: 2 PASS, 0 FAIL, 0 waits", "1 runs, 0 wrong"])
        )

    def test_a_changed_run_is_wrong_and_writing_keeps_it(self) -> None:
        # Arrange
        (self.folder / "any.sfc").write_bytes(self.image)
        target = self.folder / "record.json"

        # Act
        status = self.run_main({"programs": [an_entry(self.image)]}, record_path=target)

        # Assert
        self.assertEqual(status, 1)
        self.assertEqual(
            json.loads(target.read_text())["programs"][0]["measured"]["printed"]["PASS"], 2
        )

    def test_the_committed_record_is_read_when_none_is_given(self) -> None:
        # Arrange
        environment: dict[str, str] = {}

        # Act
        status = self.run_main(None, environment=environment)

        # Assert
        self.assertEqual(status, screens.NOTHING_RAN)


if __name__ == "__main__":
    unittest.main()
