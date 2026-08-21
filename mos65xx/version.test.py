import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mos65xx
from mos65xx import version


class VersionTest(unittest.TestCase):
    def test_the_version_is_three_numbers(self) -> None:
        parts = version.VERSION.split(".")

        self.assertEqual(len(parts), 3)
        self.assertTrue(all(part.isdigit() for part in parts))

    def test_the_package_reports_the_same_version(self) -> None:
        self.assertEqual(mos65xx.__version__, version.VERSION)


class SurfaceTest(unittest.TestCase):
    def test_everything_it_declares_is_reachable(self) -> None:
        missing = [name for name in mos65xx.__all__ if not hasattr(mos65xx, name)]

        self.assertEqual(missing, [])

    def test_reading_bytes_needs_no_machine_to_run_them_in(self) -> None:
        found = mos65xx.disassemble(bytes([0xEA, 0x60]), 0, 0x008000)

        self.assertEqual([instruction.mnemonic for instruction in found], ["nop", "rts"])

    def test_a_truncated_instruction_is_refused_rather_than_guessed(self) -> None:
        with self.assertRaises(mos65xx.Truncated):
            mos65xx.decode(bytes([0xA9]), 0, 0x008000, m=True)


if __name__ == "__main__":
    unittest.main()
