from __future__ import annotations

import hashlib
import sys
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mos65xx  # noqa: E402

EIGHT_BIT = bytes.fromhex("A9 2A 85 20 E6 20 48 68 60")

SIXTEEN_BIT = bytes.fromhex("A9 2A 85 20 E6 20 48 68 6B")

PRINTED_COSTS = [2, 3, 5, 3, 4, 6]

WIDE = ("65816", "65802")

NOP = 0xEA

EIGHT_BIT_REGISTERS = 0x30

NATIVE_STACK = 0x1FFC

PAGE_ONE_STACK = 0xFC

SCRATCH = 0x0040

RETURN_LONG = 0x6B

HOST_BYTE = 0x55

HOST_WORD = 0x5555

REGISTERS = ("a", "x", "y", "s", "pc", "d", "db", "pb", "emulation", "m8", "x8", "cycles", "steps")

ACCESSES: dict[str, tuple[int, Callable[[Any], Any]]] = {
    "read8": (1, lambda cpu: cpu.read8(SCRATCH)),
    "write8": (1, lambda cpu: cpu.write8(SCRATCH, HOST_BYTE)),
    "push8": (1, lambda cpu: cpu.push8(HOST_BYTE)),
    "push16_flat": (2, lambda cpu: cpu.push16_flat(HOST_WORD)),
}


def offered(access: str) -> list[str]:
    return [model for model in mos65xx.MODELS if access != "push16_flat" or model in WIDE]


def a_program(model: str) -> Any:
    wide = model in WIDE
    space = mos65xx.Memory(size=0x10000, fill=NOP)
    for address, value in enumerate(SIXTEEN_BIT if wide else EIGHT_BIT):
        space.write8(address, value)
    cpu = mos65xx.Cpu(model, space)
    cpu.pc = 0x0000
    cpu.trace = []
    if wide:
        cpu.set_emulation(False)
        cpu.set_status(EIGHT_BIT_REGISTERS)
        cpu.pb = cpu.db = cpu.d = 0x00
        cpu.s = NATIVE_STACK
        return cpu
    cpu.set_status(0x00)
    cpu.s = PAGE_ONE_STACK
    return cpu


def observed(cpu: Any) -> tuple[Any, ...]:
    return (
        tuple(getattr(cpu, name, None) for name in REGISTERS),
        cpu.status(),
        tuple(cpu.trace),
        hashlib.sha256(bytes(cpu.memory.data)).hexdigest(),
    )


def stepped_with(model: str, access: str) -> tuple[list[int], list[int], tuple[Any, ...]]:
    cpu = a_program(model)
    _, touch = ACCESSES[access]
    costs: list[int] = []
    advances: list[int] = []
    for _ in PRINTED_COSTS:
        before = cpu.cycles
        touch(cpu)
        advances.append(cpu.cycles - before)
        costs.append(cpu.step())
    return costs, advances, observed(cpu)


def ticked_with(model: str, access: str) -> tuple[Any, ...]:
    cpu = a_program(model)
    _, touch = ACCESSES[access]
    with mos65xx.Clock(cpu) as clock:
        for cost in PRINTED_COSTS:
            touch(cpu)
            clock.run_for(cost)
        return observed(cpu)


def costs_beside(access: str) -> dict[str, tuple[list[int], list[int]]]:
    return {model: stepped_with(model, access)[:2] for model in offered(access)}


def printed_beside(access: str) -> dict[str, tuple[list[int], list[int]]]:
    spent, _ = ACCESSES[access]
    return {model: (PRINTED_COSTS, [spent] * len(PRINTED_COSTS)) for model in offered(access)}


def ticked_beside(access: str) -> dict[str, tuple[Any, ...]]:
    return {model: ticked_with(model, access) for model in offered(access)}


def stepped_beside(access: str) -> dict[str, tuple[Any, ...]]:
    return {model: stepped_with(model, access)[2] for model in offered(access)}


class AHostAccessBetweenStepsTest(unittest.TestCase):
    def test_a_host_read_is_counted_where_it_is_made_and_not_by_the_next_step(self) -> None:
        # Arrange
        expected = printed_beside("read8")

        # Act
        found = costs_beside("read8")

        # Assert
        self.assertEqual(found, expected)

    def test_a_host_write_is_counted_where_it_is_made_and_not_by_the_next_step(self) -> None:
        # Arrange
        expected = printed_beside("write8")

        # Act
        found = costs_beside("write8")

        # Assert
        self.assertEqual(found, expected)

    def test_a_host_push_is_counted_where_it_is_made_and_not_by_the_next_step(self) -> None:
        # Arrange
        expected = printed_beside("push8")

        # Act
        found = costs_beside("push8")

        # Assert
        self.assertEqual(found, expected)

    def test_a_host_flat_push_is_counted_where_it_is_made_and_not_by_the_next_step(self) -> None:
        # Arrange
        expected = printed_beside("push16_flat")

        # Act
        found = costs_beside("push16_flat")

        # Assert
        self.assertEqual(found, expected)

    def test_a_native_rtl_after_a_host_write_still_costs_six(self) -> None:
        # Arrange
        cpu = mos65xx.Cpu("65816", mos65xx.Memory(size=0x10000, fill=NOP))
        cpu.pc = cpu.pb = 0x00
        cpu.set_emulation(False)
        cpu.s = NATIVE_STACK
        cpu.write8(0x0000, RETURN_LONG)
        before = cpu.cycles

        # Act
        spent = cpu.step()

        # Assert
        self.assertEqual((spent, cpu.cycles - before), (6, 6))


class AHostAccessUnderAPausedClockTest(unittest.TestCase):
    def test_ticking_after_a_host_read_ends_where_the_steps_end(self) -> None:
        # Arrange
        expected = stepped_beside("read8")

        # Act
        found = ticked_beside("read8")

        # Assert
        self.assertEqual(found, expected)

    def test_ticking_after_a_host_write_ends_where_the_steps_end(self) -> None:
        # Arrange
        expected = stepped_beside("write8")

        # Act
        found = ticked_beside("write8")

        # Assert
        self.assertEqual(found, expected)

    def test_ticking_after_a_host_push_ends_where_the_steps_end(self) -> None:
        # Arrange
        expected = stepped_beside("push8")

        # Act
        found = ticked_beside("push8")

        # Assert
        self.assertEqual(found, expected)

    def test_ticking_after_a_host_flat_push_ends_where_the_steps_end(self) -> None:
        # Arrange
        expected = stepped_beside("push16_flat")

        # Act
        found = ticked_beside("push16_flat")

        # Assert
        self.assertEqual(found, expected)


if __name__ == "__main__":
    unittest.main()
