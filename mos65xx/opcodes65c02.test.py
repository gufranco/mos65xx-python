import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import opcodes65c02, opcodes6502


class TableTest(unittest.TestCase):
    def test_every_table_decodes_every_byte(self):
        for name, table in opcodes65c02.TABLES.items():
            self.assertEqual(len(table), 256, name)

    def test_no_entry_names_a_mode_that_cannot_be_sized(self):
        for name, table in opcodes65c02.TABLES.items():
            for mnemonic, mode in table:
                self.assertIn(mode, opcodes6502.MODE_SIZE, f"{name} {mnemonic}")

    def test_the_cmos_part_has_none_of_the_undocumented_instructions(self):
        used = {mnemonic for mnemonic, _ in opcodes65c02.CMOS}

        self.assertEqual(used & opcodes6502.UNDOCUMENTED, set())

    def test_nor_do_the_two_that_added_instructions(self):
        for name in ("rockwell", "wdc"):
            used = {mnemonic for mnemonic, _ in opcodes65c02.TABLES[name]}

            self.assertEqual(used & opcodes6502.UNDOCUMENTED, set(), name)


class RevisionTest(unittest.TestCase):
    def test_the_three_parts_are_three_tables(self):
        self.assertEqual(sorted(opcodes65c02.TABLES), ["65c02", "rockwell", "wdc"])

    def test_the_base_part_has_no_bit_instructions(self):
        used = {mnemonic for mnemonic, _ in opcodes65c02.CMOS}

        self.assertNotIn("rmb0", used)
        self.assertNotIn("bbr0", used)

    def test_the_rockwell_part_has_all_thirty_two_of_them(self):
        used = [mnemonic for mnemonic, _ in opcodes65c02.ROCKWELL]

        for prefix in ("rmb", "smb", "bbr", "bbs"):
            self.assertEqual(sum(1 for name in used if name.startswith(prefix)), 8, prefix)

    def test_the_bit_instructions_sit_in_the_two_columns_that_carry_them(self):
        for bit in range(8):
            self.assertEqual(opcodes65c02.ROCKWELL[0x07 + bit * 0x10][0], f"rmb{bit}")
            self.assertEqual(opcodes65c02.ROCKWELL[0x87 + bit * 0x10][0], f"smb{bit}")
            self.assertEqual(opcodes65c02.ROCKWELL[0x0F + bit * 0x10][0], f"bbr{bit}")
            self.assertEqual(opcodes65c02.ROCKWELL[0x8F + bit * 0x10][0], f"bbs{bit}")

    def test_only_the_wdc_part_can_be_stopped_or_made_to_wait(self):
        self.assertEqual(opcodes65c02.WDC[0xDB][0], "stp")
        self.assertEqual(opcodes65c02.WDC[0xCB][0], "wai")
        self.assertEqual(opcodes65c02.ROCKWELL[0xDB][0], "nop")
        self.assertEqual(opcodes65c02.CMOS[0xCB][0], "nop")

    def test_the_two_later_parts_agree_everywhere_the_earlier_one_does_not_differ(self):
        differing = [
            opcode
            for opcode in range(256)
            if opcodes65c02.ROCKWELL[opcode] != opcodes65c02.WDC[opcode]
        ]

        self.assertEqual(sorted(differing), [0xCB, 0xDB])


class AdditionTest(unittest.TestCase):
    def test_the_instructions_the_cmos_part_added_are_all_there(self):
        used = {mnemonic for mnemonic, _ in opcodes65c02.CMOS}

        for mnemonic in ("tsb", "trb", "stz", "bra", "phx", "phy", "plx", "ply"):
            self.assertIn(mnemonic, used, mnemonic)

    def test_the_accumulator_can_be_incremented_and_decremented_on_its_own(self):
        self.assertEqual(opcodes65c02.CMOS[0x1A], ("inc", "accumulator"))
        self.assertEqual(opcodes65c02.CMOS[0x3A], ("dec", "accumulator"))

    def test_the_jump_through_a_pointer_can_be_indexed(self):
        self.assertEqual(opcodes65c02.CMOS[0x7C], ("jmp", "indirectX"))

    def test_the_bit_test_reaches_an_immediate_and_two_indexed_modes(self):
        self.assertEqual(opcodes65c02.CMOS[0x89], ("bit", "immediate"))
        self.assertEqual(opcodes65c02.CMOS[0x34], ("bit", "zeroPageX"))
        self.assertEqual(opcodes65c02.CMOS[0x3C], ("bit", "absoluteX"))

    def test_eight_instructions_gained_a_pointer_mode_with_no_index(self):
        indirect = [
            opcode for opcode in range(256) if opcodes65c02.CMOS[opcode][1] == "zeroPageIndirect"
        ]

        self.assertEqual(len(indirect), 8)


class NoOperationTest(unittest.TestCase):
    def test_the_lengths_the_suite_measured_are_the_lengths_in_the_table(self):
        measured = {
            0x03: 1,
            0x0B: 1,
            0x02: 2,
            0x22: 2,
            0x42: 2,
            0x62: 2,
            0x07: 2,
            0x0F: 3,
            0xCB: 1,
            0xDB: 2,
        }

        for opcode, length in measured.items():
            mnemonic, mode = opcodes65c02.CMOS[opcode]
            self.assertEqual(mnemonic, "nop", f"{opcode:02X}")
            self.assertEqual(1 + opcodes6502.MODE_SIZE[mode], length, f"{opcode:02X}")

    def test_a_no_operation_that_takes_bytes_takes_them_from_nowhere_in_particular(self):
        for opcode in (0x02, 0x22, 0x42, 0x62):
            self.assertEqual(opcodes65c02.CMOS[opcode][1], "immediate")


if __name__ == "__main__":
    unittest.main()
