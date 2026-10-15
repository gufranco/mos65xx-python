from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parent.parent

DOCUMENTS = ROOT / "docs" / "manufacturer"

RECORDS = ROOT / "conformance"

WINDOW = 5

BORROWED = 12

TABLE = re.compile(r"Table\s+(\d+(?:[-.]\d+)*)")

BAR = 0.4

DASHES = (0x2013, 0x2014, 0x2212)

SINGLES = (0x2018, 0x2019, 0x2032)

DOUBLES = (0x201C, 0x201D)

ELSEWHERE = ("suiteSays",)


class Verdict(NamedTuple):
    where: str
    quote: str
    document: str | None
    placed: int
    windows: int

    @property
    def found(self) -> bool:
        return bool(self.windows) and self.placed / self.windows >= BAR


def flatten(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    for code in DASHES:
        text = text.replace(chr(code), "-")
    for code in SINGLES:
        text = text.replace(chr(code), "'")
    for code in DOUBLES:
        text = text.replace(chr(code), '"')
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def windows(quote: str) -> list[str]:
    words = [one for one in re.split(r"\s+", quote) if one]
    if len(words) <= WINDOW:
        return [flatten(quote)]
    return [flatten(" ".join(words[at : at + WINDOW])) for at in range(len(words) - WINDOW + 1)]


def said(node: Any, trail: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{trail}.{key}" if trail else key
            if key.endswith(("quote", "Quote")) and isinstance(value, str):
                if not (node.get("assembled") or node.get("saysNothing")):
                    found.append((here, value))
            elif key.endswith(("quotes", "Quotes")) and isinstance(value, list):
                found.extend(
                    (f"{here}[{at}]", one) for at, one in enumerate(value) if isinstance(one, str)
                )
            elif key.endswith(("quotes", "Quotes")) and isinstance(value, dict):
                found.extend(
                    (f"{here}.{at}", one) for at, one in value.items() if isinstance(one, str)
                )
            else:
                found.extend(said(value, here))
    elif isinstance(node, list):
        for at, one in enumerate(node):
            found.extend(said(one, f"{trail}[{at}]"))
    return found


def quoted(records: Iterable[tuple[str, Any]] | None = None) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for name, held in loaded() if records is None else records:
        for where, quote in said(held, name):
            if not any(one in where for one in ELSEWHERE):
                found.append((where, quote))
    return found


PAGE_KEYS = frozenset(
    {
        "page",
        "pages",
        "manualPage",
        "printedPage",
        "printedPages",
        "pdfPage",
        "pdfPages",
        "printedPageRange",
        "section",
        "manualSection",
    }
)


LOCATOR = re.compile(r"\d+[.\-]\d|page|table|appendix|section", re.IGNORECASE)


def pointed(node: dict[str, Any]) -> bool:
    if PAGE_KEYS & set(node):
        return True
    for key in ("document", "source"):
        value = node.get(key)
        if isinstance(value, str) and LOCATOR.search(value):
            return True
    return False


def uncited(node: Any, inherited: bool = False, trail: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        here = inherited or pointed(node)
        for key, value in node.items():
            step = f"{trail}.{key}" if trail else key
            if key.endswith(("quote", "Quote")) and isinstance(value, str):
                if not here and not node.get("saysNothing"):
                    found.append(step)
            else:
                found.extend(uncited(value, here, step))
    elif isinstance(node, list):
        for at, one in enumerate(node):
            found.extend(uncited(one, inherited, f"{trail}[{at}]"))
    return found


def loaded() -> list[tuple[str, Any]]:
    return [(path.name, json.loads(path.read_text())) for path in sorted(RECORDS.glob("*.json"))]


def unpaged(records: Iterable[tuple[str, Any]] | None = None) -> list[str]:
    found: list[str] = []
    for name, held in loaded() if records is None else records:
        for where in uncited(held, False, name):
            if not any(one in where for one in ELSEWHERE):
                found.append(where)
    return found


def readable(path: Path, run: Any = None) -> str:
    runner = subprocess.run if run is None else run
    try:
        done = runner(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return flatten(done.stdout) + flatten(second(path))


def second(path: Path) -> str:
    beside = path.with_suffix(".txt")
    return beside.read_text(errors="replace") if beside.is_file() else ""


def library(where: Path | None = None, run: Any = None) -> dict[str, str]:
    folder = DOCUMENTS if where is None else where
    if not folder.is_dir():
        return {}
    return {path.name: readable(path, run) for path in sorted(folder.glob("*.pdf"))}


def verify(
    held: Iterable[tuple[str, str]] | None = None,
    books: dict[str, str] | None = None,
) -> list[Verdict]:
    books = library() if books is None else books
    found = []
    for where, quote in quoted() if held is None else held:
        parts = windows(quote)
        best, name = 0, None
        for title, body in books.items():
            placed = sum(1 for one in parts if one in body)
            if placed > best:
                best, name = placed, title
        found.append(Verdict(where, quote, name, best, len(parts)))
    return found


def misattributed(
    records: Iterable[tuple[str, Any]] | None = None,
    books: dict[str, str] | None = None,
) -> list[str]:
    held = library() if books is None else books
    found: list[str] = []
    for name, record in loaded() if records is None else records:
        files = _files(record)
        if not files:
            continue
        for where, document, quote in _quoted_with_document(record, name):
            wanted = files.get(document)
            if wanted is None or wanted not in held:
                continue
            parts = windows(quote)
            if not parts or any(one in held[wanted] for one in parts):
                continue
            elsewhere = [
                title
                for title, body in held.items()
                if title != wanted and any(one in body for one in parts)
            ]
            if elsewhere:
                found.append(
                    f"{where}: cites {document}, and the words are in"
                    f" {', '.join(sorted(elsewhere))} rather than in {wanted}"
                )
    return found


def _files(node: Any) -> dict[str, str]:
    found: dict[str, str] = {}
    if isinstance(node, dict):
        declared = node.get("documents")
        if isinstance(declared, dict):
            for key, value in declared.items():
                if isinstance(value, dict) and isinstance(value.get("file"), str):
                    found[key] = value["file"]
        for value in node.values():
            found.update(_files(value))
    elif isinstance(node, list):
        for one in node:
            found.update(_files(one))
    return found


def _quoted_with_document(node: Any, trail: str = "") -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        document = node.get("document")
        quote = node.get("quote")
        if isinstance(document, str) and isinstance(quote, str) and not node.get("saysNothing"):
            found.append((trail, document, quote))
        for key, value in node.items():
            found.extend(_quoted_with_document(value, f"{trail}.{key}" if trail else key))
    elif isinstance(node, list):
        for at, one in enumerate(node):
            found.extend(_quoted_with_document(one, f"{trail}[{at}]"))
    return found


def labelled(path: Path, run: Any = None) -> set[str]:
    runner = subprocess.run if run is None else run
    try:
        done = runner(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return set()
    return set(TABLE.findall(done.stdout + second(path)))


def catalogue(where: Path | None = None, run: Any = None) -> dict[str, set[str]]:
    folder = DOCUMENTS if where is None else where
    if not folder.is_dir():
        return {}
    return {path.name: labelled(path, run) for path in sorted(folder.glob("*.pdf"))}


def phantom(
    records: Iterable[tuple[str, Any]] | None = None,
    tables: dict[str, set[str]] | None = None,
) -> list[str]:
    held = catalogue() if tables is None else tables
    found: list[str] = []
    for name, record in loaded() if records is None else records:
        files = _files(record)
        if not files:
            continue
        for where, document, section in _sectioned(record, name):
            wanted = files.get(document)
            if wanted is None or wanted not in held:
                continue
            if not held[wanted]:
                continue
            for label in TABLE.findall(section):
                if label in held[wanted]:
                    continue
                elsewhere = sorted(one for one, has in held.items() if label in has)
                tail = f", and it is in {', '.join(elsewhere)}" if elsewhere else ""
                found.append(
                    f"{where}: cites {document} Table {label}, which {wanted} does not have{tail}"
                )
    return found


def _sectioned(node: Any, trail: str = "") -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        document = node.get("document")
        section = node.get("section")
        if isinstance(document, str) and isinstance(section, str):
            found.append((trail, document, section))
        for key, value in node.items():
            found.extend(_sectioned(value, f"{trail}.{key}" if trail else key))
    elif isinstance(node, list):
        for at, one in enumerate(node):
            found.extend(_sectioned(one, f"{trail}[{at}]"))
    return found


def borrowed(
    records: Iterable[tuple[str, Any]] | None = None,
    books: dict[str, str] | None = None,
) -> list[str]:
    held = library() if books is None else books
    found: list[str] = []
    for name, record in loaded() if records is None else records:
        for trail, text in _plain(record, name):
            if len(text.split()) < BORROWED:
                continue
            carried = sorted(one for one, body in held.items() if flatten(text) in body)
            if carried:
                found.append(
                    f"{trail}: {', '.join(carried)} carries these words, and the key"
                    f" is not one this checker reads"
                )
    return found


def _plain(node: Any, trail: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{trail}.{key}" if trail else key
            if key.endswith(("quote", "Quote", "quotes", "Quotes")):
                continue
            found.extend(_plain(value, here))
    elif isinstance(node, list):
        for at, one in enumerate(node):
            found.extend(_plain(one, f"{trail}[{at}]"))
    elif isinstance(node, str):
        found.append((trail, node))
    return found


def undeclared(records: Iterable[tuple[str, Any]] | None = None) -> list[str]:
    found: list[str] = []
    for name, held in loaded() if records is None else records:
        declared = _declared(held)
        if not declared:
            continue
        for where, document, _page in _cited(held, name):
            if document not in declared:
                found.append(f"{where}: cites {document!r}, which is not a declared document")
    return found


def _declared(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        held = node.get("documents")
        if isinstance(held, dict):
            found.update(held)
        for value in node.values():
            found.update(_declared(value))
    elif isinstance(node, list):
        for one in node:
            found.update(_declared(one))
    return found


def sections(records: Iterable[tuple[str, Any]] | None = None) -> list[str]:
    found: list[str] = []
    for name, held in loaded() if records is None else records:
        ranges = _ranges(held)
        if not ranges:
            continue
        for where, document, page in _cited(held, name):
            spans = ranges.get(document)
            if spans is None:
                continue
            if page is None:
                found.append(
                    f"{where}: cites {document}, which covers several parts, and names no filePage"
                )
            elif not any(low <= page <= high for low, high in spans):
                written = ", ".join(f"{low}-{high}" for low, high in spans)
                found.append(
                    f"{where}: names file page {page}, outside the {written} this part occupies in {document}"
                )
    return found


def _ranges(node: Any, trail: str = "") -> dict[str, list[tuple[int, int]]]:
    found: dict[str, list[tuple[int, int]]] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, dict) and value.get("sectionPages") is not None:
                spans = _spans(value["sectionPages"])
                if spans:
                    found[key] = spans
            found.update(_ranges(value, key))
    elif isinstance(node, list):
        for one in node:
            found.update(_ranges(one, trail))
    return found


def _spans(declared: Any) -> list[tuple[int, int]]:
    held = declared if isinstance(declared, list) else [declared]
    found = []
    for one in held:
        if not isinstance(one, dict):
            continue
        low, high = one.get("from"), one.get("to")
        if isinstance(low, int) and isinstance(high, int):
            found.append((low, high))
    return found


def _cited(node: Any, trail: str = "") -> list[tuple[str, str, int | None]]:
    found: list[tuple[str, str, int | None]] = []
    if isinstance(node, dict):
        document = node.get("document")
        if isinstance(document, str) and ("quote" in node or "rows" in node):
            page = node.get("filePage")
            found.append((trail, document, page if isinstance(page, int) else None))
        for key, value in node.items():
            found.extend(_cited(value, f"{trail}.{key}" if trail else key))
    elif isinstance(node, list):
        for at, one in enumerate(node):
            found.extend(_cited(one, f"{trail}[{at}]"))
    return found


def report(found: Sequence[Verdict], books: int) -> str:
    if not books:
        return (
            f"{len(found)} quotes checked against 0 documents: none is on this machine, "
            f"so none was checked. They are not redistributable and are named in the "
            f"References section of README.md"
        )
    missing = [one for one in found if not one.found]
    lines = [
        f"{len(found)} quotes against {books} documents, "
        f"{len(found) - len(missing)} located, {len(missing)} not"
    ]
    lines.extend(
        f"  {one.where}: placed {one.placed} of {one.windows} windows"
        f"{'' if one.document is None else f' (best in {one.document})'}\n"
        f"    {one.quote[:110]}"
        for one in missing
    )
    return "\n".join(lines)


def main(
    books: dict[str, str] | None = None,
    held: Iterable[tuple[str, str]] | None = None,
    astray: Sequence[str] | None = None,
) -> int:
    books = library() if books is None else books
    found = verify(held, books)
    print(report(found, len(books)))
    wandered = list(sections() if astray is None else astray)
    wandered += undeclared() + misattributed() + phantom() + borrowed()
    for one in wandered:
        print(f"  {one}")
    if wandered:
        return 1
    if not books:
        return 0
    return 0 if all(one.found for one in found) else 1


if __name__ == "__main__":
    sys.exit(main())
