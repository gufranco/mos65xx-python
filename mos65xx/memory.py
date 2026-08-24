"""Memory that holds what it held, because hardware never hands over a clean one.

A console that has just been switched on holds a pattern decided by the parts it
is built from. Code that reads a byte it never wrote reads that pattern, and on a
real machine that read is a bug waiting for the day the pattern changes. Memory
that begins at zero hides every one of those reads, so nothing here begins at
zero unless a caller asks for it in writing.

Nothing here can be asked for cleared. Earlier versions let a caller name a byte
to fill with, and every use of it was a test quietly arranging for a read of
unwritten memory to answer zero, which is the exact bug the scrambling exists to
expose.

Two shapes are offered because the cost of being unclean differs. `Memory` fills
a real buffer, which suits a machine that will touch most of its address space.
`SparseMemory` derives an unwritten byte from its address, which suits a test
that touches a dozen and should not pay for sixteen megabytes to do it.
"""

import random
from collections.abc import Sequence

UNSET_SEED = 0x5A5A5A5A

ADDRESS_MASK = 0xFFFFFF

_GOLDEN = 2654435761
_MIX = 2246822519
_SEED_STRIDE = 40503
_WORD = 0xFFFFFFFF


def scramble(size: int, seed: int = UNSET_SEED) -> bytearray:
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

    __slots__ = (
        "cells",
        "seed",
    )

    def __init__(self, seed: int = UNSET_SEED) -> None:
        self.cells: dict[int, int] = {}
        self.seed = seed & _WORD

    def _unwritten(self, address: int) -> int:
        mixed = (address * _GOLDEN + self.seed * _SEED_STRIDE) & _WORD
        mixed ^= mixed >> 15
        mixed = (mixed * _MIX) & _WORD
        mixed ^= mixed >> 13
        return mixed & 0xFF

    def read8(self, address: int) -> int:
        address &= ADDRESS_MASK
        found = self.cells.get(address)
        return self._unwritten(address) if found is None else found

    def write8(self, address: int, value: int) -> None:
        self.cells[address & ADDRESS_MASK] = value & 0xFF


class Memory:
    """Flat memory, holding the pattern the parts it is built from decide.

    There is no way to ask for a cleared one, because no machine hands one over.
    A read of a byte nothing wrote is a defect on real silicon, and memory that
    answers zero to it turns that defect into a passing test.

    `image` is what a board genuinely does know at power on: the bytes a mask
    ROM or a cartridge holds, loaded at the bottom. Everything the image does
    not cover stays undefined, because on the board it is.
    """

    __slots__ = ("data",)

    def __init__(
        self,
        size: int = 0x1000000,
        image: "Sequence[int] | None" = None,
        seed: int = UNSET_SEED,
    ) -> None:
        self.data = scramble(size, seed)
        if image is not None:
            self.data[: len(image)] = image

    def read8(self, address: int) -> int:
        return self.data[address & ADDRESS_MASK]

    def write8(self, address: int, value: int) -> None:
        self.data[address & ADDRESS_MASK] = value & 0xFF
