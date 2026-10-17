from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import Cpu, SparseMemory


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
    cpu.trace = []
    return cpu, memory


def traced(program: Sequence[int], **registers: Any) -> Any:
    return machine(program, **registers)[0]


def bus(cpu: Any) -> list[tuple[str, str]]:
    return [(hex(address), kind) for address, _, kind in cpu.trace]


def addresses(cpu: Any) -> list[str]:
    return [hex(address) for address, _, _ in cpu.trace]


class CycleShapeTest(unittest.TestCase):
    def test_a_read_modify_write_reads_twice_and_writes_once(self) -> None:
        # Arrange
        cpu = traced([0xE6, 0x40])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            bus(cpu),
            [
                ("0x8000", "read"),
                ("0x8001", "read"),
                ("0x40", "read"),
                ("0x40", "read"),
                ("0x40", "write"),
            ],
        )

    def test_an_indexed_store_re_reads_the_last_byte_of_the_instruction(self) -> None:
        # Arrange
        cpu = traced([0x9D, 0x00, 0x20], x=0x10)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            bus(cpu),
            [
                ("0x8000", "read"),
                ("0x8001", "read"),
                ("0x8002", "read"),
                ("0x8002", "read"),
                ("0x2010", "write"),
            ],
        )

    def test_a_shift_of_an_indexed_absolute_pays_nothing_extra_inside_a_page(self) -> None:
        # Arrange
        cpu = traced([0x1E, 0x00, 0x20], x=0x10)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(len(cpu.trace), 6)

    def test_and_pays_when_the_index_crosses_one(self) -> None:
        # Arrange
        cpu = traced([0x1E, 0xF0, 0x20], x=0x20)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(len(cpu.trace), 7)

    def test_an_increment_of_the_same_address_always_pays(self) -> None:
        # Arrange
        cpu = traced([0xFE, 0x00, 0x20], x=0x10)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(len(cpu.trace), 7)

    def test_decimal_arithmetic_costs_a_cycle_that_reads_the_operand_again(self) -> None:
        # Arrange
        cpu = traced([0x65, 0x40], d=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            bus(cpu),
            [("0x8000", "read"), ("0x8001", "read"), ("0x40", "read"), ("0x40", "read")],
        )

    def test_and_costs_it_with_an_immediate_operand_too(self) -> None:
        # Arrange
        cpu = traced([0x69, 0x11], d=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(len(cpu.trace), 3)

    def test_but_nothing_when_decimal_is_clear(self) -> None:
        # Arrange
        cpu = traced([0x69, 0x11])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(len(cpu.trace), 2)

    def test_the_same_holds_for_subtraction(self) -> None:
        # Arrange
        cpu = traced([0xE5, 0x40], d=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(len(cpu.trace), 4)

    def test_an_undocumented_single_byte_opcode_is_one_cycle(self) -> None:
        # Arrange
        cpu = traced([0x03])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(bus(cpu), [("0x8000", "read")])

    def test_the_documented_no_operation_is_still_two(self) -> None:
        # Arrange
        cpu = traced([0xEA])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(len(cpu.trace), 2)

    def test_an_indirect_jump_reads_the_address_the_older_part_would_have_used(self) -> None:
        # Arrange
        cpu, memory = machine([0x6C, 0xFF, 0x30])
        memory.write8(0x30FF, 0x34)
        memory.write8(0x3000, 0xEE)
        memory.write8(0x3100, 0x12)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            addresses(cpu), ["0x8000", "0x8001", "0x8002", "0x30ff", "0x3000", "0x3100"]
        )

    def test_and_still_arrives_at_the_corrected_destination(self) -> None:
        # Arrange
        cpu, memory = machine([0x6C, 0xFF, 0x30])
        memory.write8(0x30FF, 0x34)
        memory.write8(0x3000, 0xEE)
        memory.write8(0x3100, 0x12)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x1234)

    def test_an_indexed_indirect_jump_re_reads_the_operand_low_byte(self) -> None:
        # Arrange
        cpu = traced([0x7C, 0x00, 0x30], x=0x02)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            addresses(cpu), ["0x8000", "0x8001", "0x8002", "0x8001", "0x3002", "0x3003"]
        )

    def test_a_pull_of_an_index_register_reads_the_slot_below_first(self) -> None:
        # Arrange
        cpu = traced([0xFA], s=0x40)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(addresses(cpu), ["0x8000", "0x8001", "0x140", "0x141"])

    def test_a_bit_branch_reads_its_page_zero_address_twice(self) -> None:
        # Arrange
        cpu = traced([0x0F, 0x40, 0x10], model="w65c02")

        # Act
        cpu.step()

        # Assert
        self.assertEqual(addresses(cpu), ["0x8000", "0x8001", "0x40", "0x40", "0x8002"])

    def test_and_spends_its_taken_cycle_on_the_byte_after_itself(self) -> None:
        # Arrange
        cpu, memory = machine([0x8F, 0x40, 0x10], model="w65c02")
        memory.write8(0x0040, 0x01)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(addresses(cpu), ["0x8000", "0x8001", "0x40", "0x40", "0x8002", "0x8003"])

    def test_and_one_more_when_it_lands_backwards_on_another_page(self) -> None:
        # Arrange
        cpu, memory = machine([0x8F, 0x40, 0xF0], model="w65c02")
        memory.write8(0x0040, 0x01)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            (addresses(cpu), cpu.pc),
            (["0x8000", "0x8001", "0x40", "0x40", "0x8002", "0x8003", "0x8003"], 0x7FF3),
        )

    def test_an_undocumented_indexed_opcode_reads_the_address_it_names(self) -> None:
        # Arrange
        cpu = traced([0x54, 0x40], x=0x02)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(addresses(cpu), ["0x8000", "0x8001", "0x40", "0x42"])

    def test_an_undocumented_three_byte_opcode_reads_neither_of_its_operands(self) -> None:
        # Arrange
        cpu = traced([0x0F, 0x40, 0x10])

        # Act
        cpu.step()

        # Assert
        self.assertEqual(addresses(cpu), ["0x8000", "0x8001", "0x8002"])


if __name__ == "__main__":
    unittest.main()
