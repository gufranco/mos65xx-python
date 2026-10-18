from __future__ import annotations


class UnsupportedError(Exception): ...


class Stopped(Exception): ...


class Waiting(Stopped): ...


class RunLimit(Exception): ...


class ClockClosed(Exception): ...


class Truncated(Exception): ...


class NoSuchPin(Exception): ...


class InsideInstruction(Exception):
    def __init__(self, line: str) -> None:
        super().__init__(
            f"{line}() was called inside an instruction; tick the clock to the instruction "
            f"boundary, or set {line}_line, which the part samples when the instruction completes"
        )


class UnknownModelError(Exception):
    pass
