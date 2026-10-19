from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

WORK_RAM_BANKS = (0x7E, 0x7F)

WORK_RAM_BYTES = 0x20000

SYSTEM_AREA = 0x2000

LAYOUTS = ("lorom", "hirom")

VIDEO_WORDS = 0x8000

VIDEO_MASK = VIDEO_WORDS - 1

FLAG = 0x80

VERSIONS = {0x4210: 0x02}

OPEN_BUS = {0x4210: 0x70, 0x4212: 0x3E}

STEPS = (1, 32, 128, 128)

PATTERNS = {0: (0,), 1: (0, 1), 2: (0, 0), 3: (0, 0, 1, 1), 4: (0, 1, 2, 3)}

CHANNELS = 8

CHANNEL_REGISTERS = range(0x4300, 0x4380)

B_BUS = 0x2100

PRINTABLE = range(32, 127)

WORDS = ("PASS", "FAIL")

ROWS = 28

COLUMNS = 32

BYTE = 0xFF

WORD = 0xFFFF


def system_bank(bank: int) -> bool:
    return bank < 0x40 or 0x80 <= bank < 0xC0


class Board:
    def __init__(
        self, image: bytes, layout: str, watch: Callable[[tuple[int, int]], Any] | None = None
    ) -> None:
        if layout not in LAYOUTS:
            raise ValueError(f"{layout} is not a layout this board decodes: {', '.join(LAYOUTS)}")
        self.image = image
        self.high = layout == "hirom"
        self.watch = watch
        self.work_ram = bytearray(WORK_RAM_BYTES)
        self.video = [0] * VIDEO_WORDS
        self.address = 0
        self.increment = 0
        self.bases = [0, 0, 0, 0]
        self.layers = 0
        self.flags = {0x4210: 0, 0x4212: 0, 0x4218: 0}
        self.channels = [[0] * 16 for _ in range(CHANNELS)]
        self.tail = ""
        self.printed = dict.fromkeys(WORDS, 0)
        self.pressed_at: list[str] = []
        self.bus = 0

    def at_in_image(self, bank: int, offset: int) -> int | None:
        if self.high and (bank >= 0xC0 or (system_bank(bank) and offset >= 0x8000)):
            return ((bank & 0x3F) << 16 | offset) % len(self.image)
        if not self.high and offset >= 0x8000:
            return ((bank & 0x7F) * 0x8000 + offset - 0x8000) % len(self.image)
        return None

    def read8(self, address: int) -> int:
        self.bus = self.fetch(address)
        return self.bus

    def fetch(self, address: int) -> int:
        bank, offset = address >> 16, address & WORD
        if bank in WORK_RAM_BANKS:
            return self.work_ram[((bank - WORK_RAM_BANKS[0]) << 16) | offset]
        at = self.at_in_image(bank, offset)
        if at is not None:
            return self.image[at]
        if not system_bank(bank):
            return 0
        if offset < SYSTEM_AREA:
            return self.work_ram[offset]
        return self.read_register(offset)

    def read_register(self, offset: int) -> int:
        if offset in CHANNEL_REGISTERS:
            return self.channels[(offset >> 4) & 7][offset & 15]
        if offset == 0x2139:
            return self.video[self.address & VIDEO_MASK] & BYTE
        if offset not in self.flags:
            return 0
        self.flags[offset] ^= FLAG
        if offset == 0x4218 and self.flags[offset]:
            self.pressed_at = [*self.pressed_at, self.screen()]
        return self.flags[offset] | (self.bus & OPEN_BUS.get(offset, 0)) | VERSIONS.get(offset, 0)

    def write8(self, address: int, value: int) -> None:
        if self.watch is not None:
            self.watch((address, value))
        bank, offset = address >> 16, address & WORD
        if bank in WORK_RAM_BANKS:
            self.work_ram[((bank - WORK_RAM_BANKS[0]) << 16) | offset] = value
        elif self.at_in_image(bank, offset) is not None or not system_bank(bank):
            return
        elif offset < SYSTEM_AREA:
            self.work_ram[offset] = value
        else:
            self.write_register(offset, value)

    def write_register(self, offset: int, value: int) -> None:
        if offset in CHANNEL_REGISTERS:
            self.channels[(offset >> 4) & 7][offset & 15] = value
            return
        writers = {
            0x2107: lambda held: self.set_base(0, held),
            0x2108: lambda held: self.set_base(1, held),
            0x2109: lambda held: self.set_base(2, held),
            0x210A: lambda held: self.set_base(3, held),
            0x212C: self.set_layers,
            0x2115: self.set_increment,
            0x2116: lambda held: self.set_address((self.address & 0xFF00) | held),
            0x2117: lambda held: self.set_address((self.address & BYTE) | (held << 8)),
            0x2118: lambda held: self.write_video(held, high=False),
            0x2119: lambda held: self.write_video(held, high=True),
            0x420B: self.transfer,
        }
        writer = writers.get(offset)
        if writer is not None:
            writer(value)

    def set_base(self, layer: int, value: int) -> None:
        self.bases[layer] = (value & 0xFC) << 8

    def set_layers(self, value: int) -> None:
        self.layers = value

    def base(self) -> int:
        shown = [layer for layer in range(len(self.bases)) if self.layers & (1 << layer)]
        return self.bases[shown[0] if shown else 0]

    def set_increment(self, value: int) -> None:
        self.increment = value

    def set_address(self, value: int) -> None:
        self.address = value

    def write_video(self, value: int, high: bool) -> None:
        at = self.address & VIDEO_MASK
        word = self.video[at]
        self.video[at] = (word & BYTE) | (value << 8) if high else (word & 0xFF00) | value
        if not high:
            self.count(value)
        if high == bool(self.increment & FLAG):
            self.address = (self.address + STEPS[self.increment & 3]) & WORD

    def count(self, value: int) -> None:
        self.tail = (self.tail + (chr(value) if value in PRINTABLE else " "))[-4:]
        if self.tail in self.printed:
            self.printed[self.tail] += 1

    def transfer(self, mask: int) -> None:
        for channel in range(CHANNELS):
            if mask & (1 << channel):
                self.run_channel(channel)

    def run_channel(self, channel: int) -> None:
        held = self.channels[channel]
        control, target = held[0], held[1]
        source, bank = held[2] | (held[3] << 8), held[4]
        count = (held[5] | (held[6] << 8)) or 0x10000
        pattern = PATTERNS.get(control & 7, (0,))
        for index in range(count):
            register = B_BUS + ((target + pattern[index % len(pattern)]) & BYTE)
            if control & 0x80:
                self.write8((bank << 16) | source, self.read8(register))
            else:
                self.write8(register, self.read8((bank << 16) | source))
            if not control & 0x08:
                source = (source + (-1 if control & 0x10 else 1)) & WORD
        self.channels[channel] = [*held[:5], 0, 0, *held[7:]]

    def row(self, number: int) -> str:
        start = self.base() + number * COLUMNS
        words = [self.video[(start + column) & VIDEO_MASK] & BYTE for column in range(COLUMNS)]
        return "".join(chr(one) if one in PRINTABLE else " " for one in words)

    def screen(self) -> str:
        lines = [self.row(number).rstrip() for number in range(ROWS)]
        return "\n".join(line for line in lines if line)
