from __future__ import annotations

import json
import re
import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import Cpu  # noqa: E402

RECORDS = Path(__file__).resolve().parent

FACTS = json.loads((RECORDS / "hardware.json").read_text())["facts"]

TABLE = json.loads((RECORDS / "bus-operation.json").read_text())["groups"]

VECTORS = FACTS["vectors"]

START = 0x8000

HANDLER = 0x9000

STACK_TOP = 0x1FFF


def supporting(fact: dict[str, Any], section: str) -> str:
    return next(str(one["quote"]) for one in fact["alsoSays"] if one["section"] == section)


def printed_cycle(fact: dict[str, Any], section: str) -> int:
    found = re.search(r"after cycle (\d+)", supporting(fact, section))
    assert found is not None, f"{section} names no cycle"
    return int(found.group(1))


def last_abortable(group: str) -> int:
    rows = next(one["bus"] for one in TABLE if one["id"] == group)
    return int(next(row["cycle"] for row in rows if "3" in row.get("notes", [])))


def native(code: Sequence[int], bank: int = 0x00) -> Any:
    cpu = Cpu("65816")
    cpu.emulation = False
    cpu.set_status(0x30)
    cpu.d, cpu.db, cpu.pb, cpu.pc = 0x0000, 0x00, bank, START
    cpu.s = STACK_TOP
    cpu.a, cpu.x, cpu.y = 0x11, 0x22, 0x33
    for offset, byte in enumerate(code):
        cpu.memory.write8((bank << 16) | (START + offset), byte)
    vector = VECTORS["native"]["abort"]
    cpu.memory.write8(vector, HANDLER & 0xFF)
    cpu.memory.write8(vector + 1, HANDLER >> 8)
    return cpu


def aborting(cpu: Any, during: int) -> None:
    closed = [0]
    cpu.abort_line = during == 1

    def hook() -> None:
        closed[0] += 1
        cpu.abort_line = closed[0] == during - 1

    cpu.on_cycle = hook


def returning(stack: Sequence[int]) -> Any:
    cpu = native((0x40,))
    cpu.s = STACK_TOP - len(stack)
    for offset, byte in enumerate(stack):
        cpu.memory.write8(cpu.s + 1 + offset, byte)
    return cpu


class AbortTest(unittest.TestCase):
    def test_an_aborted_instruction_leaves_every_register_as_it_found_it(self) -> None:
        # Arrange
        fact = FACTS["abortRollback"]
        cpu = native((0xA9, 0x7F))
        before = (cpu.a, cpu.x, cpu.y, cpu.d, cpu.db, cpu.pb)
        aborting(cpu, 2)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            ((cpu.a, cpu.x, cpu.y, cpu.d, cpu.db, cpu.pb), cpu.pc),
            (before, HANDLER),
            fact["quote"],
        )

    def test_the_return_address_pushed_is_the_aborted_opcode(self) -> None:
        # Arrange
        fact = FACTS["abortRollback"]
        cpu = native((0xE8,))
        aborting(cpu, 1)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            cpu.memory.read8(STACK_TOP - 1) << 8 | cpu.memory.read8(STACK_TOP - 2),
            START,
            fact["quote"],
        )

    def test_a_modify_aborted_after_its_modify_cycle_keeps_its_status(self) -> None:
        # Arrange
        fact = FACTS["abortRollback"]
        cpu = native((0xE6, 0x10))
        cpu.memory.write8(0x000010, 0xFF)
        aborting(cpu, last_abortable("10b") + 1)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.z, cpu.pc), (True, HANDLER), supporting(fact, "8.4.1.1"))

    def test_and_one_aborted_on_its_modify_cycle_does_not(self) -> None:
        # Arrange
        fact = FACTS["abortRollback"]
        cpu = native((0xE6, 0x10))
        cpu.memory.write8(0x000010, 0xFF)
        aborting(cpu, last_abortable("10b"))

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.z, cpu.pc), (False, HANDLER), supporting(fact, "8.4.1.1"))

    def test_a_return_aborted_after_the_printed_cycle_keeps_the_status_it_pulled(self) -> None:
        # Arrange
        fact = FACTS["abortRollback"]
        cpu = returning((0x33, 0x00, 0x40, 0x00))
        aborting(cpu, printed_cycle(fact, "8.4.1.2") + 1)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.z, cpu.c, cpu.pc), (True, True, HANDLER), supporting(fact, "8.4.1.2"))

    def test_and_one_aborted_on_that_cycle_does_not(self) -> None:
        # Arrange
        fact = FACTS["abortRollback"]
        cpu = returning((0x33, 0x00, 0x40, 0x00))
        aborting(cpu, printed_cycle(fact, "8.4.1.2"))

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            (cpu.z, cpu.c, cpu.pc), (False, False, HANDLER), supporting(fact, "8.4.1.2")
        )

    def test_a_break_aborted_after_the_printed_cycle_clears_the_program_bank(self) -> None:
        # Arrange
        fact = FACTS["abortRollback"]
        cpu = native((0x00, 0x00), bank=0x12)
        aborting(cpu, printed_cycle(fact, "8.4.1.3") + 1)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.memory.read8(STACK_TOP), 0x00, supporting(fact, "8.4.1.3"))

    def test_and_one_aborted_on_that_cycle_keeps_it(self) -> None:
        # Arrange
        fact = FACTS["abortRollback"]
        cpu = native((0x00, 0x00), bank=0x12)
        aborting(cpu, printed_cycle(fact, "8.4.1.3"))

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.memory.read8(STACK_TOP), 0x12, supporting(fact, "8.4.1.3"))

    def test_an_instruction_with_the_line_never_raised_is_not_aborted(self) -> None:
        # Arrange
        cpu = native((0xA9, 0x7F))

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.pc), (0x7F, START + 2))


if __name__ == "__main__":
    unittest.main()
