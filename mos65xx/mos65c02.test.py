from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from typing import Any

from mos65xx import SparseMemory, errors, mos65c02, mos6502, opcodes65c02


def machine(
    program: Sequence[int], at: int = 0x8000, table: Any = opcodes65c02.CMOS, **registers: Any
) -> Any:
    memory = SparseMemory(seed=1)
    for offset, value in enumerate(program):
        memory.write8(at + offset, value)
    cpu = mos65c02.Cpu(memory, table=table)
    cpu.set_status(0x24)
    cpu.a = cpu.x = cpu.y = 0x00
    cpu.s = 0xFD
    cpu.pc = at
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu, memory


class FixedBugTest(unittest.TestCase):
    def test_a_jump_through_a_pointer_at_a_page_end_reads_the_right_high_byte(self) -> None:
        cpu, memory = machine([0x6C, 0xFF, 0x30])
        memory.write8(0x30FF, 0x34)
        memory.write8(0x3100, 0x12)
        memory.write8(0x3000, 0xAB)

        cpu.step()

        self.assertEqual(cpu.pc, 0x1234)

    def test_a_break_clears_the_decimal_flag(self) -> None:
        cpu, memory = machine([0x00, 0x00])
        cpu.d = True
        memory.write8(0xFFFE, 0x00)
        memory.write8(0xFFFF, 0x90)

        cpu.step()

        self.assertFalse(cpu.d)

    def test_a_decimal_add_sets_the_sign_from_the_decimal_result(self) -> None:
        cpu, _ = machine([0x69, 0x01], a=0x79)
        cpu.d = True

        cpu.step()

        self.assertEqual(cpu.a, 0x80)
        self.assertTrue(cpu.n)
        self.assertFalse(cpu.z)

    def test_a_decimal_add_that_reaches_zero_says_so(self) -> None:
        cpu, _ = machine([0x69, 0x01], a=0x99)
        cpu.d = True

        cpu.step()

        self.assertEqual(cpu.a, 0x00)
        self.assertTrue(cpu.z)
        self.assertTrue(cpu.c)

    def test_a_decimal_subtract_of_an_operand_that_is_not_a_decimal_number(self) -> None:
        """Where the two parts genuinely disagree about the answer, not the flags.

        Nothing stops a program subtracting a byte whose nibbles are not digits.
        The older part borrows out of the low digit into the high one; this part
        subtracts in binary and corrects afterwards. Given `$FC` they differ by a
        whole digit, and the suite says this part is the one that produces `$AE`.
        """

        cpu, _ = machine([0xE9, 0xFC], a=0x10)
        cpu.d = True
        cpu.c = True

        cpu.step()

        self.assertEqual(cpu.a, 0xAE)

    def test_a_decimal_subtract_sets_the_sign_from_the_decimal_result(self) -> None:
        cpu, _ = machine([0xE9, 0x01], a=0x00)
        cpu.d = True
        cpu.c = True

        cpu.step()

        self.assertEqual(cpu.a, 0x99)
        self.assertTrue(cpu.n)


class DecimalEdgeTest(unittest.TestCase):
    def test_a_decimal_add_whose_low_digit_stays_a_digit_does_not_correct_it(self) -> None:
        cpu, _ = machine([0x69, 0x02], a=0x03)
        cpu.d = True

        cpu.step()

        self.assertEqual(cpu.a, 0x05)

    def test_a_decimal_subtract_that_stays_above_zero_takes_no_sixty(self) -> None:
        cpu, _ = machine([0xE9, 0x01], a=0x50)
        cpu.d = True
        cpu.c = True

        cpu.step()

        self.assertEqual(cpu.a, 0x49)
        self.assertTrue(cpu.c)

    def test_a_decimal_subtract_whose_low_digit_covers_it_takes_no_six(self) -> None:
        cpu, _ = machine([0xE9, 0x01], a=0x09)
        cpu.d = True
        cpu.c = True

        cpu.step()

        self.assertEqual(cpu.a, 0x08)


class NewInstructionTest(unittest.TestCase):
    def test_a_branch_that_always_takes_always_takes(self) -> None:
        cpu, _ = machine([0x80, 0x10])

        cpu.step()

        self.assertEqual(cpu.pc, 0x8012)

    def test_a_store_of_zero_stores_zero(self) -> None:
        cpu, memory = machine([0x64, 0x10])
        memory.write8(0x0010, 0xFF)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0x00)

    def test_a_test_and_set_sets_the_bits_and_reports_the_old_ones(self) -> None:
        cpu, memory = machine([0x04, 0x10], a=0x0F)
        memory.write8(0x0010, 0xF0)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0xFF)
        self.assertTrue(cpu.z)

    def test_a_test_and_clear_clears_them(self) -> None:
        cpu, memory = machine([0x14, 0x10], a=0x0F)
        memory.write8(0x0010, 0xFF)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0xF0)
        self.assertFalse(cpu.z)

    def test_the_index_registers_can_be_pushed_and_pulled(self) -> None:
        cpu, _ = machine([0xDA, 0x5A, 0x7A, 0xFA], x=0x11, y=0x22)

        for _ in range(4):
            cpu.step()

        self.assertEqual((cpu.x, cpu.y), (0x11, 0x22))

    def test_pulling_them_in_the_other_order_swaps_them(self) -> None:
        cpu, _ = machine([0xDA, 0x5A, 0xFA, 0x7A], x=0x11, y=0x22)

        for _ in range(4):
            cpu.step()

        self.assertEqual((cpu.x, cpu.y), (0x22, 0x11))

    def test_the_accumulator_can_be_incremented_on_its_own(self) -> None:
        cpu, _ = machine([0x1A], a=0x41)

        cpu.step()

        self.assertEqual(cpu.a, 0x42)

    def test_and_decremented(self) -> None:
        cpu, _ = machine([0x3A], a=0x43)

        cpu.step()

        self.assertEqual(cpu.a, 0x42)

    def test_a_pointer_with_no_index_reaches_where_it_points(self) -> None:
        cpu, memory = machine([0xB2, 0x20])
        memory.write8(0x0020, 0x34)
        memory.write8(0x0021, 0x12)
        memory.write8(0x1234, 0x42)

        cpu.step()

        self.assertEqual(cpu.a, 0x42)

    def test_an_indexed_jump_through_a_pointer_goes_where_the_index_lands(self) -> None:
        cpu, memory = machine([0x7C, 0x00, 0x30], x=0x04)
        memory.write8(0x3004, 0x34)
        memory.write8(0x3005, 0x12)

        cpu.step()

        self.assertEqual(cpu.pc, 0x1234)

    def test_an_immediate_bit_test_only_reports_whether_anything_matched(self) -> None:
        cpu, _ = machine([0x89, 0x0F], a=0xF0)
        cpu.n = cpu.v = False

        cpu.step()

        self.assertTrue(cpu.z)
        self.assertFalse(cpu.n)
        self.assertFalse(cpu.v)

    def test_a_bit_test_against_memory_still_reports_its_two_top_bits(self) -> None:
        cpu, memory = machine([0x34, 0x10], a=0xFF, x=0x00)
        memory.write8(0x0010, 0xC0)

        cpu.step()

        self.assertTrue(cpu.n)
        self.assertTrue(cpu.v)

    def test_a_no_operation_of_stated_length_consumes_exactly_that(self) -> None:
        for opcode, length in ((0x03, 1), (0x02, 2), (0x0F, 3)):
            cpu, _ = machine([opcode, 0x00, 0x00])

            cpu.step()

            self.assertEqual(cpu.pc, 0x8000 + length, f"{opcode:02X}")


class RockwellTest(unittest.TestCase):
    def test_a_bit_can_be_cleared_in_the_first_page(self) -> None:
        cpu, memory = machine([0x07, 0x10], table=opcodes65c02.ROCKWELL)
        memory.write8(0x0010, 0xFF)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0xFE)

    def test_a_bit_can_be_set_there(self) -> None:
        cpu, memory = machine([0x87, 0x10], table=opcodes65c02.ROCKWELL)
        memory.write8(0x0010, 0x00)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0x01)

    def test_each_of_the_eight_reaches_its_own_bit(self) -> None:
        for bit in range(8):
            cpu, memory = machine([0x87 + bit * 0x10, 0x10], table=opcodes65c02.ROCKWELL)
            memory.write8(0x0010, 0x00)

            cpu.step()

            self.assertEqual(memory.read8(0x0010), 1 << bit, f"bit {bit}")

    def test_a_branch_on_a_clear_bit_takes_when_it_is_clear(self) -> None:
        cpu, memory = machine([0x0F, 0x10, 0x20], table=opcodes65c02.ROCKWELL)
        memory.write8(0x0010, 0xFE)

        cpu.step()

        self.assertEqual(cpu.pc, 0x8023)

    def test_and_does_not_when_it_is_set(self) -> None:
        cpu, memory = machine([0x0F, 0x10, 0x20], table=opcodes65c02.ROCKWELL)
        memory.write8(0x0010, 0xFF)

        cpu.step()

        self.assertEqual(cpu.pc, 0x8003)

    def test_a_branch_on_a_set_bit_is_the_other_way_round(self) -> None:
        cpu, memory = machine([0x8F, 0x10, 0x20], table=opcodes65c02.ROCKWELL)
        memory.write8(0x0010, 0x01)

        cpu.step()

        self.assertEqual(cpu.pc, 0x8023)

    def test_the_base_part_treats_the_same_byte_as_doing_nothing(self) -> None:
        cpu, memory = machine([0x07, 0x10])
        memory.write8(0x0010, 0xFF)

        cpu.step()

        self.assertEqual(memory.read8(0x0010), 0xFF)
        self.assertEqual(cpu.pc, 0x8002)


class WdcTest(unittest.TestCase):
    def test_the_processor_can_be_stopped(self) -> None:
        cpu, _ = machine([0xDB], table=opcodes65c02.WDC)

        cpu.step()

        self.assertTrue(cpu.stopped)

    def test_the_processor_can_be_made_to_wait(self) -> None:
        cpu, _ = machine([0xCB], table=opcodes65c02.WDC)

        cpu.step()

        self.assertTrue(cpu.waiting)

    def test_waiting_is_not_stopping(self) -> None:
        cpu, _ = machine([0xCB], table=opcodes65c02.WDC)

        cpu.step()

        self.assertFalse(cpu.stopped)

    def test_a_waiting_part_will_not_run_the_next_instruction(self) -> None:
        cpu, _ = machine([0xCB, 0xA9, 0x77], table=opcodes65c02.WDC)
        cpu.step()

        with self.assertRaises(errors.Waiting):
            cpu.step()

    def test_a_waiting_part_is_held_rather_than_finished(self) -> None:
        cpu, _ = machine([0xCB], table=opcodes65c02.WDC)

        cpu.step()

        self.assertTrue(cpu.held())

    def test_a_stopped_part_is_held_too(self) -> None:
        cpu, _ = machine([0xDB], table=opcodes65c02.WDC)

        cpu.step()

        self.assertTrue(cpu.held())

    def test_a_running_part_is_not_held(self) -> None:
        cpu, _ = machine([0xEA], table=opcodes65c02.WDC)

        cpu.step()

        self.assertFalse(cpu.held())

    def test_a_held_part_still_spends_its_hosts_cycles(self) -> None:
        cpu, _ = machine([0xCB], table=opcodes65c02.WDC)
        cpu.step()
        before = cpu.cycles

        spent = cpu.run_for(20)

        self.assertEqual((spent, cpu.cycles - before), (20, 20))

    def test_an_interrupt_releases_a_waiting_part(self) -> None:
        cpu, _ = machine([0xCB], table=opcodes65c02.WDC)
        cpu.step()

        cpu.irq()

        self.assertFalse(cpu.waiting)

    def test_the_earlier_parts_do_nothing_with_the_same_bytes(self) -> None:
        cpu, _ = machine([0xDB, 0x00], table=opcodes65c02.ROCKWELL)

        cpu.step()

        self.assertFalse(cpu.stopped)
        self.assertEqual(cpu.pc, 0x8002)


class EveryOpcodeTest(unittest.TestCase):
    def test_every_opcode_of_every_part_runs(self) -> None:
        for name, table in opcodes65c02.TABLES.items():
            for opcode in range(256):
                memory = SparseMemory(seed=opcode)
                cpu = mos65c02.Cpu(memory, table=table)
                cpu.set_status(0x24)
                cpu.a, cpu.x, cpu.y, cpu.s, cpu.pc = 0x9C, 0x5A, 0xA5, 0xFD, 0x8000
                memory.write8(0x8000, opcode)
                with self.subTest(part=name, opcode=f"${opcode:02X}"):
                    cpu.step()
                    self.assertEqual(cpu.steps, 1)

    def test_every_opcode_of_every_part_has_an_implementation(self) -> None:
        for name, table in opcodes65c02.TABLES.items():
            missing = [
                f"${opcode:02X} {mnemonic}"
                for opcode, (mnemonic, _) in enumerate(table)
                if not hasattr(mos65c02.Cpu, f"op_{mnemonic}")
            ]

            self.assertEqual(missing, [], name)


class HardwareInterruptTest(unittest.TestCase):
    """What this part does differently when a pin goes low."""

    def vectored(self, vector: int, target: int = 0x9000) -> Any:
        cpu, memory = machine([0xEA])
        memory.write8(vector, target & 0xFF)
        memory.write8(vector + 1, target >> 8)
        return cpu, memory

    def test_decimal_mode_is_cleared_on_the_way_in(self) -> None:
        cpu, _ = self.vectored(0xFFFE)
        cpu.i = False
        cpu.d = True

        cpu.irq()

        self.assertFalse(cpu.d)

    def test_which_the_older_part_does_not_do(self) -> None:
        older, memory = machine([0xEA])
        memory.write8(0xFFFE, 0x00)
        memory.write8(0xFFFF, 0x90)
        older.i = False
        older.d = True

        mos6502.Cpu.interrupt(older, 0xFFFE)

        self.assertTrue(older.d)

    def test_a_wait_ends_even_when_the_request_is_refused(self) -> None:
        cpu, _ = self.vectored(0xFFFE)
        cpu.i = True
        cpu.waiting = True

        taken = cpu.irq()

        self.assertEqual((taken, cpu.waiting), (False, False))

    def test_and_the_next_instruction_is_where_execution_carries_on(self) -> None:
        cpu, _ = self.vectored(0xFFFE)
        cpu.i = True
        cpu.waiting = True

        cpu.irq()

        self.assertEqual(cpu.pc, 0x8000)

    def test_a_wait_ends_on_the_non_maskable_pin_too(self) -> None:
        cpu, _ = self.vectored(0xFFFA, target=0x9100)
        cpu.waiting = True

        cpu.nmi()

        self.assertEqual((cpu.waiting, cpu.pc), (False, 0x9100))

    def test_an_accepted_request_still_reaches_its_handler(self) -> None:
        cpu, _ = self.vectored(0xFFFE)
        cpu.i = False
        cpu.waiting = True

        self.assertTrue(cpu.irq())


class CycleShapeTest(unittest.TestCase):
    """The spare cycles this part spends where the older one spends others."""

    def trace(self, program: Sequence[int], at: int = 0x8000, **registers: Any) -> list[Any]:
        cpu, _ = machine(program, at=at, **registers)
        cpu.trace = []
        cpu.step()
        return [(hex(address), kind) for address, _, kind in cpu.trace]

    def test_a_read_modify_write_reads_twice_and_writes_once(self) -> None:
        self.assertEqual(
            self.trace([0xE6, 0x40]),
            [
                ("0x8000", "read"),
                ("0x8001", "read"),
                ("0x40", "read"),
                ("0x40", "read"),
                ("0x40", "write"),
            ],
        )

    def test_an_indexed_store_re_reads_the_last_byte_of_the_instruction(self) -> None:
        self.assertEqual(
            self.trace([0x9D, 0x00, 0x20], x=0x10),
            [
                ("0x8000", "read"),
                ("0x8001", "read"),
                ("0x8002", "read"),
                ("0x8002", "read"),
                ("0x2010", "write"),
            ],
        )

    def test_a_shift_of_an_indexed_absolute_pays_nothing_extra_inside_a_page(self) -> None:
        self.assertEqual(len(self.trace([0x1E, 0x00, 0x20], x=0x10)), 6)

    def test_and_pays_when_the_index_crosses_one(self) -> None:
        self.assertEqual(len(self.trace([0x1E, 0xF0, 0x20], x=0x20)), 7)

    def test_an_increment_of_the_same_address_always_pays(self) -> None:
        self.assertEqual(len(self.trace([0xFE, 0x00, 0x20], x=0x10)), 7)

    def test_decimal_arithmetic_costs_a_cycle_that_reads_the_operand_again(self) -> None:
        self.assertEqual(
            self.trace([0x65, 0x40], d=True),
            [("0x8000", "read"), ("0x8001", "read"), ("0x40", "read"), ("0x40", "read")],
        )

    def test_and_costs_it_with_an_immediate_operand_too(self) -> None:
        self.assertEqual(len(self.trace([0x69, 0x11], d=True)), 3)

    def test_but_nothing_when_decimal_is_clear(self) -> None:
        self.assertEqual(len(self.trace([0x69, 0x11])), 2)

    def test_the_same_holds_for_subtraction(self) -> None:
        self.assertEqual(len(self.trace([0xE5, 0x40], d=True)), 4)

    def test_an_undocumented_single_byte_opcode_is_one_cycle(self) -> None:
        self.assertEqual(self.trace([0x03]), [("0x8000", "read")])

    def test_the_documented_no_operation_is_still_two(self) -> None:
        self.assertEqual(len(self.trace([0xEA])), 2)

    def test_an_indirect_jump_reads_the_address_the_older_part_would_have_used(self) -> None:
        cpu, memory = machine([0x6C, 0xFF, 0x30])
        memory.write8(0x30FF, 0x34)
        memory.write8(0x3000, 0xEE)
        memory.write8(0x3100, 0x12)
        cpu.trace = []

        cpu.step()

        self.assertEqual(
            [hex(address) for address, _, _ in cpu.trace],
            ["0x8000", "0x8001", "0x8002", "0x30ff", "0x3000", "0x3100"],
        )

    def test_and_still_arrives_at_the_corrected_destination(self) -> None:
        cpu, memory = machine([0x6C, 0xFF, 0x30])
        memory.write8(0x30FF, 0x34)
        memory.write8(0x3000, 0xEE)
        memory.write8(0x3100, 0x12)

        cpu.step()

        self.assertEqual(cpu.pc, 0x1234)

    def test_an_indexed_indirect_jump_re_reads_the_operand_low_byte(self) -> None:
        self.assertEqual(
            [one[0] for one in self.trace([0x7C, 0x00, 0x30], x=0x02)],
            ["0x8000", "0x8001", "0x8002", "0x8001", "0x3002", "0x3003"],
        )

    def test_a_pull_of_an_index_register_reads_the_slot_below_first(self) -> None:
        self.assertEqual(
            [one[0] for one in self.trace([0xFA], s=0x40)],
            ["0x8000", "0x8001", "0x140", "0x141"],
        )

    def test_a_bit_branch_reads_its_page_zero_address_twice(self) -> None:
        self.assertEqual(
            [one[0] for one in self.trace([0x0F, 0x40, 0x10], table=opcodes65c02.TABLES["wdc"])],
            ["0x8000", "0x8001", "0x40", "0x40", "0x8002"],
        )

    def test_and_spends_its_taken_cycle_on_the_byte_after_itself(self) -> None:
        cpu, memory = machine([0x8F, 0x40, 0x10], table=opcodes65c02.TABLES["wdc"])
        memory.write8(0x0040, 0x01)
        cpu.trace = []

        cpu.step()

        self.assertEqual(
            [hex(address) for address, _, _ in cpu.trace],
            ["0x8000", "0x8001", "0x40", "0x40", "0x8002", "0x8003"],
        )

    def test_an_undocumented_indexed_opcode_reads_the_address_it_names(self) -> None:
        self.assertEqual(
            [one[0] for one in self.trace([0x54, 0x40], x=0x02)],
            ["0x8000", "0x8001", "0x40", "0x42"],
        )

    def test_an_undocumented_three_byte_opcode_reads_neither_of_its_operands(self) -> None:
        self.assertEqual(
            [one[0] for one in self.trace([0x0F, 0x40, 0x10])],
            ["0x8000", "0x8001", "0x8002"],
        )


class ResetTest(unittest.TestCase):
    """That a reset defines the one flag this part defines and no others."""

    def machine(self, seed: int) -> Any:
        memory = SparseMemory(seed=seed)
        memory.write8(0xFFFC, 0x00)
        memory.write8(0xFFFD, 0x80)
        cpu = mos65c02.Cpu(memory, seed=seed)
        cpu.reset(seed)
        return cpu

    def test_decimal_mode_is_off_afterwards(self) -> None:
        self.assertFalse(self.machine(3).d)

    def test_whatever_the_seed_would_have_left_there(self) -> None:
        self.assertFalse(any(self.machine(seed).d for seed in range(24)))

    def test_the_older_part_leaves_it_holding_what_it_held(self) -> None:
        memory = SparseMemory(seed=5)
        memory.write8(0xFFFC, 0x00)
        memory.write8(0xFFFD, 0x80)

        def reset_part(seed: int) -> Any:
            cpu = mos6502.Cpu(memory, seed=seed)
            cpu.reset(seed)
            return cpu

        self.assertTrue(any(reset_part(seed).d for seed in range(24)))

    def test_interrupts_are_disabled_afterwards(self) -> None:
        self.assertTrue(self.machine(3).i)

    def test_and_the_program_counter_comes_from_the_vector(self) -> None:
        self.assertEqual(self.machine(3).pc, 0x8000)


if __name__ == "__main__":
    unittest.main()
