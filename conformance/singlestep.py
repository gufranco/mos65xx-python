from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conformance.divergent import recorded_divergence, unexplained  # noqa: E402
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
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def machine_for(initial: Mapping[str, Any], model: str = DEFAULT_MODEL) -> Any:
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


Tally = tuple[int, int, int, int, list[tuple[str, list[tuple[str, Any, Any]]]]]


def run_tests(tests: Iterable[Mapping[str, Any]], model: str = DEFAULT_MODEL) -> Tally:
    passed = failed = skipped = excused = 0
    examples: list[tuple[str, list[tuple[str, Any, Any]]]] = []
    for test in tests:
        try:
            wrong = check(test, model)
        except Exception as error:  # noqa: BLE001
            wrong = [("raised", type(error).__name__, str(error)[:60])]
        if not wrong:
            passed += 1
            continue
        if recorded_divergence(test, model):
            skipped += 1
            continue
        left = unexplained(test, wrong, model)
        if not left:
            excused += 1
            continue
        failed += 1
        if len(examples) < EXAMPLE_LIMIT:
            examples.append((test["name"], left))
    return passed, failed, skipped, excused, examples


def run_file(path: Path, limit: int | None = None, model: str = DEFAULT_MODEL) -> Tally:
    held = Path(path).read_text().strip()
    if not held:
        return 0, 0, 0, 0, []
    tests = json.loads(held)
    if limit:
        tests = tests[:limit]
    return run_tests(tests, model)


USAGE = "usage: python3 -m conformance.singlestep <suite directory> [tests per file] [filter] [--model name]"


class Usage(Exception):
    pass


def options(argv: Sequence[str]) -> Any:
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
    passed = failed = skipped = excused = 0
    broken = []
    empty = []
    for path in files:
        file_passed, file_failed, file_skipped, file_excused, examples = run_file(
            path, limit, model
        )
        passed += file_passed
        failed += file_failed
        skipped += file_skipped
        excused += file_excused
        if not (file_passed or file_failed or file_skipped or file_excused):
            empty.append(path.stem)
        if file_failed:
            broken.append((path.name, file_failed, examples))

    print(f"  {passed} agreed, {failed} did not")
    if excused:
        print(
            f"  {excused} agreed in every field but those a recorded divergence names,"
            f" explained in conformance/divergences.json"
        )
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
