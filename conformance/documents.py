from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent / "docs"

MANIFEST = Path(__file__).resolve().parent / "documents.json"

USAGE = "usage: documents.py [--check] [--only SUBSTRING]"

TIMEOUT = 120

RENDERED = "renderedAs"

PRINTED = "printedFromPage"


class Refused(Exception): ...


def documents(path: Path | str | None = None) -> list[dict[str, Any]]:
    with Path(path or MANIFEST).open() as handle:
        held: list[dict[str, Any]] = json.load(handle)["documents"]
    return held


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(entry: dict[str, Any], where: Path) -> None:
    path = where / str(entry["file"])
    if not path.is_file():
        raise Refused(f"{entry['file']} is not here")
    found = digest(path)
    if found != entry["sha256"]:
        raise Refused(f"{entry['file']} is a different file: {found}")
    if path.stat().st_size != entry["bytes"]:
        raise Refused(f"{entry['file']} is {path.stat().st_size} bytes, not {entry['bytes']}")


def download(entry: dict[str, Any], where: Path) -> None:
    path = where / str(entry["file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        ["curl", "-sSL", "--fail", "--globoff", "-o", str(path), str(entry["retrievedFrom"])],
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT,
    )
    if done.returncode:
        raise Refused(f"{entry['file']} could not be fetched\n{done.stderr}")


def options(argv: Sequence[str]) -> tuple[bool, str | None]:
    check = False
    only: str | None = None
    rest = list(argv)
    while rest:
        item = rest.pop(0)
        if item == "--check":
            check = True
        elif item == "--only":
            if not rest:
                raise SystemExit(USAGE)
            only = rest.pop(0)
        else:
            raise SystemExit(USAGE)
    return check, only


def wanted(held: Sequence[dict[str, Any]], only: str | None) -> list[dict[str, Any]]:
    if only is None:
        return list(held)
    return [entry for entry in held if only in str(entry["file"])]


def main(argv: Sequence[str], where: Path | str | None = None) -> int:
    check, only = options(argv)
    root = Path(where or ROOT)
    held = wanted(documents(), only)
    if not held:
        print(f"no document matches {only}")
        return 1
    refused: list[str] = []
    for entry in held:
        printed = bool(entry.get(PRINTED))
        try:
            if not check and not printed:
                download(entry, root)
            verify(entry, root)
        except (Refused, subprocess.TimeoutExpired) as raised:
            refused.append(str(raised))
            continue
        made = entry.get(RENDERED)
        note = ", rendered as " + str(made) if made else ""
        note += ", printed from a page and not re-fetchable" if printed else ""
        print(f"ok rung {entry['rung']} {entry['file']}{note}")
    for line in refused:
        print(f"REFUSED {line}")
    print(f"{len(held) - len(refused)} of {len(held)} verified")
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
