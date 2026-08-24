"""A 65816 interpreter that follows the processor rather than a convenient model.

Every one of the 256 opcodes is implemented. The 65816 defines all of them:
unlike the NMOS 6502 it has no undocumented instructions, and $42 WDM is
reserved rather than illegal and behaves as a two byte no operation.

Nothing here starts from a clean state. A processor coming out of reset holds
whatever its registers held, memory holds whatever it held, and an interpreter
that quietly begins at zero models a machine that has never existed. The reset
state below sets only what the hardware itself defines, and `Memory` fills with
a caller supplied pattern rather than with zeroes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import opcodes65816 as wdc65816
from .errors import RunLimit, Stopped, UnsupportedError, Waiting
from .memory import ADDRESS_MASK, UNSET_SEED, Memory, SparseMemory, scramble

OPCODES = wdc65816.OPCODES

__all__ = [
    "OPCODES",
    "UNSET_SEED",
    "Cpu",
    "Memory",
    "SparseMemory",
    "Stopped",
    "UnsupportedError",
    "scramble",
]

FLAG_C = 0x01
FLAG_Z = 0x02
FLAG_I = 0x04
FLAG_D = 0x08
FLAG_X = 0x10
FLAG_M = 0x20
FLAG_V = 0x40
FLAG_N = 0x80

IMMEDIATE_MODES = frozenset({"immediate", "immediateA", "immediateX"})
INDEX_WIDTH_OPS = frozenset({"ldx", "ldy", "stx", "sty", "cpx", "cpy"})

BREAK_VECTOR = 0x00FFE6
COP_VECTOR = 0x00FFE4
IRQ_VECTOR = 0x00FFEE
NMI_VECTOR = 0x00FFEA
ABORT_VECTOR = 0x00FFE8
EMULATION_BREAK_VECTOR = 0x00FFFE
EMULATION_COP_VECTOR = 0x00FFF4
EMULATION_IRQ_VECTOR = 0x00FFFE
EMULATION_NMI_VECTOR = 0x00FFFA
EMULATION_ABORT_VECTOR = 0x00FFF8
"""The two blocks of vectors, one per mode.

The native ones come from the pin descriptions rather than from the table that
lists them, which prints the emulation addresses under the native heading. Both
readings, and what settles the two the suite reaches, are in
conformance/hardware.json.
"""
BREAK_FLAG = 0x10
CYCLES_PER_MOVE = 7
PARTIAL_LIMIT = 4
"""How far into an interrupted iteration of a block move this model goes."""

NATIVE_VECTORS = {"irq": IRQ_VECTOR, "nmi": NMI_VECTOR, "abort": ABORT_VECTOR}
EMULATION_VECTORS = {
    "irq": EMULATION_IRQ_VECTOR,
    "nmi": EMULATION_NMI_VECTOR,
    "abort": EMULATION_ABORT_VECTOR,
}

ALWAYS_INDEXES = frozenset(
    {"sta", "stx", "sty", "stz", "asl", "lsr", "rol", "ror", "inc", "dec", "trb", "tsb"}
)
"""Instructions that spend the indexing cycle whether or not a carry is needed.

A write is one: the part will not aim a write at an address it might have to
correct. A read-modify-write is the other, for the same reason.
"""

BANK_ZERO_MODES = frozenset({"direct", "directX", "directY", "stack"})
"""Modes whose address is in bank zero and wraps inside it."""


HALTED_PINS = "--------"
"""What the eight output lines read once STP or WAI has taken effect.

Every line inactive, the read line included, which no ordinary cycle produces.
"""


RESET_VECTOR = 0x00FFFC

RESET_CYCLES = 8
"""How long a reset takes, counting the vector fetch.

WDC's data sheet gives no count of its own for this part, and the core it
describes is the same lineage, so the older MOS figure stands until one does:
the part "will delay 6 cycles and then fetch the new program count vectors".
"""

VECTOR_CYCLES = 2
"""The two cycles of the vector fetch, which every part pays and none states apart."""


class Cpu:
    """A 65816 in the state a reset leaves it, not in a state chosen for tidiness.

    A reset defines less than a model usually assumes. It forces emulation mode,
    which forces the accumulator and index registers to eight bits, clears
    decimal, sets the interrupt disable, zeroes the direct page and both bank
    registers, forces the high byte of the stack pointer to $01, and loads the
    program counter from the reset vector. It says nothing about the accumulator,
    the index registers, or the low byte of the stack pointer, and hardware
    leaves those holding whatever they held.

    So those are scrambled from a seed rather than zeroed. The values are
    reproducible, which keeps a differential run comparable, and they are not
    zero, which is what stops code that reads them before writing them from
    looking correct here and failing on a console.

    The slots are the point rather than a saving. This part spells the interrupt
    disable flag `.irq_disable` where the eight bit parts spell it `.i`, and
    without them a caller reaching for the wrong one sets a stray attribute in
    silence while the flag they meant keeps its value.
    """

    __slots__ = (
        "_emulation",
        "_s",
        "a",
        "address_mask",
        "c",
        "cycle_budget",
        "cycles",
        "d",
        "db",
        "decimal",
        "irq_disable",
        "irq_line",
        "locked",
        "m8",
        "memory",
        "model",
        "n",
        "nmi_line",
        "nmi_seen",
        "on_cycle",
        "package_pins",
        "pb",
        "pc",
        "pulling",
        "ready_line",
        "reset_cycles",
        "steps",
        "stopped",
        "trace",
        "v",
        "waiting",
        "x",
        "x8",
        "y",
        "z",
    )

    def __init__(
        self,
        memory: Any,
        seed: int = UNSET_SEED,
    ) -> None:
        self.memory = memory
        self.model = "65816"
        self.address_mask = ADDRESS_MASK
        self.package_pins: tuple[str, ...] = ("irq", "nmi", "rdy")
        self._emulation = False
        self._s = 0x01FF
        self.cycle_budget: int | None = None
        self.ready_line = True
        """The ready line, high when the part may proceed. Low halts it where it stands."""

        self.irq_line = False
        """The request line, active when true. Level sensitive: held, not pulsed."""

        self.nmi_line = False
        """The non-maskable line, active when true. Edge sensitive: the transition interrupts."""

        self.nmi_seen = False
        """The level the non-maskable line last had when it was read."""

        self.on_cycle: Callable[[], None] | None = None
        """Called once per cycle, after that cycle's bus activity."""

        self.trace: list[tuple[int | None, int | None, str]] | None = None
        """Every cycle this part drove, as address, value and the eight output lines.

        The address is None for the cycles after STP or WAI has taken effect,
        because a halted part drives no address at all. That is what the
        recordings carry and what the pin string reads as: eight dashes.
        """
        self.locked = False
        self.pulling = False
        self.steps = 0
        self.cycles = 0
        self.stopped = False
        self.waiting = False
        self.reset_cycles = RESET_CYCLES
        self.power_on(seed)

    @property
    def emulation(self) -> bool:
        return self._emulation

    @emulation.setter
    def emulation(self, value: bool) -> None:
        """Entering emulation mode narrows the machine, and does so at once.

        The index registers become eight bits and lose their high halves, the
        accumulator's width bit is forced, and the stack pointer is confined to
        page one. This is not something that happens on the next push: the
        registers are that narrow from the moment the mode changes.
        """
        self._emulation = bool(value)
        if self._emulation:
            self.m8 = True
            self.x8 = True
            self.x &= 0xFF
            self.y &= 0xFF
            self._s = 0x0100 | (self._s & 0xFF)

    @property
    def s(self) -> int:
        return self._s

    @s.setter
    def s(self, value: int) -> None:
        value &= 0xFFFF
        self._s = 0x0100 | (value & 0xFF) if self._emulation else value

    def power_on(self, seed: int = UNSET_SEED) -> None:
        """The state the part is in when the rail comes up and nothing else has.

        Every register holds a value derived from the seed, the program counter
        included, because a part that has been powered and not yet reset has no
        idea where it is. A caller that steps one executes rubbish from a rubbish
        address, which is what the silicon does.

        This is where the scrambling belongs. A reset defines what it defines and
        randomises nothing.
        """
        undefined = scramble(10, seed)
        self.a = undefined[0] | (undefined[1] << 8)
        self.x = undefined[2] | (undefined[3] << 8)
        self.y = undefined[4] | (undefined[5] << 8)
        self.s = undefined[6] | (undefined[7] << 8)
        self.d = undefined[8] | (undefined[9] << 8)
        self.db = undefined[0]
        self.pb = undefined[1]
        self.pc = undefined[2] | (undefined[3] << 8)
        self.n = bool(undefined[5] & 0x80)
        self.v = bool(undefined[5] & 0x40)
        self.z = bool(undefined[5] & 0x02)
        self.c = bool(undefined[5] & 0x01)
        self.decimal = bool(undefined[6] & 0x08)
        self.irq_disable = bool(undefined[6] & 0x04)
        self.emulation = bool(undefined[7] & 0x01)
        self.m8 = bool(undefined[8] & 0x20) or self.emulation
        self.x8 = bool(undefined[8] & 0x10) or self.emulation

    def reset(self, seed: int = UNSET_SEED) -> Cpu:
        """Put the processor where a reset puts it, and nowhere else.

        A reset defines less than a model usually assumes. It forces emulation
        mode, which forces the accumulator and index registers to eight bits,
        clears decimal, sets the interrupt disable, zeroes the direct page and
        both bank registers, forces the high byte of the stack pointer to $01,
        and loads the program counter from the reset vector.

        It says nothing about the accumulator, the index registers, or the low
        byte of the stack pointer, and those keep what they were already holding
        rather than being randomised here. Power on is what randomises them.

        `seed` is accepted and unused, kept so the signature matches the rest of
        the family and so a caller that seeded the part can name the seed again
        without it being an error.

        The manual gives the timing plainly: the part "will delay 6 cycles and
        then fetch the new program count vectors". Those six are charged, so a
        host pacing against a real clock is not six cycles ahead of the wall
        after every reset. They appear in `cycles` and not in `trace`, because
        every cycle of this part drives an address and no source on hand names
        the six it drives here. Six invented addresses would read as knowledge;
        a gap that OPEN-QUESTIONS.md names does not.
        """
        for _ in range(self.reset_cycles - VECTOR_CYCLES):
            self.spend()
        self.s = 0x0100 | (self.s & 0xFF)

        self.d = 0x0000
        self.db = 0x00
        self.pb = 0x00

        self.emulation = True
        self.m8 = True
        self.x8 = True
        self.decimal = False
        self.irq_disable = True

        self.pc = self.read16(RESET_VECTOR)
        self.steps = 0
        self.stopped = False
        self.waiting = False
        return self

    def status(self) -> int:
        """The status byte as anything reading it would see.

        In emulation mode the two width bits read as the break and unused bits
        of a 6502, because that is what the register is in that mode.
        """
        value = 0
        value |= FLAG_N if self.n else 0
        value |= FLAG_V if self.v else 0
        value |= FLAG_M if self.m8 else 0
        value |= FLAG_X if self.x8 else 0
        value |= FLAG_D if self.decimal else 0
        value |= FLAG_I if self.irq_disable else 0
        value |= FLAG_Z if self.z else 0
        value |= FLAG_C if self.c else 0
        return value

    def set_status(self, value: int) -> None:
        """Take a status byte, keeping only the bits the register actually has.

        Setting a width bit narrows the register it governs, and the two widths
        do not behave alike. Narrowing the index registers truncates them, so the
        high byte of X and Y is gone and widening again does not bring it back.
        Narrowing the accumulator hides its high byte rather than discarding it:
        the byte stays in the register as B, XBA swaps the halves, and widening
        again reveals it. Emulation mode forces both widths regardless of what
        the byte asked for.
        """
        self.n = bool(value & FLAG_N)
        self.v = bool(value & FLAG_V)
        self.decimal = bool(value & FLAG_D)
        self.irq_disable = bool(value & FLAG_I)
        self.z = bool(value & FLAG_Z)
        self.c = bool(value & FLAG_C)
        if self.emulation:
            self.m8 = True
            self.x8 = True
        else:
            self.m8 = bool(value & FLAG_M)
            self.x8 = bool(value & FLAG_X)
        if self.x8:
            self.x &= 0xFF
            self.y &= 0xFF

    def set_emulation(self, value: bool) -> None:
        self.emulation = bool(value)
        if self.emulation:
            self.m8 = True
            self.x8 = True
            self.x &= 0xFF
            self.y &= 0xFF
            self.s = 0x0100 | (self.s & 0xFF)

    def pins(self, data: bool, program: bool, vector: bool, write: bool) -> str:
        """The eight output lines, in the order the recordings print them.

        Valid data address, valid program address, vector pull, read or write,
        emulation, the two width bits, and memory lock. Both address lines low is
        an internal cycle, and the manufacturer says the address on one of those
        may be invalid, which is why an internal cycle is recorded with no value
        rather than with whatever the bus happened to hold.
        """
        return "".join(
            (
                "d" if data else "-",
                "p" if program else "-",
                "v" if vector else "-",
                "w" if write else "r",
                "e" if self._emulation else "-",
                "m" if self.m8 else "-",
                "x" if self.x8 else "-",
                "l" if self.locked else "-",
            )
        )

    def halt_cycle(self) -> None:
        """One cycle of a part that has shut itself down, which drives nothing.

        STP and WAI both cost three cycles to take effect, and the recordings
        agree with the manufacturer on that. What they add is what the fourth
        cycle looks like: no address at all, no value, and every one of the eight
        output lines inactive, including the read line. All 40,000 recorded cases
        show it, in both modes, with no variation beyond the width bits the part
        started with.

        A halted part is not a part that has stopped existing. Its host still has
        a clock, and this is what that clock finds on the bus each time it ticks.
        """
        if self.trace is not None:
            self.trace.append((None, None, HALTED_PINS))
        self.spend()

    def held(self) -> bool:
        """Whether the part can no longer begin an instruction on its own.

        Either of the two states it can put itself into deliberately. Only a
        reset ends the first; an interrupt ends the second.
        """
        return self.stopped or self.waiting

    def held_cycle(self) -> None:
        """One cycle of a part in that state, which here drives nothing at all."""
        self.halt_cycle()

    def spend(self) -> None:
        """Account for one cycle, and tell whoever is watching that it happened.

        Every cycle this part runs passes through here and nowhere else. That is
        deliberate: a counter kept in one place and a hook called from another
        drift the moment somebody adds a cycle to only one of them, and a host
        pacing against a clock would never find out.

        `on_cycle` is what a board hangs off the pin. It is called once per
        cycle, after that cycle's bus activity has happened, so what it observes
        is a cycle the part has finished rather than one it is about to start.
        """
        self.cycles += 1
        if self.on_cycle is not None:
            self.on_cycle()

    def read8(self, address: int, data: bool = True, program: bool = False) -> int:
        self.await_ready()
        found = self.memory.read8(address & self.address_mask) & 0xFF
        assert isinstance(found, int)
        if self.trace is not None:
            self.trace.append(
                (address & self.address_mask, found, self.pins(data, program, self.pulling, False))
            )
        self.spend()
        return found

    def write8(self, address: int, value: int) -> None:
        self.await_ready(write=True)
        self.memory.write8(address & self.address_mask, value & 0xFF)
        if self.trace is not None:
            self.trace.append(
                (address & self.address_mask, value & 0xFF, self.pins(True, False, False, True))
            )
        self.spend()

    def internal(self, address: int, write: bool = False, value: int | None = None) -> None:
        """A cycle the part spends without asking memory for anything.

        The 6502 had none of these: it drove a real address every cycle and read
        something it then ignored. This part lowers both address lines instead, so
        nothing answers, and the address it drives is allowed to be wrong. That is
        why there is usually nothing here rather than a byte.

        The exception is the modify cycle of a read-modify-write in emulation
        mode. There the part drives the byte it just read with the write line low
        and no valid address, so the value is on the bus and no memory takes it.
        That is how a part compatible with one that writes twice avoids writing
        twice.
        """
        if self.trace is not None:
            self.trace.append(
                (address & self.address_mask, value, self.pins(False, False, False, write))
            )
        self.spend()

    def opcode8(self) -> int:
        """Fetch an opcode, which is the one cycle with both address lines high."""
        value = self.read8((self.pb << 16) | self.pc, data=True, program=True)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def vector16(self, address: int) -> int:
        """Read a vector, with the pull line low for both halves of it."""
        self.pulling = True
        try:
            return self.read8(address) | (self.read8(address + 1) << 8)
        finally:
            self.pulling = False

    def read16(self, address: int) -> int:
        return self.read8(address) | (self.read8(address + 1) << 8)

    def read24(self, address: int) -> int:
        return self.read16(address) | (self.read8(address + 2) << 16)

    def read_value(self, address: int, wide: bool, mode: str | None = None) -> int:
        if not wide:
            return self.read8(address)
        return self.read8(address) | (self.read8(self.next_byte(address, mode)) << 8)

    def write_value(
        self,
        address: int,
        value: int,
        wide: bool,
        mode: str | None = None,
        high_first: bool = False,
    ) -> None:
        """Write a byte, or a word in whichever order the instruction writes it.

        A store writes the low half first. A read-modify-write writes the high
        half first, having read the low half first, so the two halves of one
        instruction go out in opposite orders. The registers end up the same
        either way and the bus does not, which is why the order is a parameter.
        """
        if not wide:
            self.write8(address, value)
            return
        if high_first:
            self.write8(self.next_byte(address, mode), value >> 8)
            self.write8(address, value)
            return
        self.write8(address, value)
        self.write8(self.next_byte(address, mode), value >> 8)

    def next_byte(self, address: int, mode: str | None) -> int:
        """The address one byte on, wrapped the way that kind of access wraps.

        The direct page and the stack live in bank zero and stay there, so a word
        that starts at $FFFF finishes at $0000 rather than in bank one. An address
        formed against the data bank is not confined that way and carries into the
        next bank as any long address would.
        """
        if mode in BANK_ZERO_MODES:
            return (address & 0xFF0000) | ((address + 1) & 0xFFFF)
        return address + 1

    def fetch8(self) -> int:
        value = self.read8((self.pb << 16) | self.pc, data=False, program=True)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def fetch16(self) -> int:
        return self.fetch8() | (self.fetch8() << 8)

    def fetch24(self) -> int:
        return self.fetch16() | (self.fetch8() << 16)

    def push8(self, value: int) -> None:
        self.write8(self.s, value)
        if self.emulation:
            self.s = 0x0100 | ((self.s - 1) & 0xFF)
        else:
            self.s = (self.s - 1) & 0xFFFF

    def pull8(self) -> int:
        if self.emulation:
            self.s = 0x0100 | ((self.s + 1) & 0xFF)
        else:
            self.s = (self.s + 1) & 0xFFFF
        return self.read8(self.s)

    def push16(self, value: int) -> None:
        """Push a word the way the 6502 instructions do, folding into page one."""
        self.push8((value >> 8) & 0xFF)
        self.push8(value & 0xFF)

    def pull16(self) -> int:
        """Pull a word the way the 6502 instructions do."""
        return self.pull8() | (self.pull8() << 8)

    def pull_flat(self, width: int) -> int:
        """Pull several bytes without folding into page one, lowest first."""
        if not self.emulation:
            value = 0
            for shift in range(0, 8 * width, 8):
                value |= self.pull8() << shift
            return value
        base = self._s
        value = 0
        for step in range(width):
            value |= self.read8((base + 1 + step) & 0xFFFF) << (8 * step)
        self.s = (base + width) & 0xFFFF
        return value

    def push16_flat(self, value: int) -> None:
        """Push a word without folding into page one.

        Emulation mode confines the stack pointer to page one, and the original
        6502 operations wrap within it: a push at $0100 continues at $01FF. The
        instructions the 65816 added do not. They step through consecutive
        addresses, so the same push writes $0100 and then $00FF and leaves the
        page, and only the pointer left behind is folded back. This is the whole
        difference between how COP and RTI behave and how PEI and PLD behave.
        """
        if not self.emulation:
            self.push16(value)
            return
        base = self._s
        self.write8(base, (value >> 8) & 0xFF)
        self.write8((base - 1) & 0xFFFF, value & 0xFF)
        self.s = (base - 2) & 0xFFFF

    def pull16_flat(self) -> int:
        """Pull a word without folding into page one, as the push above does."""
        if not self.emulation:
            return self.pull16()
        base = self._s
        low = self.read8((base + 1) & 0xFFFF)
        high = self.read8((base + 2) & 0xFFFF)
        self.s = (base + 2) & 0xFFFF
        return low | (high << 8)

    def acc(self) -> int:
        return self.a & 0xFF if self.m8 else self.a & 0xFFFF

    def set_acc(self, value: int) -> None:
        if self.m8:
            self.a = (self.a & 0xFF00) | (value & 0xFF)
        else:
            self.a = value & 0xFFFF

    def set_nz(self, value: int, wide: bool) -> None:
        mask = 0xFFFF if wide else 0xFF
        self.z = (value & mask) == 0
        self.n = bool(value & (0x8000 if wide else 0x80))

    def wide_for(self, mnemonic: str) -> bool:
        if mnemonic in INDEX_WIDTH_OPS:
            return not self.x8
        return not self.m8

    @property
    def page_wraps(self) -> bool:
        """Whether direct page addressing stays inside one page.

        In emulation mode with the low byte of the direct page register clear,
        the processor behaves as a 6502: a direct page address plus an index
        wraps within the page rather than carrying into the next one, and the two
        or three bytes of an indirect pointer wrap with it. Native mode, or any
        direct page not aligned to a page, carries normally.
        """
        return self.emulation and (self.d & 0xFF) == 0

    def direct(self, offset: int) -> int:
        """A direct page address, wrapped the way the current mode wraps it."""
        if self.page_wraps:
            return (self.d & 0xFF00) | (offset & 0xFF)
        return (self.d + offset) & 0xFFFF

    def read_pointer(self, address: int, width: int, wraps_in_page: bool = False) -> int:
        """A pointer read out of the direct page or the stack.

        Two wraps apply and they are not the same. Every pointer stays inside the
        bank it started in, so one at $FFFF continues at $0000 of that same bank
        rather than crossing into the next.

        The narrower wrap, staying inside the direct page itself, applies only in
        emulation mode with the page aligned, and only to some modes.

        The data sheet names three that leave the page: `[d]`, `[d],y` and PEI.
        A recorded cycle address confirms all three, and shows a fourth the list
        does not name, `(d,x)`, leaving it as well. So the list is incomplete
        rather than wrong.

        The remaining two, `(d)` and `(d),y`, have no case in any corpus where the
        pointer starts at the last byte of the page, so nothing has measured them.
        They follow the data sheet and wrap. That is a reading rather than a
        measurement and is marked as one, because generalising from the four that
        were measured would be inventing a rule against the only document that
        speaks. Which mode rests on which is written down in
        conformance/divergences.json, per mode, with the case.
        """
        bank = address & 0xFF0000
        if wraps_in_page and self.page_wraps:
            page = address & 0x00FF00
            return sum(
                self.read8(bank | page | ((address + step) & 0xFF)) << (8 * step)
                for step in range(width)
            )
        return sum(
            self.read8(bank | ((address + step) & 0xFFFF)) << (8 * step) for step in range(width)
        )

    def here(self) -> int:
        """The last byte the part fetched, which is where a spare cycle points."""
        return (self.pb << 16) | ((self.pc - 1) & 0xFFFF)

    def at_pc(self) -> int:
        """The next byte to fetch, in the program bank.

        The program counter is sixteen bits and the bank does not move with it, so
        this wraps inside the bank rather than carrying out of it. The difference
        shows on exactly one address in each bank and the recordings catch it.
        """
        return (self.pb << 16) | self.pc

    def unaligned(self) -> None:
        """The cycle a direct-page access costs when the register is not aligned.

        Adding an eight bit offset to a register whose low byte is clear needs no
        adder, so the part does it for nothing. When the low byte is not clear it
        spends a cycle, and drives the operand's own address while it does.
        """
        if self.d & 0xFF:
            self.internal(self.here())

    def crosses(self, base: int, index: int) -> bool:
        """Whether an indexed access spends its spare cycle.

        Three things make it unavoidable: a carry out of the low byte, a write,
        which the part will not aim at an address it might correct, and a sixteen
        bit index, where there is no low-byte-only shortcut to take.
        """
        return not self.x8 or ((base + index) & 0xFF00) != (base & 0xFF00)

    def effective(self, mode: str, mnemonic: str) -> int:
        if mode == "direct":
            offset = self.fetch8()
            self.unaligned()
            return self.direct(offset)
        if mode == "directX":
            offset = self.fetch8()
            self.unaligned()
            self.internal(self.here())
            return self.direct(offset + self.x)
        if mode == "directY":
            offset = self.fetch8()
            self.unaligned()
            self.internal(self.here())
            return self.direct(offset + self.y)
        if mode == "absolute":
            return (self.db << 16) | self.fetch16()
        if mode == "absoluteX":
            return self.indexed(self.fetch16(), self.x, mnemonic)
        if mode == "absoluteY":
            return self.indexed(self.fetch16(), self.y, mnemonic)
        if mode == "absoluteLong":
            return self.fetch24()
        if mode == "absoluteLongX":
            return self.fetch24() + self.x
        if mode == "indirect":
            offset = self.fetch8()
            self.unaligned()
            pointer = self.direct(offset)
            return (self.db << 16) | self.read_pointer(pointer, 2, wraps_in_page=True)
        if mode == "indexedIndirectX":
            offset = self.fetch8()
            self.unaligned()
            self.internal(self.here())
            pointer = self.direct(offset + self.x)
            return (self.db << 16) | self.read_pointer(pointer, 2)
        if mode == "indirectIndexedY":
            offset = self.fetch8()
            self.unaligned()
            pointer = self.direct(offset)
            base = self.read_pointer(pointer, 2, wraps_in_page=True)
            return self.indexed_from(base, self.y, mnemonic)
        if mode == "indirectLong":
            offset = self.fetch8()
            self.unaligned()
            return self.read_pointer(self.direct(offset), 3)
        if mode == "indirectLongY":
            offset = self.fetch8()
            self.unaligned()
            return self.read_pointer(self.direct(offset), 3) + self.y
        if mode == "stack":
            offset = self.fetch8()
            self.internal(self.here())
            return (self.s + offset) & 0xFFFF
        if mode == "stackIndirect":
            offset = self.fetch8()
            self.internal(self.here())
            pointer = (self.s + offset) & 0xFFFF
            base = self.read_pointer(pointer, 2)
            self.internal((pointer + 1) & 0xFFFF)
            return ((self.db << 16) | base) + self.y
        raise UnsupportedError(f"{mnemonic} cannot use {mode}")

    def indexed(self, base: int, index: int, mnemonic: str) -> int:
        """An absolute address plus an index, in the data bank."""
        return self.indexed_from(base, index, mnemonic)

    def indexed_from(self, base: int, index: int, mnemonic: str) -> int:
        """Index an address and spend the cycle if the part would spend it."""
        if mnemonic in ALWAYS_INDEXES or self.crosses(base, index):
            self.internal((self.db << 16) | (base & 0xFF00) | ((base + index) & 0xFF))
        return ((self.db << 16) | base) + index

    def operand(self, mode: str, mnemonic: str) -> int:
        wide = self.wide_for(mnemonic)
        if mode in IMMEDIATE_MODES:
            if mode == "immediate":
                return self.fetch8()
            return self.fetch16() if wide else self.fetch8()
        return self.read_value(self.effective(mode, mnemonic), wide, mode)

    def add_with_carry(self, value: int) -> None:
        wide = not self.m8
        bits = 16 if wide else 8
        left = self.acc()
        carry = 1 if self.c else 0

        sign = 0x8000 if wide else 0x80

        if self.decimal:
            top = bits - 4
            total = 0
            carry_in = carry
            intermediate = 0
            for shift in range(0, bits, 4):
                digit = ((left >> shift) & 0xF) + ((value >> shift) & 0xF) + carry_in
                if shift == top:
                    intermediate = total | (digit << shift)
                if digit > 9:
                    digit += 6
                    carry_in = 1
                else:
                    carry_in = 0
                total |= (digit & 0xF) << shift
            result = total
            self.c = bool(carry_in)
            overflow_from = intermediate
        else:
            result = left + value + carry
            self.c = result > (0xFFFF if wide else 0xFF)
            overflow_from = result

        self.v = bool(~(left ^ value) & (left ^ overflow_from) & sign)
        result &= 0xFFFF if wide else 0xFF
        self.set_nz(result, wide)
        self.set_acc(result)

    def subtract_with_carry(self, value: int) -> None:
        wide = not self.m8
        bits = 16 if wide else 8
        mask = 0xFFFF if wide else 0xFF
        left = self.acc()
        borrow = 0 if self.c else 1
        plain = left - value - borrow

        if self.decimal:
            total = 0
            borrow_in = borrow
            for shift in range(0, bits, 4):
                digit = ((left >> shift) & 0xF) - ((value >> shift) & 0xF) - borrow_in
                borrow_in = 0
                if digit < 0:
                    digit -= 6
                    borrow_in = 1
                total |= (digit & 0xF) << shift
            result = total & mask
            self.c = not borrow_in
        else:
            result = plain & mask
            self.c = plain >= 0

        sign = 0x8000 if wide else 0x80
        self.v = bool((left ^ value) & (left ^ (plain & mask)) & sign)
        self.set_nz(result, wide)
        self.set_acc(result)

    def compare(self, register: int, value: int, wide: bool) -> None:
        mask = 0xFFFF if wide else 0xFF
        self.c = register >= value
        self.set_nz((register - value) & mask, wide)

    def step(self) -> int:
        """Run one instruction, and report the cycles it took.

        The count is what a caller needs to keep a host in step with a real
        clock. A part at 3.58 MHz spends 3,580,000 cycles a second, so a host
        that adds up what each instruction returns knows exactly how far ahead
        of the wall it has run.
        """
        started = self.cycles
        if self.stopped:
            raise Stopped("the processor has been stopped")
        if self.waiting:
            raise Waiting("the processor is waiting for an interrupt")
        self.steps += 1
        opcode = self.opcode8()
        mnemonic, mode = OPCODES[opcode]
        if not wdc65816.MODE_SIZE[mode]:
            self.internal(self.at_pc())
        handler = getattr(self, f"op_{mnemonic}", None)
        if handler is None:
            raise UnsupportedError(f"{mnemonic} is not implemented")
        handler(mode)
        self.sample_pins()
        return self.cycles - started

    def call(self, address: int) -> Cpu:
        """Run from an address until the routine it names returns.

        Counts the calls it passes so a routine that calls another comes back
        here rather than at the inner return, and takes a full twenty four bit
        address because on this part the bank is part of where a routine lives.
        """
        self.pb = (address >> 16) & 0xFF
        self.pc = address & 0xFFFF
        depth = 0
        while True:
            mnemonic = OPCODES[self.read8((self.pb << 16) | self.pc)][0]
            if mnemonic in ("rts", "rtl"):
                if depth == 0:
                    return self
                depth -= 1
            elif mnemonic in ("jsr", "jsl"):
                depth += 1
            self.step()

    def run_for(self, cycles: int) -> int:
        """Run whole instructions until at least this many cycles have passed.

        Returns what was actually spent, which is almost never the number asked
        for: an instruction is not divisible, so the last one usually carries the
        count past the budget. A host pacing against a clock carries the excess
        into the next call rather than discarding it, which is what keeps a long
        run from drifting.

        A part that has shut itself down still costs its host every cycle. STP
        and WAI stop the processor, not the board it sits on, so this goes on
        producing halted cycles rather than raising: the clock outside is still
        running, and a host pacing against it has to spend that time somewhere.
        A part waiting on WAI resumes as soon as it is offered an interrupt it
        can take, so a host that keeps clocking it is doing the right thing and a
        host that stopped would hang the machine.
        """
        spent = 0
        while spent < cycles:
            if self.held():
                self.held_cycle()
                spent += 1
            else:
                spent += self.step()
        return spent

    def run_until(self, predicate: Callable[[Cpu], bool], limit: int | None = None) -> Cpu:
        """Step until the predicate holds.

        `limit` bounds the number of instructions and raises when it is reached.
        Without one this runs as long as the part would, which for a program
        that never satisfies the predicate is forever. That is what the silicon
        does, so it is what happens here unless a caller asks for otherwise.
        """
        taken = 0
        while not predicate(self):
            self.step()
            taken += 1
            if limit is not None and taken >= limit:
                raise RunLimit(f"gave up after {taken} instructions at ${self.pc:04X}")
        return self

    def op_lda(self, mode: str) -> None:
        value = self.operand(mode, "lda")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_ldx(self, mode: str) -> None:
        value = self.operand(mode, "ldx")
        self.x = value
        self.set_nz(value, not self.x8)

    def op_ldy(self, mode: str) -> None:
        value = self.operand(mode, "ldy")
        self.y = value
        self.set_nz(value, not self.x8)

    def op_sta(self, mode: str) -> None:
        self.write_value(self.effective(mode, "sta"), self.acc(), not self.m8, mode)

    def op_stx(self, mode: str) -> None:
        self.write_value(self.effective(mode, "stx"), self.x, not self.x8, mode)

    def op_sty(self, mode: str) -> None:
        self.write_value(self.effective(mode, "sty"), self.y, not self.x8, mode)

    def op_stz(self, mode: str) -> None:
        self.write_value(self.effective(mode, "stz"), 0, not self.m8, mode)

    def op_tax(self, mode: str) -> None:
        self.x = self.a & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_tay(self, mode: str) -> None:
        self.y = self.a & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.y, not self.x8)

    def op_txa(self, mode: str) -> None:
        self.set_acc(self.x)
        self.set_nz(self.acc(), not self.m8)

    def op_tya(self, mode: str) -> None:
        self.set_acc(self.y)
        self.set_nz(self.acc(), not self.m8)

    def op_txy(self, mode: str) -> None:
        self.y = self.x
        self.set_nz(self.y, not self.x8)

    def op_tyx(self, mode: str) -> None:
        self.x = self.y
        self.set_nz(self.x, not self.x8)

    def op_tsx(self, mode: str) -> None:
        self.x = self.s & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_txs(self, mode: str) -> None:
        self.s = 0x0100 | (self.x & 0xFF) if self.emulation else self.x & 0xFFFF

    def op_tas(self, mode: str) -> None:
        self.s = 0x0100 | (self.a & 0xFF) if self.emulation else self.a & 0xFFFF

    def op_tsa(self, mode: str) -> None:
        self.a = self.s & 0xFFFF
        self.set_nz(self.a, True)

    def op_tad(self, mode: str) -> None:
        self.d = self.a & 0xFFFF
        self.set_nz(self.d, True)

    def op_tda(self, mode: str) -> None:
        self.a = self.d & 0xFFFF
        self.set_nz(self.a, True)

    def op_xba(self, mode: str) -> None:
        self.internal(self.at_pc())
        self.a = ((self.a >> 8) | (self.a << 8)) & 0xFFFF
        self.set_nz(self.a & 0xFF, False)

    def op_xce(self, mode: str) -> None:
        carry = self.c
        self.c = self.emulation
        self.set_emulation(carry)

    def op_and(self, mode: str) -> None:
        value = self.acc() & self.operand(mode, "and")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_ora(self, mode: str) -> None:
        value = self.acc() | self.operand(mode, "ora")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_eor(self, mode: str) -> None:
        value = self.acc() ^ self.operand(mode, "eor")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_adc(self, mode: str) -> None:
        self.add_with_carry(self.operand(mode, "adc"))

    def op_sbc(self, mode: str) -> None:
        self.subtract_with_carry(self.operand(mode, "sbc"))

    def op_cmp(self, mode: str) -> None:
        self.compare(self.acc(), self.operand(mode, "cmp"), not self.m8)

    def op_cpx(self, mode: str) -> None:
        self.compare(self.x, self.operand(mode, "cpx"), not self.x8)

    def op_cpy(self, mode: str) -> None:
        self.compare(self.y, self.operand(mode, "cpy"), not self.x8)

    def op_bit(self, mode: str) -> None:
        value = self.operand(mode, "bit")
        wide = not self.m8
        self.z = (self.acc() & value) == 0
        if mode not in IMMEDIATE_MODES:
            self.n = bool(value & (0x8000 if wide else 0x80))
            self.v = bool(value & (0x4000 if wide else 0x40))

    def _read_modify_write(
        self, mode: str, mnemonic: str, operation: Callable[[int, bool], int]
    ) -> None:
        wide = not self.m8
        if mode == "implied":
            self.set_acc(operation(self.acc(), wide))
            return
        address = self.effective(mode, mnemonic)
        self.locked = True
        try:
            held = self.read_value(address, wide, mode)
            self.internal(
                self.next_byte(address, mode) if wide else address,
                write=self._emulation,
                value=held if self._emulation else None,
            )
            self.write_value(address, operation(held, wide), wide, mode, high_first=True)
        finally:
            self.locked = False

    def op_asl(self, mode: str) -> None:
        def shift(value: int, wide: bool) -> int:
            self.c = bool(value & (0x8000 if wide else 0x80))
            result = (value << 1) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "asl", shift)

    def op_lsr(self, mode: str) -> None:
        def shift(value: int, wide: bool) -> int:
            self.c = bool(value & 1)
            result = value >> 1
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "lsr", shift)

    def op_rol(self, mode: str) -> None:
        def rotate(value: int, wide: bool) -> int:
            carry = 1 if self.c else 0
            self.c = bool(value & (0x8000 if wide else 0x80))
            result = ((value << 1) | carry) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "rol", rotate)

    def op_ror(self, mode: str) -> None:
        def rotate(value: int, wide: bool) -> int:
            carry = (0x8000 if wide else 0x80) if self.c else 0
            self.c = bool(value & 1)
            result = (value >> 1) | carry
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "ror", rotate)

    def op_inc(self, mode: str) -> None:
        def bump(value: int, wide: bool) -> int:
            result = (value + 1) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "inc", bump)

    def op_dec(self, mode: str) -> None:
        def drop(value: int, wide: bool) -> int:
            result = (value - 1) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "dec", drop)

    def op_trb(self, mode: str) -> None:
        def clear(value: int, wide: bool) -> int:
            self.z = (value & self.acc()) == 0
            return value & ~self.acc()

        self._read_modify_write(mode, "trb", clear)

    def op_tsb(self, mode: str) -> None:
        def raise_bits(value: int, wide: bool) -> int:
            self.z = (value & self.acc()) == 0
            return value | self.acc()

        self._read_modify_write(mode, "tsb", raise_bits)

    def op_inx(self, mode: str) -> None:
        self.x = (self.x + 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_iny(self, mode: str) -> None:
        self.y = (self.y + 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.y, not self.x8)

    def op_dex(self, mode: str) -> None:
        self.x = (self.x - 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_dey(self, mode: str) -> None:
        self.y = (self.y - 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.y, not self.x8)

    def op_clc(self, mode: str) -> None:
        self.c = False

    def op_sec(self, mode: str) -> None:
        self.c = True

    def op_cld(self, mode: str) -> None:
        self.decimal = False

    def op_sed(self, mode: str) -> None:
        self.decimal = True

    def op_cli(self, mode: str) -> None:
        self.irq_disable = False

    def op_sei(self, mode: str) -> None:
        self.irq_disable = True

    def op_clv(self, mode: str) -> None:
        self.v = False

    def op_rep(self, mode: str) -> None:
        """Clear the named status bits, in three cycles whatever they are.

        The manufacturer says this and its opposite are always three cycles and
        that the third drives the operand's own address with both address lines
        low. Nothing about the operand changes that.
        """
        held = self.fetch8()
        self.internal(self.here())
        self.set_status(self.status() & ~held)

    def op_sep(self, mode: str) -> None:
        held = self.fetch8()
        self.internal(self.here())
        self.set_status(self.status() | held)

    def op_pha(self, mode: str) -> None:
        self.push8(self.a) if self.m8 else self.push16(self.a)

    def op_pla(self, mode: str) -> None:
        self.internal(self.at_pc())
        value = self.pull8() if self.m8 else self.pull16()
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_phx(self, mode: str) -> None:
        self.push8(self.x) if self.x8 else self.push16(self.x)

    def op_plx(self, mode: str) -> None:
        self.internal(self.at_pc())
        self.x = self.pull8() if self.x8 else self.pull16()
        self.set_nz(self.x, not self.x8)

    def op_phy(self, mode: str) -> None:
        self.push8(self.y) if self.x8 else self.push16(self.y)

    def op_ply(self, mode: str) -> None:
        self.internal(self.at_pc())
        self.y = self.pull8() if self.x8 else self.pull16()
        self.set_nz(self.y, not self.x8)

    def op_php(self, mode: str) -> None:
        self.push8(self.status())

    def op_plp(self, mode: str) -> None:
        self.internal(self.at_pc())
        self.set_status(self.pull8())

    def op_phb(self, mode: str) -> None:
        self.push8(self.db)

    def op_plb(self, mode: str) -> None:
        self.internal(self.at_pc())
        self.db = self.pull8()
        self.set_nz(self.db, False)

    def op_phd(self, mode: str) -> None:
        self.push16_flat(self.d)

    def op_pld(self, mode: str) -> None:
        self.internal(self.at_pc())
        self.d = self.pull16_flat()
        self.set_nz(self.d, True)

    def op_phk(self, mode: str) -> None:
        self.push8(self.pb)

    def op_pea(self, mode: str) -> None:
        self.push16_flat(self.fetch16())

    def op_pei(self, mode: str) -> None:
        offset = self.fetch8()
        self.unaligned()
        pointer = self.direct(offset)
        self.push16_flat(self.read_pointer(pointer, 2))

    def op_per(self, mode: str) -> None:
        offset = self.fetch16()
        self.internal(self.here())
        self.push16_flat((self.pc + self._signed16(offset)) & 0xFFFF)

    @staticmethod
    def _signed8(value: int) -> int:
        return value - 0x100 if value & 0x80 else value

    @staticmethod
    def _signed16(value: int) -> int:
        return value - 0x10000 if value & 0x8000 else value

    def _branch(self, taken: bool) -> None:
        """Take the branch, and spend what taking it costs.

        A taken branch costs a cycle, and in emulation mode a taken branch that
        crosses a page costs another, which is the one place this part still pays
        for a page boundary the way a 6502 does. In native mode it does not.
        """
        offset = self.fetch8()
        if not taken:
            return
        self.internal(self.here())
        target = (self.pc + self._signed8(offset)) & 0xFFFF
        if self._emulation and (target & 0xFF00) != (self.pc & 0xFF00):
            self.internal(self.here())
        self.pc = target

    def op_bra(self, mode: str) -> None:
        self._branch(True)

    def op_beq(self, mode: str) -> None:
        self._branch(self.z)

    def op_bne(self, mode: str) -> None:
        self._branch(not self.z)

    def op_bcs(self, mode: str) -> None:
        self._branch(self.c)

    def op_bcc(self, mode: str) -> None:
        self._branch(not self.c)

    def op_bmi(self, mode: str) -> None:
        self._branch(self.n)

    def op_bpl(self, mode: str) -> None:
        self._branch(not self.n)

    def op_bvs(self, mode: str) -> None:
        self._branch(self.v)

    def op_bvc(self, mode: str) -> None:
        self._branch(not self.v)

    def op_brl(self, mode: str) -> None:
        offset = self.fetch16()
        self.internal(self.here())
        self.pc = (self.pc + self._signed16(offset)) & 0xFFFF

    def op_jmp(self, mode: str) -> None:
        if mode == "absolutePC":
            self.pc = self.fetch16()
            return
        if mode == "indirectPC":
            self.pc = self.read_pointer(self.fetch16(), 2)
            return
        if mode == "indirectX":
            base = self.fetch16()
            self.internal(self.here())
            pointer = (base + self.x) & 0xFFFF
            self.pc = self.read_pointer((self.pb << 16) | pointer, 2)
            return
        if mode == "indirectLongPC":
            self.op_jml(mode)  # $DC is the long form and loads the bank too
            return
        raise UnsupportedError(f"jmp cannot use {mode}")

    def op_jml(self, mode: str) -> None:
        if mode == "absoluteLong":
            target = self.fetch24()
        elif mode == "indirectLongPC":
            target = self.read_pointer(self.fetch16(), 3)
        else:
            raise UnsupportedError(f"jml cannot use {mode}")
        self.pb = (target >> 16) & 0xFF
        self.pc = target & 0xFFFF

    def op_jsr(self, mode: str) -> None:
        """Jump to a subroutine, in whichever order the mode calls for.

        Through a plain address the part reads both halves, spends a cycle, and
        then pushes. Through an indexed pointer it pushes between the two halves
        of the address, the way the 6502 does, which is only visible when the
        stack has walked into the instruction.
        """
        if mode == "absolutePC":
            target = self.fetch16()
            self.internal(self.here())
            self.push16((self.pc - 1) & 0xFFFF)
            self.pc = target
            return
        if mode != "indirectX":
            raise UnsupportedError(f"jsr cannot use {mode}")
        low = self.fetch8()
        self.push16(self.pc)
        high = self.fetch8()
        self.internal(self.here())
        pointer = ((low | (high << 8)) + self.x) & 0xFFFF
        self.pc = self.read_pointer((self.pb << 16) | pointer, 2)

    def op_jsl(self, mode: str) -> None:
        """Jump long, pushing the bank before the address it is leaving.

        The bank goes out first, before the third operand byte has even been
        read, and the two halves of the return address follow it. So a stack that
        has walked into this instruction overwrites the bank byte it is about to
        fetch, exactly as the plain jump to subroutine can overwrite its own high
        byte.

        Like every instruction the 65816 added, its pushes step straight through
        the end of page one rather than folding back to the top of it, so in
        emulation mode a push at $0100 continues at $00FF.
        """
        target = self.fetch16()
        base = self._s
        self.write8(base, self.pb)
        self.internal(base)
        bank = self.fetch8()
        returning = (self.pc - 1) & 0xFFFF
        self.write8((base - 1) & 0xFFFF, (returning >> 8) & 0xFF)
        self.write8((base - 2) & 0xFFFF, returning & 0xFF)
        self.s = (base - 3) & 0xFFFF
        self.pb = bank
        self.pc = target

    def op_rts(self, mode: str) -> None:
        self.internal(self.at_pc())
        pulled = self.pull16()
        self.internal(self.s)
        self.pc = (pulled + 1) & 0xFFFF

    def op_rtl(self, mode: str) -> None:
        self.internal(self.at_pc())
        pulled = self.pull_flat(3)
        self.pc = ((pulled & 0xFFFF) + 1) & 0xFFFF
        self.pb = (pulled >> 16) & 0xFF

    def op_rti(self, mode: str) -> None:
        """Pull the status, the address and the bank, and apply the status last.

        The width bits come back from the stack, and the part does not act on them
        while it is still pulling: the recorded cycles carry the widths it had
        before, not the ones it is restoring. Applying the byte at the end leaves
        the same registers and drives the same pins.
        """
        self.internal(self.at_pc())
        pulled = self.pull8()
        self.pc = self.pull16()
        if not self.emulation:
            self.pb = self.pull8()
        self.set_status(pulled)

    def _software_interrupt(self, native_vector: int, emulation_vector: int) -> None:
        """Take a software interrupt the way the current mode takes one.

        Both instructions are two bytes even though the second is ignored, so the
        signature byte is fetched and discarded and the pushed return address
        points past it.

        The two modes differ in three ways. Emulation takes the 6502 vectors and
        pushes no program bank, having none to push. Native takes its own vectors
        and pushes the bank first. And the pushed status carries a different bit 4
        in each: in native mode that bit is the index width and goes out as it
        stands, while in emulation mode the width bit does not exist and the bit
        reads as the break flag, set. Nothing here has to force it, because a
        processor in emulation mode always reports its index registers as narrow,
        so the bit is already set by the time the status is read.
        """
        self.fetch8()
        pushed = self.status()
        if self.emulation:
            vector = emulation_vector
        else:
            vector = native_vector
            self.push8(self.pb)
        self.push16(self.pc)
        self.push8(pushed)
        self.irq_disable = True
        self.decimal = False
        self.pb = 0x00
        self.pc = self.vector16(vector)

    def interrupt(self, kind: str) -> bool:
        """Take a hardware interrupt, and say whether it was taken.

        A hardware interrupt differs from BRK and COP in three ways, and all
        three are in the cycle table. No opcode is consumed, so the return
        address is the instruction that would have run next. The pushed status
        carries a clear bit 4, which in emulation mode is the only thing that
        tells a handler this was a pin rather than a break. And emulation mode
        pushes one byte fewer, having no program bank to save, which is the cycle
        the table subtracts.

        A request arriving with interrupts disabled is refused rather than
        remembered, because the pin is a level and the caller still holds it. It
        still ends a wait: a program that sets the disable flag and waits is
        asking to continue at the next instruction, with no handler entered.
        """
        if self.stopped:
            return False
        self.waiting = False
        if kind == "irq" and self.irq_disable:
            return False
        vector = (EMULATION_VECTORS if self.emulation else NATIVE_VECTORS)[kind]
        if not self.emulation:
            self.push8(self.pb)
        self.push16(self.pc)
        self.push8(self.status() & ~BREAK_FLAG if self.emulation else self.status())
        self.irq_disable = True
        self.decimal = False
        self.pb = 0x00
        self.pc = self.vector16(vector)
        return True

    def await_ready(self, write: bool = False) -> None:
        """Spend cycles while the ready line is held low, which is what RDY does.

        "A low input logic level on the Ready (RDY) will halt the microprocessor
        in its current state." The part stops where it stands and the address
        lines hold what they were driving, which is how slow memory is given time
        to answer without slowing the clock.

        This part has no exception for a write. The NMOS parts do, and the MOS
        manual is explicit about it: "The RDY function will not stop the
        processor in a cycle in which a WRITE operation is being performed."
        Nothing in the W65C816S data sheet carves that out, so nothing here does,
        and the `write` argument is accepted only so that one call reaches either
        family. That is why this is shorter than the eight bit version rather
        than carrying a branch it could never take.

        A stall costs time and records nothing. The data sheet describes held
        address lines rather than an access, and this trace records accesses, so
        the cycle is charged and the bus picture is absent rather than invented.

        A caller that holds the line low and never releases it will not get out
        of here, which is exactly what a board that does the same gets. The cycle
        hook fires on every stall, so a host driving the part by hand can release
        the line from there, and a clock can release it between two cycles.
        """
        while not self.ready_line:
            self.spend()

    def sample_pins(self) -> bool:
        """Read the interrupt lines the way the part reads them, and act on one.

        The data sheet describes both pins as lines rather than as events, and
        the difference is visible. The request line is level sensitive: "a low
        input logic level initiates an interrupt sequence after the current
        instruction is completed", and "no interrupt will occur if the interrupt
        source is cleared prior to interrupt recognition". So a caller that holds
        `irq_line` low and releases it before the instruction ends gets nothing,
        which is what a device that withdrew its request would produce.

        The non-maskable line is edge sensitive instead: an interrupt happens on
        the transition, and "no interrupt will occur if NMIB remains low after
        the negative transition was processed". That is why the level is compared
        against the one last seen rather than simply tested.

        Called where the data sheet puts the recognition, after the instruction
        has completed. Which cycle within the instruction the part latches the
        level on is not stated by any document here, and is recorded as open
        rather than guessed at.
        """
        edge = self.nmi_line and not self.nmi_seen
        self.nmi_seen = self.nmi_line
        if edge:
            self.nmi()
            return True
        if self.irq_line:
            return self.irq()
        return False

    def irq(self) -> bool:
        """Pull the interrupt request line, and say whether the part took it.

        The line is level sensitive and the disable flag decides, so a request
        that arrives with interrupts disabled is not remembered: it is simply not
        taken, and a caller holding the line low will have it taken later when the
        flag clears. False means the request is still outstanding. It also
        releases a part that is waiting on WAI, which is what that instruction is
        for.
        """
        return self.interrupt("irq")

    def nmi(self) -> bool:
        """Pull the non-maskable line, which no flag defends against.

        The real pin is edge sensitive, so it is the transition that interrupts
        and holding the line low afterwards does nothing. A caller models that by
        calling this once per transition. It returns False only when the part has
        been stopped, because a part with no clock takes nothing.
        """
        return self.interrupt("nmi")

    def abort(self) -> bool:
        """Take an abort, with one part of the pin's behaviour left out.

        The pin inhibits every register change the aborted instruction would have
        made and then vectors with that instruction's own address as the return
        address, so the handler can repair whatever the bus could not reach and
        run it again. This is that sequence without the rollback, and a caller
        who needs the rollback cannot get it here.

        What stands in the way is no longer suspension. `Clock` stops the part
        between any two cycles, so the moment an abort would be latched is now
        reachable from outside. What is missing is the other half: an instruction
        that has begun cannot be abandoned, because the changes it has already
        made are in the registers rather than in a place a rollback could undo.
        Closing it means either the core checking the pin at each cycle and
        unwinding, or an instruction holding its writes until it commits, and
        neither is something to add without a recording of a real abort to hold
        it to.
        """
        return self.interrupt("abort")

    def op_brk(self, mode: str) -> None:
        self._software_interrupt(BREAK_VECTOR, EMULATION_BREAK_VECTOR)

    def op_cop(self, mode: str) -> None:
        self._software_interrupt(COP_VECTOR, EMULATION_COP_VECTOR)

    def _block_move(self, direction: int) -> None:
        """Move a block, one byte every seven cycles, and stop if time runs out.

        A block move is the one instruction on this processor that is meant to be
        interrupted. It copies a byte, steps both index registers, counts the
        accumulator down, and then rewinds the program counter over its own three
        bytes so the very same instruction is fetched again. A move of sixty
        thousand bytes is therefore sixty thousand executions of one instruction,
        and an interrupt taken in the middle resumes exactly where it stopped.

        `cycle_budget` models that window. Left unset the move runs to completion,
        which is what a program sees when nothing interrupts it. Set, the move
        performs as many whole seven cycle iterations as fit and then leaves the
        program counter part way through its own operands, exactly where the
        processor would be when the budget ran out.

        Every iteration after the first re-fetches this instruction, because that
        is what the part does: it rewound onto its own opcode and the next fetch
        starts over. Those cycles are real and they are on the bus, so they are
        here, which is why one call to step can drive dozens of them.
        """
        base = (self.pc - 1) & 0xFFFF
        destination = self.fetch8()
        source = self.fetch8()
        self.db = destination

        mask = 0xFF if self.x8 else 0xFFFF
        remaining = ((self.a + 1) & 0xFFFF) or 0x10000
        budget = self.cycle_budget
        whole = remaining if budget is None else min(remaining, max(0, budget) // CYCLES_PER_MOVE)

        for moved in range(whole):
            if moved:
                self.opcode8()
                self.fetch8()
                self.fetch8()
            self.write8((destination << 16) | self.y, self.read8((source << 16) | self.x))
            self.internal((destination << 16) | self.y)
            self.internal((destination << 16) | self.y)
            self.x = (self.x + direction) & mask
            self.y = (self.y + direction) & mask
            self.a = (self.a - 1) & 0xFFFF
            if moved + 1 < whole:
                self.pc = base

        if whole >= remaining:
            self.pc = (base + 3) & 0xFFFF
            return
        assert budget is not None, "a move with no budget finishes, and returned above"
        spent = whole * CYCLES_PER_MOVE
        self.pc = base
        self.partial_move(source, max(0, budget - spent))

    def partial_move(self, source: int, leftover: int) -> None:
        """The cycles of an iteration the window ended part way through.

        A move that runs out of time in the middle of an iteration has already
        driven that iteration's first few cycles, and they are on the bus. It
        re-fetched its own opcode, then as many of its two operands as it had time
        for, then read the source byte. It cannot have written: a write would move
        a byte, and then the count would say fifteen where the recordings say
        fourteen.

        So four is as far as this goes. A window ending after the write of a
        partial iteration is not modelled, because no recording shows one and the
        alternative is to guess whether that byte counts.
        """
        if leftover >= 1:
            self.opcode8()
        if leftover >= 2:
            self.fetch8()
        if leftover >= 3:
            self.fetch8()
        if leftover >= PARTIAL_LIMIT:
            self.read8((source << 16) | self.x)

    def op_mvn(self, mode: str) -> None:
        self._block_move(1)

    def op_mvp(self, mode: str) -> None:
        self._block_move(-1)

    def op_nop(self, mode: str) -> None:
        return

    def op_wdm(self, mode: str) -> None:
        """Two bytes, and the second is never read.

        The opcode is reserved for a processor nobody has built. It is two bytes
        long so that whatever it becomes has an operand, and the part steps over
        the second byte with both address lines low rather than fetching it.
        """
        self.internal((self.pb << 16) | self.pc)
        self.pc = (self.pc + 1) & 0xFFFF

    def op_stp(self, mode: str) -> None:
        self.internal(self.at_pc())
        self.stopped = True

    def op_wai(self, mode: str) -> None:
        self.internal(self.at_pc())
        self.waiting = True
