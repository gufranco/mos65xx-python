from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, override

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_module() -> Any:
    return importlib.import_module("mos65xx.wdc65816")


emu = load_module()
errors = importlib.import_module("mos65xx.errors")

NATIVE_16 = 0x00
NATIVE_8 = emu.FLAG_M | emu.FLAG_X


class FlatMemory:
    def __init__(self, data: Mapping[int, int] | None = None) -> None:
        self.cells: dict[int, int] = dict(data or {})

    def read8(self, address: int) -> int:
        return self.cells.get(address & 0xFFFFFF, 0x00)

    def write8(self, address: int, value: int) -> None:
        self.cells[address & 0xFFFFFF] = value & 0xFF


def run(
    code: Sequence[int],
    base: int = 0x008000,
    memory: Any = None,
    status: int = NATIVE_8,
    **registers: Any,
) -> Any:
    memory = memory or FlatMemory()
    for offset, byte in enumerate(code):
        memory.cells[base + offset] = byte
    cpu = emu.Cpu(memory)
    cpu.a = cpu.x = cpu.y = 0x0000
    cpu.s = 0x01FF
    cpu.d = 0x0000
    cpu.db = 0x00
    cpu.emulation = False
    cpu.set_status(status)
    for name, value in registers.items():
        setattr(cpu, name, value)
    cpu.call(base)
    return cpu


RTL = 0x6B


class CoverageTest(unittest.TestCase):
    def test_every_opcode_has_a_handler(self) -> None:
        without = [
            opcode
            for opcode, (mnemonic, _) in enumerate(emu.OPCODES)
            if not hasattr(emu.Cpu, f"op_{mnemonic}")
        ]

        self.assertEqual(without, [])

    def test_the_table_covers_the_whole_byte(self) -> None:
        self.assertEqual(len(emu.OPCODES), 256)

    def test_the_reserved_opcode_is_a_two_byte_no_operation(self) -> None:
        memory = FlatMemory()

        cpu = run([0x42, 0xFF, RTL], memory=memory)

        self.assertEqual(cpu.pc, 0x8002)


class ResetStateTest(unittest.TestCase):
    def test_the_registers_start_eight_bits_wide(self) -> None:
        cpu = emu.Cpu(FlatMemory())

        self.assertTrue(cpu.m8)
        self.assertTrue(cpu.x8)


class WidthTest(unittest.TestCase):
    def test_rep_widens_the_accumulator(self) -> None:
        cpu = run([0xC2, 0x20, RTL])

        self.assertFalse(cpu.m8)

    def test_sep_narrows_the_accumulator(self) -> None:
        cpu = run([0xE2, 0x20, RTL], status=NATIVE_16)

        self.assertTrue(cpu.m8)

    def test_an_immediate_load_follows_the_declared_width(self) -> None:
        cpu = run([0xA9, 0x34, 0x12, RTL], status=NATIVE_16)

        self.assertEqual(cpu.a, 0x1234)

    def test_narrowing_the_index_truncates_it(self) -> None:
        cpu = run([0xE2, 0x10, RTL], status=NATIVE_16, x=0x1234)

        self.assertEqual(cpu.x, 0x34)

    def test_the_hidden_accumulator_half_survives_a_narrow_load(self) -> None:
        cpu = run([0xA9, 0x99, RTL], a=0x1234)

        self.assertEqual(cpu.a, 0x1299)


class AddressingTest(unittest.TestCase):
    def test_absolute_reads_through_the_data_bank(self) -> None:
        memory = FlatMemory({0x600005: 0x77})

        cpu = run([0xAD, 0x05, 0x00, RTL], memory=memory, db=0x60)

        self.assertEqual(cpu.a & 0xFF, 0x77)

    def test_absolute_indexed_by_y_reads_through_the_data_bank(self) -> None:
        memory = FlatMemory({0x600005: 0x77})

        cpu = run([0xB9, 0x00, 0x00, RTL], memory=memory, db=0x60, y=0x05)

        self.assertEqual(cpu.a & 0xFF, 0x77)

    def test_a_long_read_ignores_the_data_bank(self) -> None:
        memory = FlatMemory({0x610042: 0x99})

        cpu = run([0xAF, 0x42, 0x00, 0x61, RTL], memory=memory, db=0x00)

        self.assertEqual(cpu.a & 0xFF, 0x99)

    def test_direct_page_reads_are_offset_by_the_direct_register(self) -> None:
        memory = FlatMemory({0x000312: 0x5A})

        cpu = run([0xA5, 0x12, RTL], memory=memory, d=0x0300)

        self.assertEqual(cpu.a & 0xFF, 0x5A)

    def test_an_indirect_pointer_is_taken_from_the_direct_page(self) -> None:
        memory = FlatMemory({0x000310: 0x00, 0x000311: 0x20, 0x602000: 0x3C})

        cpu = run([0xB2, 0x10, RTL], memory=memory, d=0x0300, db=0x60)

        self.assertEqual(cpu.a & 0xFF, 0x3C)

    def test_a_long_indirect_pointer_carries_its_own_bank(self) -> None:
        memory = FlatMemory({0x000310: 0x00, 0x000311: 0x20, 0x000312: 0x7E, 0x7E2000: 0xC3})

        cpu = run([0xA7, 0x10, RTL], memory=memory, d=0x0300, db=0x00)

        self.assertEqual(cpu.a & 0xFF, 0xC3)

    def test_stack_relative_reads_sit_above_the_stack_pointer(self) -> None:
        memory = FlatMemory({0x0001F3: 0x6E})

        cpu = run([0xA3, 0x04, RTL], memory=memory, s=0x01EF)

        self.assertEqual(cpu.a & 0xFF, 0x6E)


class ArithmeticTest(unittest.TestCase):
    def test_addition_carries_out_of_eight_bits(self) -> None:
        cpu = run([0x18, 0x69, 0x01, RTL], a=0xFF)

        self.assertEqual(cpu.a & 0xFF, 0x00)
        self.assertTrue(cpu.c)

    def test_addition_sets_overflow_when_the_sign_is_wrong(self) -> None:
        cpu = run([0x18, 0x69, 0x01, RTL], a=0x7F)

        self.assertTrue(cpu.v)

    def test_addition_leaves_overflow_clear_when_the_sign_holds(self) -> None:
        cpu = run([0x18, 0x69, 0x01, RTL], a=0x00)

        self.assertFalse(cpu.v)

    def test_subtraction_borrows_when_the_carry_is_clear(self) -> None:
        cpu = run([0x18, 0xE9, 0x01, RTL], a=0x10)

        self.assertEqual(cpu.a & 0xFF, 0x0E)

    def test_subtraction_below_zero_clears_the_carry(self) -> None:
        cpu = run([0x38, 0xE9, 0x02, RTL], a=0x01)

        self.assertFalse(cpu.c)

    def test_decimal_addition_carries_at_nine(self) -> None:
        cpu = run([0xF8, 0x18, 0x69, 0x01, RTL], a=0x09)

        self.assertEqual(cpu.a & 0xFF, 0x10)

    def test_decimal_subtraction_borrows_at_zero(self) -> None:
        cpu = run([0xF8, 0x38, 0xE9, 0x01, RTL], a=0x10)

        self.assertEqual(cpu.a & 0xFF, 0x09)

    def test_a_comparison_sets_the_carry_when_it_is_not_below(self) -> None:
        cpu = run([0xC9, 0x10, RTL], a=0x20)

        self.assertTrue(cpu.c)
        self.assertFalse(cpu.z)

    def test_a_comparison_of_equals_sets_zero(self) -> None:
        cpu = run([0xC9, 0x20, RTL], a=0x20)

        self.assertTrue(cpu.z)
        self.assertTrue(cpu.c)


class ShiftTest(unittest.TestCase):
    def test_a_shift_left_moves_the_top_bit_into_the_carry(self) -> None:
        cpu = run([0x0A, RTL], a=0x81)

        self.assertEqual(cpu.a & 0xFF, 0x02)
        self.assertTrue(cpu.c)

    def test_a_shift_right_moves_the_bottom_bit_into_the_carry(self) -> None:
        cpu = run([0x4A, RTL], a=0x03)

        self.assertEqual(cpu.a & 0xFF, 0x01)
        self.assertTrue(cpu.c)

    def test_a_rotate_left_brings_the_carry_in(self) -> None:
        cpu = run([0x38, 0x2A, RTL], a=0x00)

        self.assertEqual(cpu.a & 0xFF, 0x01)

    def test_a_rotate_right_brings_the_carry_into_the_top(self) -> None:
        cpu = run([0x38, 0x6A, RTL], a=0x00)

        self.assertEqual(cpu.a & 0xFF, 0x80)

    def test_a_shift_in_memory_writes_the_result_back(self) -> None:
        memory = FlatMemory({0x000042: 0x40})

        run([0x06, 0x42, RTL], memory=memory)

        self.assertEqual(memory.read8(0x000042), 0x80)

    def test_the_accumulator_half_swaps(self) -> None:
        cpu = run([0xEB, RTL], a=0x1234)

        self.assertEqual(cpu.a, 0x3412)


class StackTest(unittest.TestCase):
    def test_pushes_and_pulls_balance(self) -> None:
        cpu = run([0x08, 0x8B, 0x48, 0x68, 0xAB, 0x28, RTL], s=0x01FF)

        self.assertEqual(cpu.s, 0x01FF)

    def test_a_wide_push_moves_the_pointer_by_two(self) -> None:
        cpu = run([0x48, RTL], status=NATIVE_16, s=0x01FF, a=0x1234)

        self.assertEqual(cpu.s, 0x01FD)

    def test_a_pushed_value_comes_back(self) -> None:
        cpu = run([0x48, 0xA9, 0x00, 0x68, RTL], s=0x01FF, a=0x5A)

        self.assertEqual(cpu.a & 0xFF, 0x5A)

    def test_the_direct_register_round_trips_through_the_stack(self) -> None:
        cpu = run([0x0B, 0x2B, RTL], status=NATIVE_16, d=0x1234)

        self.assertEqual(cpu.d, 0x1234)

    def test_an_effective_address_can_be_pushed(self) -> None:
        cpu = run([0xF4, 0x34, 0x12, RTL], status=NATIVE_16, s=0x01FF)

        self.assertEqual(cpu.s, 0x01FD)


class BlockMoveTest(unittest.TestCase):
    def test_a_forward_move_copies_every_byte(self) -> None:
        memory = FlatMemory({0x7E0000 + i: i for i in range(4)})

        run(
            [0xA9, 0x03, 0x00, 0xA2, 0x00, 0x00, 0xA0, 0x00, 0x10, 0x54, 0x7F, 0x7E, RTL],
            memory=memory,
            status=NATIVE_16,
        )

        self.assertEqual([memory.read8(0x7F1000 + i) for i in range(4)], [0, 1, 2, 3])

    def test_a_forward_move_leaves_the_accumulator_at_minus_one(self) -> None:
        memory = FlatMemory()

        cpu = run(
            [0xA9, 0x01, 0x00, 0xA2, 0x00, 0x00, 0xA0, 0x00, 0x10, 0x54, 0x7F, 0x7E, RTL],
            memory=memory,
            status=NATIVE_16,
        )

        self.assertEqual(cpu.a, 0xFFFF)

    def test_a_forward_move_advances_both_index_registers(self) -> None:
        memory = FlatMemory()

        cpu = run(
            [0xA9, 0x01, 0x00, 0xA2, 0x00, 0x00, 0xA0, 0x00, 0x10, 0x54, 0x7F, 0x7E, RTL],
            memory=memory,
            status=NATIVE_16,
        )

        self.assertEqual(cpu.x, 0x0002)
        self.assertEqual(cpu.y, 0x1002)

    def test_a_move_sets_the_data_bank_to_its_destination(self) -> None:
        memory = FlatMemory()

        cpu = run(
            [0xA9, 0x00, 0x00, 0xA2, 0x00, 0x00, 0xA0, 0x00, 0x10, 0x54, 0x7F, 0x7E, RTL],
            memory=memory,
            status=NATIVE_16,
        )

        self.assertEqual(cpu.db, 0x7F)

    def test_a_move_that_runs_out_of_cycles_stays_on_its_own_opcode(self) -> None:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.emulation = False
        cpu.m8 = cpu.x8 = False
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.a, cpu.x, cpu.y = 0x00FF, 0x0000, 0x1000
        for offset, byte in enumerate((0x54, 0x7F, 0x7E)):
            memory.write8(0x008000 + offset, byte)
        cpu.cycle_budget = emu.CYCLES_PER_MOVE

        cpu.step()

        self.assertEqual(cpu.pc, 0x8000)

    def test_a_move_interrupted_partway_keeps_the_bytes_it_copied(self) -> None:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.emulation = False
        cpu.m8 = cpu.x8 = False
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.a, cpu.x, cpu.y = 0x00FF, 0x0000, 0x1000
        memory.write8(0x7E0000, 0xAB)
        for offset, byte in enumerate((0x54, 0x7F, 0x7E)):
            memory.write8(0x008000 + offset, byte)
        cpu.cycle_budget = emu.CYCLES_PER_MOVE

        cpu.step()

        self.assertEqual(memory.read8(0x7F1000), 0xAB)


class ControlTest(unittest.TestCase):
    def test_a_taken_branch_moves_the_program_counter_forward(self) -> None:
        cpu = run([0xA9, 0x00, 0xF0, 0x01, 0xEA, RTL])

        self.assertEqual(cpu.pc, 0x8005)

    def test_an_untaken_branch_falls_through(self) -> None:
        cpu = run([0xA9, 0x01, 0xF0, 0x01, 0xEA, RTL])

        self.assertEqual(cpu.pc, 0x8005)

    def test_a_branch_reaches_backwards(self) -> None:
        cpu = run([0xA2, 0x02, 0xCA, 0xD0, 0xFD, RTL])

        self.assertEqual(cpu.x, 0x00)

    def test_a_subroutine_returns_to_its_caller(self) -> None:
        cpu = run([0x20, 0x06, 0x80, 0xA9, 0x11, RTL, 0xA9, 0x22, 0x60], a=0x00)

        self.assertEqual(cpu.a & 0xFF, 0x11)

    def test_a_long_subroutine_returns_across_banks(self) -> None:
        memory = FlatMemory({0x018000: 0xA9, 0x018001: 0x33, 0x018002: 0x6B})

        cpu = run([0x22, 0x00, 0x80, 0x01, RTL], memory=memory)

        self.assertEqual(cpu.a & 0xFF, 0x33)


class EmulationModeTest(unittest.TestCase):
    def test_the_carry_and_the_emulation_flag_swap(self) -> None:
        cpu = run([0x38, 0xFB, RTL])

        self.assertTrue(cpu.emulation)
        self.assertFalse(cpu.c)

    def test_emulation_mode_forces_eight_bit_registers(self) -> None:
        cpu = run([0xC2, 0x30, 0x38, 0xFB, RTL])

        self.assertTrue(cpu.m8)
        self.assertTrue(cpu.x8)

    def test_leaving_emulation_mode_restores_the_carry(self) -> None:
        cpu = run([0x38, 0xFB, 0x18, 0xFB, RTL])

        self.assertFalse(cpu.emulation)


class HaltTest(unittest.TestCase):
    def test_stopping_the_processor_refuses_another_step(self) -> None:
        memory = FlatMemory({0x008000: 0xDB})
        cpu = emu.Cpu(memory)
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.step()

        with self.assertRaises(emu.Stopped):
            cpu.step()

    def test_a_reset_costs_the_six_cycles_the_manual_names_plus_the_vector(self) -> None:
        cpu = emu.Cpu(FlatMemory())
        before = cpu.cycles

        cpu.reset()

        self.assertEqual(cpu.cycles - before, emu.RESET_CYCLES)

    def test_every_cycle_reaches_a_watcher_including_the_internal_ones(self) -> None:
        memory = FlatMemory({0x008000: 0x0A})
        cpu = emu.Cpu(memory)
        cpu.reset()
        cpu.pb, cpu.pc = 0x00, 0x8000
        seen: list[int] = []
        cpu.on_cycle = lambda: seen.append(1)

        spent = cpu.step()

        self.assertEqual(len(seen), spent)

    def test_a_waiting_part_will_not_run_the_next_instruction(self) -> None:
        memory = FlatMemory({0x008000: 0xCB, 0x008001: 0xEA})
        cpu = emu.Cpu(memory)
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.step()

        with self.assertRaises(errors.Waiting):
            cpu.step()

    def test_a_halted_part_drives_no_address_and_no_line(self) -> None:
        memory = FlatMemory({0x008000: 0xDB})
        cpu = emu.Cpu(memory)
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.step()
        cpu.trace = []

        cpu.run_for(3)

        self.assertEqual(cpu.trace, [(None, None, emu.HALTED_PINS)] * 3)

    def test_a_halted_part_costs_time_even_with_nothing_recording(self) -> None:
        memory = FlatMemory({0x008000: 0xDB})
        cpu = emu.Cpu(memory)
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.step()
        before = cpu.cycles

        spent = cpu.run_for(12)

        self.assertEqual((spent, cpu.cycles - before), (12, 12))

    def test_a_waiting_part_is_clocked_on_rather_than_refusing(self) -> None:
        memory = FlatMemory({0x008000: 0xCB})
        cpu = emu.Cpu(memory)
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.step()

        spent = cpu.run_for(7)

        self.assertEqual(spent, 7)

    def test_a_runaway_program_gives_up_when_the_caller_asks_for_a_bound(self) -> None:
        memory = FlatMemory({0x008000: 0x80, 0x008001: 0xFE})
        cpu = emu.Cpu(memory)
        cpu.pb, cpu.pc = 0x00, 0x8000

        with self.assertRaises(emu.RunLimit):
            cpu.run_until(lambda machine: False, limit=100)

    def test_a_step_reports_the_cycles_that_instruction_took(self) -> None:
        memory = FlatMemory({0x008000: 0xEA})
        cpu = emu.Cpu(memory)
        cpu.pb, cpu.pc = 0x00, 0x8000

        cycles = cpu.step()

        self.assertEqual(cycles, 2)

    def test_a_budget_runs_whole_instructions_and_reports_what_was_spent(self) -> None:
        memory = FlatMemory(dict.fromkeys(range(0x008000, 0x008010), 0xEA))
        cpu = emu.Cpu(memory)
        cpu.pb, cpu.pc = 0x00, 0x8000

        spent = cpu.run_for(5)

        self.assertEqual(spent, 6)


class MemoryFillTest(unittest.TestCase):
    def test_no_fill_given_means_a_scrambled_machine(self) -> None:
        memory = emu.Memory(256)

        self.assertNotEqual(bytes(memory.data), bytes(256))

    def test_the_same_seed_scrambles_the_same_way(self) -> None:
        self.assertEqual(emu.Memory(256).data, emu.Memory(256).data)

    def test_a_different_seed_scrambles_differently(self) -> None:
        self.assertNotEqual(emu.Memory(256, seed=1).data, emu.Memory(256, seed=2).data)

    def test_a_cleared_one_has_to_be_asked_for_in_writing(self) -> None:
        """The rule is the default, not the absence of an option.

        A caller who genuinely wants zeroes says so, and the request is the same
        word in every member of this family. What must never happen is getting
        them without asking.
        """
        self.assertEqual(set(emu.Memory(4, fill=0).data), {0})

    def test_an_image_is_laid_at_the_front_and_the_rest_stays_undefined(self) -> None:
        memory = emu.Memory(8, image=b"\x01\x02")

        self.assertEqual(
            (bytes(memory.data[:2]), bytes(memory.data[2:]) == bytes(6)),
            (b"\x01\x02", False),
        )

    def test_a_read_wraps_to_twenty_four_bits(self) -> None:
        memory = emu.Memory(0x1000000)
        memory.write8(0x000010, 0x77)

        self.assertEqual(memory.read8(0x1000010), 0x77)

    def test_a_write_keeps_only_the_low_byte(self) -> None:
        memory = emu.Memory(16)
        memory.write8(0, 0x1FF)

        self.assertEqual(memory.read8(0), 0xFF)


class ResetTest(unittest.TestCase):
    def machine(self, vector: int = 0x8000, seed: int = emu.UNSET_SEED) -> Any:
        memory = emu.Memory(0x1000000)
        memory.write8(emu.RESET_VECTOR, vector & 0xFF)
        memory.write8(emu.RESET_VECTOR + 1, vector >> 8)
        cpu = emu.Cpu(memory, seed=seed)
        cpu.reset(seed)
        return cpu

    def test_a_reset_leaves_the_processor_in_emulation_mode(self) -> None:
        self.assertTrue(self.machine().emulation)

    def test_a_reset_forces_both_widths_to_eight_bits(self) -> None:
        cpu = self.machine()

        self.assertTrue(cpu.m8)
        self.assertTrue(cpu.x8)

    def test_a_reset_clears_decimal_and_sets_the_interrupt_disable(self) -> None:
        cpu = self.machine()

        self.assertFalse(cpu.decimal)
        self.assertTrue(cpu.irq_disable)

    def test_a_reset_zeroes_the_direct_page_and_both_bank_registers(self) -> None:
        cpu = self.machine()

        self.assertEqual((cpu.d, cpu.db, cpu.pb), (0, 0, 0))

    def test_a_reset_takes_the_program_counter_from_the_vector(self) -> None:
        self.assertEqual(self.machine(0x1234).pc, 0x1234)

    def test_a_reset_forces_the_stack_into_page_one(self) -> None:
        self.assertEqual(self.machine().s & 0xFF00, 0x0100)

    def test_a_reset_does_not_clear_what_the_hardware_leaves_undefined(self) -> None:
        one = self.machine(seed=1)
        other = self.machine(seed=2)

        self.assertNotEqual((one.a, one.x, one.y), (other.a, other.x, other.y))

    def test_the_undefined_registers_are_reproducible_from_a_seed(self) -> None:
        self.assertEqual(self.machine(seed=7).a, self.machine(seed=7).a)

    def test_a_part_that_was_only_powered_holds_rubbish(self) -> None:
        cpu = emu.Cpu(emu.Memory(0x10000))

        self.assertNotEqual((cpu.a, cpu.x, cpu.y, cpu.pc, cpu.d), (0, 0, 0, 0, 0))

    def test_and_that_part_has_not_spent_a_cycle(self) -> None:
        cpu = emu.Cpu(emu.Memory(0x10000))

        self.assertEqual(cpu.cycles, 0)

    def test_the_same_seed_powers_up_the_same_way_twice(self) -> None:
        first = emu.Cpu(emu.Memory(0x10000), seed=7)
        second = emu.Cpu(emu.Memory(0x10000), seed=7)

        self.assertEqual(
            (first.a, first.x, first.y, first.pc, first.d),
            (second.a, second.x, second.y, second.pc, second.d),
        )


class EveryOpcodeTest(unittest.TestCase):
    STATES = (
        ("native, both wide", {"emulation": False, "m8": False, "x8": False}),
        ("native, both narrow", {"emulation": False, "m8": True, "x8": True}),
        ("native, mixed", {"emulation": False, "m8": False, "x8": True}),
        ("emulation", {"emulation": True, "m8": True, "x8": True}),
    )

    def machine(self, opcode: int, state: Any) -> Any:
        memory = emu.Memory(0x1000000, seed=opcode)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        for name, value in state.items():
            setattr(cpu, name, value)
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.s = 0x1FFF
        cpu.d = 0x0100
        cpu.db = 0x7E
        memory.write8(0x008000, opcode)
        return cpu

    def test_every_opcode_executes_in_every_width(self) -> None:
        for opcode in range(256):
            for name, state in self.STATES:
                cpu = self.machine(opcode, state)
                with self.subTest(opcode=f"${opcode:02X}", state=name):
                    cpu.step()
                    self.assertGreaterEqual(cpu.steps, 1)

    def test_every_opcode_has_an_implementation_behind_it(self) -> None:
        missing = [
            f"${opcode:02X} {emu.OPCODES[opcode][0]}"
            for opcode in range(256)
            if not hasattr(emu.Cpu, f"op_{emu.OPCODES[opcode][0]}")
        ]

        self.assertEqual(missing, [])

    def test_the_table_names_an_instruction_for_every_opcode(self) -> None:
        self.assertEqual(len(emu.OPCODES), 256)
        self.assertTrue(all(name and mode for name, mode in emu.OPCODES))


class WordAndLongReadTest(unittest.TestCase):
    def machine(self) -> Any:
        return emu.Cpu(emu.Memory(0x1000000))

    def test_a_word_is_read_low_byte_first(self) -> None:
        cpu = self.machine()
        cpu.memory.write8(0x012340, 0x34)
        cpu.memory.write8(0x012341, 0x12)

        self.assertEqual(cpu.read16(0x012340), 0x1234)

    def test_a_long_address_is_read_low_byte_first(self) -> None:
        cpu = self.machine()
        cpu.memory.write8(0x012340, 0x56)
        cpu.memory.write8(0x012341, 0x34)
        cpu.memory.write8(0x012342, 0x12)

        self.assertEqual(cpu.read24(0x012340), 0x123456)


class BankZeroWordTest(unittest.TestCase):
    """A word touched through the direct page stays in bank zero, both halves.

    The manufacturer puts the direct page in bank zero and keeps it there: the
    cycle table addresses every direct access as `0,D+DO` and its second half as
    `0,D+DO+1`, and the caveats say the effective address of Direct, Direct,X and
    Direct,Y is always inside 000000 to 00FFFF. So a sixteen bit access whose low
    half sits at $FFFF finds its high half at $0000 of the same bank rather than
    at $010000, and that holds for a read, a write, and the read and the write of
    one read-modify-write.
    """

    def machine(self, code: Sequence[int]) -> Any:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.m8 = cpu.x8 = False
        cpu.d = 0xFFF0
        cpu.pb, cpu.pc = 0x00, 0x8000
        for offset, byte in enumerate(code):
            memory.write8(0x008000 + offset, byte)
        return cpu, memory

    def test_a_read_modify_write_reads_its_high_half_from_bank_zero(self) -> None:
        cpu, memory = self.machine([0x06, 0x0F])
        memory.write8(0x00FFFF, 0x01)
        memory.write8(0x000000, 0x02)
        memory.write8(0x010000, 0xEE)

        cpu.step()

        self.assertEqual(memory.read8(0x000000), 0x04)

    def test_and_writes_it_there_too(self) -> None:
        cpu, memory = self.machine([0x06, 0x0F])
        memory.write8(0x00FFFF, 0x01)
        memory.write8(0x000000, 0x02)
        memory.write8(0x010000, 0xEE)

        cpu.step()

        self.assertEqual(memory.read8(0x010000), 0xEE)

    def test_the_low_half_is_written_where_it_was_read(self) -> None:
        cpu, memory = self.machine([0x06, 0x0F])
        memory.write8(0x00FFFF, 0x01)
        memory.write8(0x000000, 0x02)

        cpu.step()

        self.assertEqual(memory.read8(0x00FFFF), 0x02)

    def test_a_bit_test_and_set_wraps_the_same_way(self) -> None:
        cpu, memory = self.machine([0x04, 0x0F])
        memory.write8(0x00FFFF, 0x01)
        memory.write8(0x000000, 0x02)
        memory.write8(0x010000, 0xEE)
        cpu.a = 0x1010

        cpu.step()

        self.assertEqual((memory.read8(0x000000), memory.read8(0x010000)), (0x12, 0xEE))

    def test_a_bit_test_and_reset_wraps_the_same_way(self) -> None:
        cpu, memory = self.machine([0x14, 0x0F])
        memory.write8(0x00FFFF, 0xFF)
        memory.write8(0x000000, 0xFF)
        memory.write8(0x010000, 0xEE)
        cpu.a = 0x0F0F

        cpu.step()

        self.assertEqual((memory.read8(0x000000), memory.read8(0x010000)), (0xF0, 0xEE))

    def test_a_store_already_wrapped_and_still_does(self) -> None:
        cpu, memory = self.machine([0x85, 0x0F])
        memory.write8(0x010000, 0xEE)
        cpu.a = 0x1234

        cpu.step()

        self.assertEqual((memory.read8(0x000000), memory.read8(0x010000)), (0x12, 0xEE))


class DirectPagePointerWrapTest(unittest.TestCase):
    """Which pointer reads stay inside the direct page, per mode.

    Emulation mode with a page-aligned direct register is the only place this
    arises. Four of these six are what a recorded cycle address shows and all
    four leave the page: the three the datasheet names and `(d,x)`, which it does
    not. The remaining two have no case in any corpus that reaches the edge, so
    they follow the datasheet and wrap. conformance/divergences.json names which
    is which and holds the evidence.

    Two of these expectations said the opposite until 2026-08-25, because the
    corpus they were measured from carried a reading that its own publishers
    corrected in 2024 and this project had pinned an archived copy from before.
    """

    def addresses(self, code: Sequence[int], operand: int = 0xFF) -> list[int]:
        seen: list[int] = []

        class Watched(FlatMemory):
            @override
            def read8(self, address: int) -> int:
                seen.append(address)
                return super().read8(address)

        memory = Watched()
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.emulation = True
        cpu.d = 0x0C00
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.x = cpu.y = 0x00
        for offset, byte in enumerate([*code, operand]):
            memory.cells[0x008000 + offset] = byte
        del seen[:]
        cpu.step()
        return [address for address in seen if 0x000C00 <= address <= 0x000D01]

    def test_a_direct_indirect_pointer_wraps_inside_the_page(self) -> None:
        self.assertEqual(self.addresses([0xB2]), [0x000CFF, 0x000C00])

    def test_a_direct_indexed_indirect_pointer_leaves_the_page(self) -> None:
        self.assertEqual(self.addresses([0xA1]), [0x000CFF, 0x000D00])

    def test_a_direct_indirect_indexed_pointer_wraps_inside_the_page(self) -> None:
        self.assertEqual(self.addresses([0xB1]), [0x000CFF, 0x000C00])

    def test_a_long_indirect_pointer_leaves_the_page(self) -> None:
        self.assertEqual(self.addresses([0xA7]), [0x000CFF, 0x000D00, 0x000D01])

    def test_a_long_indirect_indexed_pointer_leaves_the_page(self) -> None:
        self.assertEqual(self.addresses([0xB7]), [0x000CFF, 0x000D00, 0x000D01])

    def test_the_pointer_pushed_by_pei_leaves_the_page(self) -> None:
        self.assertEqual(self.addresses([0xD4]), [0x000CFF, 0x000D00])

    def test_none_of_it_happens_when_the_page_is_not_aligned(self) -> None:
        seen: list[int] = []

        class Watched(FlatMemory):
            @override
            def read8(self, address: int) -> int:
                seen.append(address)
                return super().read8(address)

        memory = Watched()
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.emulation = True
        cpu.d = 0x0C01
        cpu.pb, cpu.pc = 0x00, 0x8000
        memory.cells[0x008000] = 0xB2
        memory.cells[0x008001] = 0xFE
        del seen[:]
        cpu.step()

        self.assertEqual([a for a in seen if 0x000C00 <= a <= 0x000D01], [0x000CFF, 0x000D00])


class SoftwareInterruptTest(unittest.TestCase):
    def machine(self, opcode: int, emulation: bool) -> Any:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.emulation = emulation
        if not emulation:
            cpu.m8 = cpu.x8 = False
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.s = 0x01FF if emulation else 0x1FFF
        memory.write8(0x008000, opcode)
        return cpu, memory

    def test_a_break_in_emulation_mode_sets_the_break_flag_it_pushes(self) -> None:
        cpu, memory = self.machine(0x00, emulation=True)

        cpu.step()

        self.assertTrue(memory.read8(0x0001FD) & emu.BREAK_FLAG)

    def test_a_cop_in_emulation_mode_also_pushes_that_bit_set(self) -> None:
        cpu, memory = self.machine(0x02, emulation=True)

        cpu.step()

        self.assertTrue(memory.read8(0x0001FD) & emu.BREAK_FLAG)

    def test_native_mode_pushes_that_bit_as_the_index_width_instead(self) -> None:
        cpu, memory = self.machine(0x00, emulation=False)
        cpu.x8 = False

        cpu.step()

        self.assertFalse(memory.read8(0x001FFC) & emu.FLAG_X)

    def test_a_software_interrupt_skips_its_signature_byte(self) -> None:
        cpu, memory = self.machine(0x02, emulation=True)

        cpu.step()

        self.assertEqual(memory.read8(0x0001FE) | (memory.read8(0x0001FF) << 8), 0x8002)

    def test_a_break_in_emulation_mode_takes_its_own_vector(self) -> None:
        cpu, memory = self.machine(0x00, emulation=True)
        memory.write8(emu.EMULATION_BREAK_VECTOR, 0x00)
        memory.write8(emu.EMULATION_BREAK_VECTOR + 1, 0x90)

        cpu.step()

        self.assertEqual(cpu.pc, 0x9000)

    def test_a_cop_in_emulation_mode_takes_its_own_vector(self) -> None:
        cpu, memory = self.machine(0x02, emulation=True)
        memory.write8(emu.EMULATION_COP_VECTOR, 0x00)
        memory.write8(emu.EMULATION_COP_VECTOR + 1, 0xA0)

        cpu.step()

        self.assertEqual(cpu.pc, 0xA000)

    def test_a_break_in_native_mode_pushes_the_program_bank(self) -> None:
        cpu, memory = self.machine(0x00, emulation=False)
        cpu.pb = 0x00

        cpu.step()

        self.assertEqual(memory.read8(0x001FFF), 0x00)


class DefensivePathTest(unittest.TestCase):
    def machine(self) -> Any:
        return emu.Cpu(emu.Memory(0x10000))

    def test_an_address_mode_a_mnemonic_cannot_use_is_refused(self) -> None:
        with self.assertRaises(emu.UnsupportedError):
            self.machine().effective("nonsense", "lda")

    def test_a_mnemonic_with_no_handler_is_refused(self) -> None:
        cpu = self.machine()
        cpu.memory.write8(0x008000, 0xEA)
        cpu.pb, cpu.pc = 0x00, 0x8000
        table = list(emu.OPCODES)
        table[0xEA] = ("wibble", "implied")
        original = emu.OPCODES
        emu.OPCODES = tuple(table)
        try:
            with self.assertRaises(emu.UnsupportedError):
                cpu.step()
        finally:
            emu.OPCODES = original

    def test_a_jump_cannot_use_a_mode_the_processor_never_pairs_with_it(self) -> None:
        for handler in ("op_jmp", "op_jml", "op_jsr"):
            with self.subTest(handler=handler), self.assertRaises(emu.UnsupportedError):
                getattr(self.machine(), handler)("nonsense")

    def test_the_eight_bit_immediate_mode_takes_one_byte(self) -> None:
        cpu = self.machine()
        cpu.memory.write8(0x008000, 0x42)
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.m8 = False

        self.assertEqual(cpu.operand("immediate", "sep"), 0x42)

    def test_running_until_a_condition_returns_the_machine(self) -> None:
        cpu = self.machine()
        cpu.memory.write8(0x008000, 0xEA)
        cpu.pb, cpu.pc = 0x00, 0x8000

        self.assertIs(cpu.run_until(lambda machine: machine.steps > 0), cpu)


class HardwareInterruptTest(unittest.TestCase):
    """The three pins, in both modes, where the mode decides the stack depth."""

    def machine(self, emulation: bool, vector: int, target: int = 0x9000) -> Any:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.emulation = emulation
        if not emulation:
            cpu.m8 = cpu.x8 = False
        cpu.pb, cpu.pc = 0x12, 0x8000
        cpu.db = 0x7E
        cpu.s = 0x01FF if emulation else 0x1FFF
        cpu.irq_disable = False
        memory.write8(vector, target & 0xFF)
        memory.write8(vector + 1, target >> 8)
        return cpu, memory

    def test_a_native_interrupt_pushes_four_bytes(self) -> None:
        cpu, _ = self.machine(False, emu.IRQ_VECTOR)

        cpu.irq()

        self.assertEqual(cpu.s, 0x1FFB)

    def test_and_an_emulation_interrupt_pushes_three(self) -> None:
        cpu, _ = self.machine(True, emu.EMULATION_IRQ_VECTOR)

        cpu.irq()

        self.assertEqual(cpu.s, 0x01FC)

    def test_the_program_bank_goes_out_first_in_native_mode(self) -> None:
        cpu, memory = self.machine(False, emu.IRQ_VECTOR)

        cpu.irq()

        self.assertEqual(memory.read8(0x001FFF), 0x12)

    def test_the_return_address_is_the_instruction_that_would_have_run(self) -> None:
        cpu, memory = self.machine(False, emu.IRQ_VECTOR)

        cpu.irq()

        self.assertEqual((memory.read8(0x001FFE), memory.read8(0x001FFD)), (0x80, 0x00))

    def test_the_pushed_status_keeps_its_index_width_bit_in_native_mode(self) -> None:
        cpu, memory = self.machine(False, emu.IRQ_VECTOR)
        cpu.x8 = True

        cpu.irq()

        self.assertEqual(memory.read8(0x001FFC) & emu.BREAK_FLAG, emu.BREAK_FLAG)

    def test_and_clears_that_bit_in_emulation_mode(self) -> None:
        cpu, memory = self.machine(True, emu.EMULATION_IRQ_VECTOR)

        cpu.irq()

        self.assertEqual(memory.read8(0x0001FD) & emu.BREAK_FLAG, 0x00)

    def test_which_is_the_one_thing_that_separates_it_from_a_break(self) -> None:
        cpu, memory = self.machine(True, emu.EMULATION_BREAK_VECTOR)
        memory.write8(0x128000, 0x00)

        cpu.step()

        self.assertEqual(memory.read8(0x0001FD) & emu.BREAK_FLAG, emu.BREAK_FLAG)

    def test_the_program_bank_is_cleared_and_the_data_bank_is_not(self) -> None:
        cpu, _ = self.machine(False, emu.IRQ_VECTOR)

        cpu.irq()

        self.assertEqual((cpu.pb, cpu.db), (0x00, 0x7E))

    def test_the_handler_runs_in_binary_with_further_requests_disabled(self) -> None:
        cpu, _ = self.machine(False, emu.IRQ_VECTOR)
        cpu.decimal = True

        cpu.irq()

        self.assertEqual((cpu.decimal, cpu.irq_disable), (False, True))

    def test_a_request_is_refused_while_the_disable_flag_is_set(self) -> None:
        cpu, _ = self.machine(False, emu.IRQ_VECTOR)
        cpu.irq_disable = True

        self.assertFalse(cpu.irq())

    def test_the_non_maskable_pin_is_taken_anyway(self) -> None:
        cpu, _ = self.machine(False, emu.NMI_VECTOR, target=0x9100)
        cpu.irq_disable = True

        cpu.nmi()

        self.assertEqual(cpu.pc, 0x9100)

    def test_an_abort_is_taken_anyway_as_well(self) -> None:
        cpu, _ = self.machine(False, emu.ABORT_VECTOR, target=0x9200)
        cpu.irq_disable = True

        cpu.abort()

        self.assertEqual(cpu.pc, 0x9200)

    def test_each_pin_has_its_own_vector_in_each_mode(self) -> None:
        native = {kind: emu.NATIVE_VECTORS[kind] for kind in ("irq", "nmi", "abort")}
        emulated = {kind: emu.EMULATION_VECTORS[kind] for kind in ("irq", "nmi", "abort")}

        self.assertEqual(
            (native, emulated),
            (
                {"irq": 0x00FFEE, "nmi": 0x00FFEA, "abort": 0x00FFE8},
                {"irq": 0x00FFFE, "nmi": 0x00FFFA, "abort": 0x00FFF8},
            ),
        )

    def test_a_refused_request_still_ends_a_wait(self) -> None:
        cpu, _ = self.machine(False, emu.IRQ_VECTOR)
        cpu.irq_disable = True
        cpu.waiting = True

        taken = cpu.irq()

        self.assertEqual((taken, cpu.waiting), (False, False))

    def test_a_stopped_part_answers_nothing_at_all(self) -> None:
        cpu, _ = self.machine(False, emu.NMI_VECTOR)
        cpu.stopped = True

        self.assertEqual((cpu.nmi(), cpu.pc), (False, 0x8000))

    def test_a_return_from_interrupt_restores_the_program_bank_too(self) -> None:
        cpu, memory = self.machine(False, emu.IRQ_VECTOR)
        cpu.irq()
        memory.write8(0x009000, 0x40)

        cpu.step()

        self.assertEqual((cpu.pb, cpu.pc), (0x12, 0x8000))

    def test_and_in_emulation_mode_leaves_the_bank_where_it_was(self) -> None:
        cpu, memory = self.machine(True, emu.EMULATION_IRQ_VECTOR)
        cpu.pb = 0x00
        cpu.irq()
        memory.write8(0x009000, 0x40)

        cpu.step()

        self.assertEqual((cpu.pb, cpu.pc), (0x00, 0x8000))


class CycleShapeTest(unittest.TestCase):
    """What this part puts on the bus, including the cycles nothing answers.

    Every cycle here is checked as the recordings record one: the address, the
    value or the absence of one, and the eight output lines. A cycle with both
    address lines low is an internal cycle, and the manufacturer allows its
    address to be wrong, which is why it carries no value.
    """

    def trace(
        self,
        code: Sequence[int],
        emulation: bool = False,
        at: int = 0x8000,
        **registers: Any,
    ) -> list[Any]:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.emulation = emulation
        if not emulation:
            cpu.m8 = cpu.x8 = True
        cpu.pb, cpu.pc = 0x00, at
        cpu.s = 0x01FF
        cpu.a = cpu.x = cpu.y = 0x0000
        cpu.d = 0x0000
        cpu.db = 0x00
        for name, value in registers.items():
            setattr(cpu, name, value)
        for offset, byte in enumerate(code):
            memory.write8(at + offset, byte)
        cpu.trace = []
        cpu.step()
        return [(hex(address), value, pins) for address, value, pins in cpu.trace]

    def test_an_opcode_fetch_raises_both_address_lines(self) -> None:
        self.assertEqual(self.trace([0xEA])[0][2], "dp-r-mx-")

    def test_an_operand_read_raises_only_the_program_line(self) -> None:
        self.assertEqual(self.trace([0xA9, 0x11])[1][2], "-p-r-mx-")

    def test_a_data_read_raises_only_the_data_line(self) -> None:
        self.assertEqual(self.trace([0xA5, 0x40])[2][2], "d--r-mx-")

    def test_a_write_lowers_the_read_line(self) -> None:
        self.assertEqual(self.trace([0x85, 0x40])[2][2], "d--w-mx-")

    def test_an_internal_cycle_lowers_both_and_carries_no_value(self) -> None:
        held = self.trace([0xEA])[1]

        self.assertEqual((held[1], held[2]), (None, "---r-mx-"))

    def test_emulation_mode_shows_on_every_cycle(self) -> None:
        self.assertTrue(all(one[2][4] == "e" for one in self.trace([0xEA], emulation=True)))

    def test_the_width_bits_show_on_every_cycle(self) -> None:
        cpu_trace = self.trace([0xEA], m8=False, x8=False)

        self.assertTrue(all(one[2][5:7] == "--" for one in cpu_trace))

    def test_a_vector_read_lowers_the_pull_line(self) -> None:
        held = self.trace([0x00, 0x00])

        self.assertEqual([one[2] for one in held[-2:]], ["d-vr-mx-", "d-vr-mx-"])

    def test_a_read_modify_write_locks_memory_for_its_last_three_cycles(self) -> None:
        held = self.trace([0x06, 0x40])

        self.assertEqual([one[2][7] for one in held], ["-", "-", "l", "l", "l"])

    def test_and_for_five_when_the_accumulator_is_wide(self) -> None:
        held = self.trace([0x0E, 0x00, 0x20], m8=False)

        self.assertEqual([one[2][7] for one in held], ["-", "-", "-", "l", "l", "l", "l", "l"])

    def test_the_modify_cycle_carries_no_value_in_native_mode(self) -> None:
        held = self.trace([0x06, 0x40])

        self.assertEqual((held[3][1], held[3][2]), (None, "---r-mxl"))

    def test_and_carries_the_byte_it_read_in_emulation_mode(self) -> None:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.emulation = True
        cpu.pb, cpu.pc = 0x00, 0x8000
        memory.write8(0x008000, 0x06)
        memory.write8(0x008001, 0x40)
        memory.write8(0x000040, 0x21)
        cpu.trace = []

        cpu.step()

        self.assertEqual(cpu.trace[3], (0x000040, 0x21, "---wemxl"))

    def test_a_word_read_modify_write_writes_its_high_half_first(self) -> None:
        held = self.trace([0x0E, 0x00, 0x20], m8=False)

        self.assertEqual([one[0] for one in held[-2:]], ["0x2001", "0x2000"])

    def test_a_store_writes_its_low_half_first(self) -> None:
        held = self.trace([0x8D, 0x00, 0x20], m8=False)

        self.assertEqual([one[0] for one in held[-2:]], ["0x2000", "0x2001"])

    def test_a_reserved_opcode_steps_over_its_operand_without_reading_it(self) -> None:
        held = self.trace([0x42, 0x11])

        self.assertEqual((len(held), held[1][1], held[1][2]), (2, None, "---r-mx-"))

    def test_a_direct_page_that_is_not_aligned_costs_a_cycle(self) -> None:
        self.assertEqual(len(self.trace([0xA5, 0x40], d=0x1234)), 4)

    def test_and_costs_nothing_when_it_is_aligned(self) -> None:
        self.assertEqual(len(self.trace([0xA5, 0x40], d=0x1200)), 3)

    def test_a_sixteen_bit_index_always_costs_the_indexing_cycle(self) -> None:
        self.assertEqual(len(self.trace([0xBD, 0x00, 0x20], x8=False, x=0x0010)), 5)

    def test_an_eight_bit_index_costs_it_only_across_a_page(self) -> None:
        self.assertEqual(len(self.trace([0xBD, 0xF0, 0x20], x=0x20)), 5)

    def test_and_not_within_one(self) -> None:
        self.assertEqual(len(self.trace([0xBD, 0x00, 0x20], x=0x20)), 4)

    def test_a_store_pays_for_indexing_whatever_the_index_is(self) -> None:
        self.assertEqual(len(self.trace([0x9D, 0x00, 0x20], x=0x20)), 5)

    def test_setting_status_bits_takes_three_cycles(self) -> None:
        self.assertEqual(len(self.trace([0xE2, 0x30])), 3)

    def test_a_taken_branch_costs_a_cycle(self) -> None:
        self.assertEqual(len(self.trace([0x80, 0x10])), 3)

    def test_and_a_page_crossing_costs_another_only_in_emulation_mode(self) -> None:
        crossing = len(self.trace([0x80, 0x7F], emulation=True, at=0x80A0))

        self.assertEqual(crossing, 4)

    def test_which_native_mode_does_not_pay(self) -> None:
        cpu_trace = self.trace([0x80, 0x7F], at=0x80A0)

        self.assertEqual(len(cpu_trace), 3)

    def test_a_block_move_refetches_itself_for_every_byte(self) -> None:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.m8 = cpu.x8 = True
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.a, cpu.x, cpu.y = 0x0001, 0x0000, 0x0100
        for offset, byte in enumerate([0x54, 0x7E, 0x7F]):
            memory.write8(0x008000 + offset, byte)
        cpu.trace = []

        cpu.step()

        self.assertEqual([one[2] for one in cpu.trace[7:10]], ["dp-r-mx-", "-p-r-mx-", "-p-r-mx-"])

    def test_and_spends_two_cycles_after_each_byte_it_writes(self) -> None:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.m8 = cpu.x8 = True
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.a, cpu.x, cpu.y = 0x0000, 0x0000, 0x0100
        for offset, byte in enumerate([0x54, 0x7E, 0x7F]):
            memory.write8(0x008000 + offset, byte)
        cpu.trace = []

        cpu.step()

        self.assertEqual([one[2] for one in cpu.trace[-2:]], ["---r-mx-", "---r-mx-"])

    def test_a_move_cut_short_leaves_the_cycles_it_managed(self) -> None:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.m8 = cpu.x8 = True
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.a, cpu.x, cpu.y = 0x00FF, 0x0000, 0x0100
        cpu.cycle_budget = 11
        for offset, byte in enumerate([0x54, 0x7E, 0x7F]):
            memory.write8(0x008000 + offset, byte)
        cpu.trace = []

        cpu.step()

        self.assertEqual(len(cpu.trace), 11)

    def test_and_stops_before_the_write_of_the_byte_it_could_not_finish(self) -> None:
        memory = emu.Memory(0x1000000)
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.d = cpu.db = 0x00
        cpu.m8 = cpu.x8 = True
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.a, cpu.x, cpu.y = 0x00FF, 0x0000, 0x0100
        cpu.cycle_budget = 11
        for offset, byte in enumerate([0x54, 0x7E, 0x7F]):
            memory.write8(0x008000 + offset, byte)
        cpu.trace = []

        cpu.step()

        self.assertEqual([one[2] for one in cpu.trace[-2:]], ["-p-r-mx-", "d--r-mx-"])


class BoundedCallTest(unittest.TestCase):
    """That a routine which never returns gives up rather than hanging.

    `call` counts the calls it passes so it comes back at the right return, and
    a routine that never reaches one would otherwise run for as long as the
    process does. A caller driving a routine it did not write, which is what a
    patch harness does, wants the bound: a raised limit names where it stopped
    and a hang names nothing.
    """

    def spinning(self) -> Any:
        memory = FlatMemory()
        for offset, byte in enumerate((0x4C, 0x00, 0x80)):
            memory.cells[0x008000 + offset] = byte
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        return cpu

    def test_a_routine_that_never_returns_gives_up_at_the_bound(self) -> None:
        with self.assertRaises(emu.RunLimit):
            self.spinning().call(0x008000, limit=64)

    def test_and_says_how_far_it_got(self) -> None:
        with self.assertRaises(emu.RunLimit) as raised:
            self.spinning().call(0x008000, limit=64)

        self.assertIn("64 instructions", str(raised.exception))

    def test_a_bound_the_routine_reaches_leaves_the_registers_it_set(self) -> None:
        memory = FlatMemory()
        for offset, byte in enumerate((0xE8, 0xE8, 0x60)):
            memory.cells[0x008000 + offset] = byte
        cpu = emu.Cpu(memory)
        cpu.emulation = False
        cpu.x = 0x0000

        cpu.call(0x008000, limit=64)

        self.assertEqual(cpu.x, 0x02)


if __name__ == "__main__":
    unittest.main(verbosity=2)
