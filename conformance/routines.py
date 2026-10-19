from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mos65xx
from conformance.board import Board

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Mapping, Sequence

RECORD = Path(__file__).resolve().parent / "routines.json"

VARIABLE = "MOS65XX_TEST_IMAGES"

PRELUDE_AT = 0x1F00

LIMIT = 2_000_000

PASSED = "ff"

NOTHING_RAN = 2

SUFFIXES = (".sfc", ".smc")


def prelude(start: int) -> bytes:
    return bytes(
        (
            *(0x18, 0xFB, 0xC2, 0x30, 0xA9, 0x00, 0x00, 0x5B, 0xA2, 0xFF, 0x1E, 0x9A),
            *(0xE2, 0x30, 0xA9, 0x00, 0x48, 0xAB),
            *(0x5C, start & 0xFF, (start >> 8) & 0xFF, start >> 16),
        )
    )


def declared(path: Path | None = None) -> dict[str, Any]:
    held: dict[str, Any] = json.loads((path or RECORD).read_text())
    return held


def folder(variable: str, environment: Mapping[str, str] | None) -> tuple[Path, ...] | None:
    named = (os.environ if environment is None else environment).get(variable, "")
    found = tuple(Path(one) for one in named.split(os.pathsep) if one and Path(one).is_dir())
    return found or None


def located(digest: str, where: Sequence[Path]) -> Path | None:
    for path in sorted(one for each in where for one in each.iterdir()):
        if (
            path.suffix.lower() in SUFFIXES
            and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        ):
            return path
    return None


def copies_match(board: Board, copies: Sequence[Mapping[str, Any]]) -> list[bool]:
    return [
        all(
            board.read8(int(one["to"], 16) + at) == board.read8(int(one["from"], 16) + at)
            for at in range(one.get("length", 256))
        )
        for one in copies
    ]


def run(image: bytes, entry: Mapping[str, Any], limit: int = LIMIT) -> dict[str, Any]:
    flag = int(entry["flag"], 16)
    seen: list[int] = []
    board = Board(
        image, entry["layout"], lambda write: seen.extend([write[1]] * (write[0] == flag))
    )
    for offset, value in enumerate(prelude(int(entry["start"], 16))):
        board.write8(PRELUDE_AT + offset, value)
    cpu = mos65xx.Cpu("65816", board)
    cpu.reset()
    cpu.pc = PRELUDE_AT
    steps = 0
    for _ in range(limit):
        cpu.step()
        steps += 1
        if seen:
            break
    written = f"{seen[0]:02x}" if seen else None
    return {"flag": written, "steps": steps, "copiesMatch": copies_match(board, entry["copies"])}


def problems(measured: Mapping[str, Any]) -> list[str]:
    found = [] if measured["flag"] == PASSED else [f"the routine never set its flag to {PASSED}"]
    return found + (
        ["a block move does not match its source"] if not all(measured["copiesMatch"]) else []
    )


def one_routine(
    entry: Mapping[str, Any], where: Sequence[Path], say: Callable[[str], None], limit: int
) -> tuple[bool, bool, dict[str, Any]]:
    image = located(entry["sha256"], where)
    if image is None:
        say(f"  {entry['id']}: not on this machine, so nothing was run")
        return False, False, dict(entry)
    measured = run(image.read_bytes(), entry, limit)
    found = problems(measured) + (
        [] if measured == entry["measured"] else ["differs from the recorded run"]
    )
    say(f"  {entry['id']}: flag {measured['flag']} after {measured['steps']} steps")
    for problem in found:
        say(f"  {entry['id']}: {problem}")
    return True, bool(found), {**entry, "measured": measured}


def main(
    argv: Sequence[str] = (),
    say: Callable[[str], None] = print,
    environment: Mapping[str, str] | None = None,
    held: dict[str, Any] | None = None,
    record_path: Path | None = None,
    limit: int = LIMIT,
) -> int:
    record = declared() if held is None else held
    variable = record.get("variable", VARIABLE)
    where = folder(variable, environment)
    if where is None:
        say(f"skipped: nothing was run. Name the folder that holds the images in {variable}")
        return NOTHING_RAN
    results = [one_routine(entry, where, say, limit) for entry in record["routines"]]
    ran, wrong = sum(one[0] for one in results), sum(one[1] for one in results)
    target = RECORD if "--write" in argv else record_path
    if target is not None:
        target.write_text(
            json.dumps({**record, "routines": [one[2] for one in results]}, indent=2) + "\n"
        )
    say(f"{ran} runs, {wrong} wrong")
    if not ran and not wrong:
        return NOTHING_RAN
    return 1 if wrong else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
