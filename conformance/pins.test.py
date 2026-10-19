from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mos65xx  # noqa: E402


class RequestLineTest(unittest.TestCase):
    def part(self) -> Any:
        space = mos65xx.Memory(image=bytes([0xEA] * 16))
        space.write8(0xFFFE, 0x00)
        space.write8(0xFFFF, 0x90)
        space.write8(0xFFFA, 0x00)
        space.write8(0xFFFB, 0x70)
        cpu = mos65xx.Cpu("6502", space)
        cpu.reset()
        cpu.pc = 0x0000
        cpu.s = 0xFF
        cpu.i = False
        return cpu

    def test_a_line_held_low_is_taken_when_the_part_looks(self) -> None:
        cpu = self.part()
        cpu.irq_line = True

        cpu.step()

        self.assertEqual(cpu.pc, 0x9000)

    def test_a_line_never_raised_is_not(self) -> None:
        cpu = self.part()

        cpu.step()

        self.assertNotEqual(cpu.pc, 0x9000)

    def test_a_request_withdrawn_before_the_part_looks_is_not_taken(self) -> None:
        # Arrange
        cpu = self.part()
        cpu.memory.write8(0x0000, 0xAD)

        # Act
        with mos65xx.Clock(cpu) as clock:
            clock.tick()
            cpu.irq_line = True
            clock.tick()
            cpu.irq_line = False
            clock.run_for(6)

        # Assert
        self.assertEqual(cpu.s, 0xFF)

    def test_a_request_still_held_at_that_moment_is(self) -> None:
        cpu = self.part()
        cpu.memory.write8(0x9000, 0x02)

        with mos65xx.Clock(cpu) as clock:
            clock.tick()
            cpu.irq_line = True
            clock.run_for(40)

        self.assertTrue(cpu.held())


PROGRAM_AT = 0x0200

HANDLER = 0x0300


def polling(model: str, program: bytes) -> Any:
    space = mos65xx.Memory(image=bytes([0xEA] * 0x10000))
    for offset, held in enumerate(program):
        space.write8(PROGRAM_AT + offset, held)
    for vector in (0xFFFA, 0xFFFE):
        space.write8(vector, HANDLER & 0xFF)
        space.write8(vector + 1, HANDLER >> 8)
    cpu = mos65xx.Cpu(model, space)
    cpu.reset()
    cpu.pc, cpu.s = PROGRAM_AT, 0xFF
    cpu.trace = []
    return cpu


def raising(cpu: Any, line: str, at: int) -> None:
    closed = [0]

    def hook() -> None:
        closed[0] += 1
        if closed[0] == at:
            setattr(cpu, line, True)

    cpu.on_cycle = hook


def entered_after(cpu: Any, instructions: int) -> int | None:
    landed = []
    for _ in range(instructions):
        cpu.step()
        landed.append(cpu.pc)
    return landed.index(HANDLER) + 1 if HANDLER in landed else None


class DiePollTest(unittest.TestCase):
    def test_a_request_raised_before_the_last_cycle_is_taken_after_that_instruction(
        self,
    ) -> None:
        # Arrange
        cpu = polling("6502", bytes((0x58, 0xAD, 0x34, 0x12)))
        raising(cpu, "irq_line", 5)

        # Act
        taken = entered_after(cpu, 4)

        # Assert
        self.assertEqual(taken, 2)

    def test_a_request_raised_during_the_last_cycle_waits_for_the_next_one(self) -> None:
        # Arrange
        cpu = polling("6502", bytes((0x58, 0xAD, 0x34, 0x12)))
        raising(cpu, "irq_line", 6)

        # Act
        taken = entered_after(cpu, 4)

        # Assert
        self.assertEqual(taken, 3)

    def test_a_request_polled_is_taken_even_when_withdrawn_before_the_end(self) -> None:
        # Arrange
        cpu = polling("6502", bytes((0x58, 0xEA)))
        closed = [0]

        def hook() -> None:
            closed[0] += 1
            cpu.irq_line = closed[0] == 3

        cpu.on_cycle = hook

        # Act
        taken = entered_after(cpu, 3)

        # Assert
        self.assertEqual(taken, 2)

    def test_clearing_the_mask_takes_effect_an_instruction_late(self) -> None:
        # Arrange
        cpu = polling("6502", bytes((0x58, 0xEA, 0xEA)))
        cpu.i = True
        cpu.irq_line = True

        # Act
        taken = entered_after(cpu, 3)

        # Assert
        self.assertEqual(taken, 2)

    def test_setting_the_mask_does_not_stop_a_request_already_polled(self) -> None:
        # Arrange
        cpu = polling("6502", bytes((0x58, 0x78, 0xEA)))
        cpu.i = True
        cpu.irq_line = True

        # Act
        taken = entered_after(cpu, 3)

        # Assert
        self.assertEqual(taken, 2)

    def test_a_taken_branch_inside_its_page_polls_before_its_operand_cycle_ends(self) -> None:
        # Arrange
        cpu = polling("6502", bytes((0x58, 0x18, 0x90, 0x02)))
        raising(cpu, "irq_line", 6)

        # Act
        taken = entered_after(cpu, 4)

        # Assert
        self.assertEqual(taken, 4)

    def test_a_taken_branch_that_crosses_a_page_polls_as_its_last_cycle_begins(self) -> None:
        # Arrange
        cpu = polling("6502", bytes((0x58, 0x18, 0x90, 0x80)))
        raising(cpu, "irq_line", 7)

        # Act
        taken = entered_after(cpu, 4)

        # Assert
        self.assertEqual(taken, 3)

    def test_a_non_maskable_edge_during_the_last_cycle_waits_for_the_next_one(self) -> None:
        # Arrange
        cpu = polling("6502", bytes((0xEA, 0xAD, 0x34, 0x12)))
        raising(cpu, "nmi_line", 6)

        # Act
        taken = entered_after(cpu, 4)

        # Assert
        self.assertEqual(taken, 3)

    def test_a_break_runs_one_handler_instruction_before_a_late_edge_is_taken(self) -> None:
        # Arrange
        cpu = polling("6502", bytes((0x00,)))
        raising(cpu, "nmi_line", 6)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pc, cpu.s), (HANDLER, 0xFC))

    def test_and_the_edge_is_taken_after_that_instruction(self) -> None:
        # Arrange
        cpu = polling("6502", bytes((0x00,)))
        raising(cpu, "nmi_line", 6)
        cpu.step()

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pc, cpu.s), (HANDLER, 0xF9))

    def test_a_cmos_part_still_samples_after_the_instruction(self) -> None:
        # Arrange
        cpu = polling("65c02", bytes((0x58, 0xAD, 0x34, 0x12)))
        raising(cpu, "irq_line", 6)

        # Act
        taken = entered_after(cpu, 4)

        # Assert
        self.assertEqual(taken, 2)


class NonMaskableLineTest(unittest.TestCase):
    def part(self) -> Any:
        space = mos65xx.Memory(image=bytes([0xEA] * 16))
        space.write8(0xFFFE, 0x00)
        space.write8(0xFFFF, 0x90)
        space.write8(0xFFFA, 0x00)
        space.write8(0xFFFB, 0x70)
        cpu = mos65xx.Cpu("6502", space)
        cpu.reset()
        cpu.pc = 0x0000
        cpu.s = 0xFF
        cpu.i = False
        return cpu

    def test_the_transition_interrupts(self) -> None:
        cpu = self.part()
        cpu.nmi_line = True

        cpu.step()

        self.assertEqual(cpu.pc, 0x7000)

    def test_and_holding_it_afterwards_does_not_interrupt_again(self) -> None:
        cpu = self.part()
        cpu.nmi_line = True
        cpu.step()
        landed = cpu.pc

        cpu.step()

        self.assertNotEqual(cpu.pc, landed)

    def test_a_second_transition_interrupts_again(self) -> None:
        cpu = self.part()
        cpu.nmi_line = True
        cpu.step()
        cpu.nmi_line = False
        cpu.step()
        cpu.nmi_line = True

        cpu.step()

        self.assertEqual(cpu.pc, 0x7000)


class SixteenBitPartTest(unittest.TestCase):
    def part(self) -> Any:
        space = mos65xx.Memory(image=bytes([0xEA] * 16))
        space.write8(0x00FFEE, 0x00)
        space.write8(0x00FFEF, 0x90)
        space.write8(0x00FFEA, 0x00)
        space.write8(0x00FFEB, 0x70)
        space.write8(0x009000, 0xDB)
        space.write8(0x007000, 0xDB)
        cpu = mos65xx.Cpu("65816", space)
        cpu.reset()
        cpu.emulation = False
        cpu.irq_disable = False
        cpu.pb, cpu.pc = 0x00, 0x0000
        cpu.s = 0x01FF
        return cpu

    def test_a_held_request_is_taken(self) -> None:
        cpu = self.part()
        cpu.irq_line = True

        cpu.step()

        self.assertEqual(cpu.pc, 0x9000)

    def test_a_line_never_raised_is_not(self) -> None:
        cpu = self.part()

        cpu.step()

        self.assertNotEqual(cpu.pc, 0x9000)

    def test_the_non_maskable_transition_interrupts(self) -> None:
        cpu = self.part()
        cpu.nmi_line = True

        cpu.step()

        self.assertEqual(cpu.pc, 0x7000)

    def test_and_holding_it_afterwards_does_not_interrupt_again(self) -> None:
        cpu = self.part()
        cpu.nmi_line = True
        cpu.step()

        cpu.step()

        self.assertNotEqual(cpu.pc, 0x7000)


class ReadyLineTest(unittest.TestCase):
    def storing(self, model: str) -> Any:
        space = mos65xx.Memory(image=bytes([0x85, 0x10]))
        cpu = mos65xx.Cpu(model, space)
        cpu.reset()
        cpu.pc = 0x0000
        cpu.a = 0x5A
        return cpu

    def cost_with_the_line_dropped_before_the_write(self, model: str) -> int:
        cpu = self.storing(model)
        seen = [0]

        def hook() -> None:
            seen[0] += 1
            cpu.ready_line = seen[0] > 12 or seen[0] < 2

        cpu.on_cycle = hook
        return int(cpu.step())

    def test_a_write_goes_through_on_an_nmos_part(self) -> None:
        self.assertEqual(self.cost_with_the_line_dropped_before_the_write("6502"), 3)

    def test_and_is_held_on_a_cmos_one(self) -> None:
        self.assertGreater(self.cost_with_the_line_dropped_before_the_write("w65c02"), 3)

    def test_the_sixteen_bit_part_holds_a_write_too(self) -> None:
        space = mos65xx.Memory(image=bytes([0x85, 0x10]))
        cpu = mos65xx.Cpu("65816", space)
        cpu.reset()
        cpu.pb, cpu.pc = 0x00, 0x0000
        seen = [0]

        def hook() -> None:
            seen[0] += 1
            cpu.ready_line = seen[0] > 12 or seen[0] < 2

        cpu.on_cycle = hook

        self.assertGreater(cpu.step(), 3)

    def test_and_a_write_that_is_never_held_costs_nothing_extra(self) -> None:
        space = mos65xx.Memory(image=bytes([0x85, 0x10]))
        cpu = mos65xx.Cpu("65816", space)
        cpu.reset()
        cpu.pb, cpu.pc = 0x00, 0x0000

        self.assertEqual(cpu.step(), 3)

    def test_a_read_is_held_on_either(self) -> None:
        cpu = mos65xx.Cpu("6502", mos65xx.Memory(image=bytes([0xEA] * 8)))
        cpu.reset()
        cpu.pc = 0x0000

        with mos65xx.Clock(cpu) as clock:
            clock.tick()
            cpu.ready_line = False
            clock.run_for(6)
            stalled = cpu.pc
            cpu.ready_line = True
            clock.run_for(5)

        self.assertEqual((stalled, cpu.pc), (0x0001, 0x0003))


if __name__ == "__main__":
    unittest.main()
