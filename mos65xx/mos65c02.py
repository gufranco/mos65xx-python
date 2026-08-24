"""The CMOS core: the same part with its mistakes fixed and its gaps filled.

What it inherits is most of the machine. What it changes is small enough to list,
and every item on the list is a place where code written for one part behaves
differently on the other.

The jump through a pointer no longer reads the high byte from the start of the
page. Code that relied on the bug breaks here; code that avoided it works on both.

Decimal arithmetic now sets the sign and zero flags from the decimal answer rather
than from the binary one underneath it. On the older part those two flags were
meaningless after a decimal add, and programs learned not to look at them, so
nothing depends on the old behaviour and everything that reads them now gets the
truth.

A break clears the decimal flag on the way into its handler. On the older part it
did not, so an interrupt taken during decimal arithmetic ran its handler in
decimal mode, and handlers had to clear it themselves.

The instructions the freed opcodes bought are ordinary: a pointer mode with no
index, a store of zero, a branch that always takes, a test-and-set and its
opposite, pushes and pulls for the index registers, and an increment of the
accumulator. Two of the three parts also carry thirty two instructions for setting,
clearing and branching on a single bit in the first page, and one of those two can
be stopped or told to wait for an interrupt.

Which part a program is running on is not a detail. A bit-clear instruction on a
part that does not have it is a no-operation, and nothing reports that the bit was
never cleared.
"""

from __future__ import annotations

from typing import Any, override

from .errors import Waiting
from .mos6502 import MODIFY, READ, STACK_PAGE, WRITE
from .mos6502 import Cpu as Nmos
from .opcodes65c02 import CMOS

SINGLE_CYCLE_NOPS = frozenset(
    opcode for opcode in range(0x100) if opcode & 0x0F in (0x03, 0x0B)
) - {0xCB}
"""The undocumented opcodes that take one cycle and read nothing at all.

Two whole columns of the matrix, minus the one the WDC part spent on waiting for
an interrupt: on the parts that left it as a no-operation it still takes two
cycles, like the documented one, rather than the one its neighbours take.
"""

SHORTCUT_MODIFIES = frozenset({"asl", "lsr", "rol", "ror"})
"""Read-modify-writes that pay for indexing only when the index crosses a page."""


class Cpu(Nmos):
    """One CMOS 6502, of whichever revision its table describes.
    One slot of its own. The rest are the NMOS part's, inherited, because this is
    that core with the undocumented opcodes replaced.
    """

    __slots__ = ("waiting",)

    @override
    def __init__(self, memory: Any, table: Any = CMOS, **options: Any) -> None:
        self.waiting = False
        super().__init__(memory, table=table, **options)
        self.model = "65c02"

    @override
    def reset(self, seed: int | None = None) -> Nmos:
        """Reset this part, which defines one flag more than the older one does.

        The manufacturer's own table of differences puts it plainly: the decimal
        flag is indeterminate after a reset on the NMOS part and initialized to
        binary mode on this one. So a program that forgets to clear it before its
        first addition is correct here and wrong there, and the only way a model
        can show that is to leave the older part's flag holding whatever it held.
        """
        self.waiting = False
        held = super().reset(seed) if seed is not None else super().reset()
        self.d = False
        return held

    @override
    def add_with_carry(self, value: int) -> None:
        if not (self.d and self.decimal):
            return super().add_with_carry(value)

        carry = 1 if self.c else 0
        low = (self.a & 0x0F) + (value & 0x0F) + carry
        high = (self.a >> 4) + (value >> 4)
        if low > 0x09:
            low += 0x06
            high += 1
        self.v = bool(~(self.a ^ value) & (self.a ^ (high << 4)) & 0x80)
        if high > 0x09:
            high += 0x06
        self.c = high > 0x0F
        self.a = ((high << 4) | (low & 0x0F)) & 0xFF
        self.set_nz(self.a)
        return None

    @override
    def subtract_with_carry(self, value: int) -> None:
        """Decimal subtraction as this part does it, which is not how the older one did.

        Both produce the same digits whenever both operands are valid decimal. They
        part company as soon as one is not, and nothing stops a program subtracting
        a byte whose nibbles are not digits.

        The older part borrows out of the low digit into the high one. This part
        subtracts in binary and then corrects: sixty for a result that went below
        zero, six more when the low digit could not cover what was taken from it.
        Feed both an operand like `$FC` and they differ by one whole digit.

        The sign and zero flags describe the decimal answer here. On the older part
        they described the binary difference underneath it, which meant nothing.
        """
        if not (self.d and self.decimal):
            return super().subtract_with_carry(value)

        borrow = 0 if self.c else 1
        binary = self.a - value - borrow
        self.v = bool((self.a ^ value) & (self.a ^ (binary & 0xFF)) & 0x80)
        self.c = binary >= 0
        if binary < 0:
            binary -= 0x60
        if ((self.a & 0x0F) - borrow) < (value & 0x0F):
            binary -= 0x06
        self.a = binary & 0xFF
        self.set_nz(self.a)
        return None

    @override
    def op_jmp(self, mode: str) -> None:
        """Both indirect jumps cost a cycle the older part did not spend.

        The older part read a pointer that ended a page from the start of the same
        page. This one reads it properly, and the cycle it pays for doing so is
        that same wrong read: it reads the address the older part would have used,
        throws it away, and then reads the right one. When the pointer does not
        end a page those two addresses are the same and the cycle looks like a
        repeat, which is why it takes a pointer at $xxFF to see what it is.

        Through an indexed pointer the spare cycle re-reads the operand's low
        byte instead. Neither address is the one the data sheet's timing chart
        gives, and both are what the recordings show in every case.
        """
        if mode == "indirect":
            pointer = self.fetch16()
            low = self.read8(pointer)
            self.dead((pointer & 0xFF00) | ((pointer + 1) & 0x00FF))
            self.pc = low | (self.read8((pointer + 1) & 0xFFFF) << 8)
            return
        if mode == "indirectX":
            base = self.fetch16()
            self.dead((self.pc - 2) & 0xFFFF)
            self.pc = self.read16((base + self.x) & 0xFFFF)
            return
        self.pc = self.fetch16()

    @override
    def modify_kind(self, mnemonic: str) -> str:
        """The shifts and rotates take the shortcut a plain read takes.

        Increment and decrement of an indexed absolute address always spend the
        indexing cycle here, as they do on the older part. The four shifts and
        rotates do not: they spend it only when the index crosses a page, which
        makes them six cycles rather than seven and is the one place the data
        sheet's own timing chart lumps all six together and is wrong.
        """
        return READ if mnemonic in SHORTCUT_MODIFIES else MODIFY

    @override
    def spare_for_index(self, base: int, target: int) -> int:
        """This part re-reads the last byte of the instruction, not a wrong address.

        The older part put the half-formed address on the bus while it worked out
        the carry, which meant a spare cycle could read a device that had nothing
        to do with the instruction. This one re-reads the byte it just fetched
        instead, which reaches nothing new.
        """
        return (self.pc - 1) & 0xFFFF

    @override
    def settle(self, address: int, held: int) -> None:
        """This part reads the address again rather than writing back what it read.

        The older part wrote twice, the first time with the old contents, which a
        device acting on writes saw as two writes. This one reads, reads again,
        and writes once.
        """
        self.dead(address)

    @override
    def idles_after_opcode(self, opcode: int, mnemonic: str, mode: str) -> bool:
        """Every one byte instruction spends a cycle on the next byte but one.

        The undocumented single byte opcodes are one cycle on this part, which is
        the only place in the family where an instruction does not read a second
        byte at all. The documented no-operation is not one of them.
        """
        if mnemonic == "nop" and mode == "implied":
            return opcode not in SINGLE_CYCLE_NOPS
        return super().idles_after_opcode(opcode, mnemonic, mode)

    def spent_on_decimal(self, mode: str) -> int:
        """The operand, plus the cycle this part spends when decimal is set.

        Decimal arithmetic costs an extra cycle here and nothing on the older
        part. With an address to hand the part re-reads it. With an immediate
        operand there is no address, and the recordings fill that cycle with a
        constant that differs per suite and cannot be derived from any register,
        so this reads the last byte of the instruction and conformance/
        divergences.json records the difference rather than reproducing a
        recorder's placeholder.
        """
        if mode == "immediate":
            value = self.fetch8()
            if self.d and self.decimal:
                self.dead((self.pc - 1) & 0xFFFF)
            return value
        address = self.effective(mode)
        value = self.read8(address)
        if self.d and self.decimal:
            self.dead(address)
        return value

    @override
    def op_adc(self, mode: str) -> None:
        self.add_with_carry(self.spent_on_decimal(mode))

    @override
    def op_sbc(self, mode: str) -> None:
        self.subtract_with_carry(self.spent_on_decimal(mode))

    @override
    def op_brk(self, mode: str) -> None:
        super().op_brk(mode)
        self.d = False

    @override
    def interrupt(self, vector: int) -> None:
        """Clear decimal on the way in, which the older part does not do.

        On the NMOS part an interrupt taken in the middle of decimal arithmetic
        ran its handler in decimal mode, and every handler had to clear the flag
        itself or corrupt whatever it added. This part clears it, and that is why
        a handler written for one is not safe on the other.
        """
        super().interrupt(vector)
        self.d = False

    @override
    def irq(self) -> bool:
        """A request releases a wait even when the disable flag refuses the jump.

        That is the whole point of waiting: a program sets the disable flag, waits,
        and continues at the next instruction the moment the line goes low, with
        no handler entered and no latency spent on one.
        """
        self.waiting = False
        return super().irq()

    @override
    def nmi(self) -> None:
        self.waiting = False
        super().nmi()

    @override
    def op_nop(self, mode: str) -> None:
        """The opcodes nobody documented, which do nothing at their own pace.

        This part turned every gap in the opcode matrix into a no-operation, and
        they are not all the same size or the same length. The single byte ones
        are one cycle, which is the only instruction on the part that does not
        read a second byte. The rest read their operands, and the ones with an
        address read that address and throw the byte away, so a device mapped
        there sees the read.
        """
        if mode == "implied":
            return
        if mode == "immediate":
            self.fetch8()
            return
        if mode == "absolute":
            self.fetch16()
            return
        if mode == "absoluteX":
            self.fetch16()
            self.dead((self.pc - 1) & 0xFFFF)
            return
        self.dead(self.effective(mode))

    def op_bra(self, mode: str) -> None:
        self.branch(True)

    def op_stz(self, mode: str) -> None:
        self.write8(self.effective(mode, WRITE), 0x00)

    def op_tsb(self, mode: str) -> None:
        address = self.effective(mode)
        value = self.read8(address)
        self.settle(address, value)
        self.z = (self.a & value) == 0
        self.write8(address, value | self.a)

    def op_trb(self, mode: str) -> None:
        address = self.effective(mode)
        value = self.read8(address)
        self.settle(address, value)
        self.z = (self.a & value) == 0
        self.write8(address, value & ~self.a & 0xFF)

    @override
    def op_bit(self, mode: str) -> None:
        if mode == "immediate":
            self.z = (self.a & self.fetch8()) == 0
            return
        super().op_bit(mode)

    @override
    def op_inc(self, mode: str) -> None:
        if mode == "accumulator":
            self.a = (self.a + 1) & 0xFF
            self.set_nz(self.a)
            return
        super().op_inc(mode)

    @override
    def op_dec(self, mode: str) -> None:
        if mode == "accumulator":
            self.a = (self.a - 1) & 0xFF
            self.set_nz(self.a)
            return
        super().op_dec(mode)

    def op_phx(self, mode: str) -> None:
        self.push8(self.x)

    def op_phy(self, mode: str) -> None:
        self.push8(self.y)

    def op_plx(self, mode: str) -> None:
        self.dead(STACK_PAGE | self.s)
        self.x = self.pull8()
        self.set_nz(self.x)

    def op_ply(self, mode: str) -> None:
        self.dead(STACK_PAGE | self.s)
        self.y = self.pull8()
        self.set_nz(self.y)

    def op_stp(self, mode: str) -> None:
        self.stopped = True

    def op_wai(self, mode: str) -> None:
        self.waiting = True

    @override
    def step(self) -> int:
        """Run one instruction, unless the part is holding and cannot start one."""
        if self.waiting:
            raise Waiting("the processor is waiting for an interrupt")
        return super().step()

    @override
    def await_ready(self, write: bool = False) -> None:
        """The CMOS parts halt on any cycle, with no exception for a write."""
        self.stalls_on_write = True
        super().await_ready(write)

    @override
    def held(self) -> bool:
        """Either of the two states this part can put itself into deliberately."""
        return self.stopped or self.waiting

    @override
    def held_cycle(self) -> None:
        """One cycle of a part that has halted itself, which costs time and no bus.

        The data sheet says what the lines do: a part halted this way holds "the
        output address lines reflecting the current address being fetched", and
        stays there. It is holding an address rather than fetching one, so there
        is no access to record, and this project's trace records accesses. The
        time is charged because the board's clock is still running; the held lines
        are not represented, which OPEN-QUESTIONS.md says plainly.
        """
        self.spend()

    def modify_bit(self, bit: int, set_it: bool) -> None:
        address = self.effective("zeroPage")
        value = self.read8(address)
        self.settle(address, value)
        self.write8(address, value | (1 << bit) if set_it else value & ~(1 << bit) & 0xFF)

    def branch_on_bit(self, bit: int, wanted: bool) -> None:
        """Read a bit in the first page, then branch on it, at its own pace.

        This is the one branch on the part that does not put a half-formed address
        on the bus when it crosses a page. It spends both of its extra cycles on
        the byte after itself instead, which is where it is going to fetch from
        next if the branch is not taken.
        """
        address = self.effective("zeroPage")
        value = self.read8(address)
        self.settle(address, value)
        offset = self.fetch8()
        if bool(value & (1 << bit)) != wanted:
            return
        self.dead(self.pc)
        if offset & 0x80:
            offset -= 0x100
        target = (self.pc + offset) & 0xFFFF
        if (target & 0xFF00) != (self.pc & 0xFF00):
            self.dead(self.pc)
        self.pc = target


def _bit_handlers() -> None:
    for bit in range(8):

        def clear(self: Cpu, mode: str, bit: int = bit) -> None:
            self.modify_bit(bit, False)

        def set_bit(self: Cpu, mode: str, bit: int = bit) -> None:
            self.modify_bit(bit, True)

        def branch_clear(self: Cpu, mode: str, bit: int = bit) -> None:
            self.branch_on_bit(bit, False)

        def branch_set(self: Cpu, mode: str, bit: int = bit) -> None:
            self.branch_on_bit(bit, True)

        setattr(Cpu, f"op_rmb{bit}", clear)
        setattr(Cpu, f"op_smb{bit}", set_bit)
        setattr(Cpu, f"op_bbr{bit}", branch_clear)
        setattr(Cpu, f"op_bbs{bit}", branch_set)


_bit_handlers()
