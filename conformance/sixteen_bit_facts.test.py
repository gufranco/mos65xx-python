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

from mos65xx import Cpu  # noqa: E402

FACTS = json.loads((Path(__file__).resolve().parent / "hardware.json").read_text())["facts"]

START = 0x8000

NUMBERS = {"two": 2, "three": 3, "five": 5}

ASSIGNMENT = re.compile(r"\b([A-Z/]+)=([0-9A-F*/]+)")

REGISTERS: dict[str, Callable[[Any], int]] = {
    "D": lambda cpu: cpu.d,
    "SH": lambda cpu: cpu.s >> 8,
    "DBR": lambda cpu: cpu.db,
    "XH": lambda cpu: cpu.x >> 8,
    "PBR": lambda cpu: cpu.pb,
    "YH": lambda cpu: cpu.y >> 8,
}

FLAGS: dict[str, Callable[[Any], int]] = {
    "M": lambda cpu: int(cpu.m8),
    "X": lambda cpu: int(cpu.x8),
    "D": lambda cpu: int(cpu.decimal),
    "I": lambda cpu: int(cpu.irq_disable),
    "E": lambda cpu: int(cpu.emulation),
}

EVENTS: dict[str, tuple[Sequence[int], Callable[[Any], object]]] = {
    "brk": ((0x00, 0x00), lambda cpu: cpu.step()),
    "cop": ((0x02, 0x00), lambda cpu: cpu.step()),
    "irq": ((), lambda cpu: cpu.irq()),
    "nmi": ((), lambda cpu: cpu.nmi()),
    "abort": ((), lambda cpu: cpu.abort()),
    "reset": ((), lambda cpu: cpu.reset()),
}

EMULATION_EVENTS = {
    "brk": "irqAndBreak",
    "irq": "irqAndBreak",
    "reset": "reset",
    "nmi": "nmi",
    "abort": "abort",
    "cop": "cop",
}

NATIVE_EVENTS = ("irq", "nmi", "abort", "brk", "cop")

TABLE_LABELS = {"IRQB": "irq", "NMIB": "nmi", "ABORTB": "abort", "BRK": "brk", "COP": "cop"}

FFE0_BLOCK = range(0x00FFE0, 0x00FFF0)

INDIRECT_JUMPS = {"JMP (a)": 0x6C, "JML (a)": 0xDC, "JMP (a,x)": 0x7C, "JSR (a,x)": 0xFC}

WHOLE_TRANSFERS = {
    "TCS": (0x1B, "a", "s"),
    "TSC": (0x3B, "s", "a"),
    "TCD": (0x5B, "a", "d"),
    "TDC": (0x7B, "d", "a"),
}

LOCKING = {
    "ASL": 0x0E,
    "DEC": 0xCE,
    "INC": 0xEE,
    "LSR": 0x4E,
    "ROL": 0x2E,
    "ROR": 0x6E,
    "TRB": 0x1C,
    "TSB": 0x0C,
}

QUALIFIED = {"OpCode fetch": 0, "Valid program address": 1, "Internal Operation": 3}

CAVEAT_COLUMNS: dict[str, dict[str, int]] = {
    "6502": {},
    "65c02": {},
    "w65c02": {},
    "65816": {"emulation": True, "pb": 0, "db": 0},
}

PROGRAM_BANK = 0x12


def fact(name: str) -> dict[str, Any]:
    found = FACTS[name]
    assert isinstance(found, dict), f"{name} is not recorded as a fact"
    return found


def quote(name: str) -> str:
    return str(fact(name)["quote"])


def number(pattern: str, text: str, base: int = 10) -> int:
    found = re.search(pattern, text)
    assert found is not None, f"{pattern} is not in {text}"
    return int(found.group(1), base)


def wide(code: Sequence[int], model: str = "65816", **registers: Any) -> Any:
    cpu = Cpu(model)
    for name, value in {"emulation": False, "pb": 0, "db": 0, "d": 0, "pc": START}.items():
        setattr(cpu, name, value)
    for name, value in registers.items():
        setattr(cpu, name, value)
    for offset, byte in enumerate(code):
        cpu.memory.write8((cpu.pb << 16) | (cpu.pc + offset), byte)
    cpu.trace = []
    return cpu


def vector_read(event: str, emulation: bool) -> int:
    code, run = EVENTS[event]
    cpu = wide(code, emulation=emulation, irq_disable=False)
    run(cpu)
    return int(cpu.trace[-2][0])


def assigned(text: str) -> dict[str, int]:
    found = {}
    for name, value in ASSIGNMENT.findall(text):
        for one, held in zip(name.split("/"), value.split("/"), strict=True):
            if held != "*":
                found[one] = int(held, 16)
    return found


def observed_reset(cpu: Any) -> tuple[dict[str, int], dict[str, int]]:
    return (
        {name: read(cpu) for name, read in REGISTERS.items()},
        {name: read(cpu) for name, read in FLAGS.items()},
    )


def data_reads(cpu: Any) -> list[int]:
    return [address for address, _, pins in cpu.trace if pins[:2] == "d-" and pins[3] == "r"]


def pointer_bank(opcode: int) -> int:
    cpu = wide((opcode, 0x00, 0x30), pb=PROGRAM_BANK, x=0, x8=True)
    cpu.step()
    return data_reads(cpu)[0] >> 16


def trailing_locks(opcode: int, m8: bool) -> int:
    cpu = wide((opcode, 0x00, 0x30), m8=m8)
    cpu.step()
    locked = [pins[7] == "l" for _, _, pins in cpu.trace]
    trailing = len(locked) - locked.index(True) if True in locked else 0
    return trailing if sum(locked) == trailing else -1


def cycles(code: Sequence[int], **registers: Any) -> int:
    return int(wide(code, **registers).step())


def column_cycles(model: str) -> int:
    cpu = Cpu(model)
    for name, value in {"pc": START, "x": 0, **CAVEAT_COLUMNS[model]}.items():
        setattr(cpu, name, value)
    for offset, byte in enumerate((0x1E, 0x00, 0x30)):
        cpu.memory.write8(START + offset, byte)
    return int(cpu.step())


def notes(text: str) -> dict[int, int]:
    return {int(note): int(added) for note, added in re.findall(r"(\d+)\. Add (\d+) cycle", text)}


class ResetAndInterruptTest(unittest.TestCase):
    def test_a_reset_sets_every_register_the_data_sheet_defines(self) -> None:
        # Arrange
        registers, flags = quote("resetState").split("P Register:")
        cpu = wide((), d=0x1234, db=0x56, pb=0x78, x=0xABCD, y=0xEF01, m8=False, x8=False)
        cpu.s, cpu.decimal, cpu.irq_disable = 0x2345, True, False

        # Act
        cpu.reset()

        # Assert
        self.assertEqual(observed_reset(cpu), (assigned(registers), assigned(flags)))

    def test_every_emulation_vector_is_read_where_the_table_prints_it(self) -> None:
        # Arrange
        printed = fact("vectors")["emulation"]
        expected = {event: printed[key] for event, key in EMULATION_EVENTS.items()}

        # Act
        read = {event: vector_read(event, emulation=True) for event in EMULATION_EVENTS}

        # Assert
        self.assertEqual(read, expected)

    def test_every_native_vector_is_read_where_the_pin_descriptions_print_it(self) -> None:
        # Arrange
        printed = fact("vectors")["native"]

        # Act
        read = {event: vector_read(event, emulation=False) for event in NATIVE_EVENTS}

        # Assert
        self.assertEqual(read, {event: printed[event] for event in NATIVE_EVENTS})

    def test_no_native_vector_is_read_where_the_erratum_table_prints_it(self) -> None:
        # Arrange
        held = fact("vectors")
        erratum = held["erratumInTable6_3"]["quote"]
        table = {
            TABLE_LABELS[label]: int(address, 16)
            for address, label in re.findall(r"(00FF[0-9A-F]{2}),[0-9A-F] (\w+)", erratum)
            if label in TABLE_LABELS
        }
        pins = {event: held["native"][event] for event in ("irq", "nmi", "abort")}

        # Act
        read = {event: vector_read(event, emulation=False) for event in NATIVE_EVENTS}

        # Assert
        self.assertEqual(
            (
                {event: read[event] == table[event] for event in table},
                {event: FFE0_BLOCK.start <= read[event] < FFE0_BLOCK.stop for event in read},
                {event: read[event] for event in pins},
            ),
            (dict.fromkeys(table, False), dict.fromkeys(read, True), pins),
        )

    def test_an_interrupt_pulls_its_vector_and_sets_the_printed_flags_in_both_modes(
        self,
    ) -> None:
        # Arrange
        printed = quote("interruptEffects")
        flags = assigned(printed)
        effects = (NUMBERS[printed.split("during the ")[1].split()[0]], flags["D"], flags["I"])
        cpus = {mode: wide((), emulation=mode, decimal=True, irq_disable=False) for mode in (0, 1)}

        # Act
        taken = {mode: cpu.nmi() for mode, cpu in cpus.items()}

        # Assert
        self.assertEqual(
            {
                mode: (
                    sum(pins[2] == "v" for _, _, pins in cpu.trace),
                    cpu.decimal,
                    cpu.irq_disable,
                )
                for mode, cpu in cpus.items()
            },
            dict.fromkeys(taken, effects),
        )


class ModeTest(unittest.TestCase):
    def test_switching_to_emulation_narrows_what_the_data_sheet_says_it_narrows(self) -> None:
        # Arrange
        printed = quote("switchingToEmulation")
        stack = number(r"high byte of the Stack is set to (\d+)", printed, 16)
        index = number(r"high bytes of the X and Y Index Registers are set to (\d+)", printed, 16)
        cpu = wide((0xFB,), m8=False, x8=False, s=0x1234, x=0xABCD, y=0x5678, a=0x9ABC, c=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            (cpu.m8, cpu.x8, cpu.s >> 8, cpu.x >> 8, cpu.y >> 8, cpu.s & 0xFF, cpu.x, cpu.y, cpu.a),
            (True, True, stack, index, index, 0x34, 0xCD, 0x78, 0x9ABC),
        )

    def test_a_wide_direct_read_at_the_top_of_bank_zero_wraps_inside_it(self) -> None:
        # Arrange
        found = re.search(r"Bank 0 \((\w{6})-(\w{6})\)", quote("directIsBankZero"))
        assert found is not None
        cpu = wide((0xA5, 0xFF), m8=False, d=0xFF00, db=0x7E)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(data_reads(cpu), [int(found.group(2), 16), int(found.group(1), 16)])

    def test_each_indirect_jump_reads_its_pointer_from_the_bank_it_is_printed_to_use(
        self,
    ) -> None:
        # Arrange
        direct, program = quote("indirectJumpBanks").split(", while ")
        expected = dict.fromkeys(re.findall(r"J[A-Z]{2} \([a-z,]+\)", direct), 0) | dict.fromkeys(
            re.findall(r"J[A-Z]{2} \([a-z,]+\)", program), PROGRAM_BANK
        )

        # Act
        banks = {name: pointer_bank(opcode) for name, opcode in INDIRECT_JUMPS.items()}

        # Assert
        self.assertEqual(banks, expected)


class TransferTest(unittest.TestCase):
    def test_the_named_transfers_move_every_printed_bit_whatever_the_widths(self) -> None:
        # Arrange
        printed = quote("registerTransferWidths")
        mask = (1 << number(r"always (\d+)-bit transfers", printed)) - 1
        listed = re.search(r"accumulator size: (.+?)\.", printed)
        assert listed is not None
        named = re.findall(r"T[A-Z]{2}", listed.group(1))
        cpus = {name: wide((WHOLE_TRANSFERS[name][0],), m8=True, x8=True) for name in named}
        for name, cpu in cpus.items():
            setattr(cpu, WHOLE_TRANSFERS[name][1], 0x1234)

        # Act
        moved = {name: cpu.step() for name, cpu in cpus.items()}

        # Assert
        self.assertEqual(
            {name: getattr(cpus[name], WHOLE_TRANSFERS[name][2]) for name in moved},
            dict.fromkeys(named, 0x1234 & mask),
        )

    def test_the_destination_width_decides_how_much_of_a_transfer_is_kept(self) -> None:
        # Arrange
        cpus = {width: wide((0xAA,), a=0x1234, x8=width == 8) for width in (8, 16)}

        # Act
        stepped = {width: cpu.step() for width, cpu in cpus.items()}

        # Assert
        self.assertEqual(
            {width: cpus[width].x for width in stepped},
            {8: 0x34, 16: 0x1234},
            quote("registerTransferWidths"),
        )

    def test_the_status_push_and_pull_move_the_printed_width_whatever_the_widths(self) -> None:
        # Arrange
        width = number(r"PHP and PLP are always (\d+) bit", quote("registerTransferWidths"))
        cpus = {opcode: wide((opcode,), m8=False, x8=False, s=0x1F80) for opcode in (0x08, 0x28)}

        # Act
        stepped = {opcode: cpu.step() for opcode, cpu in cpus.items()}

        # Assert
        self.assertEqual(
            {opcode: abs(cpus[opcode].s - 0x1F80) for opcode in stepped},
            {0x08: width // 8, 0x28: width // 8},
        )

    def test_a_right_shift_leaves_negative_clear_at_either_width(self) -> None:
        # Arrange
        column = quote("aluSupersedesNothing").split()[1]
        cpus = {width: wide((0x4A,), a=0xFFFF, m8=width == 8, n=True) for width in (8, 16)}

        # Act
        stepped = {width: cpu.step() for width, cpu in cpus.items()}

        # Assert
        self.assertEqual(
            {width: cpus[width].n for width in stepped}, dict.fromkeys(cpus, column != "0")
        )


class PinTest(unittest.TestCase):
    def test_memory_lock_covers_the_printed_last_cycles_of_each_named_instruction(self) -> None:
        # Arrange
        printed = quote("memoryLock")
        found = re.search(r"last (\w+) or (\w+) cycles of (.+?) memory", printed)
        assert found is not None
        named = re.split(r",\s*(?:and\s+)?", found.group(3))
        expected = {name: (NUMBERS[found.group(1)], NUMBERS[found.group(2)]) for name in named}

        # Act
        locks = {
            name: (trailing_locks(opcode, True), trailing_locks(opcode, False))
            for name, opcode in LOCKING.items()
        }

        # Assert
        self.assertEqual(locks, expected)

    def test_each_kind_of_cycle_carries_the_qualifiers_the_table_prints(self) -> None:
        # Arrange
        printed = re.findall(
            r"([01]) ([01]) (Internal Operation|Valid program address|Valid data address|OpCode fetch)",
            quote("addressQualification"),
        )
        cpu = wide((0xBD, 0xFF, 0x30), x=1, x8=True)

        # Act
        cpu.step()

        # Assert
        positions = QUALIFIED | {"Valid data address": len(cpu.trace) - 1}
        self.assertEqual(
            {
                kind: (int(cpu.trace[at][2][0] == "d"), int(cpu.trace[at][2][1] == "p"))
                for kind, at in positions.items()
            },
            {kind: (int(vda), int(vpa)) for vda, vpa, kind in printed},
        )

    def test_the_false_read_of_a_page_crossing_carries_neither_qualifier(self) -> None:
        # Arrange
        cpus = {base: wide((0xBD, base, 0x30), emulation=True, x=1) for base in (0x00, 0xFF)}

        # Act
        stepped = {base: cpu.step() for base, cpu in cpus.items()}

        # Assert
        self.assertEqual(
            {
                base: [address for address, _, pins in cpus[base].trace if pins[:2] == "--"]
                for base in stepped
            },
            {0x00: [], 0xFF: [0x003000]},
            quote("falseReadIsVisibleOnThePins"),
        )


class CycleNoteTest(unittest.TestCase):
    def test_an_unaligned_direct_register_costs_the_printed_cycle(self) -> None:
        # Arrange
        added = notes(quote("sixteenBitCycleShapes"))[2]

        # Act
        taken = [cycles((0xA5, 0x10), m8=True, d=d) for d in (0x0000, 0x0001)]

        # Assert
        self.assertEqual(taken[1] - taken[0], added)

    def test_crossing_writing_or_a_wide_index_each_cost_the_printed_cycle(self) -> None:
        # Arrange
        added = notes(quote("sixteenBitCycleShapes"))[4]
        base = cycles((0xBD, 0x00, 0x30), x=1, x8=True)

        # Act
        taken = {
            "page boundaries": cycles((0xBD, 0xFF, 0x30), x=1, x8=True),
            "write": cycles((0x9D, 0x00, 0x30), x=1, x8=True),
            "X=0": cycles((0xBD, 0x00, 0x30), x=1, x8=False),
        }

        # Assert
        self.assertEqual(
            {name: count - base for name, count in taken.items()},
            dict.fromkeys(taken, added),
        )

    def test_in_emulation_mode_the_modify_cycle_is_a_write(self) -> None:
        # Arrange
        printed = quote("sixteenBitCycleShapes")
        cpu = wide((0x0E, 0x00, 0x30), emulation=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(
            [pins[3] for _, _, pins in cpu.trace[-2:]],
            ["w", "w"] if "RWB is low during both write and modify cycles" in printed else [],
        )

    def test_an_indexed_shift_inside_a_page_takes_what_each_column_prints(self) -> None:
        # Arrange
        printed = re.findall(r"(\d+) cycles", quote("caveatsTableIsStableAcrossRevisions"))

        # Act
        taken = [str(column_cycles(model)) for model in CAVEAT_COLUMNS]

        # Assert
        self.assertEqual(taken, printed)


if __name__ == "__main__":
    unittest.main()
