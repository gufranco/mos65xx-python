from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import FLAG_X, Cpu, Memory

ROOT = Path(__file__).resolve().parent.parent

VECTORS = json.loads((ROOT / "conformance" / "hardware.json").read_text())["facts"]["vectors"]

NATIVE = VECTORS["native"]

EMULATION = VECTORS["emulation"]

BREAK_BIT = 0x10

TARGET = 0x9000


def part(emulation: bool, wide: bool = True) -> tuple[Any, Any]:
    memory = Memory(0x1000000)
    cpu = Cpu("65816", memory)
    cpu.emulation = False
    cpu.d = cpu.db = 0x00
    cpu.emulation = emulation
    if not emulation and wide:
        cpu.m8 = cpu.x8 = False
    cpu.pb, cpu.pc = 0x00, 0x8000
    cpu.s = 0x01FF if emulation else 0x1FFF
    return cpu, memory


def software(opcode: int, emulation: bool) -> tuple[Any, Any]:
    cpu, memory = part(emulation)
    memory.write8(0x008000, opcode)
    return cpu, memory


def interrupted(emulation: bool, vector: int, target: int = TARGET) -> tuple[Any, Any]:
    cpu, memory = part(emulation)
    cpu.pb = 0x12
    cpu.db = 0x7E
    cpu.irq_disable = False
    memory.write8(vector, target & 0xFF)
    memory.write8(vector + 1, target >> 8)
    return cpu, memory


class SoftwareInterruptTest(unittest.TestCase):
    def test_a_break_in_emulation_mode_sets_the_break_flag_it_pushes(self) -> None:
        # Arrange
        cpu, memory = software(0x00, emulation=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x0001FD) & BREAK_BIT, BREAK_BIT)

    def test_a_cop_in_emulation_mode_also_pushes_that_bit_set(self) -> None:
        # Arrange
        cpu, memory = software(0x02, emulation=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x0001FD) & BREAK_BIT, BREAK_BIT)

    def test_native_mode_pushes_that_bit_as_the_index_width_instead(self) -> None:
        # Arrange
        cpu, memory = software(0x00, emulation=False)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x001FFC) & FLAG_X, 0x00)

    def test_a_software_interrupt_skips_its_signature_byte(self) -> None:
        # Arrange
        cpu, memory = software(0x02, emulation=True)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x0001FE) | (memory.read8(0x0001FF) << 8), 0x8002)

    def test_a_break_in_emulation_mode_takes_its_own_vector(self) -> None:
        # Arrange
        cpu, memory = software(0x00, emulation=True)
        memory.write8(EMULATION["irqAndBreak"], 0x00)
        memory.write8(EMULATION["irqAndBreak"] + 1, 0x90)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0x9000)

    def test_a_cop_in_emulation_mode_takes_its_own_vector(self) -> None:
        # Arrange
        cpu, memory = software(0x02, emulation=True)
        memory.write8(EMULATION["cop"], 0x00)
        memory.write8(EMULATION["cop"] + 1, 0xA0)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(cpu.pc, 0xA000)

    def test_a_break_in_native_mode_pushes_the_program_bank(self) -> None:
        # Arrange
        cpu, memory = software(0x00, emulation=False)
        memory.write8(0x001FFF, 0xEE)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((memory.read8(0x001FFF), cpu.s), (0x00, 0x1FFB))


class SixteenBitImmediateTest(unittest.TestCase):
    def test_setting_status_bits_takes_one_operand_byte_whatever_the_width(self) -> None:
        # Arrange
        cpu, memory = part(emulation=False)
        memory.write8(0x008000, 0xE2)
        memory.write8(0x008001, 0x42)
        memory.write8(0x008002, 0xEA)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pc, cpu.v, cpu.m8, cpu.x8), (0x8002, True, False, False))

    def test_running_until_a_condition_hands_the_part_back(self) -> None:
        # Arrange
        cpu, memory = part(emulation=False)
        memory.write8(0x008000, 0xEA)

        # Act
        returned = cpu.run_until(lambda machine: machine.steps > 0)

        # Assert
        self.assertIs(returned, cpu)


class HardwareInterruptTest(unittest.TestCase):
    def test_a_native_interrupt_pushes_four_bytes(self) -> None:
        # Arrange
        cpu, _ = interrupted(False, NATIVE["irq"])

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(cpu.s, 0x1FFB)

    def test_and_an_emulation_interrupt_pushes_three(self) -> None:
        # Arrange
        cpu, _ = interrupted(True, EMULATION["irqAndBreak"])

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(cpu.s, 0x01FC)

    def test_the_program_bank_goes_out_first_in_native_mode(self) -> None:
        # Arrange
        cpu, memory = interrupted(False, NATIVE["irq"])

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(memory.read8(0x001FFF), 0x12)

    def test_the_return_address_is_the_instruction_that_would_have_run(self) -> None:
        # Arrange
        cpu, memory = interrupted(False, NATIVE["irq"])

        # Act
        cpu.irq()

        # Assert
        self.assertEqual((memory.read8(0x001FFE), memory.read8(0x001FFD)), (0x80, 0x00))

    def test_the_pushed_status_keeps_its_index_width_bit_in_native_mode(self) -> None:
        # Arrange
        cpu, memory = interrupted(False, NATIVE["irq"])
        cpu.x8 = True

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(memory.read8(0x001FFC) & FLAG_X, FLAG_X)

    def test_and_clears_that_bit_in_emulation_mode(self) -> None:
        # Arrange
        cpu, memory = interrupted(True, EMULATION["irqAndBreak"])

        # Act
        cpu.irq()

        # Assert
        self.assertEqual(memory.read8(0x0001FD) & BREAK_BIT, 0x00)

    def test_which_is_the_one_thing_that_separates_it_from_a_break(self) -> None:
        # Arrange
        cpu, memory = interrupted(True, EMULATION["irqAndBreak"])
        memory.write8(0x128000, 0x00)

        # Act
        cpu.step()

        # Assert
        self.assertEqual(memory.read8(0x0001FD) & BREAK_BIT, BREAK_BIT)

    def test_the_program_bank_is_cleared_and_the_data_bank_is_not(self) -> None:
        # Arrange
        cpu, _ = interrupted(False, NATIVE["irq"])

        # Act
        cpu.irq()

        # Assert
        self.assertEqual((cpu.pb, cpu.db), (0x00, 0x7E))

    def test_the_handler_runs_in_binary_with_further_requests_disabled(self) -> None:
        # Arrange
        cpu, _ = interrupted(False, NATIVE["irq"])
        cpu.decimal = True

        # Act
        cpu.irq()

        # Assert
        self.assertEqual((cpu.decimal, cpu.irq_disable), (False, True))

    def test_a_request_is_refused_while_the_disable_flag_is_set(self) -> None:
        # Arrange
        cpu, _ = interrupted(False, NATIVE["irq"])
        cpu.irq_disable = True

        # Act
        taken = cpu.irq()

        # Assert
        self.assertEqual((taken, cpu.pc), (False, 0x8000))

    def test_the_non_maskable_pin_is_taken_anyway(self) -> None:
        # Arrange
        cpu, _ = interrupted(False, NATIVE["nmi"], target=0x9100)
        cpu.irq_disable = True

        # Act
        cpu.nmi()

        # Assert
        self.assertEqual(cpu.pc, 0x9100)

    def test_an_abort_is_taken_anyway_as_well(self) -> None:
        # Arrange
        cpu, _ = interrupted(False, NATIVE["abort"], target=0x9200)
        cpu.irq_disable = True

        # Act
        cpu.abort()

        # Assert
        self.assertEqual(cpu.pc, 0x9200)

    def test_each_pin_has_its_own_vector_in_each_mode(self) -> None:
        # Arrange
        cases = [
            (emulation, pin, vector, 0x9000 + index * 0x100)
            for index, (emulation, pin, vector) in enumerate(
                (
                    (False, "irq", NATIVE["irq"]),
                    (False, "nmi", NATIVE["nmi"]),
                    (False, "abort", NATIVE["abort"]),
                    (True, "irq", EMULATION["irqAndBreak"]),
                    (True, "nmi", EMULATION["nmi"]),
                    (True, "abort", EMULATION["abort"]),
                )
            )
        ]
        parts = [
            (interrupted(emulation, vector, target)[0], pin)
            for emulation, pin, vector, target in cases
        ]

        # Act
        for cpu, pin in parts:
            getattr(cpu, pin)()

        # Assert
        self.assertEqual([cpu.pc for cpu, _ in parts], [target for *_, target in cases])

    def test_a_refused_request_still_ends_a_wait(self) -> None:
        # Arrange
        cpu, _ = interrupted(False, NATIVE["irq"])
        cpu.irq_disable = True
        cpu.waiting = True

        # Act
        taken = cpu.irq()

        # Assert
        self.assertEqual((taken, cpu.waiting), (False, False))

    def test_a_stopped_part_answers_nothing_at_all(self) -> None:
        # Arrange
        cpu, _ = interrupted(False, NATIVE["nmi"])
        cpu.stopped = True

        # Act
        taken = cpu.nmi()

        # Assert
        self.assertEqual((taken, cpu.pc), (False, 0x8000))

    def test_a_return_from_interrupt_restores_the_program_bank_too(self) -> None:
        # Arrange
        cpu, memory = interrupted(False, NATIVE["irq"])
        cpu.irq()
        memory.write8(0x009000, 0x40)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pb, cpu.pc), (0x12, 0x8000))

    def test_and_in_emulation_mode_leaves_the_bank_where_it_was(self) -> None:
        # Arrange
        cpu, memory = interrupted(True, EMULATION["irqAndBreak"])
        cpu.pb = 0x00
        cpu.irq()
        memory.write8(0x009000, 0x40)

        # Act
        cpu.step()

        # Assert
        self.assertEqual((cpu.pb, cpu.pc), (0x00, 0x8000))


if __name__ == "__main__":
    unittest.main(verbosity=2)
