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
variant in the Famicom has the adder wired without it, so setting the flag there
changes nothing, which is why the model decides and not the flag.

Nothing starts clean. Registers and memory hold arbitrary but reproducible values
after a reset, because the hardware defines only the program counter, and a core
that clears the rest makes a read of something never written look deliberate.
"""

from .memory import UNSET_SEED, scramble
from .opcodes6502 import NMOS

STEP_LIMIT = 2_000_000

RESET_VECTOR = 0xFFFC
BREAK_VECTOR = 0xFFFE
NMI_VECTOR = 0xFFFA

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


class StepLimit(Exception):
    pass


class UnsupportedError(Exception):
    pass


class Stopped(Exception):
    pass


class Cpu:
    """One 6502, holding whatever it held until something writes to it."""

    def __init__(
        self,
        memory,
        step_limit=STEP_LIMIT,
        seed=UNSET_SEED,
        reset=True,
        decimal=True,
        table=NMOS,
    ):
        self.memory = memory
        self.step_limit = step_limit
        self.decimal = decimal
        self.table = table
        self.steps = 0
        self.stopped = False
        self.model = "6502"

        self.a = self.x = self.y = 0x00
        self.s = 0xFD
        self.pc = 0x0000
        self.n = self.v = self.d = self.z = self.c = self.b = False
        self.i = True

        if reset:
            self.reset(seed)

    def reset(self, seed=UNSET_SEED):
        """What a reset actually defines, and nothing beyond it.

        The vector decides where execution starts and the interrupt disable is
        set. Everything else keeps whatever the silicon powered up holding, so it
        is scrambled from a seed rather than cleared.
        """
        undefined = scramble(6, seed)
        self.a, self.x, self.y = undefined[0], undefined[1], undefined[2]
        self.s = undefined[3]
        self.set_status(undefined[4])
        self.i = True
        self.stopped = False
        self.steps = 0
        self.pc = self.read16(RESET_VECTOR)
        return self

    def status(self):
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

    def set_status(self, value):
        """Take a status byte, keeping only the bits the register actually has."""
        self.b = bool(value & FLAG_B)
        self.n = bool(value & FLAG_N)
        self.v = bool(value & FLAG_V)
        self.d = bool(value & FLAG_D)
        self.i = bool(value & FLAG_I)
        self.z = bool(value & FLAG_Z)
        self.c = bool(value & FLAG_C)

    def read8(self, address):
        return self.memory.read8(address & 0xFFFF) & 0xFF

    def write8(self, address, value):
        self.memory.write8(address & 0xFFFF, value & 0xFF)

    def read16(self, address):
        return self.read8(address) | (self.read8(address + 1) << 8)

    def read16_in_page(self, address):
        """A pointer read the way the part reads one, without leaving its page."""
        high = (address & 0xFF00) | ((address + 1) & 0x00FF)
        return self.read8(address) | (self.read8(high) << 8)

    def read16_in_zero_page(self, address):
        return self.read8(address & 0xFF) | (self.read8((address + 1) & 0xFF) << 8)

    def fetch8(self):
        value = self.read8(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def fetch16(self):
        low = self.fetch8()
        return low | (self.fetch8() << 8)

    def push8(self, value):
        self.write8(STACK_PAGE | self.s, value)
        self.s = (self.s - 1) & 0xFF

    def pull8(self):
        self.s = (self.s + 1) & 0xFF
        return self.read8(STACK_PAGE | self.s)

    def push16(self, value):
        self.push8((value >> 8) & 0xFF)
        self.push8(value & 0xFF)

    def pull16(self):
        low = self.pull8()
        return low | (self.pull8() << 8)

    def set_nz(self, value):
        self.z = (value & 0xFF) == 0
        self.n = bool(value & 0x80)

    def effective(self, mode):
        """Where an instruction's operand lives, by the rules of its mode."""
        if mode == "zeroPage":
            return self.fetch8()
        if mode == "zeroPageX":
            return (self.fetch8() + self.x) & 0xFF
        if mode == "zeroPageY":
            return (self.fetch8() + self.y) & 0xFF
        if mode == "absolute":
            return self.fetch16()
        if mode == "absoluteX":
            return (self.fetch16() + self.x) & 0xFFFF
        if mode == "absoluteY":
            return (self.fetch16() + self.y) & 0xFFFF
        if mode == "indexedIndirectX":
            return self.read16_in_zero_page((self.fetch8() + self.x) & 0xFF)
        if mode == "indirectIndexedY":
            return (self.read16_in_zero_page(self.fetch8()) + self.y) & 0xFFFF
        if mode == "zeroPageIndirect":
            return self.read16_in_zero_page(self.fetch8())
        raise UnsupportedError(f"{mode} has no effective address")

    def operand(self, mode):
        if mode == "immediate":
            return self.fetch8()
        if mode == "accumulator":
            return self.a
        return self.read8(self.effective(mode))

    def unindexed_base(self, mode):
        """The address before indexing, which the unstable stores need."""
        base = self.fetch16()
        index = self.x if mode == "absoluteX" else self.y
        return base, (base + index) & 0xFFFF

    def add_with_carry(self, value):
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

    def subtract_with_carry(self, value):
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

    def compare(self, register, value):
        result = (register - value) & 0xFF
        self.c = register >= value
        self.set_nz(result)

    def branch(self, taken):
        offset = self.fetch8()
        if not taken:
            return
        if offset & 0x80:
            offset -= 0x100
        self.pc = (self.pc + offset) & 0xFFFF

    def step(self):
        if self.stopped:
            raise Stopped("the processor has been stopped")
        self.steps += 1
        if self.steps > self.step_limit:
            raise StepLimit(f"stopped after {self.steps} steps at ${self.pc:04X}")
        opcode = self.fetch8()
        mnemonic, mode = self.table[opcode]
        handler = getattr(self, f"op_{mnemonic}", None)
        if handler is None:
            raise UnsupportedError(f"{mnemonic} is not implemented")
        handler(mode)

    def run_until(self, predicate):
        while not predicate(self):
            self.step()
        return self

    def call(self, address):
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

    def op_lda(self, mode):
        self.a = self.operand(mode)
        self.set_nz(self.a)

    def op_ldx(self, mode):
        self.x = self.operand(mode)
        self.set_nz(self.x)

    def op_ldy(self, mode):
        self.y = self.operand(mode)
        self.set_nz(self.y)

    def op_sta(self, mode):
        self.write8(self.effective(mode), self.a)

    def op_stx(self, mode):
        self.write8(self.effective(mode), self.x)

    def op_sty(self, mode):
        self.write8(self.effective(mode), self.y)

    def op_tax(self, mode):
        self.x = self.a
        self.set_nz(self.x)

    def op_tay(self, mode):
        self.y = self.a
        self.set_nz(self.y)

    def op_txa(self, mode):
        self.a = self.x
        self.set_nz(self.a)

    def op_tya(self, mode):
        self.a = self.y
        self.set_nz(self.a)

    def op_tsx(self, mode):
        self.x = self.s
        self.set_nz(self.x)

    def op_txs(self, mode):
        self.s = self.x

    def op_pha(self, mode):
        self.push8(self.a)

    def op_php(self, mode):
        self.push8(self.status() | FLAG_B)

    def op_pla(self, mode):
        self.a = self.pull8()
        self.set_nz(self.a)

    def op_plp(self, mode):
        self.set_status(self.pull8())
        self.b = False

    def op_and(self, mode):
        self.a &= self.operand(mode)
        self.set_nz(self.a)

    def op_ora(self, mode):
        self.a |= self.operand(mode)
        self.set_nz(self.a)

    def op_eor(self, mode):
        self.a ^= self.operand(mode)
        self.set_nz(self.a)

    def op_bit(self, mode):
        value = self.operand(mode)
        self.z = (self.a & value) == 0
        self.n = bool(value & 0x80)
        self.v = bool(value & 0x40)

    def op_adc(self, mode):
        self.add_with_carry(self.operand(mode))

    def op_sbc(self, mode):
        self.subtract_with_carry(self.operand(mode))

    def op_cmp(self, mode):
        self.compare(self.a, self.operand(mode))

    def op_cpx(self, mode):
        self.compare(self.x, self.operand(mode))

    def op_cpy(self, mode):
        self.compare(self.y, self.operand(mode))

    def op_inc(self, mode):
        address = self.effective(mode)
        value = (self.read8(address) + 1) & 0xFF
        self.write8(address, value)
        self.set_nz(value)

    def op_dec(self, mode):
        address = self.effective(mode)
        value = (self.read8(address) - 1) & 0xFF
        self.write8(address, value)
        self.set_nz(value)

    def op_inx(self, mode):
        self.x = (self.x + 1) & 0xFF
        self.set_nz(self.x)

    def op_iny(self, mode):
        self.y = (self.y + 1) & 0xFF
        self.set_nz(self.y)

    def op_dex(self, mode):
        self.x = (self.x - 1) & 0xFF
        self.set_nz(self.x)

    def op_dey(self, mode):
        self.y = (self.y - 1) & 0xFF
        self.set_nz(self.y)

    def shift_left(self, value):
        self.c = bool(value & 0x80)
        result = (value << 1) & 0xFF
        self.set_nz(result)
        return result

    def shift_right(self, value):
        self.c = bool(value & 0x01)
        result = value >> 1
        self.set_nz(result)
        return result

    def rotate_left(self, value):
        carry = 1 if self.c else 0
        self.c = bool(value & 0x80)
        result = ((value << 1) | carry) & 0xFF
        self.set_nz(result)
        return result

    def rotate_right(self, value):
        carry = 0x80 if self.c else 0
        self.c = bool(value & 0x01)
        result = (value >> 1) | carry
        self.set_nz(result)
        return result

    def read_modify_write(self, mode, transform):
        if mode == "accumulator":
            self.a = transform(self.a)
            return None, self.a
        address = self.effective(mode)
        value = transform(self.read8(address))
        self.write8(address, value)
        return address, value

    def op_asl(self, mode):
        self.read_modify_write(mode, self.shift_left)

    def op_lsr(self, mode):
        self.read_modify_write(mode, self.shift_right)

    def op_rol(self, mode):
        self.read_modify_write(mode, self.rotate_left)

    def op_ror(self, mode):
        self.read_modify_write(mode, self.rotate_right)

    def op_jmp(self, mode):
        if mode == "indirect":
            self.pc = self.read16_in_page(self.fetch16())
            return
        self.pc = self.fetch16()

    def op_jsr(self, mode):
        low = self.fetch8()
        self.push16(self.pc)
        self.pc = (self.fetch8() << 8) | low

    def op_rts(self, mode):
        self.pc = (self.pull16() + 1) & 0xFFFF

    def op_rti(self, mode):
        self.set_status(self.pull8())
        self.b = False
        self.pc = self.pull16()

    def op_brk(self, mode):
        self.pc = (self.pc + 1) & 0xFFFF
        self.push16(self.pc)
        self.push8(self.status() | FLAG_B)
        self.i = True
        self.pc = self.read16(BREAK_VECTOR)

    def op_bpl(self, mode):
        self.branch(not self.n)

    def op_bmi(self, mode):
        self.branch(self.n)

    def op_bvc(self, mode):
        self.branch(not self.v)

    def op_bvs(self, mode):
        self.branch(self.v)

    def op_bcc(self, mode):
        self.branch(not self.c)

    def op_bcs(self, mode):
        self.branch(self.c)

    def op_bne(self, mode):
        self.branch(not self.z)

    def op_beq(self, mode):
        self.branch(self.z)

    def op_clc(self, mode):
        self.c = False

    def op_sec(self, mode):
        self.c = True

    def op_cli(self, mode):
        self.i = False

    def op_sei(self, mode):
        self.i = True

    def op_clv(self, mode):
        self.v = False

    def op_cld(self, mode):
        self.d = False

    def op_sed(self, mode):
        self.d = True

    def op_nop(self, mode):
        if mode not in ("implied", "accumulator"):
            self.operand(mode)

    def op_jam(self, mode):
        self.stopped = True

    def op_slo(self, mode):
        _, value = self.read_modify_write(mode, self.shift_left)
        self.a |= value
        self.set_nz(self.a)

    def op_rla(self, mode):
        _, value = self.read_modify_write(mode, self.rotate_left)
        self.a &= value
        self.set_nz(self.a)

    def op_sre(self, mode):
        _, value = self.read_modify_write(mode, self.shift_right)
        self.a ^= value
        self.set_nz(self.a)

    def op_rra(self, mode):
        _, value = self.read_modify_write(mode, self.rotate_right)
        self.add_with_carry(value)

    def op_sax(self, mode):
        self.write8(self.effective(mode), self.a & self.x)

    def op_lax(self, mode):
        self.a = self.x = self.operand(mode)
        self.set_nz(self.a)

    def op_dcp(self, mode):
        address = self.effective(mode)
        value = (self.read8(address) - 1) & 0xFF
        self.write8(address, value)
        self.compare(self.a, value)

    def op_isc(self, mode):
        address = self.effective(mode)
        value = (self.read8(address) + 1) & 0xFF
        self.write8(address, value)
        self.subtract_with_carry(value)

    def op_anc(self, mode):
        self.a &= self.fetch8()
        self.set_nz(self.a)
        self.c = self.n

    def op_alr(self, mode):
        self.a &= self.fetch8()
        self.a = self.shift_right(self.a)

    def op_arr(self, mode):
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

    def op_sbx(self, mode):
        value = self.fetch8()
        result = (self.a & self.x) - value
        self.c = result >= 0
        self.x = result & 0xFF
        self.set_nz(self.x)

    def op_las(self, mode):
        value = self.operand(mode) & self.s
        self.a = self.x = self.s = value
        self.set_nz(value)

    def op_ane(self, mode):
        self.a = (self.a | MAGIC) & self.x & self.fetch8()
        self.set_nz(self.a)

    def op_lxa(self, mode):
        self.a = self.x = (self.a | MAGIC) & self.fetch8()
        self.set_nz(self.a)

    def unstable_store(self, mode, register):
        if mode in ("absoluteX", "absoluteY"):
            base, address = self.unindexed_base(mode)
        else:
            base = self.read16_in_zero_page(self.fetch8())
            address = (base + self.y) & 0xFFFF
        value = register & (((base >> 8) + 1) & 0xFF)
        if (base & 0xFF00) != (address & 0xFF00):
            address = (address & 0x00FF) | (value << 8)
        self.write8(address, value)

    def op_sha(self, mode):
        self.unstable_store(mode, self.a & self.x)

    def op_shx(self, mode):
        self.unstable_store(mode, self.x)

    def op_shy(self, mode):
        self.unstable_store(mode, self.y)

    def op_tas(self, mode):
        self.s = self.a & self.x
        self.unstable_store(mode, self.s)
