from __future__ import annotations


class UnsupportedError(Exception): ...


class Stopped(Exception): ...


class Waiting(Stopped): ...


class RunLimit(Exception): ...


class ClockClosed(Exception): ...


class Truncated(Exception): ...


class NoSuchPin(Exception): ...


class InsideInstruction(Exception):
    def __init__(self, line: str, pending: str | None = None) -> None:
        where, remedy = (
            ("inside an instruction", "to the instruction boundary")
            if pending is None
            else (f"while an entry through {pending}_line is pending", "through that entry")
        )
        super().__init__(
            f"{line}() was called {where}; tick the clock {remedy}, or set {line}_line, "
            "which the part samples when the instruction completes"
        )


class UnknownModelError(Exception):
    pass
