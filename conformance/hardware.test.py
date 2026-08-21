"""That the recorded manufacturer facts and the cores actually agree.

A datasheet fact copied into a file nobody checks is decoration, and it drifts.
Every entry in hardware.json that names a number this project uses is compared
against the code here, so a change to either side has to answer for itself.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import Memory, mos6502, wdc65816  # noqa: E402

HARDWARE = Path(__file__).resolve().parent / "hardware.json"


def declared() -> dict[str, Any]:
    held = json.loads(HARDWARE.read_text())
    assert isinstance(held, dict), f"{HARDWARE} does not hold an object"
    return held


def fact(name: str) -> dict[str, Any]:
    found = declared()["facts"][name]
    assert isinstance(found, dict), f"{name} is not recorded as a fact"
    return found


class DocumentTest(unittest.TestCase):
    """That the file names its sources well enough for somebody to go and check."""

    def test_every_document_is_named_with_a_revision_and_a_date_read(self) -> None:
        for named in declared()["documents"].values():
            for key in ("publisher", "title", "revision", "readOn"):
                self.assertIn(key, named)

    def test_and_says_where_the_copy_that_was_read_is_pinned(self) -> None:
        missing = [
            held["title"]
            for held in declared()["documents"].values()
            if "documents.json" not in held.get("pinnedIn", "")
        ]

        self.assertEqual(missing, [])

    def test_every_fact_says_which_document_it_came_from(self) -> None:
        known = set(declared()["documents"])

        for name, held in declared()["facts"].items():
            self.assertIn(held.get("document"), known, name)

    def test_every_fact_carries_the_words_it_was_read_from(self) -> None:
        def quoted(held: dict[str, Any]) -> bool:
            if "quote" in held:
                return True
            return any(quoted(one) for one in held.values() if isinstance(one, dict))

        for name, held in declared()["facts"].items():
            self.assertTrue(quoted(held), name)

    def test_the_authority_order_is_written_down(self) -> None:
        self.assertGreaterEqual(len(declared()["authority"]["order"]), 2)


class VectorTest(unittest.TestCase):
    """That the addresses the cores read are the addresses the pins describe."""

    def test_the_native_break_vector_is_the_one_this_project_uses(self) -> None:
        self.assertEqual(wdc65816.BREAK_VECTOR, 0x00FFE6)

    def test_the_native_coprocessor_vector_is_too(self) -> None:
        self.assertEqual(wdc65816.COP_VECTOR, 0x00FFE4)

    def test_the_emulation_vectors_are_the_ones_the_table_prints(self) -> None:
        emulation = fact("vectors")["emulation"]

        self.assertEqual(
            (wdc65816.EMULATION_BREAK_VECTOR, wdc65816.EMULATION_COP_VECTOR),
            (emulation["irqAndBreak"], emulation["cop"]),
        )

    def test_the_reset_vector_is_the_same_in_both_modes(self) -> None:
        self.assertEqual(wdc65816.RESET_VECTOR, fact("vectors")["emulation"]["reset"])

    def test_the_six_five_oh_two_break_vector_matches_the_emulation_one(self) -> None:
        self.assertEqual(mos6502.BREAK_VECTOR, fact("vectors")["emulation"]["irqAndBreak"] & 0xFFFF)

    def test_the_native_vectors_sit_in_the_block_the_document_names(self) -> None:
        native = fact("vectors")["native"]

        for name, address in native.items():
            if isinstance(address, int):
                self.assertTrue(0x00FFE0 <= address <= 0x00FFEF, name)

    def test_the_erratum_is_recorded_rather_than_quietly_ignored(self) -> None:
        held = fact("vectors")["erratumInTable6_3"]

        for key in ("quote", "whyItIsAnErratum", "measured", "whatThisProjectUses", "notSettled"):
            self.assertIn(key, held)

    def test_and_names_the_two_native_vectors_no_suite_covers(self) -> None:
        self.assertIn("hardware interrupt", fact("vectors")["erratumInTable6_3"]["notSettled"])


class ResetStateTest(unittest.TestCase):
    """That a reset leaves the part where the document says it leaves it."""

    def machine(self) -> Any:
        return wdc65816.Cpu(Memory(0x1000000, fill=0), seed=99)

    def test_the_direct_register_and_both_banks_are_cleared(self) -> None:
        cpu = self.machine()

        self.assertEqual((cpu.d, cpu.db, cpu.pb), (0x0000, 0x00, 0x00))

    def test_the_stack_high_byte_is_one_and_the_low_byte_is_not_defined(self) -> None:
        cpu = self.machine()

        self.assertEqual(cpu.s & 0xFF00, 0x0100)

    def test_the_index_high_bytes_are_cleared(self) -> None:
        cpu = self.machine()

        self.assertEqual((cpu.x & 0xFF00, cpu.y & 0xFF00), (0x0000, 0x0000))

    def test_the_widths_are_forced_narrow_and_the_part_is_in_emulation_mode(self) -> None:
        cpu = self.machine()

        self.assertEqual((cpu.emulation, cpu.m8, cpu.x8), (True, True, True))

    def test_decimal_is_off_and_interrupts_are_disabled(self) -> None:
        cpu = self.machine()

        self.assertEqual((cpu.decimal, cpu.irq_disable), (False, True))

    def test_the_undefined_registers_are_not_all_zero(self) -> None:
        cpu = self.machine()

        self.assertNotEqual((cpu.a, cpu.x, cpu.y, cpu.s & 0xFF), (0, 0, 0, 0))

    def test_a_wait_or_a_stop_does_not_survive_a_reset(self) -> None:
        cpu = self.machine()
        cpu.stopped = cpu.waiting = True

        cpu.reset(seed=99)

        self.assertEqual((cpu.stopped, cpu.waiting), (False, False))


class InterruptEffectTest(unittest.TestCase):
    """That an interrupt does the two things to the status register it must."""

    def broken(self, emulation: bool) -> Any:
        memory = Memory(0x1000000, fill=0)
        cpu = wdc65816.Cpu(memory, reset=False)
        cpu.emulation = emulation
        cpu.decimal = True
        cpu.irq_disable = False
        cpu.pb, cpu.pc = 0x00, 0x8000
        memory.write8(0x008000, 0x00)
        cpu.step()
        return cpu

    def test_decimal_is_cleared_in_native_mode(self) -> None:
        self.assertFalse(self.broken(emulation=False).decimal)

    def test_decimal_is_cleared_in_emulation_mode_too(self) -> None:
        self.assertFalse(self.broken(emulation=True).decimal)

    def test_interrupts_are_disabled_in_native_mode(self) -> None:
        self.assertTrue(self.broken(emulation=False).irq_disable)

    def test_interrupts_are_disabled_in_emulation_mode_too(self) -> None:
        self.assertTrue(self.broken(emulation=True).irq_disable)

    def test_the_program_bank_is_cleared(self) -> None:
        self.assertEqual(self.broken(emulation=False).pb, 0x00)


class TransferWidthTest(unittest.TestCase):
    """That the four always-wide transfers are wide whatever the accumulator is."""

    def machine(self) -> Any:
        cpu = wdc65816.Cpu(Memory(0x1000000, fill=0), reset=False)
        cpu.emulation = False
        cpu.m8 = True
        cpu.x8 = True
        return cpu

    def test_the_stack_pointer_reaches_the_whole_accumulator(self) -> None:
        cpu = self.machine()
        cpu.s = 0x1234

        cpu.op_tsa("implied")

        self.assertEqual(cpu.a, 0x1234)

    def test_the_direct_register_takes_the_whole_accumulator(self) -> None:
        cpu = self.machine()
        cpu.a = 0x1234

        cpu.op_tad("implied")

        self.assertEqual(cpu.d, 0x1234)

    def test_and_gives_it_back_whole(self) -> None:
        cpu = self.machine()
        cpu.d = 0x1234

        cpu.op_tda("implied")

        self.assertEqual(cpu.a, 0x1234)

    def test_the_stack_takes_the_whole_accumulator_in_native_mode(self) -> None:
        cpu = self.machine()
        cpu.a = 0x1234

        cpu.op_tas("implied")

        self.assertEqual(cpu.s, 0x1234)

    def test_but_only_its_low_byte_in_emulation_mode(self) -> None:
        cpu = self.machine()
        cpu.emulation = True
        cpu.a = 0x1234

        cpu.op_tas("implied")

        self.assertEqual(cpu.s, 0x0134)


class HonestyTest(unittest.TestCase):
    """That the entries with nothing behind them say so."""

    def test_the_late_arriving_rotate_is_recorded_as_not_modelled(self) -> None:
        self.assertIn("notModelled", fact("nmosRorArrivedLate"))

    def test_the_pin_this_project_does_not_drive_says_so(self) -> None:
        self.assertIn("Nothing in this project drives it", fact("memoryLock")["note"])

    def test_the_two_places_the_document_contradicts_itself_are_both_recorded(self) -> None:
        self.assertIn("contradictedBy", fact("indirectJumpBanks"))
        self.assertIn("whyItIsAnErratum", fact("vectors")["erratumInTable6_3"])


if __name__ == "__main__":
    unittest.main()
