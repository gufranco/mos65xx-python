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

from .mos6502 import Cpu as Nmos
from .opcodes65c02 import CMOS
from .opcodes6502 import MODE_SIZE


class Cpu(Nmos):
    """One CMOS 6502, of whichever revision its table describes."""

    @override
    def __init__(self, memory: Any, table: Any = CMOS, **options: Any) -> None:
        self.waiting = False
        super().__init__(memory, table=table, **options)
        self.model = "65c02"

    @override
    def reset(self, seed: int | None = None) -> Nmos:
        self.waiting = False
        return super().reset(seed) if seed is not None else super().reset()

    @override
    def effective(self, mode: str) -> int:
        if mode == "indirectX":
            return self.read16((self.fetch16() + self.x) & 0xFFFF)
        return super().effective(mode)

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
        if mode == "indirect":
            self.pc = self.read16(self.fetch16())
            return
        if mode == "indirectX":
            self.pc = self.effective(mode)
            return
        self.pc = self.fetch16()

    @override
    def op_brk(self, mode: str) -> None:
        super().op_brk(mode)
        self.d = False

    @override
    def op_nop(self, mode: str) -> None:
        for _ in range(MODE_SIZE[mode]):
            self.fetch8()

    def op_bra(self, mode: str) -> None:
        self.branch(True)

    def op_stz(self, mode: str) -> None:
        self.write8(self.effective(mode), 0x00)

    def op_tsb(self, mode: str) -> None:
        address = self.effective(mode)
        value = self.read8(address)
        self.z = (self.a & value) == 0
        self.write8(address, value | self.a)

    def op_trb(self, mode: str) -> None:
        address = self.effective(mode)
        value = self.read8(address)
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
        self.x = self.pull8()
        self.set_nz(self.x)

    def op_ply(self, mode: str) -> None:
        self.y = self.pull8()
        self.set_nz(self.y)

    def op_stp(self, mode: str) -> None:
        self.stopped = True

    def op_wai(self, mode: str) -> None:
        self.waiting = True

    def modify_bit(self, bit: int, set_it: bool) -> None:
        address = self.effective("zeroPage")
        value = self.read8(address)
        self.write8(address, value | (1 << bit) if set_it else value & ~(1 << bit) & 0xFF)

    def branch_on_bit(self, bit: int, wanted: bool) -> None:
        value = self.read8(self.effective("zeroPage"))
        self.branch(bool(value & (1 << bit)) == wanted)


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
