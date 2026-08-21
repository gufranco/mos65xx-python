import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import opcodes6502


class TableTest(unittest.TestCase):
    def test_every_byte_decodes_to_something(self) -> None:
        self.assertEqual(len(opcodes6502.NMOS), 256)

    def test_no_entry_names_a_mode_the_table_cannot_size(self) -> None:
        for mnemonic, mode in opcodes6502.NMOS:
            self.assertIn(mode, opcodes6502.MODE_SIZE, mnemonic)

    def test_the_documented_instructions_are_all_present(self) -> None:
        documented = {
            mnemonic for mnemonic, _ in opcodes6502.NMOS if mnemonic not in opcodes6502.UNDOCUMENTED
        }

        self.assertEqual(len(documented), 56)

    def test_every_unstable_instruction_is_also_undocumented(self) -> None:
        self.assertTrue(opcodes6502.UNSTABLE <= opcodes6502.UNDOCUMENTED)

    def test_the_load_immediate_is_where_it_has_always_been(self) -> None:
        self.assertEqual(opcodes6502.NMOS[0xA9], ("lda", "immediate"))

    def test_the_jump_indirect_is_where_it_has_always_been(self) -> None:
        self.assertEqual(opcodes6502.NMOS[0x6C], ("jmp", "indirect"))

    def test_the_undocumented_subtract_shares_an_opcode_row_with_the_real_one(self) -> None:
        self.assertEqual(opcodes6502.NMOS[0xEB], opcodes6502.NMOS[0xE9])


class SizeTest(unittest.TestCase):
    def test_an_implied_instruction_carries_no_operand(self) -> None:
        self.assertEqual(opcodes6502.operand_size("implied"), 0)

    def test_a_zero_page_operand_is_one_byte(self) -> None:
        self.assertEqual(opcodes6502.operand_size("zeroPage"), 1)

    def test_an_absolute_operand_is_two(self) -> None:
        self.assertEqual(opcodes6502.operand_size("absolute"), 2)


class BranchTest(unittest.TestCase):
    def test_a_forward_branch_counts_from_the_instruction_after_it(self) -> None:
        self.assertEqual(opcodes6502.branch_target(0x1000, 2, 0x10), 0x1012)

    def test_a_backward_branch_is_a_signed_offset(self) -> None:
        self.assertEqual(opcodes6502.branch_target(0x1000, 2, 0xF0), 0x0FF2)

    def test_a_branch_past_the_top_wraps_within_the_address_space(self) -> None:
        self.assertEqual(opcodes6502.branch_target(0xFFF0, 2, 0x40), 0x0032)


class DecodeTest(unittest.TestCase):
    def test_an_instruction_reports_where_it_was_found(self) -> None:
        found = opcodes6502.decode(bytes([0xA9, 0x42]), 0, 0x8000)

        self.assertEqual(found.address, 0x8000)
        self.assertEqual(found.mnemonic, "lda")
        self.assertEqual(found.operand, 0x42)
        self.assertEqual(found.size, 2)

    def test_an_absolute_operand_is_read_low_byte_first(self) -> None:
        found = opcodes6502.decode(bytes([0xAD, 0x34, 0x12]), 0, 0x8000)

        self.assertEqual(found.operand, 0x1234)

    def test_an_opcode_with_no_bytes_after_it_is_refused(self) -> None:
        with self.assertRaises(opcodes6502.Truncated):
            opcodes6502.decode(bytes([0xA9]), 0, 0x8000)

    def test_an_offset_past_the_end_is_refused(self) -> None:
        with self.assertRaises(opcodes6502.Truncated):
            opcodes6502.decode(b"", 0, 0x8000)

    def test_an_undocumented_instruction_says_so(self) -> None:
        self.assertTrue(opcodes6502.decode(bytes([0x07, 0x10]), 0, 0x8000).undocumented)

    def test_a_documented_one_does_not(self) -> None:
        self.assertFalse(opcodes6502.decode(bytes([0xA9, 0x10]), 0, 0x8000).undocumented)

    def test_an_unstable_instruction_says_so(self) -> None:
        self.assertTrue(opcodes6502.decode(bytes([0x8B, 0x10]), 0, 0x8000).unstable)

    def test_an_instruction_says_what_it_is_when_printed(self) -> None:
        found = opcodes6502.decode(bytes([0xA9, 0x42]), 0, 0x8000)

        self.assertIn("lda", repr(found))
        self.assertIn("8000", repr(found))

    def test_a_merely_undocumented_one_is_not_unstable(self) -> None:
        self.assertFalse(opcodes6502.decode(bytes([0x07, 0x10]), 0, 0x8000).unstable)


class RenderTest(unittest.TestCase):
    def test_an_implied_instruction_renders_as_nothing(self) -> None:
        self.assertEqual(opcodes6502.render("implied", 0, 0x8000, 1), "")

    def test_an_immediate_carries_its_hash(self) -> None:
        self.assertEqual(opcodes6502.render("immediate", 0x42, 0x8000, 2), "#$42")

    def test_a_branch_renders_the_place_it_goes(self) -> None:
        self.assertEqual(opcodes6502.render("relative", 0x10, 0x1000, 2), "$1012")

    def test_the_indexed_modes_name_their_register(self) -> None:
        self.assertEqual(opcodes6502.render("zeroPageX", 0x10, 0, 2), "$10,X")
        self.assertEqual(opcodes6502.render("zeroPageY", 0x10, 0, 2), "$10,Y")
        self.assertEqual(opcodes6502.render("absoluteX", 0x1234, 0, 3), "$1234,X")
        self.assertEqual(opcodes6502.render("absoluteY", 0x1234, 0, 3), "$1234,Y")

    def test_the_two_indirect_zero_page_modes_read_differently(self) -> None:
        self.assertEqual(opcodes6502.render("indexedIndirectX", 0x10, 0, 2), "($10,X)")
        self.assertEqual(opcodes6502.render("indirectIndexedY", 0x10, 0, 2), "($10),Y")

    def test_an_absolute_indirect_is_parenthesised(self) -> None:
        self.assertEqual(opcodes6502.render("indirect", 0x1234, 0, 3), "($1234)")

    def test_every_mode_the_table_uses_renders(self) -> None:
        for mode in opcodes6502.MODE_SIZE:
            self.assertIsInstance(opcodes6502.render(mode, 0x1234, 0x8000, 3), str)


class DisassembleTest(unittest.TestCase):
    def test_a_run_of_instructions_comes_back_in_order(self) -> None:
        found = list(opcodes6502.disassemble(bytes([0xA9, 0x01, 0xEA, 0x60]), 0, 0x8000))

        self.assertEqual([entry.mnemonic for entry in found], ["lda", "nop", "rts"])

    def test_each_instruction_carries_the_address_it_sits_at(self) -> None:
        found = list(opcodes6502.disassemble(bytes([0xA9, 0x01, 0xEA]), 0, 0x8000))

        self.assertEqual([entry.address for entry in found], [0x8000, 0x8002])

    def test_a_count_stops_it_early(self) -> None:
        found = list(opcodes6502.disassemble(bytes([0xEA] * 8), 0, 0x8000, count=3))

        self.assertEqual(len(found), 3)

    def test_bytes_that_end_mid_instruction_end_the_walk(self) -> None:
        found = list(opcodes6502.disassemble(bytes([0xEA, 0xA9]), 0, 0x8000))

        self.assertEqual([entry.mnemonic for entry in found], ["nop"])

    def test_it_can_stop_where_control_leaves(self) -> None:
        found = list(
            opcodes6502.disassemble(bytes([0xEA, 0x60, 0xEA]), 0, 0x8000, stop_at_return=True)
        )

        self.assertEqual([entry.mnemonic for entry in found], ["nop", "rts"])

    def test_addresses_wrap_at_the_top_of_the_space(self) -> None:
        found = list(opcodes6502.disassemble(bytes([0xEA, 0xEA]), 0, 0xFFFF))

        self.assertEqual([entry.address for entry in found], [0xFFFF, 0x0000])


if __name__ == "__main__":
    unittest.main()
