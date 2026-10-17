from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import Cpu, RunLimit, SparseMemory

IRQ_AND_BREAK_VECTOR = 0xFFFE

NMI_VECTOR = 0xFFFA


def machine(program: Sequence[int], at: int = 0x8000, **registers: Any) -> Any:
    memory = SparseMemory(seed=1)
    for offset, value in enumerate(program):
        memory.write8(at + offset, value)
    cpu = Cpu("6502", memory)
    cpu.set_status(0x24)
    cpu.a = cpu.x = cpu.y = 0x00
    cpu.s = 0xFD
    cpu.pc = at
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu, memory


def waiting_at(vector: int, target: int = 0x9000, **registers: Any) -> Any:
    cpu, memory = machine([0xEA], s=0xFD, **registers)
    memory.write8(vector, target & 0xFF)
    memory.write8(vector + 1, target >> 8)
    return cpu, memory


class BreakTest(unittest.TestCase):
    def test_a_break_goes_through_the_vector_and_pushes_the_break_bit(self) -> None:
        # Arrange
        cpu, memory = machine([0x00, 0x00])
        memory.write8(0xFFFE, 0x34)
        memory.write8(0xFFFF, 0x12)
        before = cpu.status()

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pc, memory.read8(0x01FB), cpu.i), (0x1234, before | 0x10, True))

    def test_a_break_pushes_the_address_after_its_padding_byte(self) -> None:
        # Arrange
        cpu, memory = machine([0x00, 0x00])
        memory.write8(0xFFFE, 0x00)
        memory.write8(0xFFFF, 0x90)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((memory.read8(0x01FD), memory.read8(0x01FC)), (0x80, 0x02))

    def test_a_break_reports_itself_as_one_and_an_interrupt_does_not(self) -> None:
        # Arrange
        cpu, memory = machine([0x00], s=0xFD)
        memory.write8(IRQ_AND_BREAK_VECTOR, 0x00)
        memory.write8(IRQ_AND_BREAK_VECTOR + 1, 0x90)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x01FB) & 0x10, 0x10)


class HardwareInterruptTest(unittest.TestCase):
    def test_a_request_is_refused_while_the_disable_flag_is_set(self) -> None:
        # Arrange
        cpu, _ = waiting_at(IRQ_AND_BREAK_VECTOR, i=True)

        # Act
        taken = cpu.irq()

        # Assert
        self.assertFalse(taken)

    def test_and_the_program_counter_has_not_moved(self) -> None:
        # Arrange
        cpu, _ = waiting_at(IRQ_AND_BREAK_VECTOR, i=True)

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(cpu.pc, 0x8000)

    def test_a_request_is_taken_once_the_flag_is_clear(self) -> None:
        # Arrange
        cpu, _ = waiting_at(IRQ_AND_BREAK_VECTOR, i=False)

        # Act
        taken = cpu.irq()

        # Assert
        self.assertTrue(taken)

    def test_and_arrives_at_the_handler_the_vector_names(self) -> None:
        # Arrange
        cpu, _ = waiting_at(IRQ_AND_BREAK_VECTOR, i=False)

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(cpu.pc, 0x9000)

    def test_the_return_address_is_the_instruction_that_would_have_run(self) -> None:
        # Arrange
        cpu, memory = waiting_at(IRQ_AND_BREAK_VECTOR, i=False)

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(memory.read8(0x01FD) << 8 | memory.read8(0x01FC), 0x8000)

    def test_the_pushed_status_has_the_break_bit_clear(self) -> None:
        # Arrange
        cpu, memory = waiting_at(IRQ_AND_BREAK_VECTOR, i=False, b=True)

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(memory.read8(0x01FB) & 0x10, 0x00)

    def test_and_the_unused_bit_set_the_way_every_push_sets_it(self) -> None:
        # Arrange
        cpu, memory = waiting_at(IRQ_AND_BREAK_VECTOR, i=False)

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(memory.read8(0x01FB) & 0x20, 0x20)

    def test_the_break_bit_in_the_register_itself_is_left_alone(self) -> None:
        # Arrange
        cpu, _ = waiting_at(IRQ_AND_BREAK_VECTOR, i=False, b=True)

        # Act
        cpu.irq()

        # Assert
        self.assertTrue(cpu.b)

    def test_the_handler_runs_with_further_requests_disabled(self) -> None:
        # Arrange
        cpu, _ = waiting_at(IRQ_AND_BREAK_VECTOR, i=False)

        # Act
        cpu.irq()

        # Assert
        self.assertTrue(cpu.i)

    def test_decimal_mode_survives_the_interrupt_on_this_part(self) -> None:
        # Arrange
        cpu, _ = waiting_at(IRQ_AND_BREAK_VECTOR, i=False, d=True)

        # Act
        cpu.irq()

        # Assert
        self.assertTrue(cpu.d)

    def test_the_non_maskable_pin_ignores_the_disable_flag(self) -> None:
        # Arrange
        cpu, _ = waiting_at(NMI_VECTOR, target=0x9100, i=True)

        # Act
        cpu.nmi()

        # Assert
        self.assertEqual(cpu.pc, 0x9100)

    def test_a_return_from_interrupt_goes_back_where_it_came_from(self) -> None:
        # Arrange
        cpu, memory = waiting_at(IRQ_AND_BREAK_VECTOR, i=False)
        cpu.irq()
        memory.write8(0x9000, 0x40)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x8000)

    def test_and_restores_the_flags_it_was_holding(self) -> None:
        # Arrange
        cpu, memory = waiting_at(IRQ_AND_BREAK_VECTOR, i=False, c=True)
        cpu.irq()
        memory.write8(0x9000, 0x40)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.c, cpu.i), (True, False))


class ReachTest(unittest.TestCase):
    def test_a_routine_runs_until_it_returns(self) -> None:
        # Arrange
        cpu, _ = machine([0xE8, 0xE8, 0x60])

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.x, 0x02)

    def test_a_nested_call_returns_to_the_outer_one(self) -> None:
        # Arrange
        cpu, memory = machine([0x20, 0x10, 0x80, 0xE8, 0x60])
        for offset, value in enumerate([0xC8, 0x60]):
            memory.write8(0x8010 + offset, value)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual((cpu.x, cpu.y), (0x01, 0x01))

    def test_a_routine_that_never_returns_gives_up_at_the_bound(self) -> None:
        # Arrange
        cpu, _ = machine([0x4C, 0x00, 0x80])

        def attempt() -> Any:
            return cpu.call(0x8000, limit=64)

        # Act
        with self.assertRaises(RunLimit) as raised:
            attempt()

        # Assert
        self.assertEqual(str(raised.exception), "gave up after 64 instructions at $8000")

    def test_a_routine_that_returns_inside_the_bound_is_untouched_by_it(self) -> None:
        # Arrange
        cpu, _ = machine([0xE8, 0xE8, 0x60])

        # Act
        cpu.call(0x8000, limit=64)

        # Assert
        self.assertEqual(cpu.x, 0x02)

    def test_a_bound_of_none_is_the_unbounded_run_it_always_was(self) -> None:
        # Arrange
        cpu, _ = machine([0xE8, 0xE8, 0x60])

        # Act
        cpu.call(0x8000, limit=None)

        # Assert
        self.assertEqual(cpu.x, 0x02)

    def test_running_until_a_condition_stops_when_it_holds(self) -> None:
        # Arrange
        cpu, _ = machine([0xE8, 0xE8, 0xE8, 0xE8])

        # Act
        cpu.run_until(lambda found: found.x >= 0x03)

        # Assert
        self.assertEqual(cpu.x, 0x03)

    def test_a_bounded_run_gives_up_rather_than_hanging(self) -> None:
        # Arrange
        cpu, _ = machine([0x4C, 0x00, 0x80])

        def attempt() -> Any:
            return cpu.run_until(lambda _: False, limit=100)

        # Act
        with self.assertRaises(RunLimit) as raised:
            attempt()

        # Assert
        self.assertEqual(str(raised.exception), "gave up after 100 instructions at $8000")

    def test_a_bounded_run_that_reaches_its_condition_does_not_raise(self) -> None:
        # Arrange
        cpu, _ = machine([0xEA, 0xEA])

        # Act
        cpu.run_until(lambda part: part.pc == 0x8002, limit=50)

        # Assert
        self.assertEqual(cpu.pc, 0x8002)


if __name__ == "__main__":
    unittest.main()
