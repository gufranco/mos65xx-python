"""The conditions a part of this family can be in that no instruction gets it out of.

One definition each, shared by every core, because a caller writing `except
Stopped` should not have to know which part raised it. Two classes with the same
name in two modules is the kind of trap that looks like it works: the exception
is caught in testing against one model and sails straight through against
another.
"""

from __future__ import annotations


class UnsupportedError(Exception):
    """An opcode this core has no handler for, which is a gap here rather than in the part."""


class Stopped(Exception):
    """The part has shut its own clock down and only RESET restarts it.

    A jammed NMOS part also reports here, because from a caller's side the two
    look the same: no further instruction will complete. What the part is doing
    on the bus differs sharply and `jammed` tells them apart.
    """


class Waiting(Stopped):
    """The part is holding after WAI, which an interrupt ends and reset also does.

    A subclass of Stopped because the two share the only thing a caller stepping
    instructions needs to know: none will complete. They are not the same state.
    A part told to STP has shut its own clock down, while a waiting part is still
    clocked and resumes on the next interrupt it is allowed to take. The NMOS
    parts have neither instruction and never raise it.
    """


class RunLimit(Exception):
    """A bounded run reached its bound before the caller's condition held.

    Only `run_until` raises this, and only when a caller asked for a bound. A
    part has no such limit: given a program that never satisfies the condition it
    runs until the power goes. The bound is a courtesy to whoever is driving, not
    a property of the silicon.
    """


class ClockClosed(Exception):
    """A clock that has been closed cannot be ticked again.

    Nothing about the processor. The clock has let its worker go and handed the
    part's hook back, so there is nothing left to advance.
    """


class Truncated(Exception):
    """The bytes ran out before the instruction did.

    One definition for both decoders. It was two, one in each opcode module, and
    the package exported the 65816 one. So `except mos65xx.Truncated` was written
    against the package, tested against the 65816, and sailed straight past the
    same condition raised by the 6502 decoder, which is the trap the standard
    names.
    """


class NoSuchPin(Exception):
    """Raised when a caller pulls a line the package does not bring out.

    The narrower parts of the family are the same die in a smaller package, and
    the lines that did not fit are simply not there. A system cannot assert one,
    so a model that quietly accepted the request would be describing a part
    nobody could build.
    """


class UnknownModelError(Exception):
    pass
