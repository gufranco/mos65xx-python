from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import Cpu, SparseMemory


def machine(
    program: Sequence[int], at: int = 0x8000, model: str = "65c02", **registers: Any
) -> Any:
    memory = SparseMemory(seed=1)
    for offset, value in enumerate(program):
        memory.write8(at + offset, value)
    cpu = Cpu(model, memory)
    cpu.set_status(0x24)
    cpu.a = cpu.x = cpu.y = 0x00
    cpu.s = 0xFD
    cpu.pc = at
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu, memory


def reset_part(model: str, seed: int) -> Any:
    memory = SparseMemory(seed=seed)
    memory.write8(0xFFFC, 0x00)
    memory.write8(0xFFFD, 0x80)
    return Cpu(model, memory, seed=seed)


class FixedBugTest(unittest.TestCase):
    def test_a_jump_through_a_pointer_at_a_page_end_reads_the_right_high_byte(self) -> None:
        # Arrange
        cpu, memory = machine([0x6C, 0xFF, 0x30])
        memory.write8(0x30FF, 0x34)
        memory.write8(0x3100, 0x12)
        memory.write8(0x3000, 0xAB)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x1234)

    def test_a_break_clears_the_decimal_flag(self) -> None:
        # Arrange
        cpu, memory = machine([0x00, 0x00], d=True)
        memory.write8(0xFFFE, 0x00)
        memory.write8(0xFFFF, 0x90)

        # Act
        cpu.step()

        # Assert
        self.assertFalse(cpu.d)

    def test_a_decimal_add_sets_the_sign_from_the_decimal_result(self) -> None:
        # Arrange
        cpu, _ = machine([0x69, 0x01], a=0x79, d=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.n, cpu.z), (0x80, True, False))

    def test_a_decimal_add_that_reaches_zero_says_so(self) -> None:
        # Arrange
        cpu, _ = machine([0x69, 0x01], a=0x99, d=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.z, cpu.c), (0x00, True, True))

    def test_a_decimal_subtract_of_an_operand_that_is_not_a_decimal_number(self) -> None:
        # Arrange
        cpu, _ = machine([0xE9, 0xFC], a=0x10, d=True, c=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0xAE)

    def test_a_decimal_subtract_sets_the_sign_from_the_decimal_result(self) -> None:
        # Arrange
        cpu, _ = machine([0xE9, 0x01], a=0x00, d=True, c=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.n), (0x99, True))


class DecimalEdgeTest(unittest.TestCase):
    def test_a_decimal_add_whose_low_digit_stays_a_digit_does_not_correct_it(self) -> None:
        # Arrange
        cpu, _ = machine([0x69, 0x02], a=0x03, d=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x05)

    def test_a_decimal_subtract_that_stays_above_zero_takes_no_sixty(self) -> None:
        # Arrange
        cpu, _ = machine([0xE9, 0x01], a=0x50, d=True, c=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.c), (0x49, True))

    def test_a_decimal_subtract_whose_low_digit_covers_it_takes_no_six(self) -> None:
        # Arrange
        cpu, _ = machine([0xE9, 0x01], a=0x09, d=True, c=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x08)


class NewInstructionTest(unittest.TestCase):
    def test_a_branch_that_always_takes_always_takes(self) -> None:
        # Arrange
        cpu, _ = machine([0x80, 0x10])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x8012)

    def test_a_store_of_zero_stores_zero(self) -> None:
        # Arrange
        cpu, memory = machine([0x64, 0x10])
        memory.write8(0x0010, 0xFF)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x0010), 0x00)

    def test_a_test_and_set_sets_the_bits_and_reports_the_old_ones(self) -> None:
        # Arrange
        cpu, memory = machine([0x04, 0x10], a=0x0F)
        memory.write8(0x0010, 0xF0)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((memory.read8(0x0010), cpu.z), (0xFF, True))

    def test_a_test_and_clear_clears_them(self) -> None:
        # Arrange
        cpu, memory = machine([0x14, 0x10], a=0x0F)
        memory.write8(0x0010, 0xFF)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((memory.read8(0x0010), cpu.z), (0xF0, False))

    def test_the_index_registers_can_be_pushed_and_pulled(self) -> None:
        # Arrange
        cpu, _ = machine([0xDA, 0x5A, 0x7A, 0xFA], x=0x11, y=0x22)

        # Act
        for _ in range(4):
            cpu.step()

        # Assert
        self.assertEqual((cpu.x, cpu.y), (0x11, 0x22))

    def test_pulling_them_in_the_other_order_swaps_them(self) -> None:
        # Arrange
        cpu, _ = machine([0xDA, 0x5A, 0xFA, 0x7A], x=0x11, y=0x22)

        # Act
        for _ in range(4):
            cpu.step()

        # Assert
        self.assertEqual((cpu.x, cpu.y), (0x22, 0x11))

    def test_the_accumulator_can_be_incremented_on_its_own(self) -> None:
        # Arrange
        cpu, _ = machine([0x1A], a=0x41)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x42)

    def test_and_decremented(self) -> None:
        # Arrange
        cpu, _ = machine([0x3A], a=0x43)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x42)

    def test_a_pointer_with_no_index_reaches_where_it_points(self) -> None:
        # Arrange
        cpu, memory = machine([0xB2, 0x20])
        memory.write8(0x0020, 0x34)
        memory.write8(0x0021, 0x12)
        memory.write8(0x1234, 0x42)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x42)

    def test_an_indexed_jump_through_a_pointer_goes_where_the_index_lands(self) -> None:
        # Arrange
        cpu, memory = machine([0x7C, 0x00, 0x30], x=0x04)
        memory.write8(0x3004, 0x34)
        memory.write8(0x3005, 0x12)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x1234)

    def test_an_immediate_bit_test_only_reports_whether_anything_matched(self) -> None:
        # Arrange
        cpu, _ = machine([0x89, 0x0F], a=0xF0, n=False, v=False)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.z, cpu.n, cpu.v), (True, False, False))

    def test_a_bit_test_against_memory_still_reports_its_two_top_bits(self) -> None:
        # Arrange
        cpu, memory = machine([0x34, 0x10], a=0xFF, x=0x00)
        memory.write8(0x0010, 0xC0)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.n, cpu.v), (True, True))

    def test_a_no_operation_of_stated_length_consumes_exactly_that(self) -> None:
        # Arrange
        lengths = {0x03: 1, 0x02: 2, 0x0F: 3}
        parts = {opcode: machine([opcode, 0x00, 0x00])[0] for opcode in lengths}

        # Act
        for cpu in parts.values():
            cpu.step()

        # Assert
        self.assertEqual({opcode: cpu.pc - 0x8000 for opcode, cpu in parts.items()}, lengths)


class ResetTest(unittest.TestCase):
    def test_decimal_mode_is_off_afterwards(self) -> None:
        # Arrange
        cpu = reset_part("65c02", 3)

        # Act
        cpu.reset(3)

        # Assert
        self.assertFalse(cpu.d)

    def test_whatever_the_seed_would_have_left_there(self) -> None:
        # Arrange
        parts = [reset_part("65c02", seed) for seed in range(24)]

        # Act
        for seed, cpu in enumerate(parts):
            cpu.reset(seed)

        # Assert
        self.assertEqual([cpu.d for cpu in parts], [False] * 24)

    def test_the_older_part_leaves_it_holding_what_it_held(self) -> None:
        # Arrange
        parts = [reset_part("6502", seed) for seed in range(24)]

        # Act
        for seed, cpu in enumerate(parts):
            cpu.reset(seed)

        # Assert
        self.assertIn(True, [cpu.d for cpu in parts])

    def test_interrupts_are_disabled_afterwards(self) -> None:
        # Arrange
        cpu = reset_part("65c02", 3)

        # Act
        cpu.reset(3)

        # Assert
        self.assertTrue(cpu.i)

    def test_and_the_program_counter_comes_from_the_vector(self) -> None:
        # Arrange
        cpu = reset_part("65c02", 3)

        # Act
        cpu.reset(3)

        # Assert
        self.assertEqual(cpu.pc, 0x8000)


if __name__ == "__main__":
    unittest.main()
