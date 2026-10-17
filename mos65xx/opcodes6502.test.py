import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import NMOS, Truncated, decode8, disassemble8, render8

EVERY_OPCODE = range(256)


def decoded(opcode: int, *operand: int) -> Any:
    return decode8(bytes([opcode, *operand, 0x00, 0x00]), 0, 0x8000)


class TableTest(unittest.TestCase):
    def test_every_byte_decodes_to_something(self) -> None:
        # Arrange
        opcodes = EVERY_OPCODE

        # Act
        found = [decoded(opcode).opcode for opcode in opcodes]

        # Assert
        self.assertEqual(found, list(range(256)))

    def test_every_entry_is_an_opcode_and_at_most_two_operand_bytes(self) -> None:
        # Arrange
        opcodes = EVERY_OPCODE

        # Act
        sizes = {decoded(opcode).size for opcode in opcodes}

        # Assert
        self.assertEqual(sizes, {1, 2, 3})

    def test_the_documented_instructions_are_the_fifty_six_appendix_b_prints(self) -> None:
        # Arrange
        opcodes = EVERY_OPCODE

        # Act
        documented = {
            decoded(opcode).mnemonic for opcode in opcodes if not decoded(opcode).undocumented
        }

        # Assert
        self.assertEqual(len(documented), 56)

    def test_every_unstable_instruction_is_also_undocumented(self) -> None:
        # Arrange
        opcodes = EVERY_OPCODE

        # Act
        stray = [
            opcode
            for opcode in opcodes
            if decoded(opcode).unstable and not decoded(opcode).undocumented
        ]

        # Assert
        self.assertEqual(stray, [])

    def test_the_load_immediate_is_where_it_has_always_been(self) -> None:
        # Arrange
        opcode = 0xA9

        # Act
        found = decoded(opcode)

        # Assert
        self.assertEqual((found.mnemonic, found.mode), ("lda", "immediate"))

    def test_the_jump_indirect_is_where_it_has_always_been(self) -> None:
        # Arrange
        opcode = 0x6C

        # Act
        found = decoded(opcode)

        # Assert
        self.assertEqual((found.mnemonic, found.mode), ("jmp", "indirect"))

    def test_the_undocumented_subtract_shares_an_opcode_row_with_the_real_one(self) -> None:
        # Arrange
        documented = decoded(0xE9)

        # Act
        found = decoded(0xEB)

        # Assert
        self.assertEqual((found.mnemonic, found.mode), (documented.mnemonic, documented.mode))

    def test_the_table_the_package_publishes_is_the_one_it_decodes_with(self) -> None:
        # Arrange
        table = NMOS

        # Act
        found = [(decoded(opcode).mnemonic, decoded(opcode).mode) for opcode in EVERY_OPCODE]

        # Assert
        self.assertEqual(found, list(table))


class SizeTest(unittest.TestCase):
    def test_an_implied_instruction_carries_no_operand(self) -> None:
        # Arrange
        opcode = 0xEA

        # Act
        found = decoded(opcode)

        # Assert
        self.assertEqual(found.size, 1)

    def test_a_zero_page_operand_is_one_byte(self) -> None:
        # Arrange
        opcode = 0xA5

        # Act
        found = decoded(opcode)

        # Assert
        self.assertEqual(found.size, 2)

    def test_an_absolute_operand_is_two(self) -> None:
        # Arrange
        opcode = 0xAD

        # Act
        found = decoded(opcode)

        # Assert
        self.assertEqual(found.size, 3)


class BranchTest(unittest.TestCase):
    def test_a_forward_branch_counts_from_the_instruction_after_it(self) -> None:
        # Arrange
        found = decode8(bytes([0xD0, 0x10]), 0, 0x1000)

        # Act
        target = render8(found.mode, found.operand, found.address, found.size)

        # Assert
        self.assertEqual(target, "$1012")

    def test_a_backward_branch_is_a_signed_offset(self) -> None:
        # Arrange
        found = decode8(bytes([0xD0, 0xF0]), 0, 0x1000)

        # Act
        target = render8(found.mode, found.operand, found.address, found.size)

        # Assert
        self.assertEqual(target, "$0FF2")

    def test_a_branch_past_the_top_wraps_within_the_address_space(self) -> None:
        # Arrange
        found = decode8(bytes([0xD0, 0x40]), 0, 0xFFF0)

        # Act
        target = render8(found.mode, found.operand, found.address, found.size)

        # Assert
        self.assertEqual(target, "$0032")


class DecodeTest(unittest.TestCase):
    def test_an_instruction_reports_where_it_was_found(self) -> None:
        # Arrange
        code = bytes([0xA9, 0x42])

        # Act
        found = decode8(code, 0, 0x8000)

        # Assert
        self.assertEqual(
            (found.address, found.mnemonic, found.operand, found.size), (0x8000, "lda", 0x42, 2)
        )

    def test_an_absolute_operand_is_read_low_byte_first(self) -> None:
        # Arrange
        code = bytes([0xAD, 0x34, 0x12])

        # Act
        found = decode8(code, 0, 0x8000)

        # Assert
        self.assertEqual(found.operand, 0x1234)

    def test_an_opcode_with_no_bytes_after_it_is_refused(self) -> None:
        # Arrange
        def attempt() -> Any:
            return decode8(bytes([0xA9]), 0, 0x8000)

        # Act
        with self.assertRaises(Truncated) as raised:
            attempt()

        # Assert
        self.assertEqual(str(raised.exception), "lda at 8000 needs 1 more bytes")

    def test_an_offset_past_the_end_is_refused(self) -> None:
        # Arrange
        def attempt() -> Any:
            return decode8(b"", 0, 0x8000)

        # Act
        with self.assertRaises(Truncated) as raised:
            attempt()

        # Assert
        self.assertEqual(str(raised.exception), "no opcode at 0")

    def test_an_undocumented_instruction_says_so(self) -> None:
        # Arrange
        code = bytes([0x07, 0x10])

        # Act
        found = decode8(code, 0, 0x8000)

        # Assert
        self.assertTrue(found.undocumented)

    def test_a_documented_one_does_not(self) -> None:
        # Arrange
        code = bytes([0xA9, 0x10])

        # Act
        found = decode8(code, 0, 0x8000)

        # Assert
        self.assertFalse(found.undocumented)

    def test_an_unstable_instruction_says_so(self) -> None:
        # Arrange
        code = bytes([0x8B, 0x10])

        # Act
        found = decode8(code, 0, 0x8000)

        # Assert
        self.assertTrue(found.unstable)

    def test_a_merely_undocumented_one_is_not_unstable(self) -> None:
        # Arrange
        code = bytes([0x07, 0x10])

        # Act
        found = decode8(code, 0, 0x8000)

        # Assert
        self.assertFalse(found.unstable)

    def test_an_instruction_says_what_it_is_when_printed(self) -> None:
        # Arrange
        found = decode8(bytes([0xA9, 0x42]), 0, 0x8000)

        # Act
        described = repr(found)

        # Assert
        self.assertEqual(described, "<lda immediate at 8000>")


class RenderTest(unittest.TestCase):
    def test_an_implied_instruction_renders_as_nothing(self) -> None:
        # Arrange
        mode = "implied"

        # Act
        text = render8(mode, 0, 0x8000, 1)

        # Assert
        self.assertEqual(text, "")

    def test_an_immediate_carries_its_hash(self) -> None:
        # Arrange
        mode = "immediate"

        # Act
        text = render8(mode, 0x42, 0x8000, 2)

        # Assert
        self.assertEqual(text, "#$42")

    def test_the_indexed_modes_name_their_register(self) -> None:
        # Arrange
        cases = (
            ("zeroPageX", 0x10, 2),
            ("zeroPageY", 0x10, 2),
            ("absoluteX", 0x1234, 3),
            ("absoluteY", 0x1234, 3),
        )

        # Act
        texts = [render8(mode, operand, 0, size) for mode, operand, size in cases]

        # Assert
        self.assertEqual(texts, ["$10,X", "$10,Y", "$1234,X", "$1234,Y"])

    def test_the_two_indirect_zero_page_modes_read_differently(self) -> None:
        # Arrange
        modes = ("indexedIndirectX", "indirectIndexedY")

        # Act
        texts = [render8(mode, 0x10, 0, 2) for mode in modes]

        # Assert
        self.assertEqual(texts, ["($10,X)", "($10),Y"])

    def test_an_absolute_indirect_is_parenthesised(self) -> None:
        # Arrange
        mode = "indirect"

        # Act
        text = render8(mode, 0x1234, 0, 3)

        # Assert
        self.assertEqual(text, "($1234)")

    def test_every_instruction_with_an_operand_renders_it(self) -> None:
        # Arrange
        found = [decoded(opcode, 0x34, 0x12) for opcode in EVERY_OPCODE]

        # Act
        silent = [
            f"{one.opcode:02X}"
            for one in found
            if one.size > 1 and "$" not in render8(one.mode, one.operand, one.address, one.size)
        ]

        # Assert
        self.assertEqual(silent, [])


class DisassembleTest(unittest.TestCase):
    def test_a_run_of_instructions_comes_back_in_order(self) -> None:
        # Arrange
        code = bytes([0xA9, 0x01, 0xEA, 0x60])

        # Act
        found = list(disassemble8(code, 0, 0x8000))

        # Assert
        self.assertEqual([entry.mnemonic for entry in found], ["lda", "nop", "rts"])

    def test_each_instruction_carries_the_address_it_sits_at(self) -> None:
        # Arrange
        code = bytes([0xA9, 0x01, 0xEA])

        # Act
        found = list(disassemble8(code, 0, 0x8000))

        # Assert
        self.assertEqual([entry.address for entry in found], [0x8000, 0x8002])

    def test_a_count_stops_it_early(self) -> None:
        # Arrange
        code = bytes([0xEA] * 8)

        # Act
        found = list(disassemble8(code, 0, 0x8000, count=3))

        # Assert
        self.assertEqual(len(found), 3)

    def test_bytes_that_end_mid_instruction_end_the_walk(self) -> None:
        # Arrange
        code = bytes([0xEA, 0xA9])

        # Act
        found = list(disassemble8(code, 0, 0x8000))

        # Assert
        self.assertEqual([entry.mnemonic for entry in found], ["nop"])

    def test_it_can_stop_where_control_leaves(self) -> None:
        # Arrange
        code = bytes([0xEA, 0x60, 0xEA])

        # Act
        found = list(disassemble8(code, 0, 0x8000, stop_at_return=True))

        # Assert
        self.assertEqual([entry.mnemonic for entry in found], ["nop", "rts"])

    def test_addresses_wrap_at_the_top_of_the_space(self) -> None:
        # Arrange
        code = bytes([0xEA, 0xEA])

        # Act
        found = list(disassemble8(code, 0, 0xFFFF))

        # Assert
        self.assertEqual([entry.address for entry in found], [0xFFFF, 0x0000])


if __name__ == "__main__":
    unittest.main()
