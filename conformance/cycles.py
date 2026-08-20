"""Check the bus, cycle by cycle, against the suite that recorded it.

The other runner compares state: where the registers, the flags and the touched
bytes ended up. This one compares what happened on the way there. Every cycle of
these parts is a bus cycle, so the recorded list of accesses is the instruction's
timing and its side effects at once, and a model that agrees with it agrees about
both.

Nothing is inferred from a cycle count here. The comparison is address by address,
value by value, read against write, in order. A model that takes the right number
of cycles by reading the wrong address fails.

    python3 conformance/cycles.py 65x02/6502/v1 --model 6502

Two things are outside the comparison and both are named in the output. A halted
part is one: a jam opcode stops the processor, and what a stopped part puts on the
bus for the rest of a recording is a property of that recording's length rather
than of the instruction. The 65816 is the other: its recordings carry pin states
and cycles with no memory access at all, which this core does not yet emit, so the
runner refuses every model it has not been held to rather than reporting an
agreement it cannot establish. Which parts those are is in VERIFIED below.
"""

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
    suite_files,
)
from mos65xx import OPCODES, UnknownModelError, describe  # noqa: E402

EXAMPLE_LIMIT = 3

HALTS = frozenset({"jam", "stp", "wai"})
"""The mnemonics whose whole behaviour is to stop, which no cycle list bounds.

One of them is the undocumented opcode that hangs an NMOS part. The other two are
the deliberate ones the CMOS and 65816 parts added, and the recordings show what a
waiting part looks like: cycles with no address, no value and every line inactive,
for as long as the recording happens to run.
"""

PLACEHOLDER_OPCODES = frozenset({0x69, 0xE9})
"""Add and subtract with an immediate operand, on the CMOS parts.

Decimal arithmetic costs those parts one extra cycle, and the data sheet says an
internal cycle's address may be invalid. The recordings fill it with a constant:
one value per suite for the add, zero for the subtract, the same whatever the
program counter and the operands are. That is a recorder's placeholder rather
than a measurement, so a case that differs only there is counted apart instead of
being called a disagreement, and conformance/divergences.json carries the numbers.
"""

VERIFIED = frozenset({"6502", "6507", "2a03", "65c02", "r65c02", "w65c02", "65816", "65802"})
"""The parts whose bus activity has been held to a suite, cycle for cycle.

Anything else is refused rather than reported on. A runner that compared a part it
had never been held to would report a disagreement per case and teach a reader
nothing, and one that skipped the comparison silently would be worse.
"""

Cycle = tuple[int | None, int | None, str]
Example = tuple[str, list[Cycle], list[Cycle]]


class Unsupported(Exception):
    """Raised rather than reporting agreement the comparison cannot establish."""


def recorded(test: Mapping[str, Any]) -> list[Cycle]:
    """The cycles the suite recorded, in the shape the model reports its own.

    A cycle with no value is one where the part drove neither address line, so
    nothing answered. The 65816 records those; the eight-bit parts have none,
    because they drive a real address in every cycle they run.
    """
    return [
        (
            None if address is None else int(address),
            None if value is None else int(value),
            str(kind),
        )
        for address, value, kind in test["cycles"]
    ]


def opcode_of(initial: Mapping[str, Any]) -> int | None:
    """The byte the part is about to fetch, wherever the bank register puts it.

    On the 65816 the program counter is only sixteen of the twenty four bits, and
    a lookup that forgets the program bank finds the wrong byte or none at all.
    """
    at = (int(initial.get("pbr", 0)) << 16) | int(initial["pc"])
    found = dict(initial["ram"]).get(at)
    return None if found is None else int(found)


def halted(test: Mapping[str, Any], model: str) -> bool:
    """Whether this case runs an opcode whose whole behaviour is to stop."""
    opcode = opcode_of(test["initial"])
    if opcode is None:
        return False
    cpu, _ = machine_for(test["initial"], model)
    table = getattr(cpu, "table", OPCODES)
    mnemonic: str = table[opcode][0]
    return mnemonic in HALTS


def only_placeholder(test: Mapping[str, Any], seen: Sequence[Cycle]) -> bool:
    """Whether the one cycle that differs is the one with no address to compute.

    Narrow on purpose: same length, exactly one cycle apart, both of them reads,
    and the opcode one of the two whose extra decimal cycle has nowhere to point.
    Anything wider would hide a real disagreement.
    """
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
    """What the model put on the bus, when that differs from the recording.

    None means they agree. A list means they do not, and it is the model's own
    sequence, which is what a reader needs beside the recorded one.
    """
    try:
        cpu, _ = machine_for(test["initial"], model)
        if not hasattr(cpu, "trace"):
            raise Unsupported(f"a {model} does not record what it puts on the bus")
        if hasattr(cpu, "cycle_budget"):
            cpu.cycle_budget = len(test.get("cycles", ())) or None
        cpu.trace = []
        cpu.step()
    except Unsupported:
        raise
    except Exception as error:  # noqa: BLE001
        return [(0, 0, f"raised {type(error).__name__}")]
    seen: list[Cycle] = list(cpu.trace)
    return None if seen == recorded(test) else seen


def run_tests(
    tests: Iterable[Mapping[str, Any]], model: str = DEFAULT_MODEL
) -> tuple[int, int, int, list[Example]]:
    """How many agreed, how many did not, how many were left out, and examples.

    Two kinds are left out and they are counted together: a case whose opcode
    halts the part, and a case that differs only at a cycle whose recorded
    address is a placeholder. Both are reported rather than hidden.
    """
    agreed = differed = skipped = 0
    examples: list[Example] = []
    for test in tests:
        if halted(test, model):
            skipped += 1
            continue
        seen = check(test, model)
        if seen is None:
            agreed += 1
            continue
        if only_placeholder(test, seen):
            skipped += 1
            continue
        differed += 1
        if len(examples) < EXAMPLE_LIMIT:
            examples.append((str(test["name"]), recorded(test), seen))
    return agreed, differed, skipped, examples


def run_file(
    path: Path, limit: int | None = None, model: str = DEFAULT_MODEL
) -> tuple[int, int, int, list[Example]]:
    """One test file, optionally only its first few cases.

    A file with nothing in it is a file with no cases, not a failure. The suites
    carry one for every opcode including the two whose whole behaviour is to stop
    the part, and those two are empty because there is nothing to record.
    """
    held = Path(path).read_text().strip()
    if not held:
        return 0, 0, 0, []
    tests = json.loads(held)
    if limit:
        tests = tests[:limit]
    return run_tests(tests, model)


def options(argv: Sequence[str]) -> tuple[list[str], str]:
    """The suite to run, how much of it, and which part it is a suite for."""
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
    named = describe(model).name
    if named not in VERIFIED:
        raise Unsupported(
            f"a {named} has not been held to a cycle recording yet; "
            f"see conformance/divergences.json for what is measured and missing"
        )
    return rest, model


USAGE = "usage: cycles.py <suite directory> [tests per file] [filter] [--model name]"


def report(examples: Sequence[Example]) -> None:
    """One disagreement, both sequences, so a reader can see which cycle moved."""
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
    for path in files:
        file_agreed, file_differed, file_skipped, examples = run_file(path, limit, model)
        agreed += file_agreed
        differed += file_differed
        skipped += file_skipped
        if file_differed:
            broken.append((path.name, file_differed, examples))

    print(
        f"  {agreed} agreed cycle for cycle, {differed} did not, "
        f"{skipped} left out as halts or placeholders"
    )
    for name, count, examples in broken[:EXAMPLE_LIMIT]:
        print(f"    {name}: {count} differed")
        report(examples)
    if len(broken) > EXAMPLE_LIMIT:
        print(f"    and {len(broken) - EXAMPLE_LIMIT} more files with disagreements")
    return 1 if differed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
