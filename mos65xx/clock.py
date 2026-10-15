from __future__ import annotations

import threading
from types import TracebackType
from typing import Any

from .errors import ClockClosed


class Clock:
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
        self._arrived.release()
        self._resume.acquire()
        if self.closed:
            raise _Closed

    def tick(self) -> int:
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
        for _ in range(cycles):
            self.tick()
        return self.cycles

    def close(self) -> None:
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


class _Closed(BaseException): ...
