from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"

BESIDE_ATTRIBUTES = "    validations:"

INSIDE_ATTRIBUTES = "      validations:"


def forms() -> list[Path]:
    return sorted(path for path in TEMPLATES.glob("*.yml") if path.name != "config.yml")


def misplaced(text: str) -> list[int]:
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if line.startswith(INSIDE_ATTRIBUTES)
    ]


class RequiredFieldTest(unittest.TestCase):
    def test_there_are_forms_to_check(self) -> None:
        self.assertGreater(len(forms()), 0)

    def test_no_form_hides_a_validation_inside_its_attributes(self) -> None:
        found = {
            path.name: misplaced(path.read_text())
            for path in forms()
            if misplaced(path.read_text())
        }

        self.assertEqual(found, {})

    def test_every_form_marks_something_required(self) -> None:
        without = [path.name for path in forms() if BESIDE_ATTRIBUTES not in path.read_text()]

        self.assertEqual(without, [])


class CheckerTest(unittest.TestCase):
    def test_a_validation_inside_attributes_is_found(self) -> None:
        text = "  - type: input\n    attributes:\n      label: x\n      validations:\n        required: true\n"

        self.assertEqual(misplaced(text), [4])

    def test_a_validation_beside_attributes_is_not(self) -> None:
        text = "  - type: input\n    attributes:\n      label: x\n    validations:\n      required: true\n"

        self.assertEqual(misplaced(text), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
