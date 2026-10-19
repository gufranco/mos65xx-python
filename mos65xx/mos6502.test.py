from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import Cpu, SparseMemory


def machine(program: Sequence[int], at: int = 0x8000, model: str = "6502", **registers: Any) -> Any:
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


def resetting(model: str, counter: int, stack: int) -> Any:
    memory = SparseMemory(seed=4)
    memory.write8(0xFFFC, 0x00)
    memory.write8(0xFFFD, 0x02)
    cpu = Cpu(model, memory)
    cpu.pc, cpu.s = counter, stack
    cpu.trace = []
    return cpu


class ResetBusTest(unittest.TestCase):
    def test_a_reset_drives_the_counter_three_times_then_the_stack_three_times(self) -> None:
        # Arrange
        cpu = resetting("6502", counter=0xEAE9, stack=0xC0)

        # Act
        cpu.reset()

        # Assert
        self.assertEqual(
            [address for address, _, _ in cpu.trace],
            [0xEAE9, 0xEAE9, 0xEAE9, 0x01C0, 0x01BF, 0x01BE, 0xFFFC, 0xFFFD],
        )

    def test_every_cycle_of_a_reset_is_a_read(self) -> None:
        # Arrange
        cpu = resetting("6502", counter=0xEAE9, stack=0xC0)

        # Act
        cpu.reset()

        # Assert
        self.assertEqual({kind for _, _, kind in cpu.trace}, {"read"})

    def test_a_reset_leaves_the_stack_pointer_three_lower(self) -> None:
        # Arrange
        cpu = resetting("6502", counter=0xEAE9, stack=0xC0)

        # Act
        cpu.reset()

        # Assert
        self.assertEqual(cpu.s, 0xBD)

    def test_the_stack_reads_of_a_reset_wrap_inside_page_one(self) -> None:
        # Arrange
        cpu = resetting("6502", counter=0xEAE9, stack=0x01)

        # Act
        cpu.reset()

        # Assert
        self.assertEqual(
            ([address for address, _, _ in cpu.trace][3:6], cpu.s),
            ([0x0101, 0x0100, 0x01FF], 0xFE),
        )

    def test_a_cmos_part_puts_nothing_on_the_bus_before_its_vector(self) -> None:
        # Arrange
        cpu = resetting("65c02", counter=0xEAE9, stack=0xC0)

        # Act
        cpu.reset()

        # Assert
        self.assertEqual(
            ([address for address, _, _ in cpu.trace], cpu.s), ([0xFFFC, 0xFFFD], 0xC0)
        )


class ResetTest(unittest.TestCase):
    def test_a_reset_takes_the_program_counter_from_the_vector(self) -> None:
        # Arrange
        memory = SparseMemory(seed=2)
        memory.write8(0xFFFC, 0x34)
        memory.write8(0xFFFD, 0x12)
        cpu = Cpu("6502", memory)

        # Act
        cpu.reset()

        # Assert
        self.assertEqual(cpu.pc, 0x1234)

    def test_a_reset_leaves_the_registers_holding_what_they_held(self) -> None:
        # Arrange
        memory = SparseMemory(seed=3)
        first = Cpu("6502", memory, seed=7)
        second = Cpu("6502", memory, seed=8)

        # Act
        for cpu in (first, second):
            cpu.reset()

        # Assert
        self.assertNotEqual((first.a, first.x, first.y), (second.a, second.x, second.y))

    def test_the_same_seed_gives_the_same_unclean_machine(self) -> None:
        # Arrange
        memory = SparseMemory(seed=3)
        first = Cpu("6502", memory, seed=9)
        second = Cpu("6502", memory, seed=9)

        # Act
        for cpu in (first, second):
            cpu.reset()

        # Assert
        self.assertEqual((first.a, first.x, first.y), (second.a, second.x, second.y))


class StatusTest(unittest.TestCase):
    def test_the_unused_bit_is_always_set(self) -> None:
        # Arrange
        cpu, _ = machine([0xEA])

        # Act
        status = cpu.status()

        # Assert
        self.assertEqual(status & 0x20, 0x20)

    def test_the_break_bit_is_kept_when_nothing_touches_it(self) -> None:
        # Arrange
        cpu, _ = machine([0xEA])
        cpu.set_status(0xFF)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.status() & 0x10, 0x10)

    def test_pulling_the_status_always_clears_the_break_bit(self) -> None:
        # Arrange
        cpu, memory = machine([0x28], s=0xFC)
        memory.write8(0x01FD, 0xFF)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.status() & 0x10, 0x00)

    def test_pushing_the_status_sets_the_break_bit(self) -> None:
        # Arrange
        cpu, memory = machine([0x08])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x01FD), cpu.status() | 0x10)

    def test_pulling_the_status_takes_every_other_bit_as_given(self) -> None:
        # Arrange
        cpu, memory = machine([0x28], s=0xFC)
        memory.write8(0x01FD, 0xCF)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.status(), 0xEF)


class AddressingTest(unittest.TestCase):
    def test_a_zero_page_index_wraps_inside_the_first_page(self) -> None:
        # Arrange
        cpu, memory = machine([0xB5, 0xFF], x=0x02)
        memory.write8(0x0001, 0x42)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x42)

    def test_an_absolute_index_does_not_wrap_inside_a_page(self) -> None:
        # Arrange
        cpu, memory = machine([0xBD, 0xFF, 0x20], x=0x02)
        memory.write8(0x2101, 0x42)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x42)

    def test_an_indexed_indirect_pointer_wraps_inside_the_first_page(self) -> None:
        # Arrange
        cpu, memory = machine([0xA1, 0xFF], x=0x00)
        memory.write8(0x00FF, 0x34)
        memory.write8(0x0000, 0x12)
        memory.write8(0x1234, 0x42)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x42)

    def test_an_indirect_indexed_pointer_wraps_the_same_way(self) -> None:
        # Arrange
        cpu, memory = machine([0xB1, 0xFF], y=0x01)
        memory.write8(0x00FF, 0x34)
        memory.write8(0x0000, 0x12)
        memory.write8(0x1235, 0x42)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x42)

    def test_a_jump_through_a_pointer_at_a_page_end_reads_the_wrong_high_byte(self) -> None:
        # Arrange
        cpu, memory = machine([0x6C, 0xFF, 0x30])
        memory.write8(0x30FF, 0x34)
        memory.write8(0x3100, 0xAB)
        memory.write8(0x3000, 0x12)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x1234)


class SubroutineTest(unittest.TestCase):
    def test_a_call_pushes_the_address_of_its_own_last_byte(self) -> None:
        # Arrange
        cpu, memory = machine([0x20, 0x55, 0x13], s=0xFD)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pc, memory.read8(0x01FD), memory.read8(0x01FC)), (0x1355, 0x80, 0x02))

    def test_a_call_whose_push_lands_on_its_own_operand_jumps_where_the_push_left_it(self) -> None:
        # Arrange
        cpu, memory = machine([0x20, 0x55, 0x13], at=0x017B, s=0x7D)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((memory.read8(0x017D), memory.read8(0x017C), cpu.pc), (0x01, 0x7D, 0x0155))

    def test_a_return_goes_to_the_byte_after_the_call(self) -> None:
        # Arrange
        cpu, memory = machine([0x60], s=0xFB)
        memory.write8(0x01FC, 0x02)
        memory.write8(0x01FD, 0x80)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x8003)


class StackTest(unittest.TestCase):
    def test_the_stack_pointer_wraps_inside_its_page(self) -> None:
        # Arrange
        cpu, memory = machine([0x48], s=0x00, a=0x5C)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.s, memory.read8(0x0100)), (0xFF, 0x5C))

    def test_a_pull_wraps_the_same_way(self) -> None:
        # Arrange
        cpu, memory = machine([0x68], s=0xFF)
        memory.write8(0x0100, 0x42)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.s, cpu.a), (0x00, 0x42))


class ArithmeticTest(unittest.TestCase):
    def test_an_add_sets_carry_when_it_leaves_the_byte(self) -> None:
        # Arrange
        cpu, _ = machine([0x69, 0x01], a=0xFF)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.c, cpu.z), (0x00, True, True))

    def test_an_add_sets_overflow_when_two_positives_make_a_negative(self) -> None:
        # Arrange
        cpu, _ = machine([0x69, 0x50], a=0x50)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.v), (0xA0, True))

    def test_a_decimal_add_carries_at_ten_rather_than_sixteen(self) -> None:
        # Arrange
        cpu, _ = machine([0x69, 0x01], a=0x09, d=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x10)

    def test_a_part_with_no_decimal_mode_adds_in_binary_regardless(self) -> None:
        # Arrange
        cpu, _ = machine([0x69, 0x01], model="2a03", a=0x09, d=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x0A)

    def test_a_decimal_subtract_borrows_at_ten(self) -> None:
        # Arrange
        cpu, _ = machine([0xE9, 0x01], a=0x10, d=True, c=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x09)

    def test_a_decimal_add_whose_low_nibble_stays_below_ten_does_not_adjust_it(self) -> None:
        # Arrange
        cpu, _ = machine([0x69, 0x03], a=0x04, d=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x07)


class BranchTest(unittest.TestCase):
    def test_a_branch_not_taken_only_costs_its_operand(self) -> None:
        # Arrange
        cpu, _ = machine([0xD0, 0x10], z=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x8002)

    def test_a_branch_taken_goes_where_it_says(self) -> None:
        # Arrange
        cpu, _ = machine([0xD0, 0x10], z=False)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x8012)

    def test_a_backward_branch_is_signed(self) -> None:
        # Arrange
        cpu, _ = machine([0xD0, 0xFC], z=False)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x7FFE)


class ClockTest(unittest.TestCase):
    def test_a_step_reports_the_cycles_that_instruction_took(self) -> None:
        # Arrange
        cpu, _ = machine([0xEA])

        # Act
        cycles = cpu.step()

        # Assert
        self.assertEqual(cycles, 2)

    def test_the_tally_adds_up_across_instructions(self) -> None:
        # Arrange
        cpu, _ = machine([0xEA, 0xEA, 0xEA])
        started = cpu.cycles

        # Act
        for _ in range(3):
            cpu.step()

        # Assert
        self.assertEqual(cpu.cycles - started, 6)

    def test_a_budget_runs_whole_instructions_and_reports_what_was_spent(self) -> None:
        # Arrange
        cpu, _ = machine([0xEA] * 8)

        # Act
        spent = cpu.run_for(5)

        # Assert
        self.assertEqual(spent, 6)

    def test_the_tally_survives_a_reset_because_a_clock_does_not_rewind(self) -> None:
        # Arrange
        cpu, _ = machine([0xEA])
        cpu.step()
        before = cpu.cycles

        # Act
        cpu.reset()

        # Assert
        self.assertGreater(cpu.cycles, before)

    def test_a_reset_costs_the_six_cycles_the_manual_names_plus_the_vector(self) -> None:
        # Arrange
        cpu, _ = machine([0xEA])
        before = cpu.cycles

        # Act
        cpu.reset()

        # Assert
        self.assertEqual(cpu.cycles - before, 6 + 2)


if __name__ == "__main__":
    unittest.main()
