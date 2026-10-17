from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import Cpu, SparseMemory, Stopped, UnsupportedError


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


def every_entry(mnemonic: str, mode: str) -> tuple[tuple[str, str], ...]:
    return tuple([(mnemonic, mode)] * 256)


def with_table(table: tuple[tuple[str, str], ...], **registers: Any) -> Any:
    memory = SparseMemory(seed=1)
    cpu = Cpu("6502", memory, table=table)
    cpu.pc = 0x8000
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu, memory


class UndocumentedTest(unittest.TestCase):
    def test_the_shift_and_or_does_both(self) -> None:
        # Arrange
        cpu, memory = machine([0x07, 0x10], a=0x01)
        memory.write8(0x0010, 0x40)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((memory.read8(0x0010), cpu.a), (0x80, 0x81))

    def test_the_store_of_both_registers_stores_their_conjunction(self) -> None:
        # Arrange
        cpu, memory = machine([0x87, 0x10], a=0xF0, x=0x3C)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x0010), 0x30)

    def test_the_load_of_both_registers_loads_both(self) -> None:
        # Arrange
        cpu, memory = machine([0xA7, 0x10])
        memory.write8(0x0010, 0x42)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.x), (0x42, 0x42))

    def test_the_unstable_transfer_uses_the_magic_the_suite_measured(self) -> None:
        # Arrange
        cpu, _ = machine([0x8B, 0x23], a=0xE4, x=0xE2)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x22)

    def test_a_jam_stops_the_processor_where_it_stands(self) -> None:
        # Arrange
        cpu, _ = machine([0x02])

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pc, cpu.stopped), (0x8001, True))

    def test_a_stopped_processor_refuses_to_step_again(self) -> None:
        # Arrange
        cpu, _ = machine([0x02])
        cpu.step()

        def attempt() -> Any:
            return cpu.step()

        # Act
        with self.assertRaises(Stopped) as raised:
            attempt()

        # Assert
        self.assertEqual(str(raised.exception), "the processor has been stopped")

    def test_a_jam_reads_the_interrupt_vector_on_its_way_to_hanging(self) -> None:
        # Arrange
        cpu, _ = machine([0x02, 0xA1])
        cpu.trace = []

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            [address for address, _, _ in cpu.trace],
            [0x8000, 0x8001, 0xFFFF, 0xFFFE, 0xFFFE],
        )

    def test_a_hung_part_goes_on_driving_the_top_of_that_vector(self) -> None:
        # Arrange
        cpu, _ = machine([0x02, 0xA1])
        cpu.step()
        cpu.trace = []

        # Act
        cpu.run_for(6)

        # Assert
        self.assertEqual([address for address, _, _ in cpu.trace], [0xFFFF] * 6)

    def test_a_hung_part_still_spends_its_hosts_cycles(self) -> None:
        # Arrange
        cpu, _ = machine([0x02, 0xA1])
        cpu.step()

        # Act
        spent = cpu.run_for(1000)

        # Assert
        self.assertEqual(spent, 1000)

    def test_a_reset_is_the_only_thing_that_ends_a_jam(self) -> None:
        # Arrange
        cpu, _ = machine([0x02, 0xA1])
        cpu.step()

        # Act
        cpu.reset()

        # Assert
        self.assertEqual((cpu.jammed, cpu.stopped), (False, False))

    def test_a_decimal_rotate_adjusts_both_halves_when_both_run_over(self) -> None:
        # Arrange
        cpu, _ = machine([0x6B, 0xFF], a=0xFF, d=True, c=True)

        # Act
        cpu.step()

        # Assert
        self.assertTrue(cpu.c)

    def test_a_decimal_rotate_leaves_the_carry_clear_when_the_high_half_does_not(self) -> None:
        # Arrange
        cpu, _ = machine([0x6B, 0x00], a=0x00, d=True, c=False)

        # Act
        cpu.step()

        # Assert
        self.assertFalse(cpu.c)


class EveryOpcodeTest(unittest.TestCase):
    STATES = (
        ("binary, carry clear", "6502", False, False),
        ("binary, carry set", "6502", False, True),
        ("decimal, carry clear", "6502", True, False),
        ("decimal, carry set", "6502", True, True),
        ("decimal flag on a part without one", "2a03", True, True),
    )

    def test_every_opcode_runs_in_every_state_with_a_handler_behind_it(self) -> None:
        # Arrange
        built = {
            (f"${opcode:02X}", name): machine(
                [opcode], model=model, d=d, c=c, a=0x9C, x=0x5A, y=0xA5
            )[0]
            for opcode in range(256)
            for name, model, d, c in self.STATES
        }

        # Act
        for cpu in built.values():
            cpu.step()

        # Assert
        self.assertEqual([key for key, cpu in built.items() if cpu.steps != 1], [])

    def test_a_mode_with_no_effective_address_is_refused_rather_than_guessed(self) -> None:
        # Arrange
        cpu, _ = with_table(every_entry("lda", "relative"))

        def attempt() -> Any:
            return cpu.step()

        # Act
        with self.assertRaises(UnsupportedError) as raised:
            attempt()

        # Assert
        self.assertEqual(str(raised.exception), "relative has no effective address")

    def test_an_opcode_with_no_handler_is_refused_rather_than_skipped(self) -> None:
        # Arrange
        cpu, _ = with_table(every_entry("nonsense", "implied"))

        def attempt() -> Any:
            return cpu.step()

        # Act
        with self.assertRaises(UnsupportedError) as raised:
            attempt()

        # Assert
        self.assertEqual(str(raised.exception), "nonsense is not implemented")

    def test_an_accumulator_operand_is_the_accumulator(self) -> None:
        # Arrange
        cpu, _ = with_table(every_entry("eor", "accumulator"), a=0x42)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.z), (0x00, True))

    def test_a_zero_page_indirect_reads_a_pointer_without_indexing(self) -> None:
        # Arrange
        cpu, memory = with_table(every_entry("lda", "zeroPageIndirect"), x=0x04, y=0x04)
        memory.write8(0x8001, 0x20)
        memory.write8(0x0020, 0x34)
        memory.write8(0x0021, 0x12)
        memory.write8(0x1234, 0x42)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.pc), (0x42, 0x8002))


if __name__ == "__main__":
    unittest.main()
