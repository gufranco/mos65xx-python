import random
from collections.abc import Sequence

UNSET_SEED = 0x5A5A5A5A

ADDRESS_MASK = 0xFFFFFF

_GOLDEN = 2654435761
_MIX = 2246822519
_SEED_STRIDE = 40503
_WORD = 0xFFFFFFFF


def scramble(size: int, seed: int = UNSET_SEED) -> bytearray:
    return bytearray(random.Random(seed).randbytes(size))


class SparseMemory:
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
    __slots__ = ("data",)

    def __init__(
        self,
        size: int = 0x1000000,
        image: "Sequence[int] | None" = None,
        seed: int = UNSET_SEED,
        fill: int | None = None,
    ) -> None:
        self.data = scramble(size, seed) if fill is None else bytearray([fill & 0xFF]) * size
        if image is not None:
            self.data[: len(image)] = image

    def read8(self, address: int) -> int:
        return self.data[address & ADDRESS_MASK]

    def write8(self, address: int, value: int) -> None:
        self.data[address & ADDRESS_MASK] = value & 0xFF
