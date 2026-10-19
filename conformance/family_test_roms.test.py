from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import ROOT

TEST_ROMS = ROOT / "conformance" / "testroms.json"

OUTCOMES = frozenset({"run", "read", "hosted"})

HELD_OUTCOMES = frozenset({"run", "read"})

DIGEST = re.compile(r"[0-9a-f]{64}")


def named_test(source: str, dotted: str) -> str | None:
    owner, _, method = dotted.rpartition(".")
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.ClassDef) and node.name == owner):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method:
                return ast.get_source_segment(source, item) or ""
    return None


def holding_problem(root: Path, held: str, name: str) -> str | None:
    file, _, dotted = held.partition("::")
    path = root / file
    if not path.is_file():
        return f"{held} names a file that is not there"
    body = named_test(path.read_text(), dotted)
    if body is None:
        return f"{held} names a test that is not there"
    if f'"{name}"' not in body and f"'{name}'" not in body:
        return f"{held} never reads {name} from the record"
    return None


def entry_problems(entry: dict[str, Any], root: Path) -> list[str]:
    name = str(entry.get("id", "")).strip()
    if not name:
        return ["an entry has no id"]
    problems = []
    if not DIGEST.fullmatch(str(entry.get("sha256", ""))):
        problems.append(f"{name}: sha256 is not 64 lowercase hex digits")
    outcome = entry.get("outcome")
    if outcome not in OUTCOMES:
        return [*problems, f"{name}: outcome is not one of run, read or hosted"]
    if outcome == "hosted":
        needs = entry.get("needs")
        if not (isinstance(needs, str) and needs.strip()):
            problems.append(f"{name}: hosted names nothing under needs")
        return problems
    held = entry.get("heldBy")
    if not isinstance(held, list) or not held:
        return [*problems, f"{name}: {outcome} is held by no test"]
    return problems + [
        f"{name}: {problem}"
        for one in held
        if (problem := holding_problem(root, str(one), name)) is not None
    ]


def unheld(record: Any, root: Path) -> list[str]:
    cartridges = record.get("cartridges") if isinstance(record, dict) else None
    if not isinstance(cartridges, list):
        return ["the record has no cartridges list"]
    if not cartridges:
        reason = record.get("none")
        return [] if isinstance(reason, str) and reason.strip() else ["no cartridge and no reason"]
    problems = [one for entry in cartridges for one in entry_problems(entry, root)]
    digests = [entry.get("sha256") for entry in cartridges]
    names = [entry.get("id") for entry in cartridges]
    if len(set(digests)) != len(digests):
        problems.append("a digest is listed twice")
    if len(set(names)) != len(names):
        problems.append("an id is listed twice")
    return problems


A_HOLDING_TEST = (
    "class CartridgeTest:\n"
    "    def test_the_exerciser_reports_no_error(self):\n"
    '        verdict = recorded("zexall")\n'
)

HELD = ["held.test.py::CartridgeTest.test_the_exerciser_reports_no_error"]

A_DIGEST = "ab" * 32


def a_folder_with_a_test(source: str = A_HOLDING_TEST) -> Path:
    folder = Path(tempfile.mkdtemp())
    (folder / "held.test.py").write_text(source)
    return folder


def a_cartridge(**fields: Any) -> dict[str, Any]:
    return {"id": "zexall", "sha256": A_DIGEST, **fields}


class EveryMemberRecordsItsTestCartridgesTest(unittest.TestCase):
    def test_the_member_keeps_the_record(self) -> None:
        # Arrange
        record = TEST_ROMS

        # Act
        kept = record.is_file()

        # Assert
        self.assertTrue(kept)

    @unittest.skipUnless(TEST_ROMS.is_file(), "this repository keeps no record")
    def test_every_cartridge_it_lists_is_run_read_or_waits_on_a_named_member(self) -> None:
        # Arrange
        record = json.loads(TEST_ROMS.read_text())

        # Act
        problems = unheld(record, ROOT)

        # Assert
        self.assertEqual(problems, [])


class TheRecordReaderTest(unittest.TestCase):
    def test_a_run_cartridge_held_by_a_test_that_reads_it_passes(self) -> None:
        # Arrange
        record = {"cartridges": [a_cartridge(outcome="run", heldBy=HELD)]}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, [])

    def test_a_read_cartridge_held_by_nothing_is_reported(self) -> None:
        # Arrange
        record = {"cartridges": [a_cartridge(outcome="read")]}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, ["zexall: read is held by no test"])

    def test_a_hosted_cartridge_naming_the_member_it_waits_on_passes(self) -> None:
        # Arrange
        record = {"cartridges": [a_cartridge(outcome="hosted", needs="a whole machine")]}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, [])

    def test_a_hosted_cartridge_naming_nothing_is_reported(self) -> None:
        # Arrange
        record = {"cartridges": [a_cartridge(outcome="hosted", needs=" ")]}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, ["zexall: hosted names nothing under needs"])

    def test_an_unknown_outcome_is_reported(self) -> None:
        # Arrange
        record = {"cartridges": [a_cartridge(outcome="skipped")]}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, ["zexall: outcome is not one of run, read or hosted"])

    def test_a_digest_that_is_not_sha256_is_reported(self) -> None:
        # Arrange
        record = {"cartridges": [a_cartridge(sha256="ABC", outcome="hosted", needs="x")]}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, ["zexall: sha256 is not 64 lowercase hex digits"])

    def test_an_entry_with_no_id_is_reported(self) -> None:
        # Arrange
        record = {"cartridges": [{"sha256": A_DIGEST, "outcome": "hosted", "needs": "x"}]}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, ["an entry has no id"])

    def test_a_test_file_that_is_not_there_is_reported(self) -> None:
        # Arrange
        record = {"cartridges": [a_cartridge(outcome="run", heldBy=["gone.test.py::A.test_b"])]}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(
            problems, ["zexall: gone.test.py::A.test_b names a file that is not there"]
        )

    def test_a_test_that_is_not_there_is_reported(self) -> None:
        # Arrange
        gone = "held.test.py::CartridgeTest.test_gone"

        # Act
        problems = unheld(
            {"cartridges": [a_cartridge(outcome="run", heldBy=[gone])]}, a_folder_with_a_test()
        )

        # Assert
        self.assertEqual(problems, [f"zexall: {gone} names a test that is not there"])

    def test_a_test_that_never_reads_the_cartridge_is_reported(self) -> None:
        # Arrange
        source = A_HOLDING_TEST.replace('"zexall"', '"other"')

        # Act
        problems = unheld(
            {"cartridges": [a_cartridge(outcome="run", heldBy=HELD)]}, a_folder_with_a_test(source)
        )

        # Assert
        self.assertEqual(problems, [f"zexall: {HELD[0]} never reads zexall from the record"])

    def test_a_cartridge_listed_twice_is_reported(self) -> None:
        # Arrange
        one = a_cartridge(outcome="hosted", needs="x")

        # Act
        problems = unheld({"cartridges": [one, one]}, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, ["a digest is listed twice", "an id is listed twice"])

    def test_an_empty_list_needs_a_reason(self) -> None:
        # Arrange
        record: dict[str, Any] = {"cartridges": []}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, ["no cartridge and no reason"])

    def test_an_empty_list_with_a_reason_passes(self) -> None:
        # Arrange
        record = {"cartridges": [], "none": "no test cartridge exercises a file format"}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, [])

    def test_a_record_without_the_list_is_reported(self) -> None:
        # Arrange
        record: dict[str, Any] = {}

        # Act
        problems = unheld(record, a_folder_with_a_test())

        # Assert
        self.assertEqual(problems, ["the record has no cartridges list"])


if __name__ == "__main__":
    unittest.main()
