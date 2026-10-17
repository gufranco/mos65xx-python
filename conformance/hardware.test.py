from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mos65xx  # noqa: E402
from mos65xx import Memory  # noqa: E402

HARDWARE = Path(__file__).resolve().parent / "hardware.json"

START = 0x8000

TARGET = 0x4321

TSC = 0x3B

TCD = 0x5B

TDC = 0x7B

TCS = 0x1B


def declared() -> dict[str, Any]:
    held = json.loads(HARDWARE.read_text())
    assert isinstance(held, dict), f"{HARDWARE} does not hold an object"
    return held


def fact(name: str) -> dict[str, Any]:
    found = declared()["facts"][name]
    assert isinstance(found, dict), f"{name} is not recorded as a fact"
    return found


def pointed(memory: Memory, vector: int) -> None:
    memory.write8(vector, TARGET & 0xFF)
    memory.write8(vector + 1, TARGET >> 8)


def about_to_run(opcode: int, vector: int, emulation: bool = False) -> Any:
    memory = Memory(0x1000000)
    memory.write8(START, opcode)
    pointed(memory, vector)
    cpu = mos65xx.Cpu("65816", memory)
    cpu.emulation = emulation
    cpu.pb, cpu.pc, cpu.s = 0x00, START, 0x01F0
    return cpu


def about_to_reset(model: str, vector: int) -> Any:
    memory = Memory(0x1000000)
    pointed(memory, vector)
    return mos65xx.Cpu(model, memory)


def a_6502_about_to_break(vector: int) -> Any:
    memory = Memory(0x10000)
    memory.write8(START, 0x00)
    pointed(memory, vector)
    cpu = mos65xx.Cpu("6502", memory)
    cpu.pc, cpu.s = START, 0xF0
    return cpu


def reset_part() -> Any:
    return mos65xx.Cpu("65816", Memory(0x1000000), seed=99)


def about_to_break(emulation: bool, bank: int = 0x00) -> Any:
    memory = Memory(0x1000000)
    cpu = mos65xx.Cpu("65816", memory)
    cpu.emulation = emulation
    cpu.decimal = True
    cpu.irq_disable = False
    cpu.pb, cpu.pc = bank, START
    memory.write8(bank << 16 | START, 0x00)
    return cpu


def about_to_transfer(opcode: int, emulation: bool = False, **registers: int) -> Any:
    memory = Memory(0x1000000)
    memory.write8(START, opcode)
    cpu = mos65xx.Cpu("65816", memory)
    cpu.emulation = False
    cpu.m8 = True
    cpu.x8 = True
    cpu.emulation = emulation
    cpu.pb, cpu.pc = 0x00, START
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu


class DocumentTest(unittest.TestCase):
    def test_every_document_is_named_with_a_revision_and_a_date_read(self) -> None:
        # Arrange
        documents = declared()["documents"]

        # Act
        missing = [
            (name, key)
            for name, held in documents.items()
            for key in ("publisher", "title", "revision", "readOn")
            if key not in held
        ]

        # Assert
        self.assertEqual(missing, [])

    def test_and_says_where_the_copy_that_was_read_is_pinned(self) -> None:
        # Arrange
        documents = declared()["documents"]

        # Act
        missing = [
            held["title"]
            for held in documents.values()
            if "README.md" not in held.get("pinnedIn", "")
        ]

        # Assert
        self.assertEqual(missing, [])

    def test_and_that_place_is_one_the_repository_actually_carries(self) -> None:
        # Arrange
        readme = ROOT / "README.md"

        # Act
        carried = readme.is_file()

        # Assert
        self.assertTrue(carried)

    def test_every_fact_says_which_document_it_came_from(self) -> None:
        # Arrange
        known = set(declared()["documents"])

        # Act
        unknown = [
            name for name, held in declared()["facts"].items() if held.get("document") not in known
        ]

        # Assert
        self.assertEqual(unknown, [])

    def test_every_fact_carries_the_words_it_was_read_from(self) -> None:
        # Arrange
        def quoted(held: dict[str, Any]) -> bool:
            if "quote" in held:
                return True
            return any(quoted(one) for one in held.values() if isinstance(one, dict))

        # Act
        unquoted = [name for name, held in declared()["facts"].items() if not quoted(held)]

        # Assert
        self.assertEqual(unquoted, [])

    def test_the_authority_order_is_written_down(self) -> None:
        # Arrange
        authority = declared()["authority"]

        # Act
        order = authority["order"]

        # Assert
        self.assertGreaterEqual(len(order), 2)


class VectorTest(unittest.TestCase):
    def test_the_native_break_vector_is_the_one_this_project_uses(self) -> None:
        # Arrange
        cpu = about_to_run(0x00, fact("vectors")["native"]["brk"])

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pb, cpu.pc), (0x00, TARGET))

    def test_the_native_coprocessor_vector_is_too(self) -> None:
        # Arrange
        cpu = about_to_run(0x02, fact("vectors")["native"]["cop"])

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pb, cpu.pc), (0x00, TARGET))

    def test_the_emulation_break_vector_is_the_one_the_table_prints(self) -> None:
        # Arrange
        cpu = about_to_run(0x00, fact("vectors")["emulation"]["irqAndBreak"], emulation=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, TARGET)

    def test_and_the_emulation_coprocessor_vector_too(self) -> None:
        # Arrange
        cpu = about_to_run(0x02, fact("vectors")["emulation"]["cop"], emulation=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, TARGET)

    def test_the_reset_vector_is_the_one_the_table_prints(self) -> None:
        # Arrange
        cpu = about_to_reset("65816", fact("vectors")["emulation"]["reset"])

        # Act
        cpu.reset()

        # Assert
        self.assertEqual((cpu.pb, cpu.pc), (0x00, TARGET))

    def test_the_six_five_oh_two_break_vector_matches_the_emulation_one(self) -> None:
        # Arrange
        cpu = a_6502_about_to_break(fact("vectors")["emulation"]["irqAndBreak"] & 0xFFFF)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, TARGET)

    def test_the_native_vectors_sit_in_the_block_the_document_names(self) -> None:
        # Arrange
        native = fact("vectors")["native"]

        # Act
        outside = [
            name
            for name, address in native.items()
            if isinstance(address, int)
            and not isinstance(address, bool)
            and not 0x00FFE0 <= address <= 0x00FFEF
        ]

        # Assert
        self.assertEqual(outside, [])

    def test_the_erratum_is_recorded_rather_than_quietly_ignored(self) -> None:
        # Arrange
        keys = ("quote", "whyItIsAnErratum", "measured", "whatThisProjectUses", "notSettled")

        # Act
        held = fact("vectors")["erratumInTable6_3"]

        # Assert
        self.assertEqual([key for key in keys if key not in held], [])

    def test_and_names_the_two_native_vectors_no_suite_covers(self) -> None:
        # Arrange
        erratum = fact("vectors")["erratumInTable6_3"]

        # Act
        unsettled = erratum["notSettled"]

        # Assert
        self.assertIn("hardware interrupt", unsettled)


class ResetStateTest(unittest.TestCase):
    def test_the_direct_register_and_both_banks_are_cleared(self) -> None:
        # Arrange
        cpu = reset_part()

        # Act
        cpu.reset(99)

        # Assert
        self.assertEqual((cpu.d, cpu.db, cpu.pb), (0x0000, 0x00, 0x00))

    def test_the_stack_high_byte_is_one_and_the_low_byte_is_not_defined(self) -> None:
        # Arrange
        cpu = reset_part()

        # Act
        cpu.reset(99)

        # Assert
        self.assertEqual(cpu.s & 0xFF00, 0x0100)

    def test_the_index_high_bytes_are_cleared(self) -> None:
        # Arrange
        cpu = reset_part()

        # Act
        cpu.reset(99)

        # Assert
        self.assertEqual((cpu.x & 0xFF00, cpu.y & 0xFF00), (0x0000, 0x0000))

    def test_the_widths_are_forced_narrow_and_the_part_is_in_emulation_mode(self) -> None:
        # Arrange
        cpu = reset_part()

        # Act
        cpu.reset(99)

        # Assert
        self.assertEqual((cpu.emulation, cpu.m8, cpu.x8), (True, True, True))

    def test_decimal_is_off_and_interrupts_are_disabled(self) -> None:
        # Arrange
        cpu = reset_part()

        # Act
        cpu.reset(99)

        # Assert
        self.assertEqual((cpu.decimal, cpu.irq_disable), (False, True))

    def test_the_undefined_registers_are_not_all_zero(self) -> None:
        # Arrange
        cpu = reset_part()

        # Act
        cpu.reset(99)

        # Assert
        self.assertNotEqual((cpu.a, cpu.x, cpu.y, cpu.s & 0xFF), (0, 0, 0, 0))

    def test_a_wait_or_a_stop_does_not_survive_a_reset(self) -> None:
        # Arrange
        cpu = reset_part()
        cpu.stopped = cpu.waiting = True

        # Act
        cpu.reset(seed=99)

        # Assert
        self.assertEqual((cpu.stopped, cpu.waiting), (False, False))


class InterruptEffectTest(unittest.TestCase):
    def test_decimal_is_cleared_in_native_mode(self) -> None:
        # Arrange
        cpu = about_to_break(emulation=False)

        # Act
        cpu.step()

        # Assert
        self.assertFalse(cpu.decimal)

    def test_decimal_is_cleared_in_emulation_mode_too(self) -> None:
        # Arrange
        cpu = about_to_break(emulation=True)

        # Act
        cpu.step()

        # Assert
        self.assertFalse(cpu.decimal)

    def test_interrupts_are_disabled_in_native_mode(self) -> None:
        # Arrange
        cpu = about_to_break(emulation=False)

        # Act
        cpu.step()

        # Assert
        self.assertTrue(cpu.irq_disable)

    def test_interrupts_are_disabled_in_emulation_mode_too(self) -> None:
        # Arrange
        cpu = about_to_break(emulation=True)

        # Act
        cpu.step()

        # Assert
        self.assertTrue(cpu.irq_disable)

    def test_the_program_bank_is_cleared(self) -> None:
        # Arrange
        cpu = about_to_break(emulation=False, bank=0x12)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pb, 0x00)


class TransferWidthTest(unittest.TestCase):
    def test_the_stack_pointer_reaches_the_whole_accumulator(self) -> None:
        # Arrange
        cpu = about_to_transfer(TSC, s=0x1234)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x1234)

    def test_the_direct_register_takes_the_whole_accumulator(self) -> None:
        # Arrange
        cpu = about_to_transfer(TCD, a=0x1234)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.d, 0x1234)

    def test_and_gives_it_back_whole(self) -> None:
        # Arrange
        cpu = about_to_transfer(TDC, d=0x1234)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.a, 0x1234)

    def test_the_stack_takes_the_whole_accumulator_in_native_mode(self) -> None:
        # Arrange
        cpu = about_to_transfer(TCS, a=0x1234)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.s, 0x1234)

    def test_but_only_its_low_byte_in_emulation_mode(self) -> None:
        # Arrange
        cpu = about_to_transfer(TCS, emulation=True, a=0x1234)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.s, 0x0134)


if __name__ == "__main__":
    unittest.main()
