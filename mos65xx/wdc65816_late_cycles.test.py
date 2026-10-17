from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import Cpu, Memory, RunLimit

MOVE = (0x54, 0x7E, 0x7F)


def part(code: Sequence[int], emulation: bool = False, at: int = 0x8000, **registers: Any) -> Any:
    memory = Memory(0x1000000)
    cpu = Cpu("65816", memory)
    cpu.emulation = False
    cpu.d = cpu.db = 0x00
    cpu.emulation = emulation
    if not emulation:
        cpu.m8 = cpu.x8 = True
    cpu.pb, cpu.pc = 0x00, at
    cpu.s = 0x01FF
    cpu.a = cpu.x = cpu.y = 0x0000
    for name, value in registers.items():
        setattr(cpu, name, value)
    for offset, byte in enumerate(code):
        memory.write8(at + offset, byte)
    cpu.trace = []
    return cpu


def bus(cpu: Any) -> list[Any]:
    return [(hex(address), value, pins) for address, value, pins in cpu.trace]


class PinTest(unittest.TestCase):
    def test_an_opcode_fetch_raises_both_address_lines(self) -> None:
        # Arrange
        cpu = part([0xEA])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(bus(cpu)[0][2], "dp-r-mx-")

    def test_an_operand_read_raises_only_the_program_line(self) -> None:
        # Arrange
        cpu = part([0xA9, 0x11])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(bus(cpu)[1][2], "-p-r-mx-")

    def test_a_data_read_raises_only_the_data_line(self) -> None:
        # Arrange
        cpu = part([0xA5, 0x40])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(bus(cpu)[2][2], "d--r-mx-")

    def test_a_write_lowers_the_read_line(self) -> None:
        # Arrange
        cpu = part([0x85, 0x40])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(bus(cpu)[2][2], "d--w-mx-")

    def test_an_internal_cycle_lowers_both_and_carries_no_value(self) -> None:
        # Arrange
        cpu = part([0xEA])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(bus(cpu)[1][1:], (None, "---r-mx-"))

    def test_emulation_mode_shows_on_every_cycle(self) -> None:
        # Arrange
        cpu = part([0xEA], emulation=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual({one[2][4] for one in bus(cpu)}, {"e"})

    def test_the_width_bits_show_on_every_cycle(self) -> None:
        # Arrange
        cpu = part([0xEA], m8=False, x8=False)

        # Act
        cpu.step()

        # Assert
        self.assertEqual({one[2][5:7] for one in bus(cpu)}, {"--"})

    def test_a_vector_read_lowers_the_pull_line(self) -> None:
        # Arrange
        cpu = part([0x00, 0x00])

        # Act
        cpu.step()

        # Assert
        self.assertEqual([one[2] for one in bus(cpu)[-2:]], ["d-vr-mx-", "d-vr-mx-"])

    def test_a_read_modify_write_locks_memory_for_its_last_three_cycles(self) -> None:
        # Arrange
        cpu = part([0x06, 0x40])

        # Act
        cpu.step()

        # Assert
        self.assertEqual([one[2][7] for one in bus(cpu)], ["-", "-", "l", "l", "l"])

    def test_and_for_five_when_the_accumulator_is_wide(self) -> None:
        # Arrange
        cpu = part([0x0E, 0x00, 0x20], m8=False)

        # Act
        cpu.step()

        # Assert
        self.assertEqual([one[2][7] for one in bus(cpu)], ["-", "-", "-", "l", "l", "l", "l", "l"])

    def test_the_modify_cycle_carries_no_value_in_native_mode(self) -> None:
        # Arrange
        cpu = part([0x06, 0x40])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(bus(cpu)[3][1:], (None, "---r-mxl"))

    def test_and_carries_the_byte_it_read_in_emulation_mode(self) -> None:
        # Arrange
        cpu = part([0x06, 0x40], emulation=True)
        cpu.memory.write8(0x000040, 0x21)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.trace[3], (0x000040, 0x21, "---wemxl"))


class OrderTest(unittest.TestCase):
    def test_a_word_read_modify_write_writes_its_high_half_first(self) -> None:
        # Arrange
        cpu = part([0x0E, 0x00, 0x20], m8=False)

        # Act
        cpu.step()

        # Assert
        self.assertEqual([one[0] for one in bus(cpu)[-2:]], ["0x2001", "0x2000"])

    def test_a_store_writes_its_low_half_first(self) -> None:
        # Arrange
        cpu = part([0x8D, 0x00, 0x20], m8=False)

        # Act
        cpu.step()

        # Assert
        self.assertEqual([one[0] for one in bus(cpu)[-2:]], ["0x2000", "0x2001"])

    def test_a_reserved_opcode_steps_over_its_operand_without_reading_it(self) -> None:
        # Arrange
        cpu = part([0x42, 0x11])

        # Act
        cpu.step()

        # Assert
        self.assertEqual((len(cpu.trace), bus(cpu)[1][1:]), (2, (None, "---r-mx-")))


class LengthTest(unittest.TestCase):
    def cycles(self, code: Sequence[int], **registers: Any) -> int:
        cpu = part(code, **registers)
        cpu.step()
        return len(cpu.trace)

    def test_a_direct_page_that_is_not_aligned_costs_a_cycle(self) -> None:
        # Arrange
        code = [0xA5, 0x40]

        # Act
        spent = self.cycles(code, d=0x1234)

        # Assert
        self.assertEqual(spent, 4)

    def test_and_costs_nothing_when_it_is_aligned(self) -> None:
        # Arrange
        code = [0xA5, 0x40]

        # Act
        spent = self.cycles(code, d=0x1200)

        # Assert
        self.assertEqual(spent, 3)

    def test_a_sixteen_bit_index_always_costs_the_indexing_cycle(self) -> None:
        # Arrange
        code = [0xBD, 0x00, 0x20]

        # Act
        spent = self.cycles(code, x8=False, x=0x0010)

        # Assert
        self.assertEqual(spent, 5)

    def test_an_eight_bit_index_costs_it_only_across_a_page(self) -> None:
        # Arrange
        code = [0xBD, 0xF0, 0x20]

        # Act
        spent = self.cycles(code, x=0x20)

        # Assert
        self.assertEqual(spent, 5)

    def test_and_not_within_one(self) -> None:
        # Arrange
        code = [0xBD, 0x00, 0x20]

        # Act
        spent = self.cycles(code, x=0x20)

        # Assert
        self.assertEqual(spent, 4)

    def test_a_store_pays_for_indexing_whatever_the_index_is(self) -> None:
        # Arrange
        code = [0x9D, 0x00, 0x20]

        # Act
        spent = self.cycles(code, x=0x20)

        # Assert
        self.assertEqual(spent, 5)

    def test_setting_status_bits_takes_three_cycles(self) -> None:
        # Arrange
        code = [0xE2, 0x30]

        # Act
        spent = self.cycles(code)

        # Assert
        self.assertEqual(spent, 3)

    def test_a_taken_branch_costs_a_cycle(self) -> None:
        # Arrange
        code = [0x80, 0x10]

        # Act
        spent = self.cycles(code)

        # Assert
        self.assertEqual(spent, 3)

    def test_and_a_page_crossing_costs_another_only_in_emulation_mode(self) -> None:
        # Arrange
        code = [0x80, 0x7F]

        # Act
        spent = self.cycles(code, emulation=True, at=0x80A0)

        # Assert
        self.assertEqual(spent, 4)

    def test_which_native_mode_does_not_pay(self) -> None:
        # Arrange
        code = [0x80, 0x7F]

        # Act
        spent = self.cycles(code, at=0x80A0)

        # Assert
        self.assertEqual(spent, 3)


class BlockMoveCycleTest(unittest.TestCase):
    def test_a_block_move_refetches_itself_for_every_byte(self) -> None:
        # Arrange
        cpu = part(MOVE, a=0x0001, y=0x0100)

        # Act
        cpu.step()

        # Assert
        self.assertEqual([one[2] for one in cpu.trace[7:10]], ["dp-r-mx-", "-p-r-mx-", "-p-r-mx-"])

    def test_and_spends_two_cycles_after_each_byte_it_writes(self) -> None:
        # Arrange
        cpu = part(MOVE, a=0x0000, y=0x0100)

        # Act
        cpu.step()

        # Assert
        self.assertEqual([one[2] for one in cpu.trace[-2:]], ["---r-mx-", "---r-mx-"])

    def test_a_move_cut_short_leaves_the_cycles_it_managed(self) -> None:
        # Arrange
        cpu = part(MOVE, a=0x00FF, y=0x0100, cycle_budget=11)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(len(cpu.trace), 11)

    def test_and_stops_before_the_write_of_the_byte_it_could_not_finish(self) -> None:
        # Arrange
        cpu = part(MOVE, a=0x00FF, y=0x0100, cycle_budget=11)

        # Act
        cpu.step()

        # Assert
        self.assertEqual([one[2] for one in cpu.trace[-2:]], ["-p-r-mx-", "d--r-mx-"])


class BoundedCallTest(unittest.TestCase):
    def test_a_routine_that_never_returns_gives_up_at_the_bound(self) -> None:
        # Arrange
        cpu = part((0x4C, 0x00, 0x80))

        def attempt() -> Any:
            return cpu.call(0x008000, limit=64)

        # Act
        with self.assertRaises(RunLimit) as raised:
            attempt()

        # Assert
        self.assertIn("64 instructions", str(raised.exception))

    def test_and_has_run_exactly_that_many(self) -> None:
        # Arrange
        cpu = part((0x4C, 0x00, 0x80))

        def attempt() -> Any:
            return cpu.call(0x008000, limit=64)

        # Act
        with self.assertRaises(RunLimit) as raised:
            attempt()

        # Assert
        self.assertEqual((cpu.steps, type(raised.exception)), (64, RunLimit))

    def test_a_bound_the_routine_reaches_leaves_the_registers_it_set(self) -> None:
        # Arrange
        cpu = part((0xE8, 0xE8, 0x60), x=0x0000)

        # Act
        cpu.call(0x008000, limit=64)

        # Assert
        self.assertEqual(cpu.x, 0x02)


if __name__ == "__main__":
    unittest.main(verbosity=2)
