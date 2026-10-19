import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.board import Board

IMAGE = bytes(range(256)) * 512


class LayoutTest(unittest.TestCase):
    def test_a_low_layout_puts_each_32k_of_the_image_in_the_upper_half_of_a_bank(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")

        # Act
        read = board.read8(0x018001)

        # Assert
        self.assertEqual(read, IMAGE[0x8001])

    def test_a_high_layout_maps_whole_64k_banks(self) -> None:
        # Arrange
        board = Board(IMAGE, "hirom")

        # Act
        read = (board.read8(0x00FFFC), board.read8(0xC10005))

        # Assert
        self.assertEqual(read, (IMAGE[0xFFFC], IMAGE[0x10005]))

    def test_a_layout_it_does_not_know_is_refused(self) -> None:
        # Arrange
        attempt = lambda: Board(IMAGE, "exhirom")  # noqa: E731

        # Act
        refusal = attempt

        # Assert
        self.assertRaisesRegex(ValueError, "exhirom is not a layout", refusal)

    def test_a_write_to_the_image_changes_nothing(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")

        # Act
        board.write8(0x008000, 0xEE)

        # Assert
        self.assertEqual(board.read8(0x008000), IMAGE[0])


class WorkRamTest(unittest.TestCase):
    def test_the_two_banks_hold_what_was_written(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")

        # Act
        board.write8(0x7FABCD, 0x42)

        # Assert
        self.assertEqual(board.read8(0x7FABCD), 0x42)

    def test_the_low_8k_of_every_system_bank_is_the_start_of_work_ram(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")

        # Act
        board.write8(0xA01000, 0x99)

        # Assert
        self.assertEqual((board.read8(0x7E1000), board.read8(0x201000)), (0x99, 0x99))

    def test_a_bank_with_no_system_area_reads_zero_below_the_image(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")

        # Act
        board.write8(0x401000, 0x77)

        # Assert
        self.assertEqual(board.read8(0x401000), 0)

    def test_a_write_is_shown_to_whoever_watches(self) -> None:
        # Arrange
        seen: list[tuple[int, int]] = []
        board = Board(IMAGE, "lorom", seen.append)

        # Act
        board.write8(0x000075, 0xFF)

        # Assert
        self.assertEqual(seen, [(0x000075, 0xFF)])


class StatusTest(unittest.TestCase):
    def test_the_vblank_flag_rises_and_is_cleared_by_the_read_beside_the_version(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")

        # Act
        read = [board.read8(0x004210) for _ in range(3)]

        # Assert
        self.assertEqual(read, [0x82, 0x02, 0x82])

    def test_the_unused_status_bits_answer_whatever_the_bus_last_carried(self) -> None:
        # Arrange
        board = Board(bytes([0x42]) * 0x8000, "lorom")
        board.read8(0x008000)

        # Act
        read = (board.read8(0x004210), board.read8(0x008000), board.read8(0x004212))

        # Assert
        self.assertEqual(read, (0xC2, 0x42, 0x82))

    def test_the_blanking_flag_alternates_and_the_pad_is_never_busy(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")

        # Act
        read = [board.read8(0x004212) for _ in range(2)]

        # Assert
        self.assertEqual(read, [0x80, 0x00])

    def test_the_pad_presses_a_and_lets_go_and_the_screen_is_kept_at_each_press(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")
        for letter in b"Failed":
            board.write8(0x002118, letter)

        # Act
        read = [board.read8(0x004218) for _ in range(4)]

        # Assert
        self.assertEqual((read, board.pressed_at), ([0x80, 0x00, 0x80, 0x00], ["Failed", "Failed"]))

    def test_any_other_register_reads_zero_and_takes_writes_silently(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")

        # Act
        board.write8(0x004202, 0x10)

        # Assert
        self.assertEqual(board.read8(0x004216), 0)


class VideoTest(unittest.TestCase):
    def test_low_byte_writes_step_the_address_when_the_increment_is_low(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")
        board.write8(0x002115, 0x00)
        board.write8(0x002116, 0x20)
        board.write8(0x002117, 0x00)

        # Act
        for letter in b"OK":
            board.write8(0x002118, letter)

        # Assert
        self.assertEqual(board.screen(), "OK")

    def test_high_byte_writes_step_by_thirty_two_when_asked(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")
        board.write8(0x002115, 0x81)

        # Act
        for letter in b"HI":
            board.write8(0x002118, letter)
            board.write8(0x002119, 0x00)

        # Assert
        self.assertEqual(board.screen(), "H\nI")

    def test_the_screen_starts_where_the_first_layer_map_starts(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")
        board.write8(0x002107, 0x04)
        board.write8(0x002116, 0x00)
        board.write8(0x002117, 0x04)

        # Act
        for letter in b"A\x01B":
            board.write8(0x002118, letter)

        # Assert
        self.assertEqual(board.screen(), "A B")

    def test_the_screen_is_the_lowest_layer_shown_on_the_main_screen(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")
        board.write8(0x002108, 0x08)
        board.write8(0x00212C, 0x02)
        board.write8(0x002116, 0x00)
        board.write8(0x002117, 0x08)

        # Act
        for letter in b"BG2":
            board.write8(0x002118, letter)

        # Assert
        self.assertEqual(board.screen(), "BG2")

    def test_every_layer_map_register_is_read(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")
        board.write8(0x002109, 0x0C)
        board.write8(0x00210A, 0x10)
        board.write8(0x00212C, 0x08)
        board.write8(0x002117, 0x10)

        # Act
        board.write8(0x002118, ord("4"))

        # Assert
        self.assertEqual(board.screen(), "4")

    def test_the_low_byte_reads_back_where_the_address_points(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")
        board.write8(0x002115, 0x80)
        board.write8(0x002118, 0x5A)

        # Act
        read = board.read8(0x002139)

        # Assert
        self.assertEqual(read, 0x5A)

    def test_every_pass_and_fail_written_is_counted_as_it_goes(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")

        # Act
        for letter in b"PASS PASS FAIL":
            board.write8(0x002118, letter)

        # Assert
        self.assertEqual(board.printed, {"PASS": 2, "FAIL": 1})


class DmaTest(unittest.TestCase):
    def test_a_transfer_from_work_ram_fills_video_memory(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")
        for offset, letter in enumerate(b"GO"):
            board.write8(0x7E0100 + offset, letter)
        for register, value in enumerate((0x00, 0x18, 0x00, 0x01, 0x7E, 0x02, 0x00)):
            board.write8(0x004300 + register, value)

        # Act
        board.write8(0x00420B, 0x01)

        # Assert
        self.assertEqual((board.screen(), board.read8(0x004305)), ("GO", 0))

    def test_a_fixed_decrementing_and_two_register_transfer_follow_their_bits(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")
        board.write8(0x7E0201, 0x41)
        board.write8(0x002115, 0x80)
        for register, value in enumerate((0x11, 0x18, 0x01, 0x02, 0x7E, 0x02, 0x00)):
            board.write8(0x004310 + register, value)
        for register, value in enumerate((0x88, 0x39, 0x00, 0x03, 0x7E, 0x01, 0x00)):
            board.write8(0x004320 + register, value)

        # Act
        board.write8(0x00420B, 0x06)

        # Assert
        self.assertEqual((board.screen(), board.read8(0x7E0300)), ("A", 0x00))

    def test_an_unknown_pattern_writes_one_register_and_a_zero_count_is_65536(self) -> None:
        # Arrange
        board = Board(IMAGE, "lorom")
        for register, value in enumerate((0x07, 0x80, 0x00, 0x00, 0x7E, 0x00, 0x00)):
            board.write8(0x004370 + register, value)

        # Act
        board.write8(0x00420B, 0x80)

        # Assert
        self.assertEqual(board.read8(0x004375) | board.read8(0x004376), 0)


if __name__ == "__main__":
    unittest.main()
