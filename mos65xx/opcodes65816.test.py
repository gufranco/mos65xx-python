from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent


cpu = importlib.import_module("mos65xx.opcodes65816")


def decode(data: Sequence[int], m: bool = True, x: bool = True) -> Any:
    return cpu.decode(bytes(data), 0, 0x008000, m=m, x=x)


class TableTest(unittest.TestCase):
    def test_every_opcode_is_defined(self) -> None:
        self.assertEqual(len(cpu.OPCODES), 256)

    def test_every_opcode_names_a_known_addressing_mode(self) -> None:
        for mnemonic, mode in cpu.OPCODES:
            self.assertIn(mode, cpu.MODE_SIZE)
            self.assertTrue(mnemonic.isalpha())

    def test_the_flag_dependent_modes_are_the_two_immediates(self) -> None:
        self.assertEqual(set(cpu.FLAG_DEPENDENT), {"immediateA", "immediateX"})


class LengthTest(unittest.TestCase):
    def test_known_instruction_lengths(self) -> None:
        cases = [
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
        ]

        for data, size, text in cases:
            instruction = decode(data)

            self.assertEqual(instruction.size, size, text)
            self.assertEqual(instruction.text, text)

    def test_an_immediate_follows_the_accumulator_width(self) -> None:
        wide = decode([0xA9, 0x01, 0x00], m=False)
        narrow = decode([0xA9, 0x01], m=True)

        self.assertEqual((wide.size, wide.text), (3, "lda #$0001"))
        self.assertEqual((narrow.size, narrow.text), (2, "lda #$01"))

    def test_an_index_immediate_follows_the_index_width(self) -> None:
        wide = decode([0xA2, 0x34, 0x12], x=False)
        narrow = decode([0xA2, 0x34], x=True)

        self.assertEqual((wide.size, wide.text), (3, "ldx #$1234"))
        self.assertEqual((narrow.size, narrow.text), (2, "ldx #$34"))

    def test_a_block_move_shows_its_operand_bytes_in_stored_order(self) -> None:
        instruction = decode([0x54, 0x7F, 0x7E])

        self.assertEqual(instruction.size, 3)
        self.assertEqual(instruction.text, "mvn $7f,$7e")
        self.assertEqual(instruction.operand, 0x7E7F)

    def test_a_truncated_instruction_is_reported(self) -> None:
        with self.assertRaises(cpu.Truncated):
            cpu.decode(b"\x8d\x01", 0, 0x008000)


class FlagTrackingTest(unittest.TestCase):
    def test_sep_narrows_and_rep_widens_the_accumulator(self) -> None:
        code = bytes([0xC2, 0x20, 0xA9, 0x34, 0x12, 0xE2, 0x20, 0xA9, 0x56])

        listing = cpu.disassemble(code, 0, 0x008000, m=True, x=True)

        self.assertEqual([i.text for i in listing[1::2]], ["lda #$1234", "lda #$56"])

    def test_sep_30_narrows_both_registers(self) -> None:
        code = bytes([0xE2, 0x30, 0xA9, 0x01, 0xA2, 0x02])

        listing = cpu.disassemble(code, 0, 0x008000, m=False, x=False)

        self.assertEqual(listing[1].text, "lda #$01")
        self.assertEqual(listing[2].text, "ldx #$02")

    def test_addresses_advance_by_the_instruction_size(self) -> None:
        code = bytes([0xEA, 0x8D, 0x01, 0x48, 0x60])

        listing = cpu.disassemble(code, 0, 0x008000)

        self.assertEqual([i.address for i in listing], [0x008000, 0x008001, 0x008004])

    def test_the_program_counter_wraps_inside_its_bank(self) -> None:
        code = bytes([0xEA, 0xEA])

        listing = cpu.disassemble(code, 0, 0x00FFFF)

        self.assertEqual([i.address for i in listing], [0x00FFFF, 0x000000])


class BranchTest(unittest.TestCase):
    def test_a_backward_branch_resolves_to_its_target(self) -> None:
        instruction = cpu.decode(bytes([0x80, 0xFE]), 0, 0x008010)

        self.assertEqual(instruction.text, "bra $8010")

    def test_a_forward_branch_resolves_to_its_target(self) -> None:
        instruction = cpu.decode(bytes([0x10, 0x05]), 0, 0x008000)

        self.assertEqual(instruction.text, "bpl $8007")


class RenderTest(unittest.TestCase):
    def test_a_mode_the_renderer_does_not_know_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            cpu.render("nonsense", 0, 0x008000, 2, 8)


class DisassembleTest(unittest.TestCase):
    def test_a_listing_stops_at_a_return_when_asked(self) -> None:
        code = bytes([0xEA, 0x60, 0xEA, 0xEA])

        listing = cpu.disassemble(code, 0, 0x008000, stop_at_return=True)

        self.assertEqual([step.text.split()[0] for step in listing], ["nop", "rts"])

    def test_a_listing_runs_on_past_a_return_when_not_asked(self) -> None:
        code = bytes([0xEA, 0x60, 0xEA])

        listing = cpu.disassemble(code, 0, 0x008000)

        self.assertEqual(len(listing), 3)

    def test_a_listing_stops_once_it_holds_the_number_of_steps_asked_for(self) -> None:
        listing = cpu.disassemble(bytes([0xEA] * 10), 0, 0x008000, count=3)

        self.assertEqual(len(listing), 3)

    def test_asking_for_no_steps_gives_none(self) -> None:
        listing = cpu.disassemble(bytes([0xEA] * 4), 0, 0x008000, count=0)

        self.assertEqual(listing, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
