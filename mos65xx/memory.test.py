import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos65xx.memory import UNSET_SEED, Memory, SparseMemory, scramble


class ScrambleTest(unittest.TestCase):
    def test_gives_the_requested_length(self) -> None:
        self.assertEqual(len(scramble(64)), 64)

    def test_repeats_for_one_seed(self) -> None:
        self.assertEqual(scramble(256, seed=7), scramble(256, seed=7))

    def test_differs_between_seeds(self) -> None:
        self.assertNotEqual(scramble(256, seed=7), scramble(256, seed=8))

    def test_is_not_a_cleared_machine(self) -> None:
        self.assertNotEqual(scramble(4096), bytearray(4096))

    def test_covers_most_of_the_byte_range(self) -> None:
        seen = set(scramble(4096))

        self.assertGreater(len(seen), 200)

    def test_gives_nothing_for_no_length(self) -> None:
        self.assertEqual(scramble(0), bytearray())


class SparseMemoryTest(unittest.TestCase):
    def test_reads_back_what_was_written(self) -> None:
        memory = SparseMemory()

        memory.write8(0x123456, 0x9C)

        self.assertEqual(memory.read8(0x123456), 0x9C)

    def test_keeps_only_the_low_byte(self) -> None:
        memory = SparseMemory()

        memory.write8(0x000010, 0x1FF)

        self.assertEqual(memory.read8(0x000010), 0xFF)

    def test_wraps_the_address_into_the_space(self) -> None:
        memory = SparseMemory()

        memory.write8(0x1000010, 0x42)

        self.assertEqual(memory.read8(0x000010), 0x42)

    def test_reads_something_it_never_held(self) -> None:
        memory = SparseMemory()

        unwritten = {memory.read8(address) for address in range(0, 0x4000, 7)}

        self.assertGreater(len(unwritten), 1)

    def test_repeats_an_unwritten_read(self) -> None:
        memory = SparseMemory(seed=99)

        self.assertEqual(memory.read8(0xABCDEF), memory.read8(0xABCDEF))

    def test_differs_between_seeds(self) -> None:
        one = SparseMemory(seed=1)
        other = SparseMemory(seed=2)

        differing = [
            address for address in range(0x400) if one.read8(address) != other.read8(address)
        ]

        self.assertGreater(len(differing), 0x200)

    def test_allocates_only_what_was_written(self) -> None:
        memory = SparseMemory()

        memory.read8(0x010000)
        memory.write8(0x020000, 1)

        self.assertEqual(len(memory.cells), 1)

    def test_a_written_zero_stays_zero(self) -> None:
        memory = SparseMemory()
        address = next(a for a in range(0x1000) if memory.read8(a) != 0)

        memory.write8(address, 0)

        self.assertEqual(memory.read8(address), 0)


class MemoryTest(unittest.TestCase):
    def test_is_scrambled_when_nothing_is_asked_for(self) -> None:
        memory = Memory(size=0x1000)

        self.assertNotEqual(memory.data, bytearray(0x1000))

    def test_a_cleared_one_has_to_be_asked_for_in_writing(self) -> None:
        """The rule is the default, not the absence of an option.

        A caller who genuinely wants zeroes says so, and the request is the same
        word in every member of this family. What must never happen is getting
        them without asking.
        """
        self.assertEqual(set(Memory(size=0x100, fill=0).data), {0})

    def test_and_the_default_is_still_nothing_like_a_cleared_machine(self) -> None:
        memory = Memory(size=0x100)

        self.assertGreater(len(set(memory.data)), 1)

    def test_a_machine_that_has_just_been_switched_on_is_not_all_zeroes(self) -> None:
        memory = Memory(size=0x100)

        self.assertNotEqual(memory.data, bytearray(0x100))

    def test_takes_an_image_at_the_bottom(self) -> None:
        memory = Memory(size=0x100, image=b"\x01\x02\x03")

        self.assertEqual(bytes(memory.data[:3]), b"\x01\x02\x03")

    def test_leaves_what_the_image_does_not_cover_undefined(self) -> None:
        memory = Memory(size=0x10, image=b"\xff")

        self.assertNotEqual(memory.data[1:], bytearray(0x0F))

    def test_which_is_the_same_pattern_it_would_have_held_without_one(self) -> None:
        bare = Memory(size=0x10, seed=7)
        loaded = Memory(size=0x10, image=b"\xff", seed=7)

        self.assertEqual(loaded.data[1:], bare.data[1:])

    def test_repeats_for_one_seed(self) -> None:
        self.assertEqual(Memory(size=0x100, seed=3).data, Memory(size=0x100, seed=3).data)

    def test_reads_back_what_was_written(self) -> None:
        memory = Memory(size=0x10000)

        memory.write8(0x1234, 0x5A)

        self.assertEqual(memory.read8(0x1234), 0x5A)

    def test_keeps_only_the_low_byte(self) -> None:
        memory = Memory(size=0x10000)

        memory.write8(0x20, 0x3FF)

        self.assertEqual(memory.read8(0x20), 0xFF)

    def test_wraps_the_address_into_the_space(self) -> None:
        memory = Memory(size=0x1000000)

        memory.write8(0x1000020, 0x77)

        self.assertEqual(memory.read8(0x000020), 0x77)


class SeedTest(unittest.TestCase):
    def test_the_default_seed_is_shared(self) -> None:
        self.assertEqual(scramble(16), scramble(16, seed=UNSET_SEED))


if __name__ == "__main__":
    unittest.main()
