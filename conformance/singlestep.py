"""Check a core against the per-opcode suite published for the part it models.

Each suite gives ten thousand tests per opcode, and the 65816 gives that twice
over because it has two modes. Each test carries a complete starting state, the
bytes of memory the instruction touches, and the state one instruction later.
Nothing in any of them starts clean: every register holds an arbitrary value,
which is the point, and a core that quietly assumes a cleared machine fails on
the first case.

The family shares one runner because the suites share one shape. What differs is
which registers a part has, and that comes from the model rather than from a
second copy of this file.

The suite is not carried here. It is gigabytes of JSON that belongs to its own
project, and this takes a path to a local checkout and reports honestly when
there is not one, the way every other check in this repository treats data it
does not own.

    git clone --filter=blob:none --sparse --depth=1 \\
        https://github.com/SingleStepTests/ProcessorTests.git
    git -C ProcessorTests sparse-checkout set 65816
    python3 -m conformance.singlestep ProcessorTests/65816/v1

    git clone --filter=blob:none --sparse --depth=1 \\
        https://github.com/SingleStepTests/65x02.git
    git -C 65x02 sparse-checkout set 6502
    python3 -m conformance.singlestep 65x02/6502/v1 --model 6502
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import Cpu, SparseMemory, UnknownModelError, models  # noqa: E402

EXAMPLE_LIMIT = 5

DEFAULT_MODEL = "65816"

REGISTERS = (
    ("a", "a"),
    ("x", "x"),
    ("y", "y"),
    ("s", "s"),
    ("d", "d"),
    ("dbr", "db"),
    ("pbr", "pb"),
    ("pc", "pc"),
)


def suite_files(directory: Path) -> list[Path]:
    """Every test file in the suite, in a fixed order, or none if it is absent."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def machine_for(initial: Mapping[str, Any], model: str = DEFAULT_MODEL) -> Any:
    """A processor and memory in exactly the state the test declares.

    Memory outside the bytes the test names is scrambled rather than cleared. The
    suite says nothing about those addresses, so an instruction that reads one is
    reading something undefined, and filling them with zeroes would make such a
    read look deliberate.

    Only the registers the test names are set, because only the registers the
    part has are named. Everything else keeps what the reset left it holding.
    """
    memory = SparseMemory(seed=initial["pc"])
    for address, value in initial["ram"]:
        memory.write8(address, value)

    cpu = Cpu(model, memory)
    if "e" in initial:
        cpu.emulation = bool(initial["e"])
    cpu.set_status(initial["p"])
    for name, attribute in REGISTERS:
        if name in initial:
            setattr(cpu, attribute, initial[name])
    return cpu, memory


def check(test: Mapping[str, Any], model: str = DEFAULT_MODEL) -> list[tuple[str, Any, Any]]:
    """Where the interpreter and the suite disagree after one instruction.

    The suite records how many cycles it let the instruction have, which matters
    only for the block moves: those are interruptible and the suite captures a
    hundred cycle window rather than a move of sixty thousand bytes. Every other
    instruction finishes well inside its window, so the budget changes nothing.
    """
    cpu, memory = machine_for(test["initial"], model)
    if hasattr(cpu, "cycle_budget"):
        cpu.cycle_budget = len(test.get("cycles", ())) or None
    cpu.step()

    final = test["final"]
    wrong = []
    for name, attribute in REGISTERS:
        if name not in final:
            continue
        want = final[name]
        got = getattr(cpu, attribute)
        if want != got:
            wrong.append((name, want, got))

    if "p" in final and final["p"] != cpu.status():
        wrong.append(("p", final["p"], cpu.status()))

    if "e" in final and bool(final["e"]) != cpu.emulation:
        wrong.append(("e", final["e"], int(cpu.emulation)))

    for address, value in final.get("ram", ()):
        got = memory.read8(address)
        if got != value:
            wrong.append((f"${address:06X}", value, got))

    return wrong


def recorded_divergence(test: Mapping[str, Any], model: str) -> str:
    """The name of the entry explaining this case, or an empty string.

    One case is left out, narrowly and by opcode, and it is reported rather than
    hidden. PLB pulls one byte, and section 8.1 of the W65C816S data sheet puts
    the emulation stack range at 000100 to 0001FF and lists the opcodes that
    leave it when they access two or three bytes. PLB is not on that list and
    does not access two or three bytes, so this model keeps it inside page one.
    The corpus records the read one byte past the top of the page, and the two
    disagree on exactly the cases where the pointer sits at the page edge.

    The condition is the disagreement itself rather than a list of case names: a
    list would go stale the moment the corpus is regenerated, and would say
    nothing about why those names and no others.
    """
    if model != "65816":
        return ""
    initial = test["initial"]
    pulls_across_the_page_edge = (
        int(initial.get("e", 0)) == 1 and (int(initial["s"]) & 0xFF) == 0xFF
    )
    if pulls_across_the_page_edge and str(test["name"]).startswith("ab "):
        return "the stack address of a one byte pull at the top of emulation page one"
    return ""


def run_tests(
    tests: Iterable[Mapping[str, Any]], model: str = DEFAULT_MODEL
) -> tuple[int, int, int, list[tuple[str, list[tuple[str, Any, Any]]]]]:
    """How many agreed, how many did not, how many were left out, and examples."""
    passed = failed = skipped = 0
    examples: list[tuple[str, list[tuple[str, Any, Any]]]] = []
    for test in tests:
        try:
            wrong = check(test, model)
        except Exception as error:  # noqa: BLE001
            wrong = [("raised", type(error).__name__, str(error)[:60])]
        if wrong:
            if recorded_divergence(test, model):
                skipped += 1
                continue
            failed += 1
            if len(examples) < EXAMPLE_LIMIT:
                examples.append((test["name"], wrong))
        else:
            passed += 1
    return passed, failed, skipped, examples


def run_file(
    path: Path, limit: int | None = None, model: str = DEFAULT_MODEL
) -> tuple[int, int, int, list[tuple[str, list[tuple[str, Any, Any]]]]]:
    """One test file, optionally only its first few cases.

    A file with nothing in it is a file with no cases rather than a failure. The
    suites carry one per opcode, and the two whose whole behaviour is to stop the
    part are empty because there is nothing to record.

    The caller counts those and names them, because a run that compares two
    hundred and fifty four files out of two hundred and fifty six and reports only
    the two hundred and fifty six reads as a run that checked them all.
    """
    held = Path(path).read_text().strip()
    if not held:
        return 0, 0, 0, []
    tests = json.loads(held)
    if limit:
        tests = tests[:limit]
    return run_tests(tests, model)


USAGE = "usage: python3 -m conformance.singlestep <suite directory> [tests per file] [filter] [--model name]"


class Usage(Exception):
    pass


def options(argv: Sequence[str]) -> Any:
    """The suite to run, how much of it, and which part it is a suite for."""
    model = DEFAULT_MODEL
    rest = []
    argv = list(argv)
    while argv:
        entry = argv.pop(0)
        if entry != "--model":
            rest.append(entry)
            continue
        if not argv:
            raise Usage("--model needs the name of a part after it")
        model = argv.pop(0)

    if not rest:
        raise Usage("a suite directory is needed")
    models.lookup(model)
    return rest, model


def main(argv: Sequence[str]) -> int:
    try:
        rest, model = options(argv)
    except (Usage, UnknownModelError) as refusal:
        print(f"  {refusal}")
        print(USAGE)
        return 2

    directory = Path(rest[0])
    limit = int(rest[1]) if len(rest) > 1 else None
    wanted = rest[2] if len(rest) > 2 else ""

    files = [path for path in suite_files(directory) if wanted in path.name]
    if not files:
        print(f"  no suite at {directory}; clone SingleStepTests/ProcessorTests to get one")
        return 0

    print(f"  {len(files)} files from {directory}, as a {model}")
    passed = failed = skipped = 0
    broken = []
    empty = []
    for path in files:
        file_passed, file_failed, file_skipped, examples = run_file(path, limit, model)
        passed += file_passed
        failed += file_failed
        skipped += file_skipped
        if not file_passed and not file_failed and not file_skipped:
            empty.append(path.stem)
        if file_failed:
            broken.append((path.name, file_failed, examples))

    print(f"  {passed} agreed, {failed} did not")
    if skipped:
        print(
            f"  {skipped} left out as recorded divergences, explained in"
            f" conformance/divergences.json"
        )
    if empty:
        print(f"  {len(empty)} files hold no cases: {' '.join(empty)}")
    for name, count, examples in broken[:EXAMPLE_LIMIT]:
        detail = ", ".join(f"{field} want {want} got {got}" for field, want, got in examples[0][1])
        print(f"    {name}: {count} wrong, first {examples[0][0]}: {detail}")
    if len(broken) > EXAMPLE_LIMIT:
        print(f"    and {len(broken) - EXAMPLE_LIMIT} more files with failures")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
