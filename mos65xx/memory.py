"""Memory that holds what it held, because hardware never hands over a clean one.

A console that has just been switched on holds a pattern decided by the parts it
is built from. Code that reads a byte it never wrote reads that pattern, and on a
real machine that read is a bug waiting for the day the pattern changes. Memory
that begins at zero hides every one of those reads, so nothing here begins at
zero unless a caller asks for it in writing.

Two shapes are offered because the cost of being unclean differs. `Memory` fills
a real buffer, which suits a machine that will touch most of its address space.
`SparseMemory` derives an unwritten byte from its address, which suits a test
that touches a dozen and should not pay for sixteen megabytes to do it.
"""

import random

UNSET_SEED = 0x5A5A5A5A

ADDRESS_MASK = 0xFFFFFF

_GOLDEN = 2654435761
_MIX = 2246822519
_SEED_STRIDE = 40503
_WORD = 0xFFFFFFFF


def scramble(size, seed=UNSET_SEED):
    """A deterministic fill that is nothing like a cleared machine.

    Reproducible from the seed, so a differential run stays comparable, and
    obviously not clean, so a read of something never written shows up.
    """
    return bytearray(random.Random(seed).randbytes(size))


class SparseMemory:
    """Unclean everywhere without being allocated anywhere.

    Holds only what has been written and derives the rest from the address, so an
    unwritten byte still reads as something arbitrary, still differs from zero,
    and still reads the same twice, at no setup cost.
    """

    def __init__(self, seed=UNSET_SEED):
        self.cells = {}
        self.seed = seed & _WORD

    def _unwritten(self, address):
        mixed = (address * _GOLDEN + self.seed * _SEED_STRIDE) & _WORD
        mixed ^= mixed >> 15
        mixed = (mixed * _MIX) & _WORD
        mixed ^= mixed >> 13
        return mixed & 0xFF

    def read8(self, address):
        address &= ADDRESS_MASK
        found = self.cells.get(address)
        return self._unwritten(address) if found is None else found

    def write8(self, address, value):
        self.cells[address & ADDRESS_MASK] = value & 0xFF


class Memory:
    """Flat memory, filled rather than cleared.

    `fill` is a byte, a bytes-like image loaded at the bottom, or None for the
    scrambled pattern above. A caller that genuinely wants zeroes asks for zero
    and says so, which is the point: it becomes a decision rather than a default.
    """

    def __init__(self, size=0x1000000, fill=None, seed=UNSET_SEED):
        if fill is None:
            self.data = scramble(size, seed)
        elif isinstance(fill, int):
            self.data = bytearray([fill & 0xFF]) * size
        else:
            self.data = bytearray(size)
            self.data[: len(fill)] = fill

    def read8(self, address):
        return self.data[address & ADDRESS_MASK]

    def write8(self, address, value):
        self.data[address & ADDRESS_MASK] = value & 0xFF
