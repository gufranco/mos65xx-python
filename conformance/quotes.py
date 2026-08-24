"""Look for every sentence these records call a quote in the documents they cite.

A record that quotes a document is making a checkable claim, and until this file
existed nothing checked it. Reading the quotes against the documents by hand
found three defects across this family: a Q and A answer that read 8259 where the
page prints 8080, inverting which part generates three acknowledge pulses; a
quote that dropped a parenthetical while labelled verbatim; and, in the sibling
repository, a sentence about a clock divided into phases that appears in none of
the twelve documents that project pins.

The documents are not in the repository and never will be: none is
redistributable. So this reports what it could not check rather than passing
quietly, and a run with no documents on disk checks nothing and says so.

Matching is deliberately loose. Every document here is a photograph of a printed
book, and the text layer a scan carries prints lhe for the and OP for DP, so an
exact search finds nothing and the absence means nothing. A quote is scored on
how many of its five-word windows appear, which survives hyphenation, collapsed
spaces and a misread word, and still fails a sentence that was never printed.
"""

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
"""How long a run of words has to be before a document carrying it is not chance."""

TABLE = re.compile(r"Table\s+(\d+(?:[-.]\d+)*)")
"""How a numbered table is named, in either family the documents here use."""
"""Words per window. Short enough to survive a misread word, long enough that
matching one is not a coincidence."""

BAR = 0.4
"""The share of windows a quote must place to count as found.

A scan misreads perhaps a word in twenty, and a quote of thirty words has
twenty-six windows, so a passing quote usually places most of them. The bar sits
low because the question is whether the sentence is on the page at all, not
whether the recogniser read it well.
"""

DASHES = (0x2013, 0x2014, 0x2212)

SINGLES = (0x2018, 0x2019, 0x2032)

DOUBLES = (0x201C, 0x201D)

ELSEWHERE = ("suiteSays",)
"""Trails whose quotes are not a manufacturer speaking.

suiteSays quotes the recording this project is measured against, which is not in
a pinned document, so looking for it there would report an absence that means
nothing.
"""


class Verdict(NamedTuple):
    """One quote, and the best any pinned document could do with it."""

    where: str
    quote: str
    document: str | None
    placed: int
    windows: int

    @property
    def found(self) -> bool:
        return bool(self.windows) and self.placed / self.windows >= BAR


def flatten(text: str) -> str:
    """Letters and digits only, so a scan's spacing and punctuation stop mattering."""
    text = unicodedata.normalize("NFKD", text)
    for code in DASHES:
        text = text.replace(chr(code), "-")
    for code in SINGLES:
        text = text.replace(chr(code), "'")
    for code in DOUBLES:
        text = text.replace(chr(code), '"')
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def windows(quote: str) -> list[str]:
    """The overlapping word runs a quote is scored on."""
    words = [one for one in re.split(r"\s+", quote) if one]
    if len(words) <= WINDOW:
        return [flatten(quote)]
    return [flatten(" ".join(words[at : at + WINDOW])) for at in range(len(words) - WINDOW + 1)]


def said(node: Any, trail: str = "") -> list[tuple[str, str]]:
    """Every quoted sentence in a record that a document should carry contiguously.

    A key ending in `quote` holds one passage. A key ending in `quotes` holds
    several, either as a list or as a map from the number a document prints
    beside each one. The plural form is what a page of numbered notes is, and
    holding it under a name of its own is what keeps it inside the checker
    rather than beside it.

    Two markers take a quote out of scope, and each says something a reader can
    check. ``assembled`` means the words are the document's but the order is not:
    a table or a figure flattened into a sentence, which no search for a run of
    words can find. ``saysNothing`` means the document is silent and the text is
    this record summarising that silence, so there is nothing to look for.
    """
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
    """Every quote a pinned document is supposed to carry."""
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
"""Every key this family uses to say where in a document something is printed.

A page named on a parent counts for the quotes beneath it, because a fact that
names one page and quotes three sentences from it is citing all three.
"""


LOCATOR = re.compile(r"\d+[.\-]\d|page|table|appendix|section", re.IGNORECASE)
"""What makes a document reference specific enough to look up.

Naming a document is not a citation; naming a section, a table or a page in it
is. A record that says W65C816S Data Sheet, 8.11.2 has told a reader where to
look, and demanding a page number on top of that would be asking for a second
form of the same thing.
"""


def pointed(node: dict[str, Any]) -> bool:
    """Whether this object says where in a document its quote is printed."""
    if PAGE_KEYS & set(node):
        return True
    for key in ("document", "source"):
        value = node.get(key)
        if isinstance(value, str) and LOCATOR.search(value):
            return True
    return False


def uncited(node: Any, inherited: bool = False, trail: str = "") -> list[str]:
    """Every quote no page can be reached from.

    A quote a reader cannot look up is a claim they have to take on trust, which
    is the thing this whole record exists not to ask of them.
    """
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
    """Every record beside this file, by name."""
    return [(path.name, json.loads(path.read_text())) for path in sorted(RECORDS.glob("*.json"))]


def unpaged(records: Iterable[tuple[str, Any]] | None = None) -> list[str]:
    """Every manufacturer quote in these records that names no page."""
    found: list[str] = []
    for name, held in loaded() if records is None else records:
        for where in uncited(held, False, name):
            if not any(one in where for one in ELSEWHERE):
                found.append(where)
    return found


def readable(path: Path, run: Any = None) -> str:
    """The text a document carries, flattened. Empty when nothing can read it.

    A machine without pdftotext installed is the same case as a machine without
    the documents: nothing can be checked, and saying so is the whole point.
    Letting the missing binary raise would turn a check that cannot run into a
    run that failed.

    ``-layout`` is what makes a table readable at all, and it is also the reason
    a quote can be in a document and unfindable here. Reading proceeds by visual
    row, so a heading stacked over two lines interleaves with whatever sits
    beside it: page 20 of the W65C02S data sheet carries "Instruction Times in
    Memory Cycle" over two lines next to another two-line heading, and comes out
    as the two first lines followed by the two second ones. Quote a single line
    of such a heading, or mark the entry ``assembled``. Without ``-layout`` the
    columns of every opcode table run together instead, which loses more.
    """
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
    """A second reading of the same document, taken from the pages as images.

    A scan carries two descriptions of itself and neither is reliable alone: the
    text layer prints lhe for the, and a reader of the images misses a faint line
    outright. Where somebody has read the pages and left the result beside the
    document as a text file, it is pooled with the layer the file already had.
    Neither reading is committed, because neither is redistributable.
    """
    beside = path.with_suffix(".txt")
    return beside.read_text(errors="replace") if beside.is_file() else ""


def library(where: Path | None = None, run: Any = None) -> dict[str, str]:
    """Every pinned document on this machine, flattened once."""
    folder = DOCUMENTS if where is None else where
    if not folder.is_dir():
        return {}
    return {path.name: readable(path, run) for path in sorted(folder.glob("*.pdf"))}


def verify(
    held: Iterable[tuple[str, str]] | None = None,
    books: dict[str, str] | None = None,
) -> list[Verdict]:
    """Every quote, scored against the best document that could place it."""
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
    """Every quote absent from the document its own record names.

    `verify` scores a quote against whichever document places it best, which
    answers "did somebody publish this sentence" and not "did the document this
    record cites publish it". Those come apart exactly when a fact is filed under
    the wrong source, and then the words are real, the check is green, and the
    citation sends a reader to a document that does not contain the sentence.

    Three facts about the CMOS part were filed under the 16-bit part's data sheet
    for that reason. Both sheets have a Table 7-1 and they are about different
    things.

    The rule is deliberately narrow: report only when the quote is absent from the
    document it names and present in another one. That is the signature of a fact
    filed under the wrong source, and it stays true for a table flattened into a
    sentence, where a search may legitimately find nothing anywhere. Reporting a
    quote that is simply unfindable would flag every such table and say nothing
    about where it came from.

    A document with no file on this machine is skipped, the same as everywhere
    else here: a check that cannot run says so rather than reporting a pass.
    """
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
    """The file each declared document names, so a quote can be held to it."""
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
    """Every quote that names a document, skipping the ones nothing can search."""
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
    """Every table a document names, spelled the way it prints them.

    Read from the text rather than from the flattened body, and compared as whole
    labels rather than by containment. Flattening removes the separator that
    tells `Table 6-7` from `Table 6-76`, and containment would call a bare
    `Table 6` present in a document whose only table is `6-5`.

    The families here are `Table 6`, which NEC uses, and `Table 6-5`, which WDC
    uses. A full stop counts as a separator only when a digit follows it, so
    "Table 6. ALU Field" is table six and "Table 1.2" is table one point two.
    """
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
    """The tables each pinned document names."""
    folder = DOCUMENTS if where is None else where
    if not folder.is_dir():
        return {}
    return {path.name: labelled(path, run) for path in sorted(folder.glob("*.pdf"))}


def phantom(
    records: Iterable[tuple[str, Any]] | None = None,
    tables: dict[str, set[str]] | None = None,
) -> list[str]:
    """Every section that sends a reader to a table its document does not have.

    A quote is held to the document beside it. The section was held to nothing,
    and four citations here named a Table 6-5 of the W65C02S data sheet. That
    sheet's tables are 3-1, 3-2, 4-1, 5-1, 5-2, 6-1 through 6-4 and 7-1; the
    sixteen bit sheet is the one with a 6-5, and that is where the number came
    from. The words quoted were right, the document named was right, and the
    table pointed at did not exist, so nothing failed and a reader looking for
    it found the wrong sheet or nothing.

    Only a numbered table is checked, because that is the one form whose presence
    is decidable. A section named in prose is left alone.

    Two things are skipped rather than counted as a pass: a document with no file
    on this machine, and one whose reading names no table at all. The second is a
    scan whose text layer did not carry the labels, and reporting every citation
    into it as a phantom would say something about the scan rather than about the
    record.
    """
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
    """Every section that names a document, so the tables in it can be held to one."""
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
    """Every passage a document carries, under a key this checker does not read.

    A quote is verified because of the name it sits under. A passage under any
    other name is a document's words that nothing holds to the document, and it
    drifts the way a comment drifts: quietly, while still reading as evidence.
    Twenty-one of them were found here in one pass, under `footnote`, under
    `notes`, and under `pushedBytes`.

    The rule is that a long run of words appearing verbatim in a pinned document
    is that document's, whatever the key is called. Short strings are left alone
    because a record repeats a mnemonic, a register name or a column heading
    legitimately, and reporting those would bury the finding among them.
    """
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
    """Every string in a record that is not already held as a quote."""
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
    """Every citation that names something the record does not declare as a document.

    A citation is only worth as much as the reader's ability to follow it. When
    the same field holds a declared key in one place, a file path in another and
    a prose title with a section glued on in a third, nothing can check any of
    them: a check written against keys silently skips the other two, and reports
    a clean run over the half it understood.

    So `document` always names a key in a `documents` block, and where the
    citation points inside that document goes in `section`. A record with no such
    block declares nothing and is left alone.
    """
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
    """The keys of every documents block in a record."""
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
    """Every fact that cites a multi-part document without landing in this part's section.

    A data book covers a dozen parts, and several of them are close relatives
    that print the same table under the same name with the same column headings.
    A quote taken from the wrong one reads as perfectly sourced: the words are
    the document's, the table number may even match, and the part is not this
    part. Searching the flattened document cannot catch it, because the flattened
    document contains every section at once.

    So a document record may declare `sectionPages`, the file pages its own part
    occupies. Where it does, every fact citing that document has to name a
    `filePage` inside them. A document that declares no range is single-part and
    nothing here applies to it.

    The pages need not be contiguous. A questions-and-answers section runs
    through the whole family, a few pages per part and back again, so one part's
    material is several blocks with other parts' material between them. A record
    may give a list of ranges for that, and one range is the common case.
    """
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
    """Every document in a record that declares which pages are this part's."""
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
    """One range or several, as pairs. Anything else declares nothing."""
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
    """Every fact that names a document, with the file page it claims."""
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
    """What was checked, what was not, and anything a person should read."""
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
