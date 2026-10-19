from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mos65xx

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Mapping

RECORD = Path(__file__).resolve().parent / "exercisers.json"

LIMIT = 200_000_000

NOTHING_RAN = 2


class Verdict:
    __slots__ = ("cycles", "steps", "trapped_at")

    def __init__(self, trapped_at: int | None, steps: int, cycles: int) -> None:
        self.trapped_at = trapped_at
        self.steps = steps
        self.cycles = cycles

    def at(self) -> str:
        return "nowhere" if self.trapped_at is None else f"{self.trapped_at:04x}"


def declared(path: Path | None = None) -> dict[str, Any]:
    held: dict[str, Any] = json.loads((path or RECORD).read_text())
    return held


def directory(variable: str, environment: Mapping[str, str] | None = None) -> Path | None:
    named = (os.environ if environment is None else environment).get(variable, "")
    return Path(named) if named and Path(named).is_dir() else None


def loaded(raw: bytes, model: str, load_at: int, start: int) -> Any:
    memory = mos65xx.Memory(fill=0)
    for offset, value in enumerate(raw):
        memory.write8(load_at + offset, value)
    cpu = mos65xx.Cpu(model, memory)
    cpu.pc = start
    return cpu


def trap(cpu: Any, limit: int = LIMIT) -> Verdict:
    for _ in range(limit):
        before = cpu.pc
        cpu.step()
        if cpu.pc == before:
            return Verdict(before, cpu.steps, cpu.cycles)
    return Verdict(None, cpu.steps, cpu.cycles)


def run(raw: bytes, program: Mapping[str, Any], model: str, limit: int = LIMIT) -> Verdict:
    start = int(program["start"], 16)
    return trap(loaded(raw, model, int(program["loadAt"], 16), start), limit)


def judged(program: Mapping[str, Any], model: str, verdict: Verdict) -> str:
    passed = verdict.at() == program["passedAt"]
    said = "passed" if passed else f"stopped at {verdict.at()}, not {program['passedAt']}"
    return f"  {program['id']} as a {model}: {said}, {verdict.steps} steps"


def one_program(
    program: Mapping[str, Any], where: Path, say: Callable[[str], None], limit: int
) -> tuple[int, int]:
    image = where / program["file"]
    if not image.is_file():
        say(f"  {program['id']}: not on this machine, so nothing was run")
        return 0, 0
    raw = image.read_bytes()
    if hashlib.sha256(raw).hexdigest() != program["sha256"]:
        say(f"  {program['id']}: does not match its published sha256")
        return 0, 1
    wrong = 0
    for one in program["runs"]:
        verdict = run(raw, program, one["model"], limit)
        say(judged(program, one["model"], verdict))
        wrong += verdict.at() != program["passedAt"]
    return len(program["runs"]), wrong


def main(
    environment: Mapping[str, str] | None = None,
    held: dict[str, Any] | None = None,
    say: Callable[[str], None] = print,
    limit: int = LIMIT,
) -> int:
    record = declared() if held is None else held
    where = directory(record["variable"], environment)
    if where is None:
        say(f"skipped: nothing was run. Check out {record['repository']}")
        say(f"at {record['commit']} and name it in {record['variable']}; nothing is carried")
        return NOTHING_RAN
    ran, wrong = 0, 0
    for program in record["programs"]:
        counted, failed = one_program(program, where, say, limit)
        ran, wrong = ran + counted, wrong + failed
    say(f"{ran} runs, {wrong} wrong")
    if not ran and not wrong:
        return NOTHING_RAN
    return 1 if wrong else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
