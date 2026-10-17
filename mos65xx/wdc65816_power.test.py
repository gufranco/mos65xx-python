from __future__ import annotations

import sys
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import UNSET_SEED, Cpu, Memory, RunLimit, Stopped, Waiting

RESET_VECTOR = 0xFFFC

CYCLES_PER_MOVED_BYTE = 7

HALTED = (None, None, "--------")

MOVE = (0x54, 0x7F, 0x7E)

STATES = (
    ("native, both wide", {"emulation": False, "m8": False, "x8": False}),
    ("native, both narrow", {"emulation": False, "m8": True, "x8": True}),
    ("native, mixed", {"emulation": False, "m8": False, "x8": True}),
    ("emulation", {"emulation": True, "m8": True, "x8": True}),
)


class FlatMemory:
    def __init__(self, data: Mapping[int, int] | None = None) -> None:
        self.cells: dict[int, int] = dict(data or {})

    def read8(self, address: int) -> int:
        return self.cells.get(address & 0xFFFFFF, 0x00)


def at_8000(memory: Any) -> Any:
    cpu = Cpu("65816", memory)
    cpu.pb, cpu.pc = 0x00, 0x8000
    return cpu


def halted(opcode: int) -> Any:
    cpu = at_8000(FlatMemory({0x008000: opcode}))
    cpu.step()
    return cpu


def mover(count: int, copied: int = 0x00) -> tuple[Any, Any]:
    memory = Memory(0x1000000)
    cpu = Cpu("65816", memory)
    cpu.emulation = False
    cpu.d = cpu.db = 0x00
    cpu.m8 = cpu.x8 = False
    cpu.pb, cpu.pc = 0x00, 0x8000
    cpu.a, cpu.x, cpu.y = count - 1, 0x0000, 0x1000
    memory.write8(0x7E0000, copied)
    for offset, byte in enumerate(MOVE):
        memory.write8(0x008000 + offset, byte)
    return cpu, memory


def reset_part(vector: int = 0x8000, seed: int = UNSET_SEED) -> Any:
    memory = Memory(0x1000000)
    memory.write8(RESET_VECTOR, vector & 0xFF)
    memory.write8(RESET_VECTOR + 1, vector >> 8)
    cpu = Cpu("65816", memory, seed=seed)
    cpu.reset(seed)
    return cpu


def poised(opcode: int, state: Mapping[str, bool]) -> Any:
    memory = Memory(0x1000000, seed=opcode)
    cpu = Cpu("65816", memory)
    cpu.emulation = False
    for name, value in state.items():
        setattr(cpu, name, value)
    cpu.pb, cpu.pc = 0x00, 0x8000
    cpu.s = 0x1FFF
    cpu.d = 0x0100
    cpu.db = 0x7E
    memory.write8(0x008000, opcode)
    return cpu


def refused(opcode: int, state: Mapping[str, bool]) -> bool:
    cpu = poised(opcode, state)
    before = cpu.steps
    cpu.step()
    return bool(cpu.steps != before + 1)


class BlockMoveTest(unittest.TestCase):
    def test_a_forward_move_copies_every_byte(self) -> None:
        # Arrange
        cpu, memory = mover(4)
        for index in range(4):
            memory.write8(0x7E0000 + index, index)

        # Act
        cpu.step()

        # Assert
        self.assertEqual([memory.read8(0x7F1000 + i) for i in range(4)], [0, 1, 2, 3])

    def test_a_forward_move_leaves_the_accumulator_at_minus_one(self) -> None:
        # Arrange
        cpu, _ = mover(2)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0xFFFF)

    def test_a_forward_move_advances_both_index_registers(self) -> None:
        # Arrange
        cpu, _ = mover(2)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.x, cpu.y), (0x0002, 0x1002))

    def test_a_move_sets_the_data_bank_to_its_destination(self) -> None:
        # Arrange
        cpu, _ = mover(1)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.db, 0x7F)

    def test_a_move_that_runs_out_of_cycles_stays_on_its_own_opcode(self) -> None:
        # Arrange
        cpu, _ = mover(0x100)
        cpu.cycle_budget = CYCLES_PER_MOVED_BYTE

        # Act
        spent = cpu.step()

        # Assert
        self.assertEqual((cpu.pc, spent, cpu.a), (0x8000, CYCLES_PER_MOVED_BYTE, 0x00FE))

    def test_a_move_interrupted_partway_keeps_the_bytes_it_copied(self) -> None:
        # Arrange
        cpu, memory = mover(0x100, copied=0xAB)
        cpu.cycle_budget = CYCLES_PER_MOVED_BYTE

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x7F1000), 0xAB)


class HaltTest(unittest.TestCase):
    def test_stopping_the_processor_refuses_another_step(self) -> None:
        # Arrange
        cpu = halted(0xDB)

        def attempt() -> Any:
            return cpu.step()

        # Act
        with self.assertRaises(Stopped) as raised:
            attempt()

        # Assert
        self.assertEqual((type(raised.exception), cpu.stopped), (Stopped, True))

    def test_a_reset_costs_the_six_cycles_the_manual_names_plus_the_vector(self) -> None:
        # Arrange
        cpu = Cpu("65816", FlatMemory())
        before = cpu.cycles

        # Act
        cpu.reset()

        # Assert
        self.assertEqual(cpu.cycles - before, 6 + 2)

    def test_every_cycle_reaches_a_watcher_including_the_internal_ones(self) -> None:
        # Arrange
        cpu = Cpu("65816", FlatMemory({0x008000: 0x0A}))
        cpu.reset()
        cpu.pb, cpu.pc = 0x00, 0x8000
        seen: list[int] = []
        cpu.on_cycle = lambda: seen.append(1)

        # Act
        spent = cpu.step()

        # Assert
        self.assertEqual((len(seen), spent), (2, 2))

    def test_a_waiting_part_will_not_run_the_next_instruction(self) -> None:
        # Arrange
        cpu = at_8000(FlatMemory({0x008000: 0xCB, 0x008001: 0xEA}))
        cpu.step()

        def attempt() -> Any:
            return cpu.step()

        # Act
        with self.assertRaises(Waiting) as raised:
            attempt()

        # Assert
        self.assertEqual((type(raised.exception), cpu.pc), (Waiting, 0x8001))

    def test_a_halted_part_drives_no_address_and_no_line(self) -> None:
        # Arrange
        cpu = halted(0xDB)
        cpu.trace = []

        # Act
        cpu.run_for(3)

        # Assert
        self.assertEqual(cpu.trace, [HALTED] * 3)

    def test_a_halted_part_costs_time_even_with_nothing_recording(self) -> None:
        # Arrange
        cpu = halted(0xDB)
        before = cpu.cycles

        # Act
        spent = cpu.run_for(12)

        # Assert
        self.assertEqual((spent, cpu.cycles - before), (12, 12))

    def test_a_waiting_part_is_clocked_on_rather_than_refusing(self) -> None:
        # Arrange
        cpu = halted(0xCB)

        # Act
        spent = cpu.run_for(7)

        # Assert
        self.assertEqual(spent, 7)

    def test_a_runaway_program_gives_up_when_the_caller_asks_for_a_bound(self) -> None:
        # Arrange
        cpu = at_8000(FlatMemory({0x008000: 0x80, 0x008001: 0xFE}))

        def attempt() -> Any:
            return cpu.run_until(lambda _machine: False, limit=100)

        # Act
        with self.assertRaises(RunLimit) as raised:
            attempt()

        # Assert
        self.assertIn("100 instructions", str(raised.exception))

    def test_a_step_reports_the_cycles_that_instruction_took(self) -> None:
        # Arrange
        cpu = at_8000(FlatMemory({0x008000: 0xEA}))

        # Act
        cycles = cpu.step()

        # Assert
        self.assertEqual(cycles, 2)

    def test_a_budget_runs_whole_instructions_and_reports_what_was_spent(self) -> None:
        # Arrange
        cpu = at_8000(FlatMemory(dict.fromkeys(range(0x008000, 0x008010), 0xEA)))

        # Act
        spent = cpu.run_for(5)

        # Assert
        self.assertEqual(spent, 6)


class MemoryFillTest(unittest.TestCase):
    def test_no_fill_given_means_a_scrambled_machine(self) -> None:
        # Arrange
        size = 256

        # Act
        memory = Memory(size)

        # Assert
        self.assertNotEqual(bytes(memory.data), bytes(256))

    def test_the_same_seed_scrambles_the_same_way(self) -> None:
        # Arrange
        first = Memory(256)

        # Act
        second = Memory(256)

        # Assert
        self.assertEqual(second.data, first.data)

    def test_a_different_seed_scrambles_differently(self) -> None:
        # Arrange
        first = Memory(256, seed=1)

        # Act
        second = Memory(256, seed=2)

        # Assert
        self.assertNotEqual(second.data, first.data)

    def test_a_cleared_one_has_to_be_asked_for_in_writing(self) -> None:
        # Arrange
        fill = 0

        # Act
        memory = Memory(4, fill=fill)

        # Assert
        self.assertEqual(set(memory.data), {0})

    def test_an_image_is_laid_at_the_front_and_the_rest_stays_undefined(self) -> None:
        # Arrange
        image = b"\x01\x02"

        # Act
        memory = Memory(8, image=image)

        # Assert
        self.assertEqual(
            (bytes(memory.data[:2]), bytes(memory.data[2:]) == bytes(6)),
            (b"\x01\x02", False),
        )

    def test_a_read_wraps_to_twenty_four_bits(self) -> None:
        # Arrange
        memory = Memory(0x1000000)
        memory.write8(0x000010, 0x77)

        # Act
        found = memory.read8(0x1000010)

        # Assert
        self.assertEqual(found, 0x77)

    def test_a_write_keeps_only_the_low_byte(self) -> None:
        # Arrange
        memory = Memory(16)

        # Act
        memory.write8(0, 0x1FF)

        # Assert
        self.assertEqual(memory.read8(0), 0xFF)


class ResetTest(unittest.TestCase):
    def test_a_reset_leaves_the_processor_in_emulation_mode(self) -> None:
        # Arrange
        vector = 0x8000

        # Act
        cpu = reset_part(vector)

        # Assert
        self.assertTrue(cpu.emulation)

    def test_a_reset_forces_both_widths_to_eight_bits(self) -> None:
        # Arrange
        vector = 0x8000

        # Act
        cpu = reset_part(vector)

        # Assert
        self.assertEqual((cpu.m8, cpu.x8), (True, True))

    def test_a_reset_clears_decimal_and_sets_the_interrupt_disable(self) -> None:
        # Arrange
        vector = 0x8000

        # Act
        cpu = reset_part(vector)

        # Assert
        self.assertEqual((cpu.decimal, cpu.irq_disable), (False, True))

    def test_a_reset_zeroes_the_direct_page_and_both_bank_registers(self) -> None:
        # Arrange
        vector = 0x8000

        # Act
        cpu = reset_part(vector)

        # Assert
        self.assertEqual((cpu.d, cpu.db, cpu.pb), (0, 0, 0))

    def test_a_reset_takes_the_program_counter_from_the_vector(self) -> None:
        # Arrange
        vector = 0x1234

        # Act
        cpu = reset_part(vector)

        # Assert
        self.assertEqual(cpu.pc, 0x1234)

    def test_a_reset_forces_the_stack_into_page_one(self) -> None:
        # Arrange
        vector = 0x8000

        # Act
        cpu = reset_part(vector)

        # Assert
        self.assertEqual(cpu.s & 0xFF00, 0x0100)

    def test_a_reset_does_not_clear_what_the_hardware_leaves_undefined(self) -> None:
        # Arrange
        one = reset_part(seed=1)

        # Act
        other = reset_part(seed=2)

        # Assert
        self.assertNotEqual((one.a, one.x, one.y), (other.a, other.x, other.y))

    def test_the_undefined_registers_are_reproducible_from_a_seed(self) -> None:
        # Arrange
        first = reset_part(seed=7)

        # Act
        second = reset_part(seed=7)

        # Assert
        self.assertEqual(second.a, first.a)

    def test_a_part_that_was_only_powered_holds_rubbish(self) -> None:
        # Arrange
        memory = Memory(0x10000)

        # Act
        cpu = Cpu("65816", memory)

        # Assert
        self.assertNotEqual((cpu.a, cpu.x, cpu.y, cpu.pc, cpu.d), (0, 0, 0, 0, 0))

    def test_and_that_part_has_not_spent_a_cycle(self) -> None:
        # Arrange
        memory = Memory(0x10000)

        # Act
        cpu = Cpu("65816", memory)

        # Assert
        self.assertEqual(cpu.cycles, 0)

    def test_the_same_seed_powers_up_the_same_way_twice(self) -> None:
        # Arrange
        first = Cpu("65816", Memory(0x10000), seed=7)

        # Act
        second = Cpu("65816", Memory(0x10000), seed=7)

        # Assert
        self.assertEqual(
            (first.a, first.x, first.y, first.pc, first.d),
            (second.a, second.x, second.y, second.pc, second.d),
        )


class EveryOpcodeTest(unittest.TestCase):
    def test_every_opcode_executes_in_every_width_with_a_handler_behind_it(self) -> None:
        # Arrange
        cases = [(opcode, name, state) for opcode in range(256) for name, state in STATES]

        # Act
        failed = [f"${op:02X} {name}" for op, name, state in cases if refused(op, state)]

        # Assert
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
