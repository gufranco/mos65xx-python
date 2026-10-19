from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mos65xx
from conformance.board import Board
from conformance.routines import folder, located

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Mapping, Sequence

RECORD = Path(__file__).resolve().parent / "screens.json"

VARIABLE = "MOS65XX_TEST_IMAGES"

CHUNK = 200_000

NOTHING_RAN = 2

TEST_NUMBER = re.compile(r"Test number: ([0-9A-F]{4})")


def declared(path: Path | None = None) -> dict[str, Any]:
    held: dict[str, Any] = json.loads((path or RECORD).read_text())
    return held


def numbered(screen: str) -> str:
    found = TEST_NUMBER.search(screen)
    return found.group(1) if found else ""


def finished(board: Board, until: Mapping[str, Any]) -> bool:
    if board.printed["FAIL"]:
        return True
    if "screen" in until and until["screen"] in board.screen():
        return True
    return "passes" in until and board.printed["PASS"] >= until["passes"]


def run(image: bytes, entry: Mapping[str, Any], chunk: int = CHUNK) -> dict[str, Any]:
    board = Board(image, entry["layout"])
    cpu = mos65xx.Cpu("65816", board)
    cpu.reset()
    for _ in range(max(1, entry["limit"] // chunk)):
        cpu.run_for(chunk)
        if finished(board, entry["until"]):
            break
    return {
        "printed": dict(board.printed),
        "failed": [numbered(screen) for screen in board.pressed_at],
        "screen": board.screen(),
        "cycles": cpu.cycles,
    }


def problems(entry: Mapping[str, Any], measured: Mapping[str, Any]) -> list[str]:
    printed, wanted = measured["printed"], entry.get("passes", 0)
    found = [f"printed FAIL {printed['FAIL']} times"] if printed["FAIL"] else []
    found += [f"stopped on a failure at {one}" for one in measured["failed"]]
    if printed["PASS"] < wanted:
        found += [f"printed PASS {printed['PASS']} times, its source prints it {wanted}"]
    shown = entry["until"].get("screen")
    return found + ([f"never showed {shown}"] if shown and shown not in measured["screen"] else [])


def one_program(
    entry: Mapping[str, Any], where: Sequence[Path], say: Callable[[str], None], chunk: int
) -> tuple[bool, bool, dict[str, Any]]:
    image = located(entry["sha256"], where)
    if image is None:
        say(f"  {entry['id']}: not on this machine, so nothing was run")
        return False, False, dict(entry)
    measured = run(image.read_bytes(), entry, chunk)
    found = problems(entry, measured) + (
        [] if measured == entry["measured"] else ["differs from the recorded run"]
    )
    printed = measured["printed"]
    say(
        f"  {entry['id']}: {printed['PASS']} PASS, {printed['FAIL']} FAIL, {len(measured['failed'])} waits"
    )
    for problem in found:
        say(f"  {entry['id']}: {problem}")
    return True, bool(found), {**entry, "measured": measured}


def main(
    argv: Sequence[str] = (),
    say: Callable[[str], None] = print,
    environment: Mapping[str, str] | None = None,
    held: dict[str, Any] | None = None,
    record_path: Path | None = None,
    chunk: int = CHUNK,
) -> int:
    record = declared() if held is None else held
    where = folder(VARIABLE, environment)
    if where is None:
        say(f"skipped: nothing was run. Name the folder that holds the images in {VARIABLE}")
        return NOTHING_RAN
    results = [one_program(entry, where, say, chunk) for entry in record["programs"]]
    ran, wrong = sum(one[0] for one in results), sum(one[1] for one in results)
    target = RECORD if "--write" in argv else record_path
    if target is not None:
        target.write_text(
            json.dumps({**record, "programs": [one[2] for one in results]}, indent=2) + "\n"
        )
    say(f"{ran} runs, {wrong} wrong")
    if not ran and not wrong:
        return NOTHING_RAN
    return 1 if wrong else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
