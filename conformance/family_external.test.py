from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import ROOT

MANIFEST = ROOT / "artifacts.manifest.json"

FOLDER = "external"

SECTION = "external"

DIGESTS = {"crc32": 8, "md5": 32, "sha1": 40, "sha256": 64}

TEXT_FIELDS = ("label", "path", "common_filename")

CHECKOUT = "checkout"

COMMIT = re.compile("[0-9a-f]{40}")


def hex_of(width: int) -> re.Pattern[str]:
    return re.compile(f"[0-9a-f]{{{width}}}")


def path_problem(rel: Any) -> str | None:
    if not isinstance(rel, str) or not rel.strip():
        return "has no path"
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts or "\\" in rel:
        return f"{rel} is not a plain path inside {FOLDER}/"
    return None


def accepted_problems(name: str, entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{name}: an accepted entry is not an object"]
    problems = [
        f"{name}: {field} is not text"
        for field in TEXT_FIELDS
        if not (isinstance(entry.get(field), str) and entry[field].strip())
    ]
    if (problem := path_problem(entry.get("path"))) is not None:
        problems.append(f"{name}: {problem}")
    size = entry.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        problems.append(f"{name}: size is not a byte count")
    problems += [
        f"{name}: {field} is not {width} lowercase hex digits"
        for field, width in DIGESTS.items()
        if not hex_of(width).fullmatch(str(entry.get(field, "")))
    ]
    provenance = entry.get("provenance")
    if not (isinstance(provenance, dict) and str(provenance.get("db", "")).strip()):
        problems.append(f"{name}: provenance names no source")
    return problems


def checkout_problems(name: str, artifact: dict[str, Any]) -> list[str]:
    problems = []
    if (problem := path_problem(artifact.get("path"))) is not None:
        problems.append(f"{name}: {problem}")
    if not str(artifact.get("repository", "")).startswith("https://"):
        problems.append(f"{name}: the repository is not an https address")
    if not COMMIT.fullmatch(str(artifact.get("commit", ""))):
        problems.append(f"{name}: the commit is not 40 lowercase hex digits")
    if not str(artifact.get("fetchedBy", "")).strip():
        problems.append(f"{name}: nothing says how to fetch it")
    return problems


def common_problems(name: str, artifact: dict[str, Any], where: Path) -> list[str]:
    problems = []
    if not str(artifact.get("purpose", "")).strip():
        problems.append(f"{name}: no purpose")
    if not isinstance(artifact.get("required"), bool):
        problems.append(f"{name}: required is not true or false")
    used = artifact.get("usedBy")
    if not isinstance(used, list) or not used:
        problems.append(f"{name}: used by nothing")
    else:
        problems += [
            f"{name}: used by {one}, which is not here"
            for one in used
            if not (where / str(one)).is_file()
        ]
    return problems


def artifact_problems(name: str, artifact: Any, where: Path) -> list[str]:
    if not isinstance(artifact, dict):
        return [f"{name}: not an object"]
    problems = common_problems(name, artifact, where)
    if artifact.get("kind") == CHECKOUT:
        return problems + checkout_problems(name, artifact)
    if not isinstance(artifact.get("canonical_form"), dict):
        problems.append(f"{name}: no canonical form")
    accepted = artifact.get("accepted")
    if not isinstance(accepted, list) or not accepted:
        return [*problems, f"{name}: accepts nothing"]
    return problems + [one for entry in accepted for one in accepted_problems(name, entry)]


def manifest_problems(manifest: Any, where: Path) -> list[str]:
    held = manifest.get(SECTION) if isinstance(manifest, dict) else None
    if not isinstance(held, dict):
        return [f"the manifest has no {SECTION} mapping"]
    problems = [
        one for name, artifact in held.items() for one in artifact_problems(name, artifact, where)
    ]
    paths = [
        entry.get("path")
        for artifact in held.values()
        if isinstance(artifact, dict) and isinstance(artifact.get("accepted"), list)
        for entry in artifact["accepted"]
        if isinstance(entry, dict)
    ]
    if len(set(paths)) != len(paths):
        problems.append("a path is listed twice")
    return problems


def a_folder_holding(files: dict[str, str]) -> Path:
    where = Path(tempfile.mkdtemp())
    for rel, body in files.items():
        (where / rel).write_text(body)
    return where


def an_entry(**fields: Any) -> dict[str, Any]:
    return {
        "label": "the only release",
        "path": "set/abc.bin",
        "common_filename": "abc.bin",
        "size": 3,
        "crc32": "352441c2",
        "md5": "9" * 32,
        "sha1": "a" * 40,
        "sha256": "b" * 64,
        "provenance": {"db": "a pack"},
        **fields,
    }


def an_artifact(**fields: Any) -> dict[str, Any]:
    return {
        "required": False,
        "purpose": "what the census reads",
        "canonical_form": {"container": "raw"},
        "usedBy": ["tool.py"],
        "accepted": [an_entry()],
        **fields,
    }


def a_checkout(**fields: Any) -> dict[str, Any]:
    return {
        "kind": "checkout",
        "required": False,
        "purpose": "the suite the processor is held to",
        "usedBy": ["tool.py"],
        "path": "suites/z80",
        "repository": "https://example.org/suites.git",
        "commit": "c" * 40,
        "fetchedBy": "python3 -m conformance.fetch external/suites",
        **fields,
    }


READERS = a_folder_holding({"tool.py": ""})


class EveryMemberDeclaresWhatItReadsTest(unittest.TestCase):
    def test_the_member_keeps_a_manifest(self) -> None:
        # Arrange
        manifest = MANIFEST

        # Act
        kept = manifest.is_file()

        # Assert
        self.assertTrue(kept)

    def test_every_artifact_it_lists_is_identified_by_every_digest(self) -> None:
        # Arrange
        manifest = json.loads(MANIFEST.read_text())

        # Act
        problems = manifest_problems(manifest, ROOT)

        # Assert
        self.assertEqual(problems, [])


class TheManifestReaderTest(unittest.TestCase):
    def test_a_complete_artifact_passes(self) -> None:
        # Arrange
        manifest = {"artifacts": {"boot": {}}, "external": {"abc": an_artifact()}}

        # Act
        problems = manifest_problems(manifest, READERS)

        # Assert
        self.assertEqual(problems, [])

    def test_a_manifest_with_no_list_is_refused(self) -> None:
        # Arrange
        manifest = ["not", "an", "object"]

        # Act
        problems = manifest_problems(manifest, READERS)

        # Assert
        self.assertEqual(problems, ["the manifest has no external mapping"])

    def test_an_artifact_that_is_not_an_object_is_refused(self) -> None:
        # Arrange
        manifest = {"external": {"abc": "text"}}

        # Act
        problems = manifest_problems(manifest, READERS)

        # Assert
        self.assertEqual(problems, ["abc: not an object"])

    def test_an_artifact_missing_its_description_is_refused_on_each_field(self) -> None:
        # Arrange
        artifact = an_artifact(purpose="", required="no", canonical_form=None, usedBy=[])

        # Act
        problems = manifest_problems({"external": {"abc": artifact}}, READERS)

        # Assert
        self.assertEqual(
            problems,
            [
                "abc: no purpose",
                "abc: required is not true or false",
                "abc: used by nothing",
                "abc: no canonical form",
            ],
        )

    def test_a_reader_that_is_not_in_the_repository_is_refused(self) -> None:
        # Arrange
        artifact = an_artifact(usedBy=["gone.py"])

        # Act
        problems = manifest_problems({"external": {"abc": artifact}}, READERS)

        # Assert
        self.assertEqual(problems, ["abc: used by gone.py, which is not here"])

    def test_an_artifact_that_accepts_nothing_is_refused(self) -> None:
        # Arrange
        artifact = an_artifact(accepted=[])

        # Act
        problems = manifest_problems({"external": {"abc": artifact}}, READERS)

        # Assert
        self.assertEqual(problems, ["abc: accepts nothing"])

    def test_an_accepted_entry_that_is_not_an_object_is_refused(self) -> None:
        # Arrange
        artifact = an_artifact(accepted=["abc.bin"])

        # Act
        problems = manifest_problems({"external": {"abc": artifact}}, READERS)

        # Assert
        self.assertEqual(problems, ["abc: an accepted entry is not an object"])

    def test_an_entry_missing_its_identity_is_refused_on_each_field(self) -> None:
        # Arrange
        entry = an_entry(label="", size=True, crc32="XYZ", md5="", provenance={})
        del entry["path"]

        # Act
        problems = manifest_problems({"external": {"abc": an_artifact(accepted=[entry])}}, READERS)

        # Assert
        self.assertEqual(
            problems,
            [
                "abc: label is not text",
                "abc: path is not text",
                "abc: has no path",
                "abc: size is not a byte count",
                "abc: crc32 is not 8 lowercase hex digits",
                "abc: md5 is not 32 lowercase hex digits",
                "abc: provenance names no source",
            ],
        )

    def test_a_path_that_leaves_the_folder_is_refused(self) -> None:
        # Arrange
        entries = [an_entry(path="../abc.bin"), an_entry(path="/abc.bin"), an_entry(path="a\\b")]

        # Act
        problems = manifest_problems({"external": {"abc": an_artifact(accepted=entries)}}, READERS)

        # Assert
        self.assertEqual(
            problems,
            [
                "abc: ../abc.bin is not a plain path inside external/",
                "abc: /abc.bin is not a plain path inside external/",
                "abc: a\\b is not a plain path inside external/",
            ],
        )

    def test_a_path_listed_under_two_names_is_refused(self) -> None:
        # Arrange
        manifest = {"external": {"abc": an_artifact(), "abd": an_artifact()}}

        # Act
        problems = manifest_problems(manifest, READERS)

        # Assert
        self.assertEqual(problems, ["a path is listed twice"])

    def test_a_complete_checkout_passes(self) -> None:
        # Arrange
        manifest = {"external": {"z80": a_checkout()}}

        # Act
        problems = manifest_problems(manifest, READERS)

        # Assert
        self.assertEqual(problems, [])

    def test_a_checkout_missing_its_pin_is_refused_on_each_field(self) -> None:
        # Arrange
        checkout = a_checkout(path="../z80", repository="git@x:y", commit="c" * 12, fetchedBy="")

        # Act
        problems = manifest_problems({"external": {"z80": checkout}}, READERS)

        # Assert
        self.assertEqual(
            problems,
            [
                "z80: ../z80 is not a plain path inside external/",
                "z80: the repository is not an https address",
                "z80: the commit is not 40 lowercase hex digits",
                "z80: nothing says how to fetch it",
            ],
        )


if __name__ == "__main__":
    unittest.main()
