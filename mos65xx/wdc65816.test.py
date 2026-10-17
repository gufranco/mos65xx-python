from __future__ import annotations

import sys
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import FLAG_M, FLAG_X, OPCODES, Cpu

NATIVE_16 = 0x00
NATIVE_8 = FLAG_M | FLAG_X

RTL = 0x6B


class FlatMemory:
    def __init__(self, data: Mapping[int, int] | None = None) -> None:
        self.cells: dict[int, int] = dict(data or {})

    def read8(self, address: int) -> int:
        return self.cells.get(address & 0xFFFFFF, 0x00)

    def write8(self, address: int, value: int) -> None:
        self.cells[address & 0xFFFFFF] = value & 0xFF


def ready(
    code: Sequence[int],
    base: int = 0x008000,
    memory: Any = None,
    status: int = NATIVE_8,
    **registers: Any,
) -> Any:
    memory = memory or FlatMemory()
    for offset, byte in enumerate(code):
        memory.cells[base + offset] = byte
    cpu = Cpu("65816", memory)
    cpu.a = cpu.x = cpu.y = 0x0000
    cpu.s = 0x01FF
    cpu.d = 0x0000
    cpu.db = 0x00
    cpu.emulation = False
    cpu.set_status(status)
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu


class CoverageTest(unittest.TestCase):
    def test_the_table_covers_the_whole_byte(self) -> None:
        # Arrange
        table = OPCODES

        # Act
        named = [opcode for opcode, (name, mode) in enumerate(table) if name and mode]

        # Assert
        self.assertEqual(named, list(range(256)))

    def test_the_reserved_opcode_is_a_two_byte_no_operation(self) -> None:
        # Arrange
        cpu = ready([0x42, 0xFF, RTL])

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.pc, 0x8002)


class ResetStateTest(unittest.TestCase):
    def test_the_registers_start_eight_bits_wide(self) -> None:
        # Arrange
        memory = FlatMemory()

        # Act
        cpu = Cpu("65816", memory)

        # Assert
        self.assertEqual((cpu.m8, cpu.x8), (True, True))


class WidthTest(unittest.TestCase):
    def test_rep_widens_the_accumulator(self) -> None:
        # Arrange
        cpu = ready([0xC2, 0x20, RTL])

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertFalse(cpu.m8)

    def test_sep_narrows_the_accumulator(self) -> None:
        # Arrange
        cpu = ready([0xE2, 0x20, RTL], status=NATIVE_16)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertTrue(cpu.m8)

    def test_an_immediate_load_follows_the_declared_width(self) -> None:
        # Arrange
        cpu = ready([0xA9, 0x34, 0x12, RTL], status=NATIVE_16)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a, 0x1234)

    def test_narrowing_the_index_truncates_it(self) -> None:
        # Arrange
        cpu = ready([0xE2, 0x10, RTL], status=NATIVE_16, x=0x1234)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.x, 0x34)

    def test_the_hidden_accumulator_half_survives_a_narrow_load(self) -> None:
        # Arrange
        cpu = ready([0xA9, 0x99, RTL], a=0x1234)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a, 0x1299)


class AddressingTest(unittest.TestCase):
    def test_absolute_reads_through_the_data_bank(self) -> None:
        # Arrange
        cpu = ready([0xAD, 0x05, 0x00, RTL], memory=FlatMemory({0x600005: 0x77}), db=0x60)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x77)

    def test_absolute_indexed_by_y_reads_through_the_data_bank(self) -> None:
        # Arrange
        memory = FlatMemory({0x600005: 0x77})
        cpu = ready([0xB9, 0x00, 0x00, RTL], memory=memory, db=0x60, y=0x05)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x77)

    def test_a_long_read_ignores_the_data_bank(self) -> None:
        # Arrange
        memory = FlatMemory({0x610042: 0x99})
        cpu = ready([0xAF, 0x42, 0x00, 0x61, RTL], memory=memory, db=0x00)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x99)

    def test_direct_page_reads_are_offset_by_the_direct_register(self) -> None:
        # Arrange
        cpu = ready([0xA5, 0x12, RTL], memory=FlatMemory({0x000312: 0x5A}), d=0x0300)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x5A)

    def test_an_indirect_pointer_is_taken_from_the_direct_page(self) -> None:
        # Arrange
        memory = FlatMemory({0x000310: 0x00, 0x000311: 0x20, 0x602000: 0x3C})
        cpu = ready([0xB2, 0x10, RTL], memory=memory, d=0x0300, db=0x60)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x3C)

    def test_a_long_indirect_pointer_carries_its_own_bank(self) -> None:
        # Arrange
        memory = FlatMemory({0x000310: 0x00, 0x000311: 0x20, 0x000312: 0x7E, 0x7E2000: 0xC3})
        cpu = ready([0xA7, 0x10, RTL], memory=memory, d=0x0300, db=0x00)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0xC3)

    def test_stack_relative_reads_sit_above_the_stack_pointer(self) -> None:
        # Arrange
        cpu = ready([0xA3, 0x04, RTL], memory=FlatMemory({0x0001F3: 0x6E}), s=0x01EF)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x6E)


class ArithmeticTest(unittest.TestCase):
    def test_addition_carries_out_of_eight_bits(self) -> None:
        # Arrange
        cpu = ready([0x18, 0x69, 0x01, RTL], a=0xFF)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual((cpu.a & 0xFF, cpu.c), (0x00, True))

    def test_addition_sets_overflow_when_the_sign_is_wrong(self) -> None:
        # Arrange
        cpu = ready([0x18, 0x69, 0x01, RTL], a=0x7F)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertTrue(cpu.v)

    def test_addition_leaves_overflow_clear_when_the_sign_holds(self) -> None:
        # Arrange
        cpu = ready([0x18, 0x69, 0x01, RTL], a=0x00)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertFalse(cpu.v)

    def test_subtraction_borrows_when_the_carry_is_clear(self) -> None:
        # Arrange
        cpu = ready([0x18, 0xE9, 0x01, RTL], a=0x10)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x0E)

    def test_subtraction_below_zero_clears_the_carry(self) -> None:
        # Arrange
        cpu = ready([0x38, 0xE9, 0x02, RTL], a=0x01)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertFalse(cpu.c)

    def test_decimal_addition_carries_at_nine(self) -> None:
        # Arrange
        cpu = ready([0xF8, 0x18, 0x69, 0x01, RTL], a=0x09)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x10)

    def test_decimal_subtraction_borrows_at_zero(self) -> None:
        # Arrange
        cpu = ready([0xF8, 0x38, 0xE9, 0x01, RTL], a=0x10)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x09)

    def test_a_comparison_sets_the_carry_when_it_is_not_below(self) -> None:
        # Arrange
        cpu = ready([0xC9, 0x10, RTL], a=0x20)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual((cpu.c, cpu.z), (True, False))

    def test_a_comparison_of_equals_sets_zero(self) -> None:
        # Arrange
        cpu = ready([0xC9, 0x20, RTL], a=0x20)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual((cpu.z, cpu.c), (True, True))


class ShiftTest(unittest.TestCase):
    def test_a_shift_left_moves_the_top_bit_into_the_carry(self) -> None:
        # Arrange
        cpu = ready([0x0A, RTL], a=0x81)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual((cpu.a & 0xFF, cpu.c), (0x02, True))

    def test_a_shift_right_moves_the_bottom_bit_into_the_carry(self) -> None:
        # Arrange
        cpu = ready([0x4A, RTL], a=0x03)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual((cpu.a & 0xFF, cpu.c), (0x01, True))

    def test_a_rotate_left_brings_the_carry_in(self) -> None:
        # Arrange
        cpu = ready([0x38, 0x2A, RTL], a=0x00)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x01)

    def test_a_rotate_right_brings_the_carry_into_the_top(self) -> None:
        # Arrange
        cpu = ready([0x38, 0x6A, RTL], a=0x00)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x80)

    def test_a_shift_in_memory_writes_the_result_back(self) -> None:
        # Arrange
        memory = FlatMemory({0x000042: 0x40})
        cpu = ready([0x06, 0x42, RTL], memory=memory)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(memory.read8(0x000042), 0x80)

    def test_the_accumulator_half_swaps(self) -> None:
        # Arrange
        cpu = ready([0xEB, RTL], a=0x1234)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a, 0x3412)


class StackTest(unittest.TestCase):
    def test_pushes_and_pulls_balance(self) -> None:
        # Arrange
        cpu = ready([0x08, 0x8B, 0x48, 0x68, 0xAB, 0x28, RTL], s=0x01FF)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.s, 0x01FF)

    def test_a_wide_push_moves_the_pointer_by_two(self) -> None:
        # Arrange
        cpu = ready([0x48, RTL], status=NATIVE_16, s=0x01FF, a=0x1234)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.s, 0x01FD)

    def test_a_pushed_value_comes_back(self) -> None:
        # Arrange
        cpu = ready([0x48, 0xA9, 0x00, 0x68, RTL], s=0x01FF, a=0x5A)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x5A)

    def test_the_direct_register_round_trips_through_the_stack(self) -> None:
        # Arrange
        cpu = ready([0x0B, 0x2B, RTL], status=NATIVE_16, d=0x1234)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.d, 0x1234)

    def test_an_effective_address_can_be_pushed(self) -> None:
        # Arrange
        cpu = ready([0xF4, 0x34, 0x12, RTL], status=NATIVE_16, s=0x01FF)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.s, 0x01FD)


if __name__ == "__main__":
    unittest.main()
