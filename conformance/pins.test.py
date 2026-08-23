"""That the interrupt inputs behave as lines rather than as events.

The distinction is the whole content of these tests. A request that is raised
and withdrawn before the part looks must produce nothing, and a non-maskable
line held low after its transition must not interrupt twice. Neither is
reachable without a clock that can stop between two cycles, which is why these
live beside it rather than with the instruction tests.
"""

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
        cpu = self.part()

        with mos65xx.Clock(cpu) as clock:
            clock.tick()
            cpu.irq_line = True
            clock.tick()
            cpu.irq_line = False
            clock.run_for(6)

        self.assertNotEqual(cpu.pc, 0x9000)

    def test_a_request_still_held_at_that_moment_is(self) -> None:
        cpu = self.part()
        cpu.memory.write8(0x9000, 0x02)

        with mos65xx.Clock(cpu) as clock:
            clock.tick()
            cpu.irq_line = True
            clock.run_for(40)

        self.assertTrue(cpu.held())


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
    """The same two lines on the part that brings out a third."""

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
    """That a low ready line halts the part, and that a write is the exception.

    The exception belongs to the NMOS parts alone, and the MOS manual states it
    outright: "The RDY function will not stop the processor in a cycle in which a
    WRITE operation is being performed." The CMOS parts have no such carve-out,
    so the same program costs a different number of cycles on each, which is what
    these two tests measure.
    """

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
