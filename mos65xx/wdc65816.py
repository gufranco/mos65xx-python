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

from . import opcodes65816 as wdc65816
from .memory import ADDRESS_MASK, UNSET_SEED, Memory, SparseMemory, scramble

STEP_LIMIT = 2_000_000

OPCODES = wdc65816.OPCODES

__all__ = [
    "OPCODES",
    "STEP_LIMIT",
    "UNSET_SEED",
    "Cpu",
    "Memory",
    "SparseMemory",
    "StepLimit",
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
EMULATION_BREAK_VECTOR = 0x00FFFE
EMULATION_COP_VECTOR = 0x00FFF4
BREAK_FLAG = 0x10
CYCLES_PER_MOVE = 7

BANK_ZERO_MODES = frozenset({"direct", "directX", "directY", "stack"})
"""Modes whose address is in bank zero and wraps inside it."""


class StepLimit(Exception):
    pass


class UnsupportedError(Exception):
    pass


class Stopped(Exception):
    pass


RESET_VECTOR = 0x00FFFC


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
    """

    def __init__(self, memory, step_limit=STEP_LIMIT, seed=UNSET_SEED, reset=True):
        self.memory = memory
        self.step_limit = step_limit
        self.model = "65816"
        self.address_mask = ADDRESS_MASK
        self._emulation = False
        self._s = 0x01FF
        self.cycle_budget = None
        self.steps = 0
        self.stopped = False
        self.waiting = False
        if reset:
            self.reset(seed)
        else:
            self.a = self.x = self.y = 0x0000
            self.s = 0x01FF
            self.d = 0x0000
            self.db = self.pb = 0x00
            self.pc = 0x0000
            self.n = self.v = self.z = self.c = False
            self.m8 = self.x8 = True
            self.decimal = False
            self.irq_disable = True
            self.emulation = False

    @property
    def emulation(self):
        return self._emulation

    @emulation.setter
    def emulation(self, value):
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
    def s(self):
        return self._s

    @s.setter
    def s(self, value):
        value &= 0xFFFF
        self._s = 0x0100 | (value & 0xFF) if self._emulation else value

    def reset(self, seed=UNSET_SEED):
        """Put the processor where a reset puts it, undefined parts included."""
        undefined = scramble(8, seed)
        self.a = undefined[0] | (undefined[1] << 8)
        self.x = undefined[2]
        self.y = undefined[3]
        self.s = 0x0100 | undefined[4]

        self.d = 0x0000
        self.db = 0x00
        self.pb = 0x00

        self.emulation = True
        self.m8 = True
        self.x8 = True
        self.decimal = False
        self.irq_disable = True

        self.n = bool(undefined[5] & 0x80)
        self.v = bool(undefined[5] & 0x40)
        self.z = bool(undefined[5] & 0x02)
        self.c = bool(undefined[5] & 0x01)

        self.pc = self.read16(RESET_VECTOR)
        self.steps = 0
        self.stopped = False
        self.waiting = False

    def status(self):
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

    def set_status(self, value):
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

    def set_emulation(self, value):
        self.emulation = bool(value)
        if self.emulation:
            self.m8 = True
            self.x8 = True
            self.x &= 0xFF
            self.y &= 0xFF
            self.s = 0x0100 | (self.s & 0xFF)

    def read8(self, address):
        return self.memory.read8(address & self.address_mask) & 0xFF

    def write8(self, address, value):
        self.memory.write8(address & self.address_mask, value & 0xFF)

    def read16(self, address):
        return self.read8(address) | (self.read8(address + 1) << 8)

    def read24(self, address):
        return self.read16(address) | (self.read8(address + 2) << 16)

    def read_value(self, address, wide, mode=None):
        if not wide:
            return self.read8(address)
        return self.read8(address) | (self.read8(self.next_byte(address, mode)) << 8)

    def write_value(self, address, value, wide, mode=None):
        self.write8(address, value)
        if wide:
            self.write8(self.next_byte(address, mode), value >> 8)

    def next_byte(self, address, mode):
        """The address one byte on, wrapped the way that kind of access wraps.

        The direct page and the stack live in bank zero and stay there, so a word
        that starts at $FFFF finishes at $0000 rather than in bank one. An address
        formed against the data bank is not confined that way and carries into the
        next bank as any long address would.
        """
        if mode in BANK_ZERO_MODES:
            return (address & 0xFF0000) | ((address + 1) & 0xFFFF)
        return address + 1

    def fetch8(self):
        value = self.read8((self.pb << 16) | self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def fetch16(self):
        return self.fetch8() | (self.fetch8() << 8)

    def fetch24(self):
        return self.fetch16() | (self.fetch8() << 16)

    def push8(self, value):
        self.write8(self.s, value)
        if self.emulation:
            self.s = 0x0100 | ((self.s - 1) & 0xFF)
        else:
            self.s = (self.s - 1) & 0xFFFF

    def pull8(self):
        if self.emulation:
            self.s = 0x0100 | ((self.s + 1) & 0xFF)
        else:
            self.s = (self.s + 1) & 0xFFFF
        return self.read8(self.s)

    def push16(self, value):
        """Push a word the way the 6502 instructions do, folding into page one."""
        self.push8((value >> 8) & 0xFF)
        self.push8(value & 0xFF)

    def pull16(self):
        """Pull a word the way the 6502 instructions do."""
        return self.pull8() | (self.pull8() << 8)

    def push_flat(self, value, width):
        """Push several bytes without folding into page one, highest first."""
        if not self.emulation:
            for shift in range(8 * (width - 1), -1, -8):
                self.push8((value >> shift) & 0xFF)
            return
        base = self._s
        for step, shift in enumerate(range(8 * (width - 1), -1, -8)):
            self.write8((base - step) & 0xFFFF, (value >> shift) & 0xFF)
        self.s = (base - width) & 0xFFFF

    def pull_flat(self, width):
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

    def push16_flat(self, value):
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

    def pull16_flat(self):
        """Pull a word without folding into page one, as the push above does."""
        if not self.emulation:
            return self.pull16()
        base = self._s
        low = self.read8((base + 1) & 0xFFFF)
        high = self.read8((base + 2) & 0xFFFF)
        self.s = (base + 2) & 0xFFFF
        return low | (high << 8)

    def acc(self):
        return self.a & 0xFF if self.m8 else self.a & 0xFFFF

    def set_acc(self, value):
        if self.m8:
            self.a = (self.a & 0xFF00) | (value & 0xFF)
        else:
            self.a = value & 0xFFFF

    def set_nz(self, value, wide):
        mask = 0xFFFF if wide else 0xFF
        self.z = (value & mask) == 0
        self.n = bool(value & (0x8000 if wide else 0x80))

    def wide_for(self, mnemonic):
        if mnemonic in INDEX_WIDTH_OPS:
            return not self.x8
        return not self.m8

    @property
    def page_wraps(self):
        """Whether direct page addressing stays inside one page.

        In emulation mode with the low byte of the direct page register clear,
        the processor behaves as a 6502: a direct page address plus an index
        wraps within the page rather than carrying into the next one, and the two
        or three bytes of an indirect pointer wrap with it. Native mode, or any
        direct page not aligned to a page, carries normally.
        """
        return self.emulation and (self.d & 0xFF) == 0

    def direct(self, offset):
        """A direct page address, wrapped the way the current mode wraps it."""
        if self.page_wraps:
            return (self.d & 0xFF00) | (offset & 0xFF)
        return (self.d + offset) & 0xFFFF

    def read_pointer(self, address, width, wraps_in_page=False):
        """A pointer read out of the direct page or the stack.

        Two wraps apply and they are not the same. Every pointer stays inside the
        bank it started in, so one at $FFFF continues at $0000 of that same bank
        rather than crossing into the next.

        The narrower wrap, staying inside the direct page itself, applies only in
        emulation mode with the page aligned, and only to some modes. Which ones
        is not a rule worth inventing: the hardware is inconsistent, and with the
        same page and the same operand `AND [dp]` reads its bank byte past the end
        of the page while `ORA [dp],Y` wraps back to the start of it. The
        conformance suite decides that, per mode.
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

    def effective(self, mode, mnemonic):
        if mode == "direct":
            return self.direct(self.fetch8())
        if mode == "directX":
            return self.direct(self.fetch8() + self.x)
        if mode == "directY":
            return self.direct(self.fetch8() + self.y)
        if mode == "absolute":
            return (self.db << 16) | self.fetch16()
        if mode == "absoluteX":
            return ((self.db << 16) | self.fetch16()) + self.x
        if mode == "absoluteY":
            return ((self.db << 16) | self.fetch16()) + self.y
        if mode == "absoluteLong":
            return self.fetch24()
        if mode == "absoluteLongX":
            return self.fetch24() + self.x
        if mode == "indirect":
            return (self.db << 16) | self.read_pointer(self.direct(self.fetch8()), 2)
        if mode == "indexedIndirectX":
            pointer = self.direct(self.fetch8() + self.x)
            return (self.db << 16) | self.read_pointer(pointer, 2)
        if mode == "indirectIndexedY":
            pointer = self.direct(self.fetch8())
            return ((self.db << 16) | self.read_pointer(pointer, 2, wraps_in_page=True)) + self.y
        if mode == "indirectLong":
            return self.read_pointer(self.direct(self.fetch8()), 3)
        if mode == "indirectLongY":
            return self.read_pointer(self.direct(self.fetch8()), 3, wraps_in_page=True) + self.y
        if mode == "stack":
            return (self.s + self.fetch8()) & 0xFFFF
        if mode == "stackIndirect":
            pointer = (self.s + self.fetch8()) & 0xFFFF
            return ((self.db << 16) | self.read_pointer(pointer, 2)) + self.y
        raise UnsupportedError(f"{mnemonic} cannot use {mode}")

    def operand(self, mode, mnemonic):
        wide = self.wide_for(mnemonic)
        if mode in IMMEDIATE_MODES:
            if mode == "immediate":
                return self.fetch8()
            return self.fetch16() if wide else self.fetch8()
        return self.read_value(self.effective(mode, mnemonic), wide, mode)

    def add_with_carry(self, value):
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

    def subtract_with_carry(self, value):
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

    def compare(self, register, value, wide):
        mask = 0xFFFF if wide else 0xFF
        self.c = register >= value
        self.set_nz((register - value) & mask, wide)

    def step(self):
        if self.stopped:
            raise Stopped("the processor has been stopped")
        self.steps += 1
        if self.steps > self.step_limit:
            raise StepLimit(f"stopped after {self.steps} steps at ${self.pb:02X}:{self.pc:04X}")
        opcode = self.fetch8()
        mnemonic, mode = OPCODES[opcode]
        handler = getattr(self, f"op_{mnemonic}", None)
        if handler is None:
            raise UnsupportedError(f"{mnemonic} is not implemented")
        handler(mode)

    def call(self, address):
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

    def run_until(self, predicate):
        while not predicate(self):
            self.step()
        return self

    def op_lda(self, mode):
        value = self.operand(mode, "lda")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_ldx(self, mode):
        value = self.operand(mode, "ldx")
        self.x = value
        self.set_nz(value, not self.x8)

    def op_ldy(self, mode):
        value = self.operand(mode, "ldy")
        self.y = value
        self.set_nz(value, not self.x8)

    def op_sta(self, mode):
        self.write_value(self.effective(mode, "sta"), self.acc(), not self.m8, mode)

    def op_stx(self, mode):
        self.write_value(self.effective(mode, "stx"), self.x, not self.x8, mode)

    def op_sty(self, mode):
        self.write_value(self.effective(mode, "sty"), self.y, not self.x8, mode)

    def op_stz(self, mode):
        self.write_value(self.effective(mode, "stz"), 0, not self.m8, mode)

    def op_tax(self, mode):
        self.x = self.a & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_tay(self, mode):
        self.y = self.a & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.y, not self.x8)

    def op_txa(self, mode):
        self.set_acc(self.x)
        self.set_nz(self.acc(), not self.m8)

    def op_tya(self, mode):
        self.set_acc(self.y)
        self.set_nz(self.acc(), not self.m8)

    def op_txy(self, mode):
        self.y = self.x
        self.set_nz(self.y, not self.x8)

    def op_tyx(self, mode):
        self.x = self.y
        self.set_nz(self.x, not self.x8)

    def op_tsx(self, mode):
        self.x = self.s & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_txs(self, mode):
        self.s = 0x0100 | (self.x & 0xFF) if self.emulation else self.x & 0xFFFF

    def op_tas(self, mode):
        self.s = 0x0100 | (self.a & 0xFF) if self.emulation else self.a & 0xFFFF

    def op_tsa(self, mode):
        self.a = self.s & 0xFFFF
        self.set_nz(self.a, True)

    def op_tad(self, mode):
        self.d = self.a & 0xFFFF
        self.set_nz(self.d, True)

    def op_tda(self, mode):
        self.a = self.d & 0xFFFF
        self.set_nz(self.a, True)

    def op_xba(self, mode):
        self.a = ((self.a >> 8) | (self.a << 8)) & 0xFFFF
        self.set_nz(self.a & 0xFF, False)

    def op_xce(self, mode):
        carry = self.c
        self.c = self.emulation
        self.set_emulation(carry)

    def op_and(self, mode):
        value = self.acc() & self.operand(mode, "and")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_ora(self, mode):
        value = self.acc() | self.operand(mode, "ora")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_eor(self, mode):
        value = self.acc() ^ self.operand(mode, "eor")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_adc(self, mode):
        self.add_with_carry(self.operand(mode, "adc"))

    def op_sbc(self, mode):
        self.subtract_with_carry(self.operand(mode, "sbc"))

    def op_cmp(self, mode):
        self.compare(self.acc(), self.operand(mode, "cmp"), not self.m8)

    def op_cpx(self, mode):
        self.compare(self.x, self.operand(mode, "cpx"), not self.x8)

    def op_cpy(self, mode):
        self.compare(self.y, self.operand(mode, "cpy"), not self.x8)

    def op_bit(self, mode):
        value = self.operand(mode, "bit")
        wide = not self.m8
        self.z = (self.acc() & value) == 0
        if mode not in IMMEDIATE_MODES:
            self.n = bool(value & (0x8000 if wide else 0x80))
            self.v = bool(value & (0x4000 if wide else 0x40))

    def _read_modify_write(self, mode, mnemonic, operation):
        wide = not self.m8
        if mode == "implied":
            self.set_acc(operation(self.acc(), wide))
            return
        address = self.effective(mode, mnemonic)
        self.write_value(address, operation(self.read_value(address, wide), wide), wide)

    def op_asl(self, mode):
        def shift(value, wide):
            self.c = bool(value & (0x8000 if wide else 0x80))
            result = (value << 1) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "asl", shift)

    def op_lsr(self, mode):
        def shift(value, wide):
            self.c = bool(value & 1)
            result = value >> 1
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "lsr", shift)

    def op_rol(self, mode):
        def rotate(value, wide):
            carry = 1 if self.c else 0
            self.c = bool(value & (0x8000 if wide else 0x80))
            result = ((value << 1) | carry) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "rol", rotate)

    def op_ror(self, mode):
        def rotate(value, wide):
            carry = (0x8000 if wide else 0x80) if self.c else 0
            self.c = bool(value & 1)
            result = (value >> 1) | carry
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "ror", rotate)

    def op_inc(self, mode):
        def bump(value, wide):
            result = (value + 1) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "inc", bump)

    def op_dec(self, mode):
        def drop(value, wide):
            result = (value - 1) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "dec", drop)

    def op_trb(self, mode):
        wide = not self.m8
        address = self.effective(mode, "trb")
        value = self.read_value(address, wide)
        self.z = (value & self.acc()) == 0
        self.write_value(address, value & ~self.acc(), wide)

    def op_tsb(self, mode):
        wide = not self.m8
        address = self.effective(mode, "tsb")
        value = self.read_value(address, wide)
        self.z = (value & self.acc()) == 0
        self.write_value(address, value | self.acc(), wide)

    def op_inx(self, mode):
        self.x = (self.x + 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_iny(self, mode):
        self.y = (self.y + 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.y, not self.x8)

    def op_dex(self, mode):
        self.x = (self.x - 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_dey(self, mode):
        self.y = (self.y - 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.y, not self.x8)

    def op_clc(self, mode):
        self.c = False

    def op_sec(self, mode):
        self.c = True

    def op_cld(self, mode):
        self.decimal = False

    def op_sed(self, mode):
        self.decimal = True

    def op_cli(self, mode):
        self.irq_disable = False

    def op_sei(self, mode):
        self.irq_disable = True

    def op_clv(self, mode):
        self.v = False

    def op_rep(self, mode):
        self.set_status(self.status() & ~self.fetch8())

    def op_sep(self, mode):
        self.set_status(self.status() | self.fetch8())

    def op_pha(self, mode):
        self.push8(self.a) if self.m8 else self.push16(self.a)

    def op_pla(self, mode):
        value = self.pull8() if self.m8 else self.pull16()
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_phx(self, mode):
        self.push8(self.x) if self.x8 else self.push16(self.x)

    def op_plx(self, mode):
        self.x = self.pull8() if self.x8 else self.pull16()
        self.set_nz(self.x, not self.x8)

    def op_phy(self, mode):
        self.push8(self.y) if self.x8 else self.push16(self.y)

    def op_ply(self, mode):
        self.y = self.pull8() if self.x8 else self.pull16()
        self.set_nz(self.y, not self.x8)

    def op_php(self, mode):
        self.push8(self.status())

    def op_plp(self, mode):
        self.set_status(self.pull8())

    def op_phb(self, mode):
        self.push8(self.db)

    def op_plb(self, mode):
        self.db = self.pull8()
        self.set_nz(self.db, False)

    def op_phd(self, mode):
        self.push16_flat(self.d)

    def op_pld(self, mode):
        self.d = self.pull16_flat()
        self.set_nz(self.d, True)

    def op_phk(self, mode):
        self.push8(self.pb)

    def op_pea(self, mode):
        self.push16_flat(self.fetch16())

    def op_pei(self, mode):
        self.push16_flat(self.read_pointer(self.direct(self.fetch8()), 2, wraps_in_page=True))

    def op_per(self, mode):
        offset = self.fetch16()
        self.push16_flat((self.pc + self._signed16(offset)) & 0xFFFF)

    @staticmethod
    def _signed8(value):
        return value - 0x100 if value & 0x80 else value

    @staticmethod
    def _signed16(value):
        return value - 0x10000 if value & 0x8000 else value

    def _branch(self, taken):
        offset = self.fetch8()
        if taken:
            self.pc = (self.pc + self._signed8(offset)) & 0xFFFF

    def op_bra(self, mode):
        self._branch(True)

    def op_beq(self, mode):
        self._branch(self.z)

    def op_bne(self, mode):
        self._branch(not self.z)

    def op_bcs(self, mode):
        self._branch(self.c)

    def op_bcc(self, mode):
        self._branch(not self.c)

    def op_bmi(self, mode):
        self._branch(self.n)

    def op_bpl(self, mode):
        self._branch(not self.n)

    def op_bvs(self, mode):
        self._branch(self.v)

    def op_bvc(self, mode):
        self._branch(not self.v)

    def op_brl(self, mode):
        offset = self.fetch16()
        self.pc = (self.pc + self._signed16(offset)) & 0xFFFF

    def op_jmp(self, mode):
        if mode == "absolutePC":
            self.pc = self.fetch16()
            return
        if mode == "indirectPC":
            self.pc = self.read_pointer(self.fetch16(), 2)
            return
        if mode == "indirectX":
            pointer = (self.fetch16() + self.x) & 0xFFFF
            self.pc = self.read_pointer((self.pb << 16) | pointer, 2)
            return
        if mode == "indirectLongPC":
            self.op_jml(mode)  # $DC is the long form and loads the bank too
            return
        raise UnsupportedError(f"jmp cannot use {mode}")

    def op_jml(self, mode):
        if mode == "absoluteLong":
            target = self.fetch24()
        elif mode == "indirectLongPC":
            target = self.read_pointer(self.fetch16(), 3)
        else:
            raise UnsupportedError(f"jml cannot use {mode}")
        self.pb = (target >> 16) & 0xFF
        self.pc = target & 0xFFFF

    def op_jsr(self, mode):
        if mode == "absolutePC":
            target = self.fetch16()
        elif mode == "indirectX":
            pointer = (self.fetch16() + self.x) & 0xFFFF
            target = self.read_pointer((self.pb << 16) | pointer, 2)
        else:
            raise UnsupportedError(f"jsr cannot use {mode}")
        self.push16((self.pc - 1) & 0xFFFF)
        self.pc = target

    def op_jsl(self, mode):
        target = self.fetch24()
        self.push_flat((self.pb << 16) | ((self.pc - 1) & 0xFFFF), 3)
        self.pb = (target >> 16) & 0xFF
        self.pc = target & 0xFFFF

    def op_rts(self, mode):
        self.pc = (self.pull16() + 1) & 0xFFFF

    def op_rtl(self, mode):
        pulled = self.pull_flat(3)
        self.pc = ((pulled & 0xFFFF) + 1) & 0xFFFF
        self.pb = (pulled >> 16) & 0xFF

    def op_rti(self, mode):
        self.set_status(self.pull8())
        self.pc = self.pull16()
        if not self.emulation:
            self.pb = self.pull8()

    def _software_interrupt(self, native_vector, emulation_vector):
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
        self.pc = self.read16(vector)

    def op_brk(self, mode):
        self._software_interrupt(BREAK_VECTOR, EMULATION_BREAK_VECTOR)

    def op_cop(self, mode):
        self._software_interrupt(COP_VECTOR, EMULATION_COP_VECTOR)

    def _block_move(self, direction):
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
        """
        base = (self.pc - 1) & 0xFFFF
        destination = self.fetch8()
        source = self.fetch8()
        self.db = destination

        mask = 0xFF if self.x8 else 0xFFFF
        remaining = ((self.a + 1) & 0xFFFF) or 0x10000
        budget = self.cycle_budget
        whole = remaining if budget is None else min(remaining, max(0, budget) // CYCLES_PER_MOVE)

        for _ in range(whole):
            self.write8((destination << 16) | self.y, self.read8((source << 16) | self.x))
            self.x = (self.x + direction) & mask
            self.y = (self.y + direction) & mask
            self.a = (self.a - 1) & 0xFFFF

        if whole >= remaining:
            self.pc = (base + 3) & 0xFFFF
            return
        spent = whole * CYCLES_PER_MOVE
        self.pc = (base + min(max(0, budget - spent), 3)) & 0xFFFF

    def op_mvn(self, mode):
        self._block_move(1)

    def op_mvp(self, mode):
        self._block_move(-1)

    def op_nop(self, mode):
        return

    def op_wdm(self, mode):
        self.fetch8()

    def op_stp(self, mode):
        self.stopped = True

    def op_wai(self, mode):
        self.waiting = True
