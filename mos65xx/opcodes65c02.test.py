import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import TABLES, decode8, render8

EVERY_OPCODE = range(256)

BIT_PREFIXES = ("rmb", "smb", "bbr", "bbs")


def decoded(name: str, opcode: int) -> Any:
    return decode8(bytes([opcode, 0x34, 0x12]), 0, 0x8000, table=TABLES[name])


def mnemonics(name: str) -> list[str]:
    return [decoded(name, opcode).mnemonic for opcode in EVERY_OPCODE]


class TableTest(unittest.TestCase):
    def test_every_table_decodes_every_byte(self) -> None:
        # Arrange
        names = sorted(TABLES)

        # Act
        found = {name: [decoded(name, op).opcode for op in EVERY_OPCODE] for name in names}

        # Assert
        self.assertEqual(found, {name: list(range(256)) for name in names})

    def test_every_entry_is_an_opcode_and_at_most_two_operand_bytes(self) -> None:
        # Arrange
        names = sorted(TABLES)

        # Act
        sizes = {name: {decoded(name, op).size for op in EVERY_OPCODE} for name in names}

        # Assert
        self.assertEqual(sizes, {name: {1, 2, 3} for name in names})

    def test_none_of_the_three_parts_has_an_undocumented_instruction(self) -> None:
        # Arrange
        names = sorted(TABLES)

        # Act
        found = {
            name: [op for op in EVERY_OPCODE if decoded(name, op).undocumented] for name in names
        }

        # Assert
        self.assertEqual(found, {"65c02": [], "rockwell": [], "wdc": []})

    def test_every_instruction_with_an_operand_renders_it(self) -> None:
        # Arrange
        found = [decoded(name, op) for name in sorted(TABLES) for op in EVERY_OPCODE]

        # Act
        silent = [
            f"{one.mnemonic} {one.mode}"
            for one in found
            if one.size > 1 and "$" not in render8(one.mode, one.operand, one.address, one.size)
        ]

        # Assert
        self.assertEqual(silent, [])


class RevisionTest(unittest.TestCase):
    def test_the_three_parts_are_three_tables(self) -> None:
        # Arrange
        published = TABLES

        # Act
        names = sorted(published)

        # Assert
        self.assertEqual(names, ["65c02", "rockwell", "wdc"])

    def test_the_base_part_has_no_bit_instructions(self) -> None:
        # Arrange
        name = "65c02"

        # Act
        used = mnemonics(name)

        # Assert
        self.assertEqual([one for one in used if one.startswith(BIT_PREFIXES)], [])

    def test_the_rockwell_part_has_all_thirty_two_of_them(self) -> None:
        # Arrange
        name = "rockwell"

        # Act
        used = mnemonics(name)

        # Assert
        self.assertEqual(
            [sum(1 for one in used if one.startswith(prefix)) for prefix in BIT_PREFIXES],
            [8, 8, 8, 8],
        )

    def test_the_bit_instructions_sit_in_the_two_columns_that_carry_them(self) -> None:
        # Arrange
        columns = {0x07: "rmb", 0x87: "smb", 0x0F: "bbr", 0x8F: "bbs"}

        # Act
        found = [
            decoded("rockwell", column + bit * 0x10).mnemonic
            for column in columns
            for bit in range(8)
        ]

        # Assert
        self.assertEqual(
            found, [f"{prefix}{bit}" for prefix in columns.values() for bit in range(8)]
        )

    def test_only_the_wdc_part_can_be_stopped_or_made_to_wait(self) -> None:
        # Arrange
        cases = (("wdc", 0xDB), ("wdc", 0xCB), ("rockwell", 0xDB), ("65c02", 0xCB))

        # Act
        found = [decoded(name, opcode).mnemonic for name, opcode in cases]

        # Assert
        self.assertEqual(found, ["stp", "wai", "nop", "nop"])

    def test_the_two_later_parts_agree_everywhere_but_the_two_wdc_added(self) -> None:
        # Arrange
        rockwell = mnemonics("rockwell")

        # Act
        wdc = mnemonics("wdc")

        # Assert
        self.assertEqual([op for op in EVERY_OPCODE if rockwell[op] != wdc[op]], [0xCB, 0xDB])


class AdditionTest(unittest.TestCase):
    def test_the_instructions_the_cmos_part_added_are_all_there(self) -> None:
        # Arrange
        added = ("tsb", "trb", "stz", "bra", "phx", "phy", "plx", "ply")

        # Act
        used = set(mnemonics("65c02"))

        # Assert
        self.assertEqual([one for one in added if one not in used], [])

    def test_the_accumulator_can_be_incremented_and_decremented_on_its_own(self) -> None:
        # Arrange
        opcodes = (0x1A, 0x3A)

        # Act
        found = [(decoded("65c02", op).mnemonic, decoded("65c02", op).mode) for op in opcodes]

        # Assert
        self.assertEqual(found, [("inc", "accumulator"), ("dec", "accumulator")])

    def test_the_jump_through_a_pointer_can_be_indexed(self) -> None:
        # Arrange
        opcode = 0x7C

        # Act
        found = decoded("65c02", opcode)

        # Assert
        self.assertEqual((found.mnemonic, found.mode, found.size), ("jmp", "indirectX", 3))

    def test_the_bit_test_reaches_an_immediate_and_two_indexed_modes(self) -> None:
        # Arrange
        opcodes = (0x89, 0x34, 0x3C)

        # Act
        found = [(decoded("65c02", op).mnemonic, decoded("65c02", op).mode) for op in opcodes]

        # Assert
        self.assertEqual(found, [("bit", "immediate"), ("bit", "zeroPageX"), ("bit", "absoluteX")])

    def test_eight_instructions_gained_a_pointer_mode_with_no_index(self) -> None:
        # Arrange
        found = [decoded("65c02", op) for op in EVERY_OPCODE]

        # Act
        indirect = [one for one in found if render8(one.mode, 0x20, 0, one.size) == "($20)"]

        # Assert
        self.assertEqual(len(indirect), 8)


class NoOperationTest(unittest.TestCase):
    def test_the_lengths_the_suite_measured_are_the_lengths_in_the_table(self) -> None:
        # Arrange
        measured = {
            0x03: 1,
            0x0B: 1,
            0x02: 2,
            0x22: 2,
            0x42: 2,
            0x62: 2,
            0x07: 2,
            0x0F: 3,
            0xCB: 1,
            0xDB: 2,
        }

        # Act
        found = {op: (decoded("65c02", op).mnemonic, decoded("65c02", op).size) for op in measured}

        # Assert
        self.assertEqual(found, {op: ("nop", length) for op, length in measured.items()})

    def test_a_no_operation_that_takes_bytes_takes_them_from_nowhere_in_particular(self) -> None:
        # Arrange
        opcodes = (0x02, 0x22, 0x42, 0x62)

        # Act
        found = [decoded("65c02", op).mode for op in opcodes]

        # Assert
        self.assertEqual(found, ["immediate"] * 4)


if __name__ == "__main__":
    unittest.main()
