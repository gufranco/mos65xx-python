"""That the issue templates ask for what they say they ask for.

A form field is required when `validations:` sits beside `attributes:`. Indent it
one level further and it becomes an unknown key inside `attributes:`, which
GitHub accepts in silence and renders as an optional field. The form still works,
still looks right in review, and quietly stops collecting the thing it was
written to collect.

This reads the text rather than parsing it. A parser would need PyYAML, and the
package promises no dependencies, so a check that forced one on anybody running
the suite would cost more than it is worth. The indentation in these files is
fixed by the schema GitHub defines, which is what makes the text answerable.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"

BESIDE_ATTRIBUTES = "    validations:"
"""Four spaces: a key of the body item, which is where it belongs."""

INSIDE_ATTRIBUTES = "      validations:"
"""Six spaces: a key of `attributes`, where GitHub ignores it."""


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
    """That the check above reports the fault rather than sailing past it."""

    def test_a_validation_inside_attributes_is_found(self) -> None:
        text = "  - type: input\n    attributes:\n      label: x\n      validations:\n        required: true\n"

        self.assertEqual(misplaced(text), [4])

    def test_a_validation_beside_attributes_is_not(self) -> None:
        text = "  - type: input\n    attributes:\n      label: x\n    validations:\n      required: true\n"

        self.assertEqual(misplaced(text), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
