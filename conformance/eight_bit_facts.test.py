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

from mos65xx import Cpu, Memory, NoSuchPin  # noqa: E402

FACTS = json.loads((Path(__file__).resolve().parent / "hardware.json").read_text())["facts"]

DIVERGENCES = json.loads((Path(__file__).resolve().parent / "divergences.json").read_text())

START = 0x0200

NUMBERS = {"two": 2, "three": 3, "five": 5, "six": 6}

HEADING = re.compile(r"(A\.\d(?:\.\d)?) [^.]*?(?:\((\d+)(?: or (\d+))? cycles\)|(\w+) cycles)\.")

SECOND_PRINTING = {
    "A.1": ((0xE8,),),
    "A.2.2": ((0xA5, 0x10),),
    "A.2.3": ((0xAD, 0x00, 0x30),),
    "A.2.4": ((0xA1, 0x10),),
    "A.2.5": ((0xB9, 0x00, 0x30), (0xB9, 0xFF, 0x30)),
    "A.2.7": ((0xB1, 0x10), (0xB1, 0x12)),
    "A.3.1": ((0x85, 0x10),),
    "A.3.2": ((0x8D, 0x00, 0x30),),
    "A.3.3": ((0x81, 0x10),),
    "A.3.4": ((0x99, 0x00, 0x30),),
    "A.4.1": ((0x06, 0x10),),
    "A.4.2": ((0x0E, 0x00, 0x30),),
    "A.4.3": ((0x16, 0x10),),
    "A.4.4": ((0x1E, 0x00, 0x30),),
    "A.5.1": ((0x48,),),
    "A.5.2": ((0x68,),),
    "A.5.3": ((0x20, 0x00, 0x30),),
    "A.5.5": ((0x40,),),
    "A.5.7": ((0x60,),),
}

POINTERS = (0x00, 0x30, 0xFF, 0x30)

IMPLIED = frozenset(
    {
        "clc",
        "cld",
        "cli",
        "clv",
        "dex",
        "dey",
        "inx",
        "iny",
        "nop",
        "sec",
        "sed",
        "sei",
        "stp",
        "tax",
        "tay",
        "tsx",
        "txa",
        "txs",
        "tya",
        "wai",
    }
)

SINGLE_CYCLE_NOP = (0x03, 0x0B)

BREAK_FETCHED = 2

BREAK = (0xFFFE, 0xFFFF)

NMI = (0xFFFA, 0xFFFB)


def fact(name: str) -> dict[str, Any]:
    found = FACTS[name]
    assert isinstance(found, dict), f"{name} is not recorded as a fact"
    return found


def quote(name: str) -> str:
    return str(fact(name)["quote"])


def eight(model: str, code: Sequence[int], **registers: Any) -> Any:
    cpu = Cpu(model)
    for name, value in {"pc": START, **registers}.items():
        setattr(cpu, name, value)
    for offset, byte in enumerate(code):
        cpu.memory.write8(START + offset, byte)
    cpu.trace = []
    return cpu


def number(pattern: str, text: str) -> int:
    found = re.search(pattern, text)
    assert found is not None, f"{pattern} is not in {text}"
    return int(found.group(1))


def registers(cpu: Any) -> tuple[int, ...]:
    return (cpu.a, cpu.x, cpu.y, cpu.s, cpu.status(), cpu.pc)


def spent(code: Sequence[int]) -> int:
    cpu = eight("6502", code, x=0, y=1, s=0xF0)
    for offset, byte in enumerate(POINTERS):
        cpu.memory.write8(0x10 + offset, byte)
    return int(cpu.step())


def headings(text: str) -> dict[str, tuple[int, ...]]:
    found: dict[str, tuple[int, ...]] = {}
    for section, low, high, word in HEADING.findall(text):
        counts = (NUMBERS[word],) if word else (int(low),)
        found[section] = (*counts, int(high)) if high else counts
    return found


def spare_read(model: str) -> str:
    cpu = eight(model, (0xBD, 0xFF, 0x30), x=1)
    cpu.step()
    spare = cpu.trace[3][0]
    if spare == START + 2:
        return "last instruction byte"
    return "invalid address" if spare == 0x3000 else f"${spare:04X}"


def first_cycles(cpu: Any, count: int) -> list[tuple[int, Any]]:
    found = []
    for _ in range(count):
        pc, index = cpu.pc, len(cpu.trace)
        cpu.step()
        found.append((pc, cpu.trace[index]))
    return found


def decimal_after(model: str, event: str) -> bool:
    cpu = eight(model, (0x00, 0x00), d=True, i=False)
    {"reset": cpu.reset, "break": cpu.step, "irq": cpu.irq, "nmi": cpu.nmi}[event]()
    return bool(cpu.d)


def implied_opcodes(model: str) -> list[int]:
    table = Cpu(model).table
    return [
        opcode
        for opcode, (mnemonic, mode) in enumerate(table)
        if mode == "implied" and mnemonic in IMPLIED and opcode & 0x0F not in SINGLE_CYCLE_NOP
    ]


class RaiseNmi:
    def __init__(self, cpu: Any) -> None:
        self.cpu = cpu
        self.cycles = 0

    def __call__(self) -> None:
        self.cycles += 1
        self.cpu.nmi_line = self.cycles >= BREAK_FETCHED


def break_meeting_an_nmi(model: str) -> tuple[int, ...]:
    cpu = eight(model, (0x00, 0x00), i=False)
    cpu.on_cycle = RaiseNmi(cpu)
    cpu.step()
    return tuple(address for address, _, _ in cpu.trace if address in (*BREAK, *NMI))


def vectors_read_for(clause: str) -> tuple[int, ...]:
    if clause.endswith("BRK vector is ignored"):
        return NMI
    assert clause.startswith("BRK is executed"), f"no reading of {clause}"
    return (*BREAK, *NMI)


def printed_break_with_an_interrupt(name: str) -> dict[str, tuple[int, ...]]:
    found = re.search(r"fetch of BRK instruction: NMOS[^,]*, (.+?); [^,]+, (.+?)\.", quote(name))
    assert found is not None, f"{name} prints no row for an interrupt during BRK"
    nmos, cmos = (vectors_read_for(clause) for clause in found.groups())
    return {"6502": nmos} | dict.fromkeys(fact(name)["appliesTo"], cmos)


def reach(cpu: Any) -> int:
    cpu.memory.write8(0x0000, 0x5A)
    return next(1 << bit for bit in range(1, 17) if cpu.read8(1 << bit) == 0x5A)


def brought_out(cpu: Any) -> set[str]:
    found = set()
    for pin, pull in (("irq", cpu.irq), ("nmi", cpu.nmi)):
        try:
            pull()
        except NoSuchPin:
            continue
        found.add(pin)
    return found


def printed_kinds(text: str) -> list[str]:
    return ["read" if flag == "1" else "write" for flag in re.findall(r"R/W (\d)", text)]


def discarded_read_high_byte() -> str:
    held = next(
        one
        for one in DIVERGENCES["divergences"]
        if "discarded read of an indexed access" in one["subject"]
    )
    found = re.search(r"ADH: (BAH(?: \+ C)?)\.", held["andAlsoSays"]["quote"])
    assert found is not None, "the second printing names no high byte for the discarded read"
    return found.group(1)


class NmosFactTest(unittest.TestCase):
    def test_no_register_comes_up_the_same_from_two_seeds(self) -> None:
        # Arrange
        models = fact("nothingStartsClean")["appliesTo"]

        # Act
        same = [
            name for name in models if registers(Cpu(name, seed=1)) == registers(Cpu(name, seed=2))
        ]

        # Assert
        self.assertEqual(same, [], quote("nothingStartsClean"))

    def test_a_reset_waits_the_printed_cycles_then_reads_the_printed_vector(self) -> None:
        # Arrange
        printed = quote("nmosReset")
        delay = number(r"delay (\d+) cycles", printed)
        vector = [int(found, 16) for found in re.findall(r"location ([0-9A-F]{4})", printed)]
        cpu = eight("6502", ())
        before = cpu.cycles

        # Act
        cpu.reset()

        # Assert
        self.assertEqual(
            (cpu.cycles - before, [address for address, _, _ in cpu.trace][delay:]),
            (delay + len(vector), vector),
        )

    def test_every_cycle_of_an_instruction_puts_an_address_and_data_on_the_bus(self) -> None:
        # Arrange
        cpu = eight("6502", (0xA9, 0x01, 0x85, 0x10, 0xE6, 0x10, 0x48), s=0xF0)
        before = cpu.cycles

        # Act
        cpu.run_for(13)

        # Assert
        self.assertEqual(
            (len(cpu.trace), {kind for _, _, kind in cpu.trace}),
            (cpu.cycles - before, {"read", "write"}),
            quote("nmosSingleCycleAppendix"),
        )

    def test_an_indexed_modify_reads_twice_and_writes_twice_where_the_appendix_prints(
        self,
    ) -> None:
        # Arrange
        printed = quote("nmosReadModifyWriteWritesTwice")
        carry = 0 if discarded_read_high_byte() == "BAH" else 1
        cpu = eight("6502", (0xFE, 0xFF, 0x30), x=1)
        cpu.memory.write8(0x3100, 0x41)
        discarded = cpu.memory.read8(0x3000 + (carry << 8))

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            cpu.trace[3:],
            list(
                zip(
                    (0x3000 + (carry << 8), 0x3100, 0x3100, 0x3100),
                    (discarded, 0x41, 0x41, 0x42),
                    printed_kinds(printed),
                    strict=True,
                )
            ),
        )

    def test_the_rotate_right_works_on_the_part_this_project_models(self) -> None:
        # Arrange
        cpu = eight("6502", (0x6A,), a=0x02, c=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.a, cpu.c), (0x81, False), quote("nmosRorArrivedLate"))

    def test_every_instruction_begins_by_fetching_its_own_opcode(self) -> None:
        # Arrange
        program = (0xA9, 0x01, 0x85, 0x10, 0xE6, 0x10, 0xE8, 0x48)
        cpu = eight("6502", program, s=0xF0)

        # Act
        first = first_cycles(cpu, 5)

        # Assert
        self.assertEqual(
            [entry for _, entry in first],
            [(pc, program[pc - START], "read") for pc, _ in first],
            quote("nmosCycleShapesNowImplemented"),
        )

    def test_every_heading_of_the_second_printing_gives_the_cycles_the_model_takes(
        self,
    ) -> None:
        # Arrange
        printed = headings(quote("nmosCycleTablesFromASecondPrinting"))

        # Act
        taken = {
            section: tuple(spent(code) for code in variants)
            for section, variants in SECOND_PRINTING.items()
        }

        # Assert
        self.assertEqual(taken, printed)

    def test_a_narrow_package_reaches_and_brings_out_only_what_its_page_lists(self) -> None:
        # Arrange
        printed = quote("nmosFamilyPackages")
        found = re.search(r"Features of (\d+): (\d+)K Addressable Bytes", printed)
        assert found is not None
        cpu = Cpu(found.group(1), memory=Memory(fill=0))
        cpu.i = True
        pins = {name.lower() for name in ("IRQ", "NMI") if f"{name} Interrupt" in printed}

        # Act
        observed = (reach(cpu), brought_out(cpu))

        # Assert
        self.assertEqual(observed, (int(found.group(2)) * 1024, pins))


class CmosFactTest(unittest.TestCase):
    def test_an_indexed_spare_read_lands_where_each_part_is_printed_to_put_it(self) -> None:
        # Arrange
        models = fact("cmosCycleShapes")["appliesTo"]

        # Act
        nmos, cmos = spare_read("6502"), ", ".join(sorted({spare_read(name) for name in models}))

        # Assert
        self.assertIn(
            f"NMOS 6502, extra read of {nmos}; W65C02S, extra read of {cmos}.",
            quote("cmosCycleShapes"),
        )

    def test_the_decimal_flag_is_cleared_where_each_part_is_printed_to_clear_it(self) -> None:
        # Arrange
        models = fact("cmosInterruptClearsDecimal")["appliesTo"]
        events = ("reset", "break", "irq", "nmi")

        # Act
        kept, cleared = (
            decimal_after("6502", "reset"),
            not any(decimal_after(name, event) for name in models for event in events),
        )

        # Assert
        nmos = "indeterminate" if kept else "cleared"
        cmos = "initialized to binary mode (D=0)" if cleared else "left alone"
        self.assertIn(
            f"NMOS 6502, {nmos} after reset; W65C02S, {cmos} after reset and interrupts.",
            quote("cmosInterruptClearsDecimal"),
        )

    def test_every_implied_instruction_takes_the_printed_cycles(self) -> None:
        # Arrange
        held = fact("impliedModeCycles")
        cpus = [
            eight(name, (opcode,), i=True)
            for name in held["appliesTo"]
            for opcode in implied_opcodes(name)
        ]

        # Act
        taken = {cpu.step() for cpu in cpus}

        # Assert
        self.assertEqual(taken, {held["cycles"]})

    def test_an_nmi_after_the_break_fetch_is_taken_as_each_part_is_printed_to(self) -> None:
        # Arrange
        expected = printed_break_with_an_interrupt("cmosInterruptDuringBreak")

        # Act
        observed = {name: break_meeting_an_nmi(name) for name in expected}

        # Assert
        self.assertEqual(observed, expected)

    def test_a_part_without_the_nmi_pin_keeps_its_break_vector(self) -> None:
        # Arrange
        cpu = eight("6507", (0x00, 0x00), i=False)
        cpu.on_cycle = RaiseNmi(cpu)
        watched = {address & cpu.address_mask for address in (*BREAK, *NMI)}

        # Act
        with self.assertRaises(NoSuchPin):
            cpu.step()

        # Assert
        self.assertEqual(
            [address for address, _, _ in cpu.trace if address in watched],
            [address & cpu.address_mask for address in BREAK],
        )

    def test_a_second_manufacturer_prints_the_same_break_and_interrupt_row(self) -> None:
        # Arrange
        expected = printed_break_with_an_interrupt("cmosEnhancementsFromASecondManufacturer")

        # Act
        observed = {name: break_meeting_an_nmi(name) for name in expected}

        # Assert
        self.assertEqual(observed, expected)


if __name__ == "__main__":
    unittest.main()
