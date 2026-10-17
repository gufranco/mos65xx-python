from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import (
    FLAG_DEPENDENT,
    MODE_SIZE,
    OPCODES,
    Truncated,
    decode,
    disassemble,
    render,
)

LENGTHS = (
    ([0xEA], 1, "nop"),
    ([0x60], 1, "rts"),
    ([0x6B], 1, "rtl"),
    ([0xE2, 0x20], 2, "sep #$20"),
    ([0xC2, 0x30], 2, "rep #$30"),
    ([0x8D, 0x01, 0x48], 3, "sta $4801"),
    ([0x8F, 0x1C, 0xF0, 0xC8], 4, "sta $c8f01c"),
    ([0xBF, 0x1C, 0xF0, 0xC8], 4, "lda $c8f01c,x"),
    ([0xBD, 0x03, 0x03], 3, "lda $0303,x"),
    ([0xA5, 0x12], 2, "lda $12"),
    ([0xA7, 0x12], 2, "lda [$12]"),
    ([0xB7, 0x12], 2, "lda [$12],y"),
    ([0x80, 0x10], 2, "bra $8012"),
    ([0x82, 0x00, 0x10], 3, "brl $9003"),
)


def decoded(data: Sequence[int], m: bool = True, x: bool = True) -> Any:
    return decode(bytes(data), 0, 0x008000, m=m, x=x)


class TableTest(unittest.TestCase):
    def test_every_opcode_is_defined(self) -> None:
        # Arrange
        table = OPCODES

        # Act
        count = len(table)

        # Assert
        self.assertEqual(count, 256)

    def test_every_opcode_names_a_known_addressing_mode(self) -> None:
        # Arrange
        table = OPCODES

        # Act
        stray = [
            f"{mnemonic} {mode}"
            for mnemonic, mode in table
            if mode not in MODE_SIZE or not mnemonic.isalpha()
        ]

        # Assert
        self.assertEqual(stray, [])

    def test_the_flag_dependent_modes_are_the_two_immediates(self) -> None:
        # Arrange
        published = FLAG_DEPENDENT

        # Act
        modes = set(published)

        # Assert
        self.assertEqual(modes, {"immediateA", "immediateX"})


class LengthTest(unittest.TestCase):
    def test_known_instruction_lengths(self) -> None:
        # Arrange
        cases = LENGTHS

        # Act
        found = [(decoded(data).size, decoded(data).text) for data, _, _ in cases]

        # Assert
        self.assertEqual(found, [(size, text) for _, size, text in cases])

    def test_an_immediate_follows_the_accumulator_width(self) -> None:
        # Arrange
        cases = (([0xA9, 0x01, 0x00], False), ([0xA9, 0x01], True))

        # Act
        found = [(decoded(data, m=m).size, decoded(data, m=m).text) for data, m in cases]

        # Assert
        self.assertEqual(found, [(3, "lda #$0001"), (2, "lda #$01")])

    def test_an_index_immediate_follows_the_index_width(self) -> None:
        # Arrange
        cases = (([0xA2, 0x34, 0x12], False), ([0xA2, 0x34], True))

        # Act
        found = [(decoded(data, x=x).size, decoded(data, x=x).text) for data, x in cases]

        # Assert
        self.assertEqual(found, [(3, "ldx #$1234"), (2, "ldx #$34")])

    def test_a_block_move_shows_its_operand_bytes_in_stored_order(self) -> None:
        # Arrange
        data = [0x54, 0x7F, 0x7E]

        # Act
        instruction = decoded(data)

        # Assert
        self.assertEqual(
            (instruction.size, instruction.text, instruction.operand), (3, "mvn $7f,$7e", 0x7E7F)
        )

    def test_a_truncated_instruction_is_reported(self) -> None:
        # Arrange
        def attempt() -> Any:
            return decode(b"\x8d\x01", 0, 0x008000)

        # Act
        with self.assertRaises(Truncated) as raised:
            attempt()

        # Assert
        self.assertEqual(raised.exception.args, (0,))


class FlagTrackingTest(unittest.TestCase):
    def test_sep_narrows_and_rep_widens_the_accumulator(self) -> None:
        # Arrange
        code = bytes([0xC2, 0x20, 0xA9, 0x34, 0x12, 0xE2, 0x20, 0xA9, 0x56])

        # Act
        listing = disassemble(code, 0, 0x008000, m=True, x=True)

        # Assert
        self.assertEqual([i.text for i in listing[1::2]], ["lda #$1234", "lda #$56"])

    def test_sep_30_narrows_both_registers(self) -> None:
        # Arrange
        code = bytes([0xE2, 0x30, 0xA9, 0x01, 0xA2, 0x02])

        # Act
        listing = disassemble(code, 0, 0x008000, m=False, x=False)

        # Assert
        self.assertEqual([i.text for i in listing[1:]], ["lda #$01", "ldx #$02"])

    def test_addresses_advance_by_the_instruction_size(self) -> None:
        # Arrange
        code = bytes([0xEA, 0x8D, 0x01, 0x48, 0x60])

        # Act
        listing = disassemble(code, 0, 0x008000)

        # Assert
        self.assertEqual([i.address for i in listing], [0x008000, 0x008001, 0x008004])

    def test_the_program_counter_wraps_inside_its_bank(self) -> None:
        # Arrange
        code = bytes([0xEA, 0xEA])

        # Act
        listing = disassemble(code, 0, 0x00FFFF)

        # Assert
        self.assertEqual([i.address for i in listing], [0x00FFFF, 0x000000])


class BranchTest(unittest.TestCase):
    def test_a_backward_branch_resolves_to_its_target(self) -> None:
        # Arrange
        code = bytes([0x80, 0xFE])

        # Act
        instruction = decode(code, 0, 0x008010)

        # Assert
        self.assertEqual(instruction.text, "bra $8010")

    def test_a_forward_branch_resolves_to_its_target(self) -> None:
        # Arrange
        code = bytes([0x10, 0x05])

        # Act
        instruction = decode(code, 0, 0x008000)

        # Assert
        self.assertEqual(instruction.text, "bpl $8007")


class RenderTest(unittest.TestCase):
    def test_a_mode_the_renderer_does_not_know_is_refused(self) -> None:
        # Arrange
        def attempt() -> Any:
            return render("nonsense", 0, 0x008000, 2, 8)

        # Act
        with self.assertRaises(KeyError) as raised:
            attempt()

        # Assert
        self.assertEqual(raised.exception.args, ("nonsense",))


class DisassembleTest(unittest.TestCase):
    def test_a_listing_stops_at_a_return_when_asked(self) -> None:
        # Arrange
        code = bytes([0xEA, 0x60, 0xEA, 0xEA])

        # Act
        listing = disassemble(code, 0, 0x008000, stop_at_return=True)

        # Assert
        self.assertEqual([step.text.split()[0] for step in listing], ["nop", "rts"])

    def test_a_listing_runs_on_past_a_return_when_not_asked(self) -> None:
        # Arrange
        code = bytes([0xEA, 0x60, 0xEA])

        # Act
        listing = disassemble(code, 0, 0x008000)

        # Assert
        self.assertEqual(len(listing), 3)

    def test_a_listing_stops_once_it_holds_the_number_of_steps_asked_for(self) -> None:
        # Arrange
        code = bytes([0xEA] * 10)

        # Act
        listing = disassemble(code, 0, 0x008000, count=3)

        # Assert
        self.assertEqual(len(listing), 3)

    def test_asking_for_no_steps_gives_none(self) -> None:
        # Arrange
        code = bytes([0xEA] * 4)

        # Act
        listing = disassemble(code, 0, 0x008000, count=0)

        # Assert
        self.assertEqual(listing, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
