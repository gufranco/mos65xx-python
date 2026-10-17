from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conformance import cycles, divergent, singlestep  # noqa: E402

FOLDED = divergent.FOLDED_PUSH

FLAT = divergent.FLAT_PUSH

RECORD = Path(__file__).resolve().parent / "divergences.json"


def a_case(name: str, **initial: Any) -> dict[str, Any]:
    start = {
        "pc": 0x8000,
        "s": 0x01F0,
        "p": 0x00,
        "a": 0x1234,
        "x": 0x0005,
        "y": 0x0078,
        "dbr": 0x12,
        "d": 0x0000,
        "pbr": 0x00,
        "e": 1,
        "ram": [[0x008000, 0xEA], [0x008001, 0xFA]],
    }
    return {"name": name, "initial": {**start, **initial}, "final": {}, "cycles": []}


def recorded_subjects() -> list[str]:
    held = json.loads(RECORD.read_text())["divergences"]
    return [str(one["subject"]) for one in held]


class OnePullTest(unittest.TestCase):
    def test_a_pull_at_the_page_edge_is_named(self) -> None:
        # Arrange
        case = a_case("ab e 75", s=0x01FF)

        # Act
        found = divergent.recorded_divergence(case, "65816")

        # Assert
        self.assertIn("one byte pull", found)

    def test_one_anywhere_else_in_the_page_is_not(self) -> None:
        # Arrange
        case = a_case("ab e 75", s=0x01FE)

        # Act
        found = divergent.recorded_divergence(case, "65816")

        # Assert
        self.assertEqual(found, "")

    def test_nor_is_one_in_native_mode(self) -> None:
        # Arrange
        case = a_case("ab n 75", s=0x01FF, e=0)

        # Act
        found = divergent.recorded_divergence(case, "65816")

        # Assert
        self.assertEqual(found, "")

    def test_nor_is_a_different_opcode_at_the_same_edge(self) -> None:
        # Arrange
        case = a_case("68 e 75", s=0x01FF)

        # Act
        found = divergent.recorded_divergence(case, "65816")

        # Assert
        self.assertEqual(found, "")

    def test_nor_is_it_left_out_for_another_part(self) -> None:
        # Arrange
        case = a_case("ab e 75", s=0x01FF)

        # Act
        found = divergent.recorded_divergence(case, "6502")

        # Assert
        self.assertEqual(found, "")


class TableCallTest(unittest.TestCase):
    def test_a_call_at_the_bottom_of_page_one_is_compared_rather_than_left_out(self) -> None:
        # Arrange
        case = a_case("fc e 458", s=0x0100)

        # Act
        found = divergent.recorded_divergence(case, "65816")

        # Assert
        self.assertEqual(found, "")

    def test_and_only_the_two_bytes_the_readings_disagree_on_are_excused(self) -> None:
        # Arrange
        case = a_case("fc e 458", s=0x0100)
        wrong = [("$0001FF", 0x34, 0x99), ("$0000FF", 0x55, 0x34), ("s", 0x01FE, 0x01FD)]

        # Act
        left = divergent.unexplained(case, wrong, "65816")

        # Assert
        self.assertEqual(left, [("s", 0x01FE, 0x01FD)])

    def test_one_with_room_below_it_excuses_nothing(self) -> None:
        # Arrange
        case = a_case("fc e 458", s=0x0101)
        wrong = [("$0001FF", 0x34, 0x99)]

        # Act
        left = divergent.unexplained(case, wrong, "65816")

        # Assert
        self.assertEqual(left, wrong)


class PointerTest(unittest.TestCase):
    def test_a_pointer_starting_at_the_end_of_an_aligned_page_is_named(self) -> None:
        # Arrange
        case = a_case("e1 e 8669")

        # Act
        found = divergent.recorded_divergence(case, "65816")

        # Assert
        self.assertIn("multi-byte pointer", found)

    def test_one_that_stops_short_of_the_end_is_not(self) -> None:
        # Arrange
        case = a_case("e1 e 8669", x=0x04)

        # Act
        found = divergent.recorded_divergence(case, "65816")

        # Assert
        self.assertEqual(found, "")

    def test_nor_is_one_with_an_unaligned_direct_register(self) -> None:
        # Arrange
        case = a_case("e1 e 8669", d=0x0001)

        # Act
        found = divergent.recorded_divergence(case, "65816")

        # Assert
        self.assertEqual(found, "")

    def test_nor_is_one_whose_operand_the_case_does_not_carry(self) -> None:
        # Arrange
        case = a_case("e1 e 8669", ram=[[0x008000, 0xE1]])

        # Act
        found = divergent.recorded_divergence(case, "65816")

        # Assert
        self.assertEqual(found, "")

    def test_nor_is_another_mode_reading_the_same_pointer(self) -> None:
        # Arrange
        case = a_case("b2 e 8669")

        # Act
        found = divergent.recorded_divergence(case, "65816")

        # Assert
        self.assertEqual(found, "")


class DataBankTest(unittest.TestCase):
    def test_a_break_with_a_data_bank_set_excuses_only_that_register(self) -> None:
        # Arrange
        case = a_case("00 e 1")
        wrong = [("dbr", 0x12, 0x00), ("a", 0x1234, 0x9999)]

        # Act
        left = divergent.unexplained(case, wrong, "65816")

        # Assert
        self.assertEqual(left, [("a", 0x1234, 0x9999)])

    def test_so_does_a_coprocessor_call(self) -> None:
        # Arrange
        case = a_case("02 e 1")
        wrong = [("dbr", 0x12, 0x00)]

        # Act
        left = divergent.unexplained(case, wrong, "65816")

        # Assert
        self.assertEqual(left, [])

    def test_a_break_that_starts_in_bank_zero_excuses_nothing(self) -> None:
        # Arrange
        case = a_case("00 e 1", dbr=0x00)
        wrong = [("dbr", 0x05, 0x00)]

        # Act
        left = divergent.unexplained(case, wrong, "65816")

        # Assert
        self.assertEqual(left, wrong)

    def test_nor_does_one_in_native_mode(self) -> None:
        # Arrange
        case = a_case("00 n 1", e=0)
        wrong = [("dbr", 0x12, 0x00)]

        # Act
        left = divergent.unexplained(case, wrong, "65816")

        # Assert
        self.assertEqual(left, wrong)

    def test_a_case_left_out_outright_has_nothing_excused_field_by_field(self) -> None:
        # Arrange
        case = a_case("ab e 75", s=0x01FF)
        wrong = [("$000200", 0x01, 0x02)]

        # Act
        left = divergent.unexplained(case, wrong, "65816")

        # Assert
        self.assertEqual(left, wrong)


class RecordTest(unittest.TestCase):
    def test_every_condition_names_a_divergence_the_record_explains(self) -> None:
        # Arrange
        named = [
            *(subject for subject, _ in divergent.DIVERGENT),
            *(subject for subject, _, _ in divergent.EXCUSED_FIELDS),
            *(subject for subject, _, _ in divergent.EXCUSED_ADDRESSES),
        ]

        # Act
        missing = [subject for subject in named if subject not in recorded_subjects()]

        # Assert
        self.assertEqual(missing, [])


def a_break(**final: Any) -> dict[str, Any]:
    case = a_case("00 e 1", ram=[[0x008000, 0x00], [0x008001, 0x00]])
    return {**case, "final": final}


def a_table_call() -> dict[str, Any]:
    ram = [[0x008000, 0xFC], [0x008001, 0x00], [0x008002, 0x90]]
    case = a_case("fc e 458", s=0x0100, x=0x00, ram=ram)
    seen = cycles.check(case, "65816") or []
    recorded = [
        [FOLDED if address == FLAT else address, value, pins] for address, value, pins in seen
    ]
    return {**case, "cycles": recorded}


def run_main(runner: Any, cases: list[dict[str, Any]], name: str) -> str:
    said = io.StringIO()
    with tempfile.TemporaryDirectory() as where:
        (Path(where) / name).write_text(json.dumps(cases))
        with contextlib.redirect_stdout(said):
            runner.main([where, "--model", "65816"])
    return said.getvalue()


class RunTest(unittest.TestCase):
    def test_a_case_whose_only_difference_is_excused_is_counted_as_excused(self) -> None:
        # Arrange
        case = a_break(dbr=0x12)

        # Act
        counted = singlestep.run_tests([case], model="65816")[:4]

        # Assert
        self.assertEqual(counted, (0, 0, 0, 1))

    def test_and_one_that_also_differs_elsewhere_still_fails(self) -> None:
        # Arrange
        case = a_break(dbr=0x12, a=0x9999)

        # Act
        counted = singlestep.run_tests([case], model="65816")

        # Assert
        self.assertEqual((*counted[:4], counted[4][0][1]), (0, 1, 0, 0, [("a", 0x9999, 0x1234)]))

    def test_the_state_runner_says_how_many_it_excused(self) -> None:
        # Arrange
        case = a_break(dbr=0x12)

        # Act
        said = run_main(singlestep, [case], "00.e.json")

        # Assert
        self.assertIn("1 agreed in every field but those a recorded divergence names", said)


class CycleTest(unittest.TestCase):
    def test_a_table_call_differing_only_at_the_folded_push_is_excused(self) -> None:
        # Arrange
        case = a_table_call()

        # Act
        counted = cycles.run_tests([case], "65816")[:4]

        # Assert
        self.assertEqual(counted, (0, 0, 0, 1))

    def test_and_one_differing_anywhere_else_still_differs(self) -> None:
        # Arrange
        case = a_table_call()
        case["cycles"][0][1] = 0x00

        # Act
        counted = cycles.run_tests([case], "65816")[:4]

        # Assert
        self.assertEqual(counted, (0, 1, 0, 0))

    def test_an_address_other_than_the_two_named_is_not_excused(self) -> None:
        # Arrange
        want = [(0x000100, 0x80, "w"), (0x0001FE, 0x01, "w")]
        seen = [(0x000100, 0x80, "w"), (0x0000FE, 0x01, "w")]

        # Act
        found = divergent.differs_only_where_excused(
            a_case("fc e 1", s=0x0100), "65816", want, seen
        )

        # Assert
        self.assertFalse(found)

    def test_nor_is_a_trace_of_another_length(self) -> None:
        # Arrange
        want = [(FOLDED, 0x01, "w")]
        seen = [(FLAT, 0x01, "w"), (0x000100, 0x80, "w")]

        # Act
        found = divergent.differs_only_where_excused(
            a_case("fc e 1", s=0x0100), "65816", want, seen
        )

        # Assert
        self.assertFalse(found)

    def test_nor_a_case_no_divergence_names(self) -> None:
        # Arrange
        want = [(FOLDED, 0x01, "w")]
        seen = [(FLAT, 0x01, "w")]

        # Act
        found = divergent.differs_only_where_excused(
            a_case("fc e 1", s=0x0101), "65816", want, seen
        )

        # Assert
        self.assertFalse(found)

    def test_the_cycle_runner_says_how_many_it_excused(self) -> None:
        # Arrange
        case = a_table_call()

        # Act
        said = run_main(cycles, [case], "fc.e.json")

        # Assert
        self.assertIn("1 agreed on every cycle but the one address", said)


if __name__ == "__main__":
    unittest.main()
