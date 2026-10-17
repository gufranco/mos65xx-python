from __future__ import annotations

import json
import re
import sys
import unittest
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import Cpu, Memory  # noqa: E402

FACTS = json.loads((Path(__file__).resolve().parent / "hardware.json").read_text())["facts"]

START = 0x8000

FILL = 0x55

PROGRAM_BANK = 0x12

DATA_BANK = 0x34

ALIGNED_PAGE = 0x0C00

AWAY_FROM_THE_STACK = 0x4000

EVENTS: dict[str, tuple[Sequence[int], Callable[[Any], object]]] = {
    "BRK": ((0x00, 0x00), lambda cpu: cpu.step()),
    "COP": ((0x02, 0x00), lambda cpu: cpu.step()),
    "IRQ": ((), lambda cpu: cpu.irq()),
    "NMI": ((), lambda cpu: cpu.nmi()),
    "ABORT": ((), lambda cpu: cpu.abort()),
}

POINTER_MODES = {
    "(Direct,X)": 0xA1,
    "(Direct)": 0xB2,
    "(Direct),Y": 0xB1,
    "[Direct]": 0xA7,
    "[Direct],Y": 0xB7,
    "PEI": 0xD4,
}

STACK_OPERATIONS: dict[str, tuple[Sequence[int], int]] = {
    "JSL": ((0x22, 0x00, 0x90, 0x00), 0x0100),
    "JSR(a,x)": ((0xFC, 0x00, 0x90), 0x0100),
    "PEA": ((0xF4, 0x34, 0x12), 0x0100),
    "PEI": ((0xD4, 0x10), 0x0100),
    "PER": ((0x62, 0x34, 0x12), 0x0100),
    "PHD": ((0x0B,), 0x0100),
    "PLD": ((0x2B,), 0x01FF),
    "RTL": ((0x6B,), 0x01FF),
    "d,s": ((0xA3, 0x10), 0x01FF),
    "(d,s),y": ((0xB3, 0x10), 0x01FF),
    "JSR a": ((0x20, 0x00, 0x90), 0x0100),
    "RTS": ((0x60,), 0x01FF),
}

STACK_NAMES = re.compile(r"\(d,s\),y|d,s|JSR\(a,x\)|[A-Z]{3}")

OUTSIDE_PAGE_ONE = (range(0x0000, 0x0100), range(0x0200, 0x0300))


def fact(name: str) -> dict[str, Any]:
    found = FACTS[name]
    assert isinstance(found, dict), f"{name} is not recorded as a fact"
    return found


def quote(name: str) -> str:
    return str(fact(name)["quote"])


def emulated(code: Sequence[int], **registers: Any) -> Any:
    cpu = Cpu("65816", memory=Memory(fill=FILL))
    for name, value in {"emulation": True, "pb": 0, "db": 0, "pc": START, **registers}.items():
        setattr(cpu, name, value)
    for offset, byte in enumerate(code):
        cpu.memory.write8((cpu.pb << 16) | (cpu.pc + offset), byte)
    cpu.trace = []
    return cpu


def banks_after(event: str, emulation: bool) -> dict[str, int]:
    code, run = EVENTS[event]
    cpu = emulated(code, emulation=emulation, pb=PROGRAM_BANK, db=DATA_BANK, irq_disable=False)
    run(cpu)
    return {"PBR": cpu.pb, "DBR": cpu.db}


def printed_banks(cleared: str, value: str) -> dict[str, int]:
    kept = {"PBR": PROGRAM_BANK, "DBR": DATA_BANK}
    return kept | dict.fromkeys(re.findall(r"PBR|DBR", cleared), int(value, 16))


def pointer_leaves_the_page(opcode: int) -> bool:
    cpu = emulated((opcode, 0xFF), d=ALIGNED_PAGE, x=0, y=0, s=0x01F0)
    cpu.step()
    data = [address for address, _, pins in cpu.trace if pins[0] == "d"]
    return ALIGNED_PAGE + 0x100 in data


def leaves_page_one(name: str) -> bool:
    code, stack = STACK_OPERATIONS[name]
    cpu = emulated(code, d=AWAY_FROM_THE_STACK, x=0, y=0, s=stack)
    cpu.step()
    touched = [address for address, _, pins in cpu.trace if pins[0] == "d"]
    return any(address in span for address in touched for span in OUTSIDE_PAGE_ONE)


def printed_stack_operations(text: str) -> set[str]:
    listed = text.split("two or three bytes:")[1].replace(" ", "")
    return set(STACK_NAMES.findall(listed))


class InterruptBankTest(unittest.TestCase):
    def test_each_interrupt_clears_the_banks_the_data_sheet_names_for_its_mode(self) -> None:
        # Arrange
        printed = quote("programBankOnInterrupt")
        native = re.search(r"Native mode, the .+?\(([A-Z]+)\) is cleared to (\d+)", printed)
        emulation = re.search(r"Emulation mode, the (.+?) registers are cleared to (\d+)", printed)
        assert native is not None and emulation is not None
        expected = {
            (event, mode): printed_banks(*found.groups())
            for event in EVENTS
            for mode, found in ((False, native), (True, emulation))
        }

        # Act
        observed = {(event, mode): banks_after(event, mode) for event, mode in expected}

        # Assert
        self.assertEqual(observed, expected)


class DirectPageTest(unittest.TestCase):
    def test_in_emulation_only_the_printed_exceptions_leave_the_direct_page(self) -> None:
        # Arrange
        printed = quote("directRangeInEmulation")
        listed = re.search(r"except for (.+?) addressing modes and the (\w+) instruction", printed)
        assert listed is not None
        named = {*listed.group(1).split(" and "), listed.group(2)}

        # Act
        leaving = {
            mode for mode, opcode in POINTER_MODES.items() if pointer_leaves_the_page(opcode)
        }

        # Assert
        self.assertEqual(leaving, named)


class StackRangeTest(unittest.TestCase):
    def test_every_operation_the_current_sheet_names_leaves_page_one(self) -> None:
        # Arrange
        named = printed_stack_operations(quote("stackRangeInEmulation"))
        unnamed = {"JSR a", "RTS"}

        # Act
        leaving = {name for name in named | unnamed if leaves_page_one(name)}

        # Assert
        self.assertEqual(leaving, named)

    def test_exactly_the_operations_the_first_printing_names_leave_page_one(self) -> None:
        # Arrange
        named = printed_stack_operations(quote("stackRangeInEmulationAsFirstPrinted"))

        # Act
        leaving = {name for name in STACK_OPERATIONS if leaves_page_one(name)}

        # Assert
        self.assertEqual(leaving, named)


if __name__ == "__main__":
    unittest.main()
