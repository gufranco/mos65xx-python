import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mos65xx
from mos65xx import version


class VersionTest(unittest.TestCase):
    def test_the_version_is_three_numbers(self):
        parts = version.VERSION.split(".")

        self.assertEqual(len(parts), 3)
        self.assertTrue(all(part.isdigit() for part in parts))

    def test_the_package_reports_the_same_version(self):
        self.assertEqual(mos65xx.__version__, version.VERSION)


if __name__ == "__main__":
    unittest.main()
