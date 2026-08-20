from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import SparseMemory, mos6502, opcodes6502


def machine(
    program: Sequence[int], at: int = 0x8000, decimal: bool = True, **registers: Any
) -> Any:
    memory = SparseMemory(seed=1)
    for offset, value in enumerate(program):
        memory.write8(at + offset, value)
    cpu = mos6502.Cpu(memory, decimal=decimal, reset=False)
    cpu.set_status(0x24)
    cpu.a = cpu.x = cpu.y = 0x00
    cpu.s = 0xFD
    cpu.pc = at
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu, memory


class ResetTest(unittest.TestCase):
    def test_a_reset_takes_the_program_counter_from_the_vector(self) -> None:
        memory = SparseMemory(seed=2)
        memory.write8(0xFFFC, 0x34)
        memory.write8(0xFFFD, 0x12)

        cpu = mos6502.Cpu(memory)

        self.assertEqual(cpu.pc, 0x1234)

    def test_a_reset_leaves_the_registers_holding_what_they_held(self) -> None:
        memory = SparseMemory(seed=3)

        first = mos6502.Cpu(memory, seed=7)
        second = mos6502.Cpu(memory, seed=8)

        self.assertNotEqual((first.a, first.x, first.y), (second.a, second.x, second.y))

    def test_the_same_seed_gives_the_same_unclean_machine(self) -> None:
        memory = SparseMemory(seed=3)

        first = mos6502.Cpu(memory, seed=9)
        second = mos6502.Cpu(memory, seed=9)

        self.assertEqual((first.a, first.x, first.y), (second.a, second.x, second.y))


class StatusTest(unittest.TestCase):
    def test_the_unused_bit_is_always_set(self) -> None:
        cpu, _ = machine([0xEA])

        self.assertTrue(cpu.status() & 0x20)

    def test_the_break_bit_is_kept_when_nothing_touches_it(self) -> None:
        cpu, _ = machine([0xEA])
        cpu.set_status(0xFF)

        cpu.step()

        self.assertTrue(cpu.status() & 0x10)

    def test_pulling_the_status_always_clears_the_break_bit(self) -> None:
        cpu, memory = machine([0x28], s=0xFC)
        memory.write8(0x01FD, 0xFF)

        cpu.step()

        self.assertFalse(cpu.status() & 0x10)

    def test_pushing_the_status_sets_the_break_bit(self) -> None:
        cpu, memory = machine([0x08])
        cpu.step()

        self.assertEqual(memory.read8(0x01FD), cpu.status() | 0x10)

    def test_pulling_the_status_takes_every_other_bit_as_given(self) -> None:
        cpu, memory = machine([0x28], s=0xFC)
        memory.write8(0x01FD, 0xCF)

        cpu.step()

        self.assertEqual(cpu.status(), 0xEF)


class AddressingTest(unittest.TestCase):
    def test_a_zero_page_index_wraps_inside_the_first_page(self) -> None:
        cpu, memory = machine([0xB5, 0xFF], x=0x02)
        memory.write8(0x0001, 0x42)

        cpu.step()

        self.assertEqual(cpu.a, 0x42)

    def test_an_absolute_index_does_not_wrap_inside_a_page(self) -> None:
        cpu, memory = machine([0xBD, 0xFF, 0x20], x=0x02)
        memory.write8(0x2101, 0x42)

        cpu.step()

        self.assertEqual(cpu.a, 0x42)

    def test_an_indexed_indirect_pointer_wraps_inside_the_first_page(self) -> None:
        cpu, memory = machine([0xA1, 0xFF], x=0x00)
        memory.write8(0x00FF, 0x34)
        memory.write8(0x0000, 0x12)
        memory.write8(0x1234, 0x42)

        cpu.step()

        self.assertEqual(cpu.a, 0x42)

    def test_an_indirect_indexed_pointer_wraps_the_same_way(self) -> None:
        cpu, memory = machine([0xB1, 0xFF], y=0x01)
        memory.write8(0x00FF, 0x34)
        memory.write8(0x0000, 0x12)
        memory.write8(0x1235, 0x42)

        cpu.step()

        self.assertEqual(cpu.a, 0x42)

    def test_a_jump_through_a_pointer_at_a_page_end_reads_the_wrong_high_byte(self) -> None:
        cpu, memory = machine([0x6C, 0xFF, 0x30])
        memory.write8(0x30FF, 0x34)
        memory.write8(0x3100, 0xAB)
        memory.write8(0x3000, 0x12)

        cpu.step()

        self.assertEqual(cpu.pc, 0x1234)


class SubroutineTest(unittest.TestCase):
    def test_a_call_pushes_the_address_of_its_own_last_byte(self) -> None:
        cpu, memory = machine([0x20, 0x55, 0x13], s=0xFD)

        cpu.step()

        self.assertEqual(cpu.pc, 0x1355)
        self.assertEqual(memory.read8(0x01FD), 0x80)
        self.assertEqual(memory.read8(0x01FC), 0x02)

    def test_a_call_whose_push_lands_on_its_own_operand_jumps_where_the_push_left_it(self) -> None:
        cpu, memory = machine([0x20, 0x55, 0x13], at=0x017B, s=0x7D)

        cpu.step()

        self.assertEqual(memory.read8(0x017D), 0x01)
        self.assertEqual(memory.read8(0x017C), 0x7D)
        self.assertEqual(cpu.pc, 0x0155)

    def test_a_return_goes_to_the_byte_after_the_call(self) -> None:
        cpu, memory = machine([0x60], s=0xFB)
        memory.write8(0x01FC, 0x02)
        memory.write8(0x01FD, 0x80)

        cpu.step()

        self.assertEqual(cpu.pc, 0x8003)


class StackTest(unittest.TestCase):
    def test_the_stack_pointer_wraps_inside_its_page(self) -> None:
        cpu, memory = machine([0x48], s=0x00)

        cpu.step()

        self.assertEqual(cpu.s, 0xFF)
        self.assertEqual(memory.read8(0x0100), cpu.a)

    def test_a_pull_wraps_the_same_way(self) -> None:
        cpu, memory = machine([0x68], s=0xFF)
        memory.write8(0x0100, 0x42)

        cpu.step()

        self.assertEqual(cpu.s, 0x00)
        self.assertEqual(cpu.a, 0x42)


class ArithmeticTest(unittest.TestCase):
    def test_an_add_sets_carry_when_it_leaves_the_byte(self) -> None:
        cpu, _ = machine([0x69, 0x01], a=0xFF)

        cpu.step()

        self.assertEqual(cpu.a, 0x00)
        self.assertTrue(cpu.c)
        self.assertTrue(cpu.z)

    def test_an_add_sets_overflow_when_two_positives_make_a_negative(self) -> None:
        cpu, _ = machine([0x69, 0x50], a=0x50)

        cpu.step()

        self.assertEqual(cpu.a, 0xA0)
        self.assertTrue(cpu.v)

    def test_a_decimal_add_carries_at_ten_rather_than_sixteen(self) -> None:
        cpu, _ = machine([0x69, 0x01], a=0x09)
        cpu.d = True

        cpu.step()

        self.assertEqual(cpu.a, 0x10)

    def test_a_part_with_no_decimal_mode_adds_in_binary_regardless(self) -> None:
        cpu, _ = machine([0x69, 0x01], a=0x09, decimal=False)
        cpu.d = True

        cpu.step()

        self.assertEqual(cpu.a, 0x0A)

    def test_a_decimal_subtract_borrows_at_ten(self) -> None:
        cpu, _ = machine([0xE9, 0x01], a=0x10)
        cpu.d = True
        cpu.c = True

        cpu.step()

        self.assertEqual(cpu.a, 0x09)


class UndocumentedTest(unittest.TestCase):
    def test_the_shift_and_or_does_both(self) -> None:
        cpu, memory = machine([0x07, 0x10], a=0x01)
        memory.write8(0x0010, 0x40)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0x80)
        self.assertEqual(cpu.a, 0x81)

    def test_the_store_of_both_registers_stores_their_conjunction(self) -> None:
        cpu, memory = machine([0x87, 0x10], a=0xF0, x=0x3C)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0x30)

    def test_the_load_of_both_registers_loads_both(self) -> None:
        cpu, memory = machine([0xA7, 0x10])
        memory.write8(0x0010, 0x42)

        cpu.step()

        self.assertEqual((cpu.a, cpu.x), (0x42, 0x42))

    def test_the_unstable_transfer_uses_the_magic_the_suite_measured(self) -> None:
        cpu, _ = machine([0x8B, 0x23], a=0xE4, x=0xE2)

        cpu.step()

        self.assertEqual(cpu.a, 0x22)

    def test_a_jam_stops_the_processor_where_it_stands(self) -> None:
        cpu, _ = machine([0x02])

        cpu.step()

        self.assertEqual(cpu.pc, 0x8001)
        self.assertTrue(cpu.stopped)

    def test_a_stopped_processor_refuses_to_step_again(self) -> None:
        cpu, _ = machine([0x02])
        cpu.step()

        with self.assertRaises(mos6502.Stopped):
            cpu.step()


class BranchTest(unittest.TestCase):
    def test_a_branch_not_taken_only_costs_its_operand(self) -> None:
        cpu, _ = machine([0xD0, 0x10])
        cpu.z = True

        cpu.step()

        self.assertEqual(cpu.pc, 0x8002)

    def test_a_branch_taken_goes_where_it_says(self) -> None:
        cpu, _ = machine([0xD0, 0x10])
        cpu.z = False

        cpu.step()

        self.assertEqual(cpu.pc, 0x8012)

    def test_a_backward_branch_is_signed(self) -> None:
        cpu, _ = machine([0xD0, 0xFC])
        cpu.z = False

        cpu.step()

        self.assertEqual(cpu.pc, 0x7FFE)


class InterruptTest(unittest.TestCase):
    def test_a_break_goes_through_the_vector_and_pushes_the_break_bit(self) -> None:
        cpu, memory = machine([0x00, 0x00])
        memory.write8(0xFFFE, 0x34)
        memory.write8(0xFFFF, 0x12)
        before = cpu.status()

        cpu.step()

        self.assertEqual(cpu.pc, 0x1234)
        self.assertEqual(memory.read8(0x01FB), before | 0x10)
        self.assertTrue(cpu.i)

    def test_a_break_pushes_the_address_after_its_padding_byte(self) -> None:
        cpu, memory = machine([0x00, 0x00])
        memory.write8(0xFFFE, 0x00)
        memory.write8(0xFFFF, 0x90)

        cpu.step()

        self.assertEqual(memory.read8(0x01FD), 0x80)
        self.assertEqual(memory.read8(0x01FC), 0x02)


class LimitTest(unittest.TestCase):
    def test_a_run_that_never_ends_is_stopped_rather_than_hanging(self) -> None:
        cpu, _ = machine([0x4C, 0x00, 0x80])
        cpu.step_limit = 100

        with self.assertRaises(mos6502.StepLimit):
            cpu.run_until(lambda _: False)


class EveryOpcodeTest(unittest.TestCase):
    STATES = (
        ("binary, carry clear", {"d": False, "c": False, "decimal": True}),
        ("binary, carry set", {"d": False, "c": True, "decimal": True}),
        ("decimal, carry clear", {"d": True, "c": False, "decimal": True}),
        ("decimal, carry set", {"d": True, "c": True, "decimal": True}),
        ("decimal flag on a part without one", {"d": True, "c": True, "decimal": False}),
    )

    def machine(self, opcode: int, state: Any) -> Any:
        memory = SparseMemory(seed=opcode)
        cpu = mos6502.Cpu(memory, reset=False, decimal=state["decimal"])
        cpu.set_status(0x24)
        cpu.d, cpu.c = state["d"], state["c"]
        cpu.a, cpu.x, cpu.y = 0x9C, 0x5A, 0xA5
        cpu.s = 0xFD
        cpu.pc = 0x8000
        memory.write8(0x8000, opcode)
        return cpu

    def test_every_opcode_runs_in_every_state(self) -> None:
        for opcode in range(256):
            for name, state in self.STATES:
                cpu = self.machine(opcode, state)
                with self.subTest(opcode=f"${opcode:02X}", state=name):
                    cpu.step()
                    self.assertEqual(cpu.steps, 1)

    def test_every_opcode_has_an_implementation_behind_it(self) -> None:
        missing = [
            f"${opcode:02X} {mnemonic}"
            for opcode, (mnemonic, _) in enumerate(opcodes6502.NMOS)
            if not hasattr(mos6502.Cpu, f"op_{mnemonic}")
        ]

        self.assertEqual(missing, [])

    def test_a_mode_no_instruction_uses_is_refused_rather_than_guessed(self) -> None:
        cpu, _ = machine([0xEA])

        with self.assertRaises(mos6502.UnsupportedError):
            cpu.effective("nonsense")

    def test_an_opcode_with_no_handler_is_refused_rather_than_skipped(self) -> None:
        cpu, _ = machine([0x00])
        cpu.table = tuple([("nonsense", "implied")] * 256)

        with self.assertRaises(mos6502.UnsupportedError):
            cpu.step()


class ReachTest(unittest.TestCase):
    def test_a_routine_runs_until_it_returns(self) -> None:
        cpu, _ = machine([0xE8, 0xE8, 0x60])

        cpu.call(0x8000)

        self.assertEqual(cpu.x, 0x02)

    def test_a_nested_call_returns_to_the_outer_one(self) -> None:
        cpu, memory = machine([0x20, 0x10, 0x80, 0xE8, 0x60])
        for offset, value in enumerate([0xC8, 0x60]):
            memory.write8(0x8010 + offset, value)

        cpu.call(0x8000)

        self.assertEqual((cpu.x, cpu.y), (0x01, 0x01))

    def test_running_until_a_condition_stops_when_it_holds(self) -> None:
        cpu, _ = machine([0xE8, 0xE8, 0xE8, 0xE8])

        cpu.run_until(lambda found: found.x >= 0x03)

        self.assertEqual(cpu.x, 0x03)

    def test_an_accumulator_operand_is_the_accumulator(self) -> None:
        cpu, _ = machine([0xEA], a=0x42)

        self.assertEqual(cpu.operand("accumulator"), 0x42)

    def test_a_decimal_add_whose_low_nibble_stays_below_ten_does_not_adjust_it(self) -> None:
        cpu, _ = machine([0x69, 0x03], a=0x04)
        cpu.d = True

        cpu.step()

        self.assertEqual(cpu.a, 0x07)

    def test_a_decimal_rotate_adjusts_both_halves_when_both_run_over(self) -> None:
        cpu, _ = machine([0x6B, 0xFF], a=0xFF)
        cpu.d = True
        cpu.c = True

        cpu.step()

        self.assertTrue(cpu.c)

    def test_a_decimal_rotate_leaves_the_carry_clear_when_the_high_half_does_not(self) -> None:
        cpu, _ = machine([0x6B, 0x00], a=0x00)
        cpu.d = True
        cpu.c = False

        cpu.step()

        self.assertFalse(cpu.c)

    def test_a_zero_page_indirect_reads_a_pointer_without_indexing(self) -> None:
        cpu, memory = machine([0xEA])
        memory.write8(0x0020, 0x34)
        memory.write8(0x0021, 0x12)
        memory.write8(0x8001, 0x20)
        cpu.pc = 0x8001

        self.assertEqual(cpu.effective("zeroPageIndirect"), 0x1234)


if __name__ == "__main__":
    unittest.main()
