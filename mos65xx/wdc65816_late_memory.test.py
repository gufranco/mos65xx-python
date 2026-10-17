from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import Cpu, Memory

START = 0x008000


def native(code: Sequence[int], **registers: Any) -> tuple[Any, Any]:
    memory = Memory(0x1000000)
    cpu = Cpu("65816", memory)
    cpu.emulation = False
    cpu.d = cpu.db = 0x00
    cpu.m8 = cpu.x8 = False
    cpu.pb, cpu.pc = 0x00, START & 0xFFFF
    for offset, byte in enumerate(code):
        memory.write8(START + offset, byte)
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu, memory


class Watched:
    def __init__(self) -> None:
        self.cells: dict[int, int] = {}
        self.seen: list[int] = []

    def read8(self, address: int) -> int:
        self.seen.append(address)
        return self.cells.get(address & 0xFFFFFF, 0x00)

    def write8(self, address: int, value: int) -> None:
        self.cells[address & 0xFFFFFF] = value & 0xFF


def emulated_reads(code: Sequence[int], direct: int) -> tuple[Any, Watched]:
    memory = Watched()
    cpu = Cpu("65816", memory)
    cpu.emulation = False
    cpu.d = cpu.db = 0x00
    cpu.emulation = True
    cpu.d = direct
    cpu.pb, cpu.pc = 0x00, START & 0xFFFF
    cpu.x = cpu.y = 0x00
    for offset, byte in enumerate(code):
        memory.cells[START + offset] = byte
    memory.seen.clear()
    return cpu, memory


def page_reads(memory: Watched) -> list[int]:
    return [address for address in memory.seen if 0x000C00 <= address <= 0x000D01]


class WordAndLongReadTest(unittest.TestCase):
    def test_a_word_is_read_low_byte_first(self) -> None:
        # Arrange
        cpu, memory = native([0xAF, 0x40, 0x23, 0x01])
        memory.write8(0x012340, 0x34)
        memory.write8(0x012341, 0x12)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x1234)

    def test_a_long_address_is_read_low_byte_first(self) -> None:
        # Arrange
        cpu, memory = native([0xDC, 0x00, 0x30])
        memory.write8(0x003000, 0x56)
        memory.write8(0x003001, 0x34)
        memory.write8(0x003002, 0x12)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pb, cpu.pc), (0x12, 0x3456))


class BankZeroWordTest(unittest.TestCase):
    def wrapping(self, code: Sequence[int], low: int, high: int, **registers: Any) -> Any:
        cpu, memory = native(code, d=0xFFF0, **registers)
        memory.write8(0x00FFFF, low)
        memory.write8(0x000000, high)
        memory.write8(0x010000, 0xEE)
        return cpu, memory

    def test_a_read_modify_write_reads_its_high_half_from_bank_zero(self) -> None:
        # Arrange
        cpu, memory = self.wrapping([0x06, 0x0F], 0x01, 0x02)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x000000), 0x04)

    def test_and_writes_it_there_too(self) -> None:
        # Arrange
        cpu, memory = self.wrapping([0x06, 0x0F], 0x01, 0x02)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x010000), 0xEE)

    def test_the_low_half_is_written_where_it_was_read(self) -> None:
        # Arrange
        cpu, memory = self.wrapping([0x06, 0x0F], 0x01, 0x02)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x00FFFF), 0x02)

    def test_a_bit_test_and_set_wraps_the_same_way(self) -> None:
        # Arrange
        cpu, memory = self.wrapping([0x04, 0x0F], 0x01, 0x02, a=0x1010)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((memory.read8(0x000000), memory.read8(0x010000)), (0x12, 0xEE))

    def test_a_bit_test_and_reset_wraps_the_same_way(self) -> None:
        # Arrange
        cpu, memory = self.wrapping([0x14, 0x0F], 0xFF, 0xFF, a=0x0F0F)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((memory.read8(0x000000), memory.read8(0x010000)), (0xF0, 0xEE))

    def test_a_store_already_wrapped_and_still_does(self) -> None:
        # Arrange
        cpu, memory = native([0x85, 0x0F], d=0xFFF0, a=0x1234)
        memory.write8(0x010000, 0xEE)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((memory.read8(0x000000), memory.read8(0x010000)), (0x12, 0xEE))


class DirectPagePointerWrapTest(unittest.TestCase):
    def test_a_direct_indirect_pointer_wraps_inside_the_page(self) -> None:
        # Arrange
        cpu, memory = emulated_reads([0xB2, 0xFF], 0x0C00)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(page_reads(memory), [0x000CFF, 0x000C00])

    def test_a_direct_indexed_indirect_pointer_wraps_inside_the_page(self) -> None:
        # Arrange
        cpu, memory = emulated_reads([0xA1, 0xFF], 0x0C00)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(page_reads(memory), [0x000CFF, 0x000C00])

    def test_a_direct_indirect_indexed_pointer_wraps_inside_the_page(self) -> None:
        # Arrange
        cpu, memory = emulated_reads([0xB1, 0xFF], 0x0C00)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(page_reads(memory), [0x000CFF, 0x000C00])

    def test_a_long_indirect_pointer_leaves_the_page(self) -> None:
        # Arrange
        cpu, memory = emulated_reads([0xA7, 0xFF], 0x0C00)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(page_reads(memory), [0x000CFF, 0x000D00, 0x000D01])

    def test_a_long_indirect_indexed_pointer_leaves_the_page(self) -> None:
        # Arrange
        cpu, memory = emulated_reads([0xB7, 0xFF], 0x0C00)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(page_reads(memory), [0x000CFF, 0x000D00, 0x000D01])

    def test_the_pointer_pushed_by_pei_leaves_the_page(self) -> None:
        # Arrange
        cpu, memory = emulated_reads([0xD4, 0xFF], 0x0C00)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(page_reads(memory), [0x000CFF, 0x000D00])

    def test_none_of_it_happens_when_the_page_is_not_aligned(self) -> None:
        # Arrange
        cpu, memory = emulated_reads([0xB2, 0xFE], 0x0C01)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(page_reads(memory), [0x000CFF, 0x000D00])


if __name__ == "__main__":
    unittest.main(verbosity=2)
