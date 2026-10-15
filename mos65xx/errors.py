from __future__ import annotations


class UnsupportedError(Exception): ...


class Stopped(Exception): ...


class Waiting(Stopped): ...


class RunLimit(Exception): ...


class ClockClosed(Exception): ...


class Truncated(Exception): ...


class NoSuchPin(Exception): ...


class UnknownModelError(Exception):
    pass
