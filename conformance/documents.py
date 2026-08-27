"""Bring the documents down again, and refuse anything that is not what was read.

The documents are the publishers' rather than this project's, so what the
repository carries is their identity and this script, not the files. A reader who
runs it ends up with the same twelve documents that every citation in this
package was taken from, or with an error naming the one that differs.

A digest is the whole point. Two documents can share a title, a publisher and a
revision number and still not be the same file, and a citation against the wrong
one is worse than no citation, because it looks checked.

Usage:
    python3 -m conformance.documents [--check] [--only SUBSTRING]
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent / "docs"
"""Where the documents go, which is not where this script lives.

The folder is ignored by git, so a script inside it would be ignored too and the
identity of every document would exist on one machine. It lives beside the rest
of the record instead, and writes into the folder that is not carried.
"""

MANIFEST = Path(__file__).resolve().parent / "documents.json"

USAGE = "usage: documents.py [--check] [--only SUBSTRING]"

TIMEOUT = 120
"""Seconds to wait on one document, none of which is larger than a few megabytes."""

RENDERED = "renderedAs"
"""The key naming a PDF this project made from a document published as text."""

PRINTED = "printedFromPage"
"""The key marking a document that was published as a page and printed to PDF.

A print is not reproducible. A different browser, a different version of the same
browser, or the page having changed since all give a different file, so the digest
identifies this print rather than the page it came from. Fetching the address
would return the page's markup, which would overwrite the thing that was read, so
these are verified and never downloaded.
"""


class Refused(Exception):
    """A document arrived that is not the one recorded."""


def documents(path: Path | str | None = None) -> list[dict[str, Any]]:
    with Path(path or MANIFEST).open() as handle:
        held: list[dict[str, Any]] = json.load(handle)["documents"]
    return held


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(entry: dict[str, Any], where: Path) -> None:
    """That the file on disk is the one the manifest names, by digest and by size."""
    path = where / str(entry["file"])
    if not path.is_file():
        raise Refused(f"{entry['file']} is not here")
    found = digest(path)
    if found != entry["sha256"]:
        raise Refused(f"{entry['file']} is a different file: {found}")
    if path.stat().st_size != entry["bytes"]:
        raise Refused(f"{entry['file']} is {path.stat().st_size} bytes, not {entry['bytes']}")


def download(entry: dict[str, Any], where: Path) -> None:
    """One document, from the publisher, into the place the manifest names.

    Only ever called for a document the publisher serves as a file. A page that
    was printed to PDF is verified and left alone, because fetching its address
    would replace it with markup.
    """
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
