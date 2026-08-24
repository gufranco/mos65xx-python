"""How fast the model runs, and a floor it must not fall through.

Not a benchmark for its own sake. A model of a processor is only useful if it can
be driven for long enough to be interesting, and the way that stops being true is
gradual: a helper grows an allocation, a property becomes a lookup, and a year
later nothing can be swept. A floor that fails loudly is cheaper than noticing.

The floor is deliberately far below what the model does today. It is there to
catch something several times slower, not to police the noise between one runner
and another, because a shared runner's variance is larger than any change worth
arguing about.

Every figure is a median across repeats rather than a mean, because one scheduling
hiccup moves a mean and moves a median much less, and the runtime version is
printed beside it because it is the single thing that changes these numbers most.

Nothing here needs an image or a cartridge. It runs whatever the fill puts in
front of it, which is the same work the conformance sweep does.

The floor is checked here and never from inside the test suite, because the suite
runs under a coverage tracer and the tracer costs about ten times what the model
does: a million a second becomes a hundred thousand. A throughput
assertion in that environment measures the tracer, passes or fails for reasons
that have nothing to do with this code, and would have to be set so low it could
not catch anything. So the tests here check the measuring, with a clock they
control, and the measurement itself is a step of its own.

Usage:
    python3 -m conformance.speed [--repeats N] [--instructions N]
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, override

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mos65xx

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence

INSTRUCTIONS = 200_000
"""How many cycles one repeat runs. Long enough to swamp the setup."""

FILL = 0xEA
"""The byte the part runs through: NOP, the simplest instruction it has.

The cheapest instruction is the demanding measure, because it is the one where
the decode is the whole cost. A fill of something longer would run fewer
instructions for the same cycles and read as faster.
"""

REPEATS = 7
"""How many repeats a median is taken over. Odd, so the median is a measurement."""

FLOOR = 700_000
"""Cycles per second the model must beat, uninstrumented.

Measured at 3.80 million on Python 3.14 when this was written, so the floor
sits about five times below it. That leaves room for a shared runner having a
bad minute and none for a change that made the model several times slower.

There is no percentage of real time reported beside it, as the sibling package
reports. That part has one clock rate in its data sheet. This one shipped in
speed grades from a few megahertz upward across two decades, so there is no
single rate that is the silicon's, and inventing one to divide by would dress a
choice up as a measurement.
"""


class Usage(Exception):
    pass


class Timed:
    """What a run measured."""

    def __init__(self, part: str, instructions: int, seconds: Sequence[float]) -> None:
        self.part = part
        self.instructions = instructions
        self.seconds = tuple(seconds)

    @property
    def median(self) -> float:
        return statistics.median(self.seconds)

    @property
    def rate(self) -> float:
        """Cycles per second, at the median."""
        return self.instructions / self.median

    def beats(self, floor: int) -> bool:
        return self.rate >= floor

    @override
    def __repr__(self) -> str:
        return f"<Timed {self.part}, {self.rate:,.0f} cycles per second>"


def _clock() -> float:  # pragma: no cover
    return time.perf_counter()


def timed(
    part: str = "6502",
    instructions: int = INSTRUCTIONS,
    repeats: int = REPEATS,
    clock: Callable[[], float] = _clock,
) -> Timed:
    """Run that many cycles that many times, from a fresh part each repeat."""
    seconds = []
    for _ in range(repeats):
        chip = mos65xx.Cpu(part, mos65xx.Memory(image=bytes([FILL]) * 65536))
        chip.reset()
        at = clock()
        chip.run_for(instructions)
        seconds.append(clock() - at)
    return Timed(part, instructions, seconds)


def lines_for(found: Timed, floor: int = FLOOR) -> list[str]:
    """What was measured, with the numbers a reader needs to judge it."""
    said = [
        f"  {found.part}: {found.rate:,.0f} cycles per second at the median"
        f" of {len(found.seconds)} runs of {found.instructions:,}",
        f"     median {found.median:.3f}s, fastest {min(found.seconds):.3f}s,"
        f" slowest {max(found.seconds):.3f}s",
        f"     on Python {sys.version.split()[0]}",
    ]
    if not found.beats(floor):
        said.append(
            f"  ! below the floor of {floor:,} cycles per second."
            " Something got several times slower rather than a little noisier"
        )
    return said


def options(argv: Sequence[str]) -> tuple[int, int]:
    """How many cycles and how many repeats, from the command line."""
    instructions = INSTRUCTIONS
    repeats = REPEATS
    rest = list(argv)
    while rest:
        item = rest.pop(0)
        if item not in ("--instructions", "--repeats"):
            raise Usage(f"unknown option {item}")
        if not rest:
            raise Usage(f"{item} needs a value")
        if item == "--instructions":
            instructions = int(rest.pop(0))
        else:
            repeats = int(rest.pop(0))
    return instructions, repeats


def main(
    argv: Sequence[str],
    floor: int = FLOOR,
    run: Callable[..., Timed] = timed,
    say: Callable[[str], object] = print,
) -> int:
    try:
        instructions, repeats = options(argv)
    except Usage as error:
        say(str(error))
        return 2

    found = run(instructions=instructions, repeats=repeats)
    for line in lines_for(found, floor):
        say(line)
    return 0 if found.beats(floor) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
