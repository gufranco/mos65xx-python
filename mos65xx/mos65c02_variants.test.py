from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import Cpu, SparseMemory, Waiting

IRQ_AND_BREAK_VECTOR = 0xFFFE

NMI_VECTOR = 0xFFFA


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


def vectored(vector: int, target: int = 0x9000, model: str = "65c02", **registers: Any) -> Any:
    cpu, memory = machine([0xEA], model=model, **registers)
    memory.write8(vector, target & 0xFF)
    memory.write8(vector + 1, target >> 8)
    return cpu, memory


class RockwellTest(unittest.TestCase):
    def test_a_bit_can_be_cleared_in_the_first_page(self) -> None:
        # Arrange
        cpu, memory = machine([0x07, 0x10], model="r65c02")
        memory.write8(0x0010, 0xFF)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x0010), 0xFE)

    def test_a_bit_can_be_set_there(self) -> None:
        # Arrange
        cpu, memory = machine([0x87, 0x10], model="r65c02")
        memory.write8(0x0010, 0x00)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x0010), 0x01)

    def test_each_of_the_eight_reaches_its_own_bit(self) -> None:
        # Arrange
        parts = [machine([0x87 + bit * 0x10, 0x10], model="r65c02") for bit in range(8)]
        for _, memory in parts:
            memory.write8(0x0010, 0x00)

        # Act
        for cpu, _ in parts:
            cpu.step()

        # Assert
        self.assertEqual(
            [memory.read8(0x0010) for _, memory in parts], [1 << bit for bit in range(8)]
        )

    def test_a_branch_on_a_clear_bit_takes_when_it_is_clear(self) -> None:
        # Arrange
        cpu, memory = machine([0x0F, 0x10, 0x20], model="r65c02")
        memory.write8(0x0010, 0xFE)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x8023)

    def test_and_does_not_when_it_is_set(self) -> None:
        # Arrange
        cpu, memory = machine([0x0F, 0x10, 0x20], model="r65c02")
        memory.write8(0x0010, 0xFF)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x8003)

    def test_a_branch_on_a_set_bit_is_the_other_way_round(self) -> None:
        # Arrange
        cpu, memory = machine([0x8F, 0x10, 0x20], model="r65c02")
        memory.write8(0x0010, 0x01)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x8023)

    def test_the_base_part_treats_the_same_byte_as_doing_nothing(self) -> None:
        # Arrange
        cpu, memory = machine([0x07, 0x10])
        memory.write8(0x0010, 0xFF)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((memory.read8(0x0010), cpu.pc), (0xFF, 0x8002))


class WdcTest(unittest.TestCase):
    def test_the_processor_can_be_stopped(self) -> None:
        # Arrange
        cpu, _ = machine([0xDB], model="w65c02")

        # Act
        cpu.step()

        # Assert
        self.assertTrue(cpu.stopped)

    def test_the_processor_can_be_made_to_wait(self) -> None:
        # Arrange
        cpu, _ = machine([0xCB], model="w65c02")

        # Act
        cpu.step()

        # Assert
        self.assertTrue(cpu.waiting)

    def test_waiting_is_not_stopping(self) -> None:
        # Arrange
        cpu, _ = machine([0xCB], model="w65c02")

        # Act
        cpu.step()

        # Assert
        self.assertFalse(cpu.stopped)

    def test_the_wdc_part_resets_in_the_seven_cycles_wdc_states(self) -> None:
        # Arrange
        cpu = Cpu("w65c02", SparseMemory())
        before = cpu.cycles

        # Act
        cpu.reset()

        # Assert
        self.assertEqual(cpu.cycles - before, 7)

    def test_and_the_parts_whose_makers_said_nothing_keep_the_mos_figure(self) -> None:
        # Arrange
        parts = [Cpu(name, SparseMemory()) for name in ("6502", "65c02", "r65c02", "65816")]

        # Act
        for cpu in parts:
            cpu.reset()

        # Assert
        self.assertEqual([cpu.cycles for cpu in parts], [8, 8, 8, 8])

    def test_a_waiting_part_will_not_run_the_next_instruction(self) -> None:
        # Arrange
        cpu, _ = machine([0xCB, 0xA9, 0x77], model="w65c02")
        cpu.step()

        def attempt() -> Any:
            return cpu.step()

        # Act
        with self.assertRaises(Waiting) as raised:
            attempt()

        # Assert
        self.assertEqual(str(raised.exception), "the processor is waiting for an interrupt")

    def test_a_waiting_part_is_held_rather_than_finished(self) -> None:
        # Arrange
        cpu, _ = machine([0xCB], model="w65c02")
        cpu.step()

        # Act
        held = cpu.held()

        # Assert
        self.assertTrue(held)

    def test_a_stopped_part_is_held_too(self) -> None:
        # Arrange
        cpu, _ = machine([0xDB], model="w65c02")
        cpu.step()

        # Act
        held = cpu.held()

        # Assert
        self.assertTrue(held)

    def test_a_running_part_is_not_held(self) -> None:
        # Arrange
        cpu, _ = machine([0xEA], model="w65c02")
        cpu.step()

        # Act
        held = cpu.held()

        # Assert
        self.assertFalse(held)

    def test_a_held_part_still_spends_its_hosts_cycles(self) -> None:
        # Arrange
        cpu, _ = machine([0xCB], model="w65c02")
        cpu.step()
        before = cpu.cycles

        # Act
        spent = cpu.run_for(20)

        # Assert
        self.assertEqual((spent, cpu.cycles - before), (20, 20))

    def test_an_interrupt_releases_a_waiting_part(self) -> None:
        # Arrange
        cpu, _ = machine([0xCB], model="w65c02")
        cpu.step()

        # Act
        cpu.irq()

        # Assert
        self.assertFalse(cpu.waiting)

    def test_the_earlier_parts_do_nothing_with_the_same_bytes(self) -> None:
        # Arrange
        cpu, _ = machine([0xDB, 0x00], model="r65c02")

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.stopped, cpu.pc), (False, 0x8002))


class EveryOpcodeTest(unittest.TestCase):
    def test_every_opcode_of_every_part_runs_with_a_handler_behind_it(self) -> None:
        # Arrange
        built = {
            (name, f"${opcode:02X}"): machine([opcode], model=name, a=0x9C, x=0x5A, y=0xA5)[0]
            for name in ("65c02", "r65c02", "w65c02")
            for opcode in range(256)
        }

        # Act
        for cpu in built.values():
            cpu.step()

        # Assert
        self.assertEqual([key for key, cpu in built.items() if cpu.steps != 1], [])


class HardwareInterruptTest(unittest.TestCase):
    def test_decimal_mode_is_cleared_on_the_way_in(self) -> None:
        # Arrange
        cpu, _ = vectored(IRQ_AND_BREAK_VECTOR, i=False, d=True)

        # Act
        cpu.irq()

        # Assert
        self.assertFalse(cpu.d)

    def test_which_the_older_part_does_not_do(self) -> None:
        # Arrange
        older, _ = vectored(IRQ_AND_BREAK_VECTOR, model="6502", i=False, d=True)

        # Act
        older.irq()

        # Assert
        self.assertEqual((older.pc, older.d), (0x9000, True))

    def test_a_wait_ends_even_when_the_request_is_refused(self) -> None:
        # Arrange
        cpu, _ = vectored(IRQ_AND_BREAK_VECTOR, i=True, waiting=True)

        # Act
        taken = cpu.irq()

        # Assert
        self.assertEqual((taken, cpu.waiting), (False, False))

    def test_and_the_next_instruction_is_where_execution_carries_on(self) -> None:
        # Arrange
        cpu, _ = vectored(IRQ_AND_BREAK_VECTOR, i=True, waiting=True)

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(cpu.pc, 0x8000)

    def test_a_wait_ends_on_the_non_maskable_pin_too(self) -> None:
        # Arrange
        cpu, _ = vectored(NMI_VECTOR, target=0x9100, waiting=True)

        # Act
        cpu.nmi()

        # Assert
        self.assertEqual((cpu.waiting, cpu.pc), (False, 0x9100))

    def test_an_accepted_request_still_reaches_its_handler(self) -> None:
        # Arrange
        cpu, _ = vectored(IRQ_AND_BREAK_VECTOR, i=False, waiting=True)

        # Act
        taken = cpu.irq()

        # Assert
        self.assertEqual((taken, cpu.pc), (True, 0x9000))


if __name__ == "__main__":
    unittest.main()
