import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mos65xx
from mos65xx import doctor


class VersionTest(unittest.TestCase):
    def test_the_version_is_three_numbers(self) -> None:
        # Arrange
        reported = mos65xx.__version__

        # Act
        parts = reported.split(".")

        # Assert
        self.assertEqual([part.isdigit() for part in parts], [True, True, True])

    def test_the_package_reports_the_version_its_file_carries(self) -> None:
        # Arrange
        written = doctor.installed_version()

        # Act
        reported = mos65xx.__version__

        # Assert
        self.assertEqual(reported, written)


class SurfaceTest(unittest.TestCase):
    def test_everything_it_declares_is_reachable(self) -> None:
        # Arrange
        declared = mos65xx.__all__

        # Act
        missing = [name for name in declared if not hasattr(mos65xx, name)]

        # Assert
        self.assertEqual(missing, [])

    def test_reading_bytes_needs_no_machine_to_run_them_in(self) -> None:
        # Arrange
        code = bytes([0xEA, 0x60])

        # Act
        found = mos65xx.disassemble(code, 0, 0x008000)

        # Assert
        self.assertEqual([instruction.mnemonic for instruction in found], ["nop", "rts"])

    def test_a_truncated_instruction_is_refused_rather_than_guessed(self) -> None:
        # Arrange
        def attempt() -> Any:
            return mos65xx.decode(bytes([0xA9]), 0, 0x008000, m=True)

        # Act
        with self.assertRaises(mos65xx.Truncated) as raised:
            attempt()

        # Assert
        self.assertEqual(raised.exception.args, (0,))


if __name__ == "__main__":
    unittest.main()
