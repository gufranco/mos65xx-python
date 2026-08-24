"""Driving a part one cycle at a time, the way a crystal drives one.

`step()` runs a whole instruction because that is the unit a program is written
in. A board has no such unit. It has a clock, and between two edges of it a
cartridge can change what a read will answer, a video chip can raise a line, and
a second processor can take the bus.

Reaching that from outside needs the part suspended part way through an
instruction, and an instruction here is an ordinary call stack: `step` calls a
handler, the handler reads an operand, the read spends a cycle. Python cannot
suspend a call stack. A generator suspends only its own frame, so making the
read yield would mean making every function between it and `step` a generator
too, which is a rewrite of every instruction in the package and a worse one to
read afterwards.

The way round it is the way ares and bsnes take: run the instruction on a thread
of its own and let it block where the cycle is spent. The instruction code stays
exactly as it is and never learns it was interrupted. A cycle costs a pair of
handoffs between two threads, so this is far slower than `step`, and that is the
correct trade: `step` is there when a caller wants speed, and this is there when
a caller wants the truth about where a cycle falls.

Only one thread runs at a time. The worker holds the part while the driver
waits, then the driver holds it while the worker waits, so nothing is shared
concurrently and no lock protects the processor itself.
"""

from __future__ import annotations

import threading
from types import TracebackType
from typing import Any

from .errors import ClockClosed


class Clock:
    """One part, advanced a cycle at a time rather than an instruction at a time.

    Built around a part, it takes over that part's `on_cycle` hook and gives it
    back when closed. A part being clocked must not also be stepped by hand: the
    worker is inside an instruction, and calling `step` from outside would run a
    second one on top of it.
    """

    __slots__ = (
        "_arrived",
        "_failure",
        "_previous",
        "_resume",
        "_worker",
        "closed",
        "cpu",
        "cycles",
    )

    def __init__(self, cpu: Any) -> None:
        self.cpu = cpu
        self.cycles = 0
        self.closed = False
        self._resume = threading.Semaphore(0)
        self._arrived = threading.Semaphore(0)
        self._failure: BaseException | None = None
        self._previous = cpu.on_cycle
        cpu.on_cycle = self._reached_a_cycle
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self) -> None:
        """Run the part forever, blocking inside every cycle it spends.

        A part that has stopped advancing the program still costs its host every
        cycle, so this keeps clocking it rather than letting the refusal out.
        Which call does that differs by family and the difference is real: a
        halted Z80 goes on executing, so `step` keeps working and returns the
        four T states each pass costs, while a jammed or stopped 65xx part
        completes no further instruction and produces its cycles through
        `held_cycle`. Asking the part which it is keeps the clock out of the
        business of knowing.
        """
        holds = hasattr(self.cpu, "held_cycle")
        self._resume.acquire()
        try:
            while not self.closed:
                if holds and self.cpu.held():
                    self.cpu.held_cycle()
                else:
                    self.cpu.step()
        except _Closed:
            pass
        except BaseException as failure:  # noqa: BLE001
            self._failure = failure
        self._arrived.release()

    def _reached_a_cycle(self) -> None:
        """Hand the part back to the driver, and wait to be given it again."""
        self._arrived.release()
        self._resume.acquire()
        if self.closed:
            raise _Closed

    def tick(self) -> int:
        """Advance the part by exactly one cycle, and report the total spent.

        Returns the running total rather than one, because one is the answer
        every time and a total is what a caller pacing against a wall needs.
        """
        if self.closed:
            raise ClockClosed("this clock has been closed")
        self._resume.release()
        self._arrived.acquire()
        if self._failure is not None:
            failure, self._failure = self._failure, None
            self.closed = True
            raise failure
        self.cycles += 1
        return self.cycles

    def run_for(self, cycles: int) -> int:
        """Advance exactly this many cycles, no more and no fewer.

        The difference from the part's own `run_for` is the whole point of this
        class. That one spends whole instructions and overshoots, because an
        instruction cannot be cut in half. This one stops between any two cycles,
        including the middle of an instruction, because that is where a board
        would.
        """
        for _ in range(cycles):
            self.tick()
        return self.cycles

    def close(self) -> None:
        """Let the worker go, and give the part its hook back."""
        if self.closed:
            return
        self.closed = True
        self._resume.release()
        self._arrived.acquire()
        self._worker.join(timeout=5.0)
        self.cpu.on_cycle = self._previous

    def __iter__(self) -> Clock:
        return self

    def __next__(self) -> int:
        if self.closed:
            raise StopIteration
        return self.tick()

    def __enter__(self) -> Clock:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.close()


class _Closed(BaseException):
    """Raised inside the worker to unwind it when the clock is closed.

    A BaseException rather than an Exception so that no `except Exception` in an
    instruction can swallow it and leave the thread running after the driver has
    gone.
    """
