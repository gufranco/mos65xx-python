"""Check the interpreter against the SingleStepTests suite for the 65816.

The suite gives 20,000 tests per opcode, 10,000 in native mode and 10,000 in
emulation mode. Each test carries a complete starting state, the bytes of memory
the instruction touches, and the state one instruction later. Nothing in it
starts clean: every register holds an arbitrary value, which is the point, and a
core that quietly assumes a cleared machine fails on the first case.

The suite is not carried here. It is gigabytes of JSON that belongs to its own
project, and this takes a path to a local checkout and reports honestly when
there is not one, the way every other check in this repository treats data it
does not own.

    git clone --filter=blob:none --sparse --depth=1 \\
        https://github.com/SingleStepTests/ProcessorTests.git
    git -C ProcessorTests sparse-checkout set 65816
    python3 conformance/singlestep.py ProcessorTests/65816/v1
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mos65xx import Cpu, SparseMemory  # noqa: E402

ADDRESS_SPACE = 0x1000000
EXAMPLE_LIMIT = 5

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


def suite_files(directory):
    """Every test file in the suite, in a fixed order, or none if it is absent."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def machine_for(initial):
    """A processor and memory in exactly the state the test declares.

    Memory outside the bytes the test names is scrambled rather than cleared. The
    suite says nothing about those addresses, so an instruction that reads one is
    reading something undefined, and filling them with zeroes would make such a
    read look deliberate.
    """
    memory = SparseMemory(seed=initial["pc"])
    for address, value in initial["ram"]:
        memory.write8(address, value)

    cpu = Cpu(memory, reset=False)
    cpu.emulation = bool(initial["e"])
    cpu.set_status(initial["p"])
    cpu.a = initial["a"]
    cpu.x = initial["x"]
    cpu.y = initial["y"]
    cpu.s = initial["s"]
    cpu.d = initial["d"]
    cpu.db = initial["dbr"]
    cpu.pb = initial["pbr"]
    cpu.pc = initial["pc"]
    return cpu, memory


def check(test):
    """Where the interpreter and the suite disagree after one instruction.

    The suite records how many cycles it let the instruction have, which matters
    only for the block moves: those are interruptible and the suite captures a
    hundred cycle window rather than a move of sixty thousand bytes. Every other
    instruction finishes well inside its window, so the budget changes nothing.
    """
    cpu, memory = machine_for(test["initial"])
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


def run_tests(tests):
    """How many agreed, how many did not, and a few that did not."""
    passed = failed = 0
    examples = []
    for test in tests:
        try:
            wrong = check(test)
        except Exception as error:  # noqa: BLE001
            wrong = [("raised", type(error).__name__, str(error)[:60])]
        if wrong:
            failed += 1
            if len(examples) < EXAMPLE_LIMIT:
                examples.append((test["name"], wrong))
        else:
            passed += 1
    return passed, failed, examples


def run_file(path, limit=None):
    """One test file, optionally only its first few cases."""
    with Path(path).open() as handle:
        tests = json.load(handle)
    if limit:
        tests = tests[:limit]
    return run_tests(tests)


def main(argv):
    if not argv:
        print("usage: singlestep.py <suite directory> [tests per file] [name filter]")
        return 2

    directory = Path(argv[0])
    limit = int(argv[1]) if len(argv) > 1 else None
    wanted = argv[2] if len(argv) > 2 else ""

    files = [path for path in suite_files(directory) if wanted in path.name]
    if not files:
        print(f"  no suite at {directory}; clone SingleStepTests/ProcessorTests to get one")
        return 0

    print(f"  {len(files)} files from {directory}")
    passed = failed = 0
    broken = []
    for path in files:
        file_passed, file_failed, examples = run_file(path, limit)
        passed += file_passed
        failed += file_failed
        if file_failed:
            broken.append((path.name, file_failed, examples))

    print(f"  {passed} agreed, {failed} did not")
    for name, count, examples in broken[:EXAMPLE_LIMIT]:
        detail = ", ".join(f"{field} want {want} got {got}" for field, want, got in examples[0][1])
        print(f"    {name}: {count} wrong, first {examples[0][0]}: {detail}")
    if len(broken) > EXAMPLE_LIMIT:
        print(f"    and {len(broken) - EXAMPLE_LIMIT} more files with failures")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
