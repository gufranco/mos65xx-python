import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx import UNSET_SEED, Memory, SparseMemory, scramble


class ScrambleTest(unittest.TestCase):
    def test_gives_the_requested_length(self) -> None:
        # Arrange
        size = 64

        # Act
        found = scramble(size)

        # Assert
        self.assertEqual(len(found), 64)

    def test_repeats_for_one_seed(self) -> None:
        # Arrange
        first = scramble(256, seed=7)

        # Act
        second = scramble(256, seed=7)

        # Assert
        self.assertEqual(second, first)

    def test_differs_between_seeds(self) -> None:
        # Arrange
        first = scramble(256, seed=7)

        # Act
        second = scramble(256, seed=8)

        # Assert
        self.assertNotEqual(second, first)

    def test_is_not_a_cleared_machine(self) -> None:
        # Arrange
        size = 4096

        # Act
        found = scramble(size)

        # Assert
        self.assertNotEqual(found, bytearray(4096))

    def test_covers_most_of_the_byte_range(self) -> None:
        # Arrange
        size = 4096

        # Act
        seen = set(scramble(size))

        # Assert
        self.assertGreater(len(seen), 200)

    def test_gives_nothing_for_no_length(self) -> None:
        # Arrange
        size = 0

        # Act
        found = scramble(size)

        # Assert
        self.assertEqual(found, bytearray())

    def test_the_default_seed_is_the_published_one(self) -> None:
        # Arrange
        named = scramble(16, seed=0x5A5A5A5A)

        # Act
        found = scramble(16)

        # Assert
        self.assertEqual((found, UNSET_SEED), (named, 0x5A5A5A5A))


class SparseMemoryTest(unittest.TestCase):
    def test_reads_back_what_was_written(self) -> None:
        # Arrange
        memory = SparseMemory()

        # Act
        memory.write8(0x123456, 0x9C)

        # Assert
        self.assertEqual(memory.read8(0x123456), 0x9C)

    def test_keeps_only_the_low_byte(self) -> None:
        # Arrange
        memory = SparseMemory()

        # Act
        memory.write8(0x000010, 0x1FF)

        # Assert
        self.assertEqual(memory.read8(0x000010), 0xFF)

    def test_wraps_the_address_into_the_space(self) -> None:
        # Arrange
        memory = SparseMemory()

        # Act
        memory.write8(0x1000010, 0x42)

        # Assert
        self.assertEqual(memory.read8(0x000010), 0x42)

    def test_reads_something_it_never_held(self) -> None:
        # Arrange
        memory = SparseMemory()

        # Act
        unwritten = {memory.read8(address) for address in range(0, 0x4000, 7)}

        # Assert
        self.assertGreater(len(unwritten), 1)

    def test_repeats_an_unwritten_read(self) -> None:
        # Arrange
        memory = SparseMemory(seed=99)
        first = memory.read8(0xABCDEF)

        # Act
        second = memory.read8(0xABCDEF)

        # Assert
        self.assertEqual(second, first)

    def test_differs_between_seeds(self) -> None:
        # Arrange
        one = SparseMemory(seed=1)
        other = SparseMemory(seed=2)

        # Act
        differing = [
            address for address in range(0x400) if one.read8(address) != other.read8(address)
        ]

        # Assert
        self.assertGreater(len(differing), 0x200)

    def test_allocates_only_what_was_written(self) -> None:
        # Arrange
        memory = SparseMemory()
        memory.read8(0x010000)

        # Act
        memory.write8(0x020000, 1)

        # Assert
        self.assertEqual(memory.cells, {0x020000: 1})

    def test_a_written_zero_stays_zero(self) -> None:
        # Arrange
        memory = SparseMemory()
        address = next(a for a in range(0x1000) if memory.read8(a) != 0)

        # Act
        memory.write8(address, 0)

        # Assert
        self.assertEqual(memory.read8(address), 0)


class MemoryTest(unittest.TestCase):
    def test_is_scrambled_when_nothing_is_asked_for(self) -> None:
        # Arrange
        size = 0x1000

        # Act
        memory = Memory(size=size)

        # Assert
        self.assertNotEqual(memory.data, bytearray(0x1000))

    def test_a_cleared_one_has_to_be_asked_for_in_writing(self) -> None:
        # Arrange
        fill = 0

        # Act
        memory = Memory(size=0x100, fill=fill)

        # Assert
        self.assertEqual(set(memory.data), {0})

    def test_and_the_default_is_still_nothing_like_a_cleared_machine(self) -> None:
        # Arrange
        size = 0x100

        # Act
        memory = Memory(size=size)

        # Assert
        self.assertGreater(len(set(memory.data)), 1)

    def test_a_machine_that_has_just_been_switched_on_is_not_all_zeroes(self) -> None:
        # Arrange
        size = 0x100

        # Act
        memory = Memory(size=size)

        # Assert
        self.assertNotEqual(memory.data, bytearray(0x100))

    def test_takes_an_image_at_the_bottom(self) -> None:
        # Arrange
        image = b"\x01\x02\x03"

        # Act
        memory = Memory(size=0x100, image=image)

        # Assert
        self.assertEqual(bytes(memory.data[:3]), b"\x01\x02\x03")

    def test_leaves_what_the_image_does_not_cover_undefined(self) -> None:
        # Arrange
        image = b"\xff"

        # Act
        memory = Memory(size=0x10, image=image)

        # Assert
        self.assertNotEqual(memory.data[1:], bytearray(0x0F))

    def test_which_is_the_same_pattern_it_would_have_held_without_one(self) -> None:
        # Arrange
        bare = Memory(size=0x10, seed=7)

        # Act
        loaded = Memory(size=0x10, image=b"\xff", seed=7)

        # Assert
        self.assertEqual(loaded.data[1:], bare.data[1:])

    def test_repeats_for_one_seed(self) -> None:
        # Arrange
        first = Memory(size=0x100, seed=3)

        # Act
        second = Memory(size=0x100, seed=3)

        # Assert
        self.assertEqual(second.data, first.data)

    def test_reads_back_what_was_written(self) -> None:
        # Arrange
        memory = Memory(size=0x10000)

        # Act
        memory.write8(0x1234, 0x5A)

        # Assert
        self.assertEqual(memory.read8(0x1234), 0x5A)

    def test_keeps_only_the_low_byte(self) -> None:
        # Arrange
        memory = Memory(size=0x10000)

        # Act
        memory.write8(0x20, 0x3FF)

        # Assert
        self.assertEqual(memory.read8(0x20), 0xFF)

    def test_wraps_the_address_into_the_space(self) -> None:
        # Arrange
        memory = Memory(size=0x1000000)

        # Act
        memory.write8(0x1000020, 0x77)

        # Assert
        self.assertEqual(memory.read8(0x000020), 0x77)


if __name__ == "__main__":
    unittest.main()
