from __future__ import annotations

import sys
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import FLAG_M, FLAG_X, Cpu

NATIVE_16 = 0x00
NATIVE_8 = FLAG_M | FLAG_X

RTL = 0x6B


class FlatMemory:
    def __init__(self, data: Mapping[int, int] | None = None) -> None:
        self.cells: dict[int, int] = dict(data or {})

    def read8(self, address: int) -> int:
        return self.cells.get(address & 0xFFFFFF, 0x00)

    def write8(self, address: int, value: int) -> None:
        self.cells[address & 0xFFFFFF] = value & 0xFF


def ready(
    code: Sequence[int],
    base: int = 0x008000,
    memory: Any = None,
    status: int = NATIVE_8,
    **registers: Any,
) -> Any:
    memory = memory or FlatMemory()
    for offset, byte in enumerate(code):
        memory.cells[base + offset] = byte
    cpu = Cpu("65816", memory)
    cpu.a = cpu.x = cpu.y = 0x0000
    cpu.s = 0x01FF
    cpu.d = 0x0000
    cpu.db = 0x00
    cpu.emulation = False
    cpu.set_status(status)
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu


class ControlTest(unittest.TestCase):
    def test_a_taken_branch_moves_the_program_counter_forward(self) -> None:
        # Arrange
        cpu = ready([0xA9, 0x00, 0xF0, 0x01, 0xEA, RTL])

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.pc, 0x8005)

    def test_an_untaken_branch_falls_through(self) -> None:
        # Arrange
        cpu = ready([0xA9, 0x01, 0xF0, 0x01, 0xEA, RTL])

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.pc, 0x8005)

    def test_a_branch_reaches_backwards(self) -> None:
        # Arrange
        cpu = ready([0xA2, 0x02, 0xCA, 0xD0, 0xFD, RTL])

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.x, 0x00)

    def test_a_subroutine_returns_to_its_caller(self) -> None:
        # Arrange
        cpu = ready([0x20, 0x06, 0x80, 0xA9, 0x11, RTL, 0xA9, 0x22, 0x60], a=0x00)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x11)

    def test_a_long_subroutine_returns_across_banks(self) -> None:
        # Arrange
        memory = FlatMemory({0x018000: 0xA9, 0x018001: 0x33, 0x018002: 0x6B})
        cpu = ready([0x22, 0x00, 0x80, 0x01, RTL], memory=memory)

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual(cpu.a & 0xFF, 0x33)


class EmulationModeTest(unittest.TestCase):
    def test_the_carry_and_the_emulation_flag_swap(self) -> None:
        # Arrange
        cpu = ready([0x38, 0xFB, RTL])

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual((cpu.emulation, cpu.c), (True, False))

    def test_emulation_mode_forces_eight_bit_registers(self) -> None:
        # Arrange
        cpu = ready([0xC2, 0x30, 0x38, 0xFB, RTL])

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertEqual((cpu.m8, cpu.x8), (True, True))

    def test_leaving_emulation_mode_restores_the_carry(self) -> None:
        # Arrange
        cpu = ready([0x38, 0xFB, 0x18, 0xFB, RTL])

        # Act
        cpu.call(0x8000)

        # Assert
        self.assertFalse(cpu.emulation)


if __name__ == "__main__":
    unittest.main()
