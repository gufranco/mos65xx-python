"""The 6502 core: eight bit registers, sixteen address lines, and its mistakes.

The part is small enough that its bugs are as well known as its instruction set,
and a core that quietly fixes any of them is wrong for every machine that shipped
one. Three matter most.

A jump through a pointer that ends a page reads the high byte from the start of
the same page rather than from the next one, so a pointer at `$30FF` takes its
high byte from `$3000`. Programs were built around it.

A jump to a subroutine pushes the return address between reading the two halves
of its own destination. Almost always that is invisible, and the once it is not
is when the stack has walked into the instruction: the push overwrites the high
byte of the destination, and the jump then goes wherever the pushed byte says.
Reading the destination first and pushing afterwards produces the same answer
every time except that one, which is the only time it matters.

Anything indexed inside the first page stays inside the first page. The zero page
index modes and both indirect modes wrap at `$FF`, so a pointer at `$FF` has its
high byte at `$00`.

And the break bit behaves like nothing else in the register. Pushing the status
always sets it, whatever the register held. Pulling the status always clears it,
whatever was pulled. In between it simply keeps its value, so it is stored like a
flag and written like neither. A core that treats it as a normal flag disagrees
the moment anything pulls, and a core that refuses to store it at all disagrees
with every instruction that leaves the register alone.

Decimal mode is a property of the part rather than of the program. The Ricoh
2A03 has the adder wired without it, so setting the flag there changes nothing,
which is why the model decides and not the flag.

Nothing starts clean. Registers and memory hold arbitrary but reproducible values
after a reset, because the hardware defines only the program counter, and a core
that clears the rest makes a read of something never written look deliberate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .errors import NoSuchPin, RunLimit, Stopped, UnsupportedError
from .memory import UNSET_SEED, scramble
from .opcodes6502 import MODE_SIZE, NMOS

RESET_VECTOR = 0xFFFC

RESET_CYCLES = 8
"""How long a reset takes on an NMOS part, counting the vector fetch.

The manual gives it as a delay plus the fetch: the part "will delay 6 cycles and
then fetch the new program count vectors". WDC states seven for its own CMOS
part, which is a different part and a different manufacturer, so the figure is a
property of the model rather than of the family.
"""

VECTOR_CYCLES = 2
"""The two cycles of the vector fetch, which every part pays and none states apart."""
BREAK_VECTOR = 0xFFFE
NMI_VECTOR = 0xFFFA
IRQ_VECTOR = 0xFFFE

JAM_HIGH = 0xFFFF
"""The address a hung part settles on, which is the top of the interrupt vector."""

JAM_LOW = 0xFFFE
"""The other half of that vector, which a hung part reads twice on the way in."""
"""The same address the break instruction uses: one vector serves both."""

STACK_PAGE = 0x0100

FLAG_C = 0x01
FLAG_Z = 0x02
FLAG_I = 0x04
FLAG_D = 0x08
FLAG_B = 0x10
FLAG_U = 0x20
FLAG_V = 0x40
FLAG_N = 0x80

MAGIC = 0xEE

READ = "read"
WRITE = "write"
MODIFY = "modify"
"""What an access is for, which decides what indexing costs."""


class Cpu:
    """One 6502, holding whatever it held until something writes to it.
    The slots are the point rather than a saving. Two names in this family mean
    different things on different parts, `.i` here and `.irq_disable` on the
    65816, and without them a caller reaching for the wrong one sets a stray
    attribute in silence: the flag they meant keeps its value and the interrupt
    code they wrote never fires. `status()` and `set_status()` are the portable
    spelling, and this makes the unportable one fail instead of going nowhere.
    """

    __slots__ = (
        "a",
        "address_mask",
        "b",
        "c",
        "cycles",
        "d",
        "decimal",
        "i",
        "irq_line",
        "jammed",
        "memory",
        "model",
        "n",
        "nmi_line",
        "nmi_seen",
        "on_cycle",
        "package_pins",
        "pc",
        "ready_line",
        "reset_cycles",
        "s",
        "stalls_on_write",
        "steps",
        "stopped",
        "table",
        "trace",
        "v",
        "x",
        "y",
        "z",
    )

    def __init__(
        self,
        memory: Any,
        seed: int = UNSET_SEED,
        decimal: bool = True,
        table: Any = NMOS,
    ) -> None:
        self.memory = memory
        self.decimal = decimal
        self.table = table
        self.steps = 0
        self.cycles = 0
        self.stopped = False
        self.jammed = False
        self.reset_cycles = RESET_CYCLES
        self.model = "6502"
        self.address_mask = 0xFFFF
        self.package_pins: tuple[str, ...] = ("irq", "nmi", "rdy")

        self.ready_line = True
        """The ready line, high when the part may proceed. Low halts it where it stands."""

        self.stalls_on_write = False
        """Whether a low ready line stops a write cycle. It does not on an NMOS part."""

        self.irq_line = False
        """The request line, active when true. Level sensitive: held, not pulsed."""

        self.nmi_line = False
        """The non-maskable line, active when true. Edge sensitive: the transition interrupts."""

        self.nmi_seen = False
        """The level the non-maskable line last had when it was read."""

        self.on_cycle: Callable[[], None] | None = None
        """Called once per cycle, after that cycle's bus activity."""

        self.trace: list[tuple[int, int, str]] | None = None

        self.power_on(seed)

    def power_on(self, seed: int = UNSET_SEED) -> None:
        """The state the part is in when the rail comes up and nothing else has.

        Every register holds a byte derived from the seed. Not zero, and not the
        0xFD that emulators write into the stack pointer, which is a value a 6502
        reaches only after a reset has already run and is therefore a claim about
        a reset rather than about power on.

        This is where the scrambling belongs. A part that has been powered and
        not yet reset holds rubbish, and a caller that steps it executes rubbish
        from a rubbish address, which is what the silicon does.
        """
        undefined = scramble(7, seed)
        self.a, self.x, self.y = undefined[0], undefined[1], undefined[2]
        self.s = undefined[3]
        self.set_status(undefined[4])
        self.pc = undefined[5] | (undefined[6] << 8)

    def reset(self, seed: int = UNSET_SEED) -> Cpu:
        """What a reset actually defines, and nothing beyond it.

        The vector decides where execution starts and the interrupt disable is
        set. Everything else keeps whatever it was already holding, because a
        reset does not write into the accumulator. The manual is careful to say
        only that the state afterwards is unknown: "It should be assumed that any
        time the reset line has been pulled low and then high, the internal
        states of the machine are unknown and all registers must be
        re-initialized." Unknown is not the same as randomised, and the part that
        does the randomising here is power on.

        `seed` is accepted and unused. It is kept because a caller that resets a
        part it built with a seed reasonably expects to name one, and because
        removing it would change a signature the family shares.

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
        self.i = True
        self.stopped = False
        self.jammed = False
        self.steps = 0
        self.pc = self.read16(RESET_VECTOR)
        return self

    def status(self) -> int:
        """The status byte as anything reading it would see."""
        value = FLAG_U
        value |= FLAG_B if self.b else 0
        value |= FLAG_N if self.n else 0
        value |= FLAG_V if self.v else 0
        value |= FLAG_D if self.d else 0
        value |= FLAG_I if self.i else 0
        value |= FLAG_Z if self.z else 0
        value |= FLAG_C if self.c else 0
        return value

    def set_status(self, value: int) -> None:
        """Take a status byte, keeping only the bits the register actually has."""
        self.b = bool(value & FLAG_B)
        self.n = bool(value & FLAG_N)
        self.v = bool(value & FLAG_V)
        self.d = bool(value & FLAG_D)
        self.i = bool(value & FLAG_I)
        self.z = bool(value & FLAG_Z)
        self.c = bool(value & FLAG_C)

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

    def read8(self, address: int) -> int:
        self.await_ready()
        found = self.memory.read8(address & 0xFFFF) & 0xFF
        assert isinstance(found, int)
        if self.trace is not None:
            self.trace.append((address & 0xFFFF, found, "read"))
        self.spend()
        return found

    def write8(self, address: int, value: int) -> None:
        self.await_ready(write=True)
        self.memory.write8(address & 0xFFFF, value & 0xFF)
        if self.trace is not None:
            self.trace.append((address & 0xFFFF, value & 0xFF, "write"))
        self.spend()

    def dead(self, address: int) -> None:
        """A cycle spent reading something the part will not use.

        Every cycle of this processor is a bus cycle: it has no way to think
        without driving an address, so what looks like internal work is a read
        whose result is thrown away. Those reads reach real devices, and a device
        that counts its own reads can tell. They are cycles, so they are here.
        """
        self.read8(address)

    def read16(self, address: int) -> int:
        return self.read8(address) | (self.read8(address + 1) << 8)

    def read16_in_page(self, address: int) -> int:
        """A pointer read the way the part reads one, without leaving its page."""
        high = (address & 0xFF00) | ((address + 1) & 0x00FF)
        return self.read8(address) | (self.read8(high) << 8)

    def read16_in_zero_page(self, address: int) -> int:
        return self.read8(address & 0xFF) | (self.read8((address + 1) & 0xFF) << 8)

    def fetch8(self) -> int:
        value = self.read8(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def fetch16(self) -> int:
        low = self.fetch8()
        return low | (self.fetch8() << 8)

    def push8(self, value: int) -> None:
        self.write8(STACK_PAGE | self.s, value)
        self.s = (self.s - 1) & 0xFF

    def pull8(self) -> int:
        self.s = (self.s + 1) & 0xFF
        return self.read8(STACK_PAGE | self.s)

    def push16(self, value: int) -> None:
        self.push8((value >> 8) & 0xFF)
        self.push8(value & 0xFF)

    def pull16(self) -> int:
        low = self.pull8()
        return low | (self.pull8() << 8)

    def set_nz(self, value: int) -> None:
        self.z = (value & 0xFF) == 0
        self.n = bool(value & 0x80)

    def effective(self, mode: str, kind: str = READ) -> int:
        """Where an instruction's operand lives, by the rules of its mode.

        The kind of access decides how many cycles getting there costs, so it has
        to be named. Indexing wrong and correcting it is free for a read that
        happens to stay inside a page and never free for a write, and both are
        below in `indexed`.
        """
        if mode == "zeroPage":
            return self.fetch8()
        if mode == "zeroPageX":
            base = self.fetch8()
            self.dead(self.spare_in_page_zero(base))
            return (base + self.x) & 0xFF
        if mode == "zeroPageY":
            base = self.fetch8()
            self.dead(self.spare_in_page_zero(base))
            return (base + self.y) & 0xFF
        if mode == "absolute":
            return self.fetch16()
        if mode == "absoluteX":
            return self.indexed(self.fetch16(), self.x, kind)
        if mode == "absoluteY":
            return self.indexed(self.fetch16(), self.y, kind)
        if mode == "indexedIndirectX":
            base = self.fetch8()
            self.dead(self.spare_in_page_zero(base))
            return self.read16_in_zero_page((base + self.x) & 0xFF)
        if mode == "indirectIndexedY":
            return self.indexed(self.read16_in_zero_page(self.fetch8()), self.y, kind)
        if mode == "zeroPageIndirect":
            return self.read16_in_zero_page(self.fetch8())
        raise UnsupportedError(f"{mode} has no effective address")

    def indexed(self, base: int, index: int, kind: str) -> int:
        """Add an index, and pay what the part pays for adding it.

        The part adds the index to the low byte and puts the result on the bus
        before it knows whether a carry into the high byte is needed. For a read
        that costs nothing when no carry is needed, because the address it read
        was the right one. When a carry is needed it read the wrong address, and
        the cycle spent doing that is visible: the wrong address appears on the
        bus, and only then is the right one read.

        A write never takes the shortcut. The part will not write to an address it
        might have to correct, so it always spends the cycle, and always as a read
        of the uncorrected address. The same is true of a read-modify-write.
        """
        target = (base + index) & 0xFFFF
        uncorrected = (base & 0xFF00) | (target & 0x00FF)
        if kind != READ or uncorrected != target:
            self.dead(self.spare_for_index(base, target))
        return target

    def idles_after_opcode(self, opcode: int, mnemonic: str, mode: str) -> bool:
        """Whether a one byte instruction spends a cycle on the byte after it.

        On this part every one of them does: it has no operand to fetch and
        nothing else to drive, so it reads the next byte and ignores it. The CMOS
        parts turned some of the opcodes nobody documented into single cycles,
        which is why this is a question rather than a rule.
        """
        return not MODE_SIZE[mode]

    def spare_for_index(self, base: int, target: int) -> int:
        """Which address the spare cycle of an indexed access reads.

        This part puts the half-formed address there: the low byte with the index
        added and the high byte as it was. The CMOS parts do not, and that is a
        per-part decision rather than a detail, so it is a method.
        """
        return (base & 0xFF00) | (target & 0x00FF)

    def spare_in_page_zero(self, base: int) -> int:
        """Which address the spare cycle of a page zero indexed access reads.

        This part reads the page zero address before the index was added.
        """
        return base

    def modify_kind(self, mnemonic: str) -> str:
        """Whether a read-modify-write pays the indexing cycle unconditionally.

        On this part every one of them does: it will not write to an address it
        might have to correct, so the half-formed address goes on the bus first
        whether or not a carry turns out to be needed. The CMOS parts pay it for
        some of these instructions and not others, which is why this is a method.
        """
        return MODIFY

    def settle(self, address: int, held: int) -> None:
        """What this part does between reading a value and writing the new one.

        It writes back what it just read. There is nowhere to keep the value while
        the operation runs, so the address is written twice and the first write
        carries the old contents.
        """
        self.write8(address, held)

    def operand(self, mode: str) -> int:
        if mode == "immediate":
            return self.fetch8()
        if mode == "accumulator":
            return self.a
        return self.read8(self.effective(mode))

    def unindexed_base(self, mode: str) -> tuple[int, int]:
        """The address before indexing, which the unstable stores need."""
        base = self.fetch16()
        index = self.x if mode == "absoluteX" else self.y
        return base, (base + index) & 0xFFFF

    def add_with_carry(self, value: int) -> None:
        carry = 1 if self.c else 0
        if self.d and self.decimal:
            low = (self.a & 0x0F) + (value & 0x0F) + carry
            if low > 0x09:
                low += 0x06
            high = (self.a >> 4) + (value >> 4) + (1 if low > 0x0F else 0)
            binary = (self.a + value + carry) & 0xFF
            self.z = binary == 0
            self.n = bool((high << 4) & 0x80)
            self.v = bool(~(self.a ^ value) & (self.a ^ (high << 4)) & 0x80)
            if high > 0x09:
                high += 0x06
            self.c = high > 0x0F
            self.a = ((high << 4) | (low & 0x0F)) & 0xFF
            return
        total = self.a + value + carry
        self.c = total > 0xFF
        self.v = bool(~(self.a ^ value) & (self.a ^ total) & 0x80)
        self.a = total & 0xFF
        self.set_nz(self.a)

    def subtract_with_carry(self, value: int) -> None:
        borrow = 0 if self.c else 1
        binary = (self.a - value - borrow) & 0xFF
        self.c = (self.a - value - borrow) >= 0
        self.v = bool((self.a ^ value) & (self.a ^ binary) & 0x80)
        self.set_nz(binary)
        if self.d and self.decimal:
            low = (self.a & 0x0F) - (value & 0x0F) - borrow
            high = (self.a >> 4) - (value >> 4)
            if low & 0x10:
                low -= 0x06
                high -= 1
            if high & 0x10:
                high -= 0x06
            self.a = ((high << 4) | (low & 0x0F)) & 0xFF
            return
        self.a = binary

    def compare(self, register: int, value: int) -> None:
        result = (register - value) & 0xFF
        self.c = register >= value
        self.set_nz(result)

    def branch(self, taken: bool) -> None:
        """Take the branch, and pay for it in the order the part pays.

        A branch not taken costs nothing beyond its two bytes. Taken, the part
        spends a cycle with the instruction it is not going to run on the bus
        while it adds the offset to the low byte of the counter. If that addition
        carries, it spends another with the half-corrected address on the bus.
        """
        offset = self.fetch8()
        if not taken:
            return
        if offset & 0x80:
            offset -= 0x100
        self.dead(self.pc)
        target = (self.pc + offset) & 0xFFFF
        uncorrected = (self.pc & 0xFF00) | (target & 0x00FF)
        if uncorrected != target:
            self.dead(uncorrected)
        self.pc = target

    def step(self) -> int:
        """Run one instruction, and report the cycles it took.

        The count is what a caller needs to keep a host in step with a real
        clock. A part at 1.023 MHz spends 1,023,000 cycles a second, so a host
        that adds up what each instruction returns knows exactly how far ahead
        of the wall it has run.
        """
        started = self.cycles
        if self.stopped:
            raise Stopped("the processor has been stopped")
        self.steps += 1
        opcode = self.fetch8()
        mnemonic, mode = self.table[opcode]
        if self.idles_after_opcode(opcode, mnemonic, mode):
            self.dead(self.pc)
        handler = getattr(self, f"op_{mnemonic}", None)
        if handler is None:
            raise UnsupportedError(f"{mnemonic} is not implemented")
        handler(mode)
        self.sample_pins()
        return self.cycles - started

    def run_for(self, cycles: int) -> int:
        """Run whole instructions until at least this many cycles have passed.

        Returns what was actually spent, which is almost never the number asked
        for: an instruction is not divisible, so the last one usually carries the
        count past the budget. A host pacing against a clock carries the excess
        into the next call rather than discarding it, which is what keeps a long
        run from drifting.

        A hung part still costs its host every cycle. Once a jam opcode has run
        no further instruction ever completes, but the clock does not stop and
        neither does this: it goes on driving $FFFF a cycle at a time and returns
        the budget it spent, because that is what a board with a jammed processor
        in it actually does.
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

    def call(self, address: int) -> Cpu:
        """Run from an address until the routine it names returns."""
        self.pc = address & 0xFFFF
        depth = 0
        while True:
            mnemonic = self.table[self.read8(self.pc)][0]
            if mnemonic == "rts":
                if depth == 0:
                    return self
                depth -= 1
            elif mnemonic == "jsr":
                depth += 1
            self.step()

    def op_lda(self, mode: str) -> None:
        self.a = self.operand(mode)
        self.set_nz(self.a)

    def op_ldx(self, mode: str) -> None:
        self.x = self.operand(mode)
        self.set_nz(self.x)

    def op_ldy(self, mode: str) -> None:
        self.y = self.operand(mode)
        self.set_nz(self.y)

    def op_sta(self, mode: str) -> None:
        self.write8(self.effective(mode, WRITE), self.a)

    def op_stx(self, mode: str) -> None:
        self.write8(self.effective(mode, WRITE), self.x)

    def op_sty(self, mode: str) -> None:
        self.write8(self.effective(mode, WRITE), self.y)

    def op_tax(self, mode: str) -> None:
        self.x = self.a
        self.set_nz(self.x)

    def op_tay(self, mode: str) -> None:
        self.y = self.a
        self.set_nz(self.y)

    def op_txa(self, mode: str) -> None:
        self.a = self.x
        self.set_nz(self.a)

    def op_tya(self, mode: str) -> None:
        self.a = self.y
        self.set_nz(self.a)

    def op_tsx(self, mode: str) -> None:
        self.x = self.s
        self.set_nz(self.x)

    def op_txs(self, mode: str) -> None:
        self.s = self.x

    def op_pha(self, mode: str) -> None:
        self.push8(self.a)

    def op_php(self, mode: str) -> None:
        self.push8(self.status() | FLAG_B)

    def op_pla(self, mode: str) -> None:
        self.dead(STACK_PAGE | self.s)
        self.a = self.pull8()
        self.set_nz(self.a)

    def op_plp(self, mode: str) -> None:
        self.dead(STACK_PAGE | self.s)
        self.set_status(self.pull8())
        self.b = False

    def op_and(self, mode: str) -> None:
        self.a &= self.operand(mode)
        self.set_nz(self.a)

    def op_ora(self, mode: str) -> None:
        self.a |= self.operand(mode)
        self.set_nz(self.a)

    def op_eor(self, mode: str) -> None:
        self.a ^= self.operand(mode)
        self.set_nz(self.a)

    def op_bit(self, mode: str) -> None:
        value = self.operand(mode)
        self.z = (self.a & value) == 0
        self.n = bool(value & 0x80)
        self.v = bool(value & 0x40)

    def op_adc(self, mode: str) -> None:
        self.add_with_carry(self.operand(mode))

    def op_sbc(self, mode: str) -> None:
        self.subtract_with_carry(self.operand(mode))

    def op_cmp(self, mode: str) -> None:
        self.compare(self.a, self.operand(mode))

    def op_cpx(self, mode: str) -> None:
        self.compare(self.x, self.operand(mode))

    def op_cpy(self, mode: str) -> None:
        self.compare(self.y, self.operand(mode))

    def op_inc(self, mode: str) -> None:
        self.read_modify_write(mode, "inc", self.bump)

    def op_dec(self, mode: str) -> None:
        self.read_modify_write(mode, "dec", self.drop)

    def bump(self, value: int) -> int:
        result = (value + 1) & 0xFF
        self.set_nz(result)
        return result

    def drop(self, value: int) -> int:
        result = (value - 1) & 0xFF
        self.set_nz(result)
        return result

    def op_inx(self, mode: str) -> None:
        self.x = (self.x + 1) & 0xFF
        self.set_nz(self.x)

    def op_iny(self, mode: str) -> None:
        self.y = (self.y + 1) & 0xFF
        self.set_nz(self.y)

    def op_dex(self, mode: str) -> None:
        self.x = (self.x - 1) & 0xFF
        self.set_nz(self.x)

    def op_dey(self, mode: str) -> None:
        self.y = (self.y - 1) & 0xFF
        self.set_nz(self.y)

    def shift_left(self, value: int) -> int:
        self.c = bool(value & 0x80)
        result = (value << 1) & 0xFF
        self.set_nz(result)
        return result

    def shift_right(self, value: int) -> int:
        self.c = bool(value & 0x01)
        result = value >> 1
        self.set_nz(result)
        return result

    def rotate_left(self, value: int) -> int:
        carry = 1 if self.c else 0
        self.c = bool(value & 0x80)
        result = ((value << 1) | carry) & 0xFF
        self.set_nz(result)
        return result

    def rotate_right(self, value: int) -> int:
        carry = 0x80 if self.c else 0
        self.c = bool(value & 0x01)
        result = (value >> 1) | carry
        self.set_nz(result)
        return result

    def read_modify_write(
        self, mode: str, mnemonic: str, transform: Callable[[int], int]
    ) -> tuple[int | None, int]:
        """Read it, write it back unchanged, then write the new value.

        The second write is the one nobody expects. This part has nowhere to keep
        the result while it decides, so it puts the value it just read straight
        back and only then writes what the operation produced. A device mapped at
        that address is written twice, the first time with its own old value, and
        a device that acts on writes acts twice.
        """
        if mode == "accumulator":
            self.a = transform(self.a)
            return None, self.a
        address = self.effective(mode, self.modify_kind(mnemonic))
        held = self.read8(address)
        self.settle(address, held)
        value = transform(held)
        self.write8(address, value)
        return address, value

    def op_asl(self, mode: str) -> None:
        self.read_modify_write(mode, "asl", self.shift_left)

    def op_lsr(self, mode: str) -> None:
        self.read_modify_write(mode, "lsr", self.shift_right)

    def op_rol(self, mode: str) -> None:
        self.read_modify_write(mode, "rol", self.rotate_left)

    def op_ror(self, mode: str) -> None:
        self.read_modify_write(mode, "ror", self.rotate_right)

    def op_jmp(self, mode: str) -> None:
        if mode == "indirect":
            self.pc = self.read16_in_page(self.fetch16())
            return
        self.pc = self.fetch16()

    def op_jsr(self, mode: str) -> None:
        """Read half the destination, push, then read the other half.

        The push happens between the two halves of the address it is jumping to,
        which is invisible except when the stack has walked into the instruction:
        then the push overwrites the byte that has not been read yet, and the
        jump goes wherever the pushed byte says. Between the two, the part spends
        a cycle reading the stack it is about to write.
        """
        low = self.fetch8()
        self.dead(STACK_PAGE | self.s)
        self.push16(self.pc)
        self.pc = (self.fetch8() << 8) | low

    def op_rts(self, mode: str) -> None:
        self.dead(STACK_PAGE | self.s)
        pulled = self.pull16()
        self.dead(pulled)
        self.pc = (pulled + 1) & 0xFFFF

    def op_rti(self, mode: str) -> None:
        self.dead(STACK_PAGE | self.s)
        self.set_status(self.pull8())
        self.b = False
        self.pc = self.pull16()

    def op_brk(self, mode: str) -> None:
        self.pc = (self.pc + 1) & 0xFFFF
        self.push16(self.pc)
        self.push8(self.status() | FLAG_B)
        self.i = True
        self.pc = self.read16(BREAK_VECTOR)

    def interrupt(self, vector: int) -> None:
        """Take an interrupt the way a pin does, rather than the way BRK does.

        Three things separate this from a break. The return address is the next
        instruction rather than the byte after a signature, because no opcode was
        consumed. The pushed status has the break bit clear, which is the only
        thing a handler can look at to tell which of the two happened. And the
        register itself keeps whatever that bit held: it is stored like a flag and
        written like neither, the same rule the break instruction follows.
        """
        self.dead(self.pc)
        self.dead(self.pc)
        self.push16(self.pc)
        self.push8(self.status() & ~FLAG_B)
        self.i = True
        self.pc = self.read16(vector)

    def require(self, pin: str) -> None:
        """Refuse a line this part does not bring out of its package."""
        if pin not in self.package_pins:
            raise NoSuchPin(
                f"the {self.model} has no {pin} pin; it brings out {', '.join(self.package_pins)}"
            )

    def await_ready(self, write: bool = False) -> None:
        """Spend cycles while the ready line is held low, which is what RDY does.

        "A low input logic level on the Ready (RDY) will halt the microprocessor
        in its current state." The part stops where it stands and the address
        lines hold what they were driving, which is how slow memory is given time
        to answer without slowing the clock.

        The NMOS parts carve out one case and the MOS manual is explicit about
        it: "The RDY function will not stop the processor in a cycle in which a
        WRITE operation is being performed." A write already on its way out is
        finished. The CMOS parts have no such exception, and that difference is a
        property of the part rather than of this model, so it lives in
        `stalls_on_write`.

        A stall costs time and records nothing. The data sheet describes held
        address lines rather than an access, and this trace records accesses, so
        the cycle is charged and the bus picture is absent rather than invented.

        A caller that holds the line low and never releases it will not get out
        of here, which is exactly what a board that does the same gets. The cycle
        hook fires on every stall, so a host driving the part by hand can release
        the line from there, and a clock can release it between two cycles.
        """
        if write and not self.stalls_on_write:
            return
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
        flag clears. False means the request is still outstanding.
        """
        self.require("irq")
        if self.i:
            return False
        self.interrupt(IRQ_VECTOR)
        return True

    def nmi(self) -> None:
        """Pull the non-maskable line, which no flag defends against.

        The real pin is edge sensitive, so it is the transition that interrupts
        and holding the line low afterwards does nothing. A caller models that by
        calling this once per transition, which is why there is nothing to poll
        and nothing to report.
        """
        self.require("nmi")
        self.interrupt(NMI_VECTOR)

    def op_bpl(self, mode: str) -> None:
        self.branch(not self.n)

    def op_bmi(self, mode: str) -> None:
        self.branch(self.n)

    def op_bvc(self, mode: str) -> None:
        self.branch(not self.v)

    def op_bvs(self, mode: str) -> None:
        self.branch(self.v)

    def op_bcc(self, mode: str) -> None:
        self.branch(not self.c)

    def op_bcs(self, mode: str) -> None:
        self.branch(self.c)

    def op_bne(self, mode: str) -> None:
        self.branch(not self.z)

    def op_beq(self, mode: str) -> None:
        self.branch(self.z)

    def op_clc(self, mode: str) -> None:
        self.c = False

    def op_sec(self, mode: str) -> None:
        self.c = True

    def op_cli(self, mode: str) -> None:
        self.i = False

    def op_sei(self, mode: str) -> None:
        self.i = True

    def op_clv(self, mode: str) -> None:
        self.v = False

    def op_cld(self, mode: str) -> None:
        self.d = False

    def op_sed(self, mode: str) -> None:
        self.d = True

    def op_nop(self, mode: str) -> None:
        if mode not in ("implied", "accumulator"):
            self.operand(mode)

    def op_jam(self, mode: str) -> None:
        """Hang the part, which is not the same as stopping it.

        Nothing documents these opcodes, so the authority here is the recorded
        corpus, and it is unanimous: 120,000 recordings across all twelve of them
        agree cycle for cycle with no variation at all. After the opcode and the
        byte behind it the part reads $FFFF, then $FFFE twice, and from there
        drives $FFFF for as long as it is clocked.

        Those are the interrupt vector, so what the part is doing looks like a
        BRK that never finished: it began fetching a handler and stalled with the
        address bus held high. It is still a running processor. The clock still
        ticks, the bus still cycles, and a device watching $FFFF still sees reads
        arrive. Only RESET ends it.

        That is why this sets a state of its own rather than reusing `stopped`. A
        part told to STP genuinely halts and drives nothing, while a jammed part
        drives $FFFF forever, and a host pacing against a real clock has to keep
        spending cycles on it rather than being handed an exception.
        """
        self.read8(JAM_HIGH)
        self.read8(JAM_LOW)
        self.read8(JAM_LOW)
        self.jammed = True
        self.stopped = True

    def jam_cycle(self) -> None:
        """One cycle of a hung part, which is a read of $FFFF it does nothing with."""
        self.read8(JAM_HIGH)

    def held(self) -> bool:
        """Whether the part can no longer begin an instruction on its own.

        A question rather than an attribute because the parts answer it
        differently. This one can only be hung, by an opcode nobody documented.
        The CMOS parts added two instructions that hold deliberately.
        """
        return self.jammed

    def held_cycle(self) -> None:
        """One cycle of a part in that state, which for this one is a read of $FFFF."""
        self.jam_cycle()

    def op_slo(self, mode: str) -> None:
        _, value = self.read_modify_write(mode, "slo", self.shift_left)
        self.a |= value
        self.set_nz(self.a)

    def op_rla(self, mode: str) -> None:
        _, value = self.read_modify_write(mode, "rla", self.rotate_left)
        self.a &= value
        self.set_nz(self.a)

    def op_sre(self, mode: str) -> None:
        _, value = self.read_modify_write(mode, "sre", self.shift_right)
        self.a ^= value
        self.set_nz(self.a)

    def op_rra(self, mode: str) -> None:
        _, value = self.read_modify_write(mode, "rra", self.rotate_right)
        self.add_with_carry(value)

    def op_sax(self, mode: str) -> None:
        self.write8(self.effective(mode, WRITE), self.a & self.x)

    def op_lax(self, mode: str) -> None:
        self.a = self.x = self.operand(mode)
        self.set_nz(self.a)

    def op_dcp(self, mode: str) -> None:
        _, value = self.read_modify_write(mode, "dcp", lambda held: (held - 1) & 0xFF)
        self.compare(self.a, value)

    def op_isc(self, mode: str) -> None:
        _, value = self.read_modify_write(mode, "isc", lambda held: (held + 1) & 0xFF)
        self.subtract_with_carry(value)

    def op_anc(self, mode: str) -> None:
        self.a &= self.fetch8()
        self.set_nz(self.a)
        self.c = self.n

    def op_alr(self, mode: str) -> None:
        self.a &= self.fetch8()
        self.a = self.shift_right(self.a)

    def op_arr(self, mode: str) -> None:
        value = self.fetch8()
        self.a &= value
        carry = 0x80 if self.c else 0
        if self.d and self.decimal:
            result = (self.a >> 1) | carry
            self.set_nz(result)
            self.v = bool((result ^ self.a) & 0x40)
            low = self.a & 0x0F
            if low + (self.a & 0x01) > 0x05:
                result = (result & 0xF0) | ((result + 0x06) & 0x0F)
            high = self.a & 0xF0
            if high + (self.a & 0x10) > 0x50:
                result = (result + 0x60) & 0xFF
                self.c = True
            else:
                self.c = False
            self.a = result
            return
        self.a = (self.a >> 1) | carry
        self.set_nz(self.a)
        self.c = bool(self.a & 0x40)
        self.v = bool(((self.a >> 6) ^ (self.a >> 5)) & 0x01)

    def op_sbx(self, mode: str) -> None:
        value = self.fetch8()
        result = (self.a & self.x) - value
        self.c = result >= 0
        self.x = result & 0xFF
        self.set_nz(self.x)

    def op_las(self, mode: str) -> None:
        value = self.operand(mode) & self.s
        self.a = self.x = self.s = value
        self.set_nz(value)

    def op_ane(self, mode: str) -> None:
        self.a = (self.a | MAGIC) & self.x & self.fetch8()
        self.set_nz(self.a)

    def op_lxa(self, mode: str) -> None:
        self.a = self.x = (self.a | MAGIC) & self.fetch8()
        self.set_nz(self.a)

    def unstable_store(self, mode: str, register: int) -> None:
        if mode in ("absoluteX", "absoluteY"):
            base, address = self.unindexed_base(mode)
        else:
            base = self.read16_in_zero_page(self.fetch8())
            address = (base + self.y) & 0xFFFF
        self.dead((base & 0xFF00) | (address & 0x00FF))
        value = register & (((base >> 8) + 1) & 0xFF)
        if (base & 0xFF00) != (address & 0xFF00):
            address = (address & 0x00FF) | (value << 8)
        self.write8(address, value)

    def op_sha(self, mode: str) -> None:
        self.unstable_store(mode, self.a & self.x)

    def op_shx(self, mode: str) -> None:
        self.unstable_store(mode, self.x)

    def op_shy(self, mode: str) -> None:
        self.unstable_store(mode, self.y)

    def op_tas(self, mode: str) -> None:
        self.s = self.a & self.x
        self.unstable_store(mode, self.s)
