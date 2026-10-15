from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conformance.singlestep import (  # noqa: E402
    DEFAULT_MODEL,
    Usage,
    machine_for,
    recorded_divergence,
    suite_files,
)
from mos65xx import UnknownModelError, models  # noqa: E402

EXAMPLE_LIMIT = 3

PLACEHOLDER_OPCODES = frozenset({0x69, 0xE9})

VERIFIED = frozenset({"6502", "6507", "2a03", "65c02", "r65c02", "w65c02", "65816", "65802"})

Cycle = tuple[int | None, int | None, str]
Example = tuple[str, list[Cycle], list[Cycle]]


class Unsupported(Exception): ...


def recorded(test: Mapping[str, Any]) -> list[Cycle]:
    return [
        (
            None if address is None else int(address),
            None if value is None else int(value),
            str(kind),
        )
        for address, value, kind in test["cycles"]
    ]


def opcode_of(initial: Mapping[str, Any]) -> int | None:
    at = (int(initial.get("pbr", 0)) << 16) | int(initial["pc"])
    found = dict(initial["ram"]).get(at)
    return None if found is None else int(found)


def only_placeholder(test: Mapping[str, Any], seen: Sequence[Cycle]) -> bool:
    opcode = opcode_of(test["initial"])
    if opcode not in PLACEHOLDER_OPCODES:
        return False
    want = recorded(test)
    if len(want) != len(seen):
        return False
    apart = [index for index, cycle in enumerate(want) if cycle != seen[index]]
    if len(apart) != 1:
        return False
    at = apart[0]
    return want[at][2] == seen[at][2] == "read"


def check(test: Mapping[str, Any], model: str = DEFAULT_MODEL) -> list[Cycle] | None:
    try:
        cpu, _ = machine_for(test["initial"], model)
        if not hasattr(cpu, "trace"):
            raise Unsupported(f"a {model} does not record what it puts on the bus")
        if hasattr(cpu, "cycle_budget"):
            cpu.cycle_budget = len(test.get("cycles", ())) or None
        cpu.trace = []
        cpu.step()
        want = len(recorded(test))
        while cpu.held() and len(cpu.trace) < want:
            cpu.held_cycle()
    except Unsupported:
        raise
    except Exception as error:  # noqa: BLE001
        return [(0, 0, f"raised {type(error).__name__}")]
    seen: list[Cycle] = list(cpu.trace)
    return None if seen == recorded(test) else seen


def run_tests(
    tests: Iterable[Mapping[str, Any]], model: str = DEFAULT_MODEL
) -> tuple[int, int, int, list[Example]]:
    agreed = differed = skipped = 0
    examples: list[Example] = []
    for test in tests:
        seen = check(test, model)
        if seen is None:
            agreed += 1
            continue
        if only_placeholder(test, seen) or recorded_divergence(test, model):
            skipped += 1
            continue
        differed += 1
        if len(examples) < EXAMPLE_LIMIT:
            examples.append((str(test["name"]), recorded(test), seen))
    return agreed, differed, skipped, examples


def run_file(
    path: Path, limit: int | None = None, model: str = DEFAULT_MODEL
) -> tuple[int, int, int, list[Example]]:
    held = Path(path).read_text().strip()
    if not held:
        return 0, 0, 0, []
    tests = json.loads(held)
    if limit:
        tests = tests[:limit]
    return run_tests(tests, model)


def options(argv: Sequence[str]) -> tuple[list[str], str]:
    model = DEFAULT_MODEL
    rest = []
    remaining = list(argv)
    while remaining:
        entry = remaining.pop(0)
        if entry != "--model":
            rest.append(entry)
            continue
        if not remaining:
            raise Usage("--model needs the name of a part after it")
        model = remaining.pop(0)

    if not rest:
        raise Usage("a suite directory is needed")
    named = models.lookup(model).name
    if named not in VERIFIED:
        raise Unsupported(
            f"a {named} has not been held to a cycle recording yet; "
            f"see conformance/divergences.json for what is measured and missing"
        )
    return rest, model


USAGE = "usage: python3 -m conformance.cycles <suite directory> [tests per file] [filter] [--model name]"


def report(examples: Sequence[Example]) -> None:
    first, want, got = examples[0]
    print(f"      first {first}")
    print(f"      recorded {want}")
    print(f"      model    {got}")


def main(argv: Sequence[str]) -> int:
    try:
        rest, model = options(argv)
    except (Usage, UnknownModelError, Unsupported) as refusal:
        print(f"  {refusal}")
        print(USAGE)
        return 2

    directory = Path(rest[0])
    limit = int(rest[1]) if len(rest) > 1 else None
    wanted = rest[2] if len(rest) > 2 else ""

    files = [path for path in suite_files(directory) if wanted in path.name]
    if not files:
        print(f"  no suite at {directory}; run conformance/fetch.py to get one")
        return 0

    print(f"  {len(files)} files from {directory}, as a {model}")
    agreed = differed = skipped = 0
    broken = []
    empty = []
    for path in files:
        file_agreed, file_differed, file_skipped, examples = run_file(path, limit, model)
        agreed += file_agreed
        differed += file_differed
        skipped += file_skipped
        if not (file_agreed or file_differed or file_skipped):
            empty.append(path.stem)
        if file_differed:
            broken.append((path.name, file_differed, examples))

    if empty:
        print(f"  {len(empty)} files hold no cases: {' '.join(empty)}")
    print(
        f"  {agreed} agreed cycle for cycle, {differed} did not,"
        f" {skipped} left out as placeholders or recorded divergences"
    )
    for name, count, examples in broken[:EXAMPLE_LIMIT]:
        print(f"    {name}: {count} differed")
        report(examples)
    if len(broken) > EXAMPLE_LIMIT:
        print(f"    and {len(broken) - EXAMPLE_LIMIT} more files with disagreements")
    return 1 if differed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
