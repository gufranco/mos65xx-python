from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from typing import Any

from mos65xx import SparseMemory, mos65c02, opcodes65c02


def machine(
    program: Sequence[int], at: int = 0x8000, table: Any = opcodes65c02.CMOS, **registers: Any
) -> Any:
    memory = SparseMemory(seed=1)
    for offset, value in enumerate(program):
        memory.write8(at + offset, value)
    cpu = mos65c02.Cpu(memory, reset=False, table=table)
    cpu.set_status(0x24)
    cpu.a = cpu.x = cpu.y = 0x00
    cpu.s = 0xFD
    cpu.pc = at
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu, memory


class FixedBugTest(unittest.TestCase):
    def test_a_jump_through_a_pointer_at_a_page_end_reads_the_right_high_byte(self) -> None:
        cpu, memory = machine([0x6C, 0xFF, 0x30])
        memory.write8(0x30FF, 0x34)
        memory.write8(0x3100, 0x12)
        memory.write8(0x3000, 0xAB)

        cpu.step()

        self.assertEqual(cpu.pc, 0x1234)

    def test_a_break_clears_the_decimal_flag(self) -> None:
        cpu, memory = machine([0x00, 0x00])
        cpu.d = True
        memory.write8(0xFFFE, 0x00)
        memory.write8(0xFFFF, 0x90)

        cpu.step()

        self.assertFalse(cpu.d)

    def test_a_decimal_add_sets_the_sign_from_the_decimal_result(self) -> None:
        cpu, _ = machine([0x69, 0x01], a=0x79)
        cpu.d = True

        cpu.step()

        self.assertEqual(cpu.a, 0x80)
        self.assertTrue(cpu.n)
        self.assertFalse(cpu.z)

    def test_a_decimal_add_that_reaches_zero_says_so(self) -> None:
        cpu, _ = machine([0x69, 0x01], a=0x99)
        cpu.d = True

        cpu.step()

        self.assertEqual(cpu.a, 0x00)
        self.assertTrue(cpu.z)
        self.assertTrue(cpu.c)

    def test_a_decimal_subtract_of_an_operand_that_is_not_a_decimal_number(self) -> None:
        """Where the two parts genuinely disagree about the answer, not the flags.

        Nothing stops a program subtracting a byte whose nibbles are not digits.
        The older part borrows out of the low digit into the high one; this part
        subtracts in binary and corrects afterwards. Given `$FC` they differ by a
        whole digit, and the suite says this part is the one that produces `$AE`.
        """

        cpu, _ = machine([0xE9, 0xFC], a=0x10)
        cpu.d = True
        cpu.c = True

        cpu.step()

        self.assertEqual(cpu.a, 0xAE)

    def test_a_decimal_subtract_sets_the_sign_from_the_decimal_result(self) -> None:
        cpu, _ = machine([0xE9, 0x01], a=0x00)
        cpu.d = True
        cpu.c = True

        cpu.step()

        self.assertEqual(cpu.a, 0x99)
        self.assertTrue(cpu.n)


class DecimalEdgeTest(unittest.TestCase):
    def test_a_decimal_add_whose_low_digit_stays_a_digit_does_not_correct_it(self) -> None:
        cpu, _ = machine([0x69, 0x02], a=0x03)
        cpu.d = True

        cpu.step()

        self.assertEqual(cpu.a, 0x05)

    def test_a_decimal_subtract_that_stays_above_zero_takes_no_sixty(self) -> None:
        cpu, _ = machine([0xE9, 0x01], a=0x50)
        cpu.d = True
        cpu.c = True

        cpu.step()

        self.assertEqual(cpu.a, 0x49)
        self.assertTrue(cpu.c)

    def test_a_decimal_subtract_whose_low_digit_covers_it_takes_no_six(self) -> None:
        cpu, _ = machine([0xE9, 0x01], a=0x09)
        cpu.d = True
        cpu.c = True

        cpu.step()

        self.assertEqual(cpu.a, 0x08)


class NewInstructionTest(unittest.TestCase):
    def test_a_branch_that_always_takes_always_takes(self) -> None:
        cpu, _ = machine([0x80, 0x10])

        cpu.step()

        self.assertEqual(cpu.pc, 0x8012)

    def test_a_store_of_zero_stores_zero(self) -> None:
        cpu, memory = machine([0x64, 0x10])
        memory.write8(0x0010, 0xFF)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0x00)

    def test_a_test_and_set_sets_the_bits_and_reports_the_old_ones(self) -> None:
        cpu, memory = machine([0x04, 0x10], a=0x0F)
        memory.write8(0x0010, 0xF0)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0xFF)
        self.assertTrue(cpu.z)

    def test_a_test_and_clear_clears_them(self) -> None:
        cpu, memory = machine([0x14, 0x10], a=0x0F)
        memory.write8(0x0010, 0xFF)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0xF0)
        self.assertFalse(cpu.z)

    def test_the_index_registers_can_be_pushed_and_pulled(self) -> None:
        cpu, _ = machine([0xDA, 0x5A, 0x7A, 0xFA], x=0x11, y=0x22)

        for _ in range(4):
            cpu.step()

        self.assertEqual((cpu.x, cpu.y), (0x11, 0x22))

    def test_pulling_them_in_the_other_order_swaps_them(self) -> None:
        cpu, _ = machine([0xDA, 0x5A, 0xFA, 0x7A], x=0x11, y=0x22)

        for _ in range(4):
            cpu.step()

        self.assertEqual((cpu.x, cpu.y), (0x22, 0x11))

    def test_the_accumulator_can_be_incremented_on_its_own(self) -> None:
        cpu, _ = machine([0x1A], a=0x41)

        cpu.step()

        self.assertEqual(cpu.a, 0x42)

    def test_and_decremented(self) -> None:
        cpu, _ = machine([0x3A], a=0x43)

        cpu.step()

        self.assertEqual(cpu.a, 0x42)

    def test_a_pointer_with_no_index_reaches_where_it_points(self) -> None:
        cpu, memory = machine([0xB2, 0x20])
        memory.write8(0x0020, 0x34)
        memory.write8(0x0021, 0x12)
        memory.write8(0x1234, 0x42)

        cpu.step()

        self.assertEqual(cpu.a, 0x42)

    def test_an_indexed_jump_through_a_pointer_goes_where_the_index_lands(self) -> None:
        cpu, memory = machine([0x7C, 0x00, 0x30], x=0x04)
        memory.write8(0x3004, 0x34)
        memory.write8(0x3005, 0x12)

        cpu.step()

        self.assertEqual(cpu.pc, 0x1234)

    def test_an_immediate_bit_test_only_reports_whether_anything_matched(self) -> None:
        cpu, _ = machine([0x89, 0x0F], a=0xF0)
        cpu.n = cpu.v = False

        cpu.step()

        self.assertTrue(cpu.z)
        self.assertFalse(cpu.n)
        self.assertFalse(cpu.v)

    def test_a_bit_test_against_memory_still_reports_its_two_top_bits(self) -> None:
        cpu, memory = machine([0x34, 0x10], a=0xFF, x=0x00)
        memory.write8(0x0010, 0xC0)

        cpu.step()

        self.assertTrue(cpu.n)
        self.assertTrue(cpu.v)

    def test_a_no_operation_of_stated_length_consumes_exactly_that(self) -> None:
        for opcode, length in ((0x03, 1), (0x02, 2), (0x0F, 3)):
            cpu, _ = machine([opcode, 0x00, 0x00])

            cpu.step()

            self.assertEqual(cpu.pc, 0x8000 + length, f"{opcode:02X}")


class RockwellTest(unittest.TestCase):
    def test_a_bit_can_be_cleared_in_the_first_page(self) -> None:
        cpu, memory = machine([0x07, 0x10], table=opcodes65c02.ROCKWELL)
        memory.write8(0x0010, 0xFF)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0xFE)

    def test_a_bit_can_be_set_there(self) -> None:
        cpu, memory = machine([0x87, 0x10], table=opcodes65c02.ROCKWELL)
        memory.write8(0x0010, 0x00)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0x01)

    def test_each_of_the_eight_reaches_its_own_bit(self) -> None:
        for bit in range(8):
            cpu, memory = machine([0x87 + bit * 0x10, 0x10], table=opcodes65c02.ROCKWELL)
            memory.write8(0x0010, 0x00)

            cpu.step()

            self.assertEqual(memory.read8(0x0010), 1 << bit, f"bit {bit}")

    def test_a_branch_on_a_clear_bit_takes_when_it_is_clear(self) -> None:
        cpu, memory = machine([0x0F, 0x10, 0x20], table=opcodes65c02.ROCKWELL)
        memory.write8(0x0010, 0xFE)

        cpu.step()

        self.assertEqual(cpu.pc, 0x8023)

    def test_and_does_not_when_it_is_set(self) -> None:
        cpu, memory = machine([0x0F, 0x10, 0x20], table=opcodes65c02.ROCKWELL)
        memory.write8(0x0010, 0xFF)

        cpu.step()

        self.assertEqual(cpu.pc, 0x8003)

    def test_a_branch_on_a_set_bit_is_the_other_way_round(self) -> None:
        cpu, memory = machine([0x8F, 0x10, 0x20], table=opcodes65c02.ROCKWELL)
        memory.write8(0x0010, 0x01)

        cpu.step()

        self.assertEqual(cpu.pc, 0x8023)

    def test_the_base_part_treats_the_same_byte_as_doing_nothing(self) -> None:
        cpu, memory = machine([0x07, 0x10])
        memory.write8(0x0010, 0xFF)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0xFF)
        self.assertEqual(cpu.pc, 0x8002)


class WdcTest(unittest.TestCase):
    def test_the_processor_can_be_stopped(self) -> None:
        cpu, _ = machine([0xDB], table=opcodes65c02.WDC)

        cpu.step()

        self.assertTrue(cpu.stopped)

    def test_the_processor_can_be_made_to_wait(self) -> None:
        cpu, _ = machine([0xCB], table=opcodes65c02.WDC)

        cpu.step()

        self.assertTrue(cpu.waiting)

    def test_waiting_is_not_stopping(self) -> None:
        cpu, _ = machine([0xCB], table=opcodes65c02.WDC)

        cpu.step()

        self.assertFalse(cpu.stopped)

    def test_the_earlier_parts_do_nothing_with_the_same_bytes(self) -> None:
        cpu, _ = machine([0xDB, 0x00], table=opcodes65c02.ROCKWELL)

        cpu.step()

        self.assertFalse(cpu.stopped)
        self.assertEqual(cpu.pc, 0x8002)


class EveryOpcodeTest(unittest.TestCase):
    def test_every_opcode_of_every_part_runs(self) -> None:
        for name, table in opcodes65c02.TABLES.items():
            for opcode in range(256):
                memory = SparseMemory(seed=opcode)
                cpu = mos65c02.Cpu(memory, reset=False, table=table)
                cpu.set_status(0x24)
                cpu.a, cpu.x, cpu.y, cpu.s, cpu.pc = 0x9C, 0x5A, 0xA5, 0xFD, 0x8000
                memory.write8(0x8000, opcode)
                with self.subTest(part=name, opcode=f"${opcode:02X}"):
                    cpu.step()
                    self.assertEqual(cpu.steps, 1)

    def test_every_opcode_of_every_part_has_an_implementation(self) -> None:
        for name, table in opcodes65c02.TABLES.items():
            missing = [
                f"${opcode:02X} {mnemonic}"
                for opcode, (mnemonic, _) in enumerate(table)
                if not hasattr(mos65c02.Cpu, f"op_{mnemonic}")
            ]

            self.assertEqual(missing, [], name)


if __name__ == "__main__":
    unittest.main()
