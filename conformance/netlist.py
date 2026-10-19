from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mos65xx

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence

VARIABLE = "NETLIST"

AT = 0x0200

FILL = 0xEA


class Case:
    __slots__ = ("cycles", "program", "steps", "why")

    def __init__(self, why: str, program: bytes, cycles: int, steps: int) -> None:
        self.why = why
        self.program = program
        self.cycles = cycles
        self.steps = steps


CASES = (
    Case(
        "the discarded read of an indexed access that crosses a page",
        bytes((0xA2, 0x01, 0xBD, 0xFF, 0x12)),
        7,
        2,
    ),
    Case(
        "a taken branch that stays inside its page",
        bytes((0xA9, 0x01, 0xD0, 0x10)),
        5,
        2,
    ),
    Case(
        "a taken branch that crosses a page backwards",
        bytes((0xA9, 0x01, 0xD0, 0xE0)),
        6,
        2,
    ),
    Case(
        "the discarded read of an indexed access that stays inside its page",
        bytes((0xA2, 0x01, 0xBD, 0x00, 0x12)),
        6,
        2,
    ),
    Case(
        "a branch not taken, which spends no extra cycle at all",
        bytes((0xA9, 0x00, 0xD0, 0x10)),
        4,
        2,
    ),
    Case(
        "a jump through a pointer that ends a page, which reads the wrong high byte",
        bytes((0x6C, 0xFF, 0x12)),
        5,
        1,
    ),
    Case(
        "a read modify write on absolute, which writes the old value before the new",
        bytes((0x0E, 0x34, 0x12)),
        6,
        1,
    ),
    Case(
        "an indexed write, which does the discarded read even though it will not use it",
        bytes((0xA2, 0x01, 0x9D, 0xFF, 0x12)),
        7,
        2,
    ),
    Case(
        "a read modify write on indexed, which is five cycles and never skips one",
        bytes((0xA2, 0x01, 0x1E, 0xFF, 0x12)),
        9,
        2,
    ),
    Case(
        "an indirect indexed read that crosses a page",
        bytes((0xA0, 0x01, 0xB1, 0x80)),
        7,
        2,
    ),
    Case(
        "the second cycle of a two cycle opcode, which reads and does not increment",
        bytes((0x18, 0xEA)),
        4,
        2,
    ),
    Case(
        "a zero page indexed read, which wraps inside the page rather than carrying",
        bytes((0xA2, 0xFF, 0xB5, 0x02)),
        6,
        2,
    ),
)


def probe() -> Path | None:
    named = os.environ.get(VARIABLE, "")
    if not named:
        return None
    where = Path(named)
    return where if where.is_file() else None


RESET = Case(
    "a reset, from the cycle in progress when the line goes high to the push after it",
    bytes((0x48,)),
    11,
    1,
)

FIRST_STACK_CYCLE = 3

CHECKED = len(CASES) + 1


def _addresses(where: Path, argv: list[str], run: Any = None) -> list[int]:
    runner = subprocess.run if run is None else run
    done = runner(
        [str(where), *argv],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return [int(line.split()[1], 16) for line in done.stdout.splitlines() if line.strip()]


def _memory(program: bytes) -> Any:
    memory = mos65xx.Memory(image=bytes([FILL]) * 65536)
    for step, held in enumerate(program):
        memory.write8(AT + step, held)
    memory.write8(0xFFFC, AT & 0xFF)
    memory.write8(0xFFFD, AT >> 8)
    return memory


def reset_modelled(counter: int, stack: int) -> list[int]:
    cpu = mos65xx.Cpu("6502", _memory(RESET.program))
    cpu.pc = counter
    cpu.s = stack
    cpu.trace = []
    cpu.reset()
    for _ in range(RESET.steps):
        cpu.step()
    return [address for address, _value, *_rest in cpu.trace][: RESET.cycles]


def compare_reset(where: Path, run: Any = None) -> list[str]:
    die = _addresses(where, ["reset", RESET.program.hex(), str(RESET.cycles)], run)
    if len(die) != RESET.cycles:
        return [f"{RESET.why}: the die answered {len(die)} of {RESET.cycles} cycles"]
    ours = reset_modelled(die[0], die[FIRST_STACK_CYCLE] & 0xFF)
    if die == ours:
        return []
    return [
        f"{RESET.why}: die {[f'{one:04X}' for one in die]} model {[f'{one:04X}' for one in ours]}"
    ]


def _run(where: Path, case: Case, run: Any = None) -> list[int]:
    return _addresses(where, [case.program.hex(), str(case.cycles)], run)


def modelled(case: Case) -> list[int]:
    cpu = mos65xx.Cpu("6502", _memory(case.program))
    cpu.reset()
    cpu.trace = []
    for _ in range(case.steps):
        cpu.step()
    return [address for address, _value, *_rest in cpu.trace]


def compare(where: Path, cases: Sequence[Case] = CASES, run: Any = None) -> list[str]:
    found = []
    for case in cases:
        die = _run(where, case, run)
        ours = modelled(case)
        shared = min(len(die), len(ours))
        if die[:shared] != ours[:shared]:
            found.append(
                f"{case.why}: die {[f'{one:04X}' for one in die[:shared]]}"
                f" model {[f'{one:04X}' for one in ours[:shared]]}"
            )
    return found


def main(
    argv: Sequence[str] = (),
    where: Callable[[], Path | None] = probe,
    run: Any = None,
) -> int:
    found = where()
    if found is None:
        print(
            f"  skipped: no simulation on this machine. Point {VARIABLE} at a built"
            " perfect6502 probe to run these. Nothing is fetched or carried here."
        )
        return 0
    astray = compare(found, CASES, run) + compare_reset(found, run)
    for one in astray:
        print(f"  ! {one}")
    print(f"  {CHECKED} cases against the die, {CHECKED - len(astray)} agreed")
    return 1 if astray else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
