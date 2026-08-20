"""That each recorded disagreement is described honestly and matches the code.

A divergence file is worth having only if the behaviour it describes is the
behaviour the cores have. Each entry below is exercised: the code is driven into
exactly the case the entry is about, and what it does is compared against what
the entry claims this project does.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import Memory, wdc65816  # noqa: E402

DIVERGENCES = Path(__file__).resolve().parent / "divergences.json"

ALIGNED_PAGE = 0x0C00
"""A direct register with a clear low byte, which is when the page wrap applies."""


def declared() -> dict[str, Any]:
    held = json.loads(DIVERGENCES.read_text())
    assert isinstance(held, dict), f"{DIVERGENCES} does not hold an object"
    return held


def about(subject: str) -> dict[str, Any]:
    for one in declared()["divergences"]:
        found: dict[str, Any] = one
        if subject in found["subject"]:
            return found
    raise AssertionError(f"nothing recorded about {subject}")


class Watched(Memory):
    """Memory that remembers which addresses were read, in order."""

    def __init__(self) -> None:
        super().__init__(0x1000000, fill=0)
        self.seen: list[int] = []

    @override
    def read8(self, address: int) -> int:
        self.seen.append(address)
        return super().read8(address)


class ShapeTest(unittest.TestCase):
    """That every entry says the four things a reader needs."""

    def test_each_one_names_the_document_and_quotes_it(self) -> None:
        for one in declared()["divergences"]:
            self.assertIn("document", one["documentSays"], one["subject"])
            self.assertIn("quote", one["documentSays"], one["subject"])

    def test_each_one_says_what_was_measured(self) -> None:
        for one in declared()["divergences"]:
            self.assertIn("corpus", one["suiteSays"], one["subject"])

    def test_each_one_says_what_this_project_does(self) -> None:
        for one in declared()["divergences"]:
            self.assertTrue(one["whatThisProjectDoes"], one["subject"])

    def test_each_one_says_what_would_settle_it(self) -> None:
        for one in declared()["divergences"]:
            self.assertTrue(one["whatWouldSettleIt"], one["subject"])

    def test_asking_about_something_unrecorded_fails_rather_than_saying_nothing(self) -> None:
        with self.assertRaises(AssertionError):
            about("a disagreement nobody has found")


class DataBankOnInterruptTest(unittest.TestCase):
    """The first divergence, driven: does a software interrupt clear the bank."""

    def broken(self, emulation: bool) -> Any:
        memory = Memory(0x1000000, fill=0)
        cpu = wdc65816.Cpu(memory, reset=False)
        cpu.emulation = emulation
        cpu.db = 0x7E
        cpu.pb, cpu.pc = 0x00, 0x8000
        memory.write8(0x008000, 0x00)
        cpu.step()
        return cpu

    def test_the_data_bank_survives_a_break_in_emulation_mode(self) -> None:
        self.assertEqual(self.broken(emulation=True).db, 0x7E)

    def test_and_in_native_mode(self) -> None:
        self.assertEqual(self.broken(emulation=False).db, 0x7E)

    def test_which_is_what_the_entry_says_this_project_does(self) -> None:
        held = about("data bank register after a software interrupt")

        self.assertIn("leaves the data bank alone", held["whatThisProjectDoes"])

    def test_the_program_bank_is_cleared_either_way(self) -> None:
        self.assertEqual((self.broken(emulation=True).pb, self.broken(emulation=False).pb), (0, 0))


class PointerWrapTest(unittest.TestCase):
    """The second divergence, driven: one case per mode, read off the addresses."""

    def addresses(self, opcode: int) -> list[int]:
        memory = Watched()
        cpu = wdc65816.Cpu(memory, reset=False)
        cpu.emulation = True
        cpu.d = ALIGNED_PAGE
        cpu.x = cpu.y = 0x00
        cpu.pb, cpu.pc = 0x00, 0x8000
        memory.write8(0x008000, opcode)
        memory.write8(0x008001, 0xFF)
        del memory.seen[:]
        cpu.step()
        return [one for one in memory.seen if ALIGNED_PAGE <= one <= ALIGNED_PAGE + 0x101]

    def test_the_four_measured_modes_behave_as_the_recorded_cases_show(self) -> None:
        recorded = {
            one["mode"]: one for one in about("multi-byte pointer read")["suiteSays"]["cases"]
        }
        opcodes = {"(d,x)": 0xA1, "[d]": 0xA7, "[d],y": 0xB7, "PEI": 0xD4}

        for mode, opcode in opcodes.items():
            inside = all(address <= ALIGNED_PAGE + 0xFF for address in self.addresses(opcode)[1:])
            self.assertEqual(inside, "wrapped inside" in recorded[mode]["verdict"], mode)

    def test_the_two_unmeasured_modes_follow_the_document(self) -> None:
        for opcode in (0xB2, 0xB1):
            self.assertTrue(
                all(address <= ALIGNED_PAGE + 0xFF for address in self.addresses(opcode)[1:]),
                hex(opcode),
            )

    def test_and_the_entry_says_that_is_where_they_come_from(self) -> None:
        held = about("multi-byte pointer read")

        self.assertIn("(d) and (d),y", held["suiteSays"]["notCovered"])
        self.assertIn("document reading rather than a measurement", held["whatWouldSettleIt"])

    def test_nothing_wraps_when_the_direct_register_is_not_page_aligned(self) -> None:
        memory = Watched()
        cpu = wdc65816.Cpu(memory, reset=False)
        cpu.emulation = True
        cpu.d = ALIGNED_PAGE | 0x01
        cpu.pb, cpu.pc = 0x00, 0x8000
        memory.write8(0x008000, 0xB2)
        memory.write8(0x008001, 0xFE)
        del memory.seen[:]
        cpu.step()

        self.assertIn(ALIGNED_PAGE + 0x100, memory.seen)


if __name__ == "__main__":
    unittest.main()
