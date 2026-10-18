from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .errors import NoSuchPin, RunLimit, Stopped, UnsupportedError
from .memory import UNSET_SEED, scramble
from .opcodes6502 import MODE_SIZE, NMOS

RESET_VECTOR = 0xFFFC

RESET_CYCLES = 8

VECTOR_CYCLES = 2
BREAK_VECTOR = 0xFFFE
NMI_VECTOR = 0xFFFA
IRQ_VECTOR = 0xFFFE

JAM_HIGH = 0xFFFF

JAM_LOW = 0xFFFE

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


class Cpu:
    __slots__ = (
        "_open",
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

        self.stalls_on_write = False

        self.irq_line = False

        self.nmi_line = False

        self.nmi_seen = False

        self.on_cycle: Callable[[], None] | None = None

        self._open = False

        self.trace: list[tuple[int, int, str]] | None = None

        self.power_on(seed)

    def power_on(self, seed: int = UNSET_SEED) -> None:
        undefined = scramble(7, seed)
        self.a, self.x, self.y = undefined[0], undefined[1], undefined[2]
        self.s = undefined[3]
        self.set_status(undefined[4])
        self.pc = undefined[5] | (undefined[6] << 8)

    def reset(self, seed: int = UNSET_SEED) -> Cpu:
        for _ in range(self.reset_cycles - VECTOR_CYCLES):
            self.spend()
        self.i = True
        self.stopped = False
        self.jammed = False
        self.steps = 0
        self.pc = self.read16(RESET_VECTOR)
        self.close_cycle()
        return self

    def status(self) -> int:
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
        self.b = bool(value & FLAG_B)
        self.n = bool(value & FLAG_N)
        self.v = bool(value & FLAG_V)
        self.d = bool(value & FLAG_D)
        self.i = bool(value & FLAG_I)
        self.z = bool(value & FLAG_Z)
        self.c = bool(value & FLAG_C)

    def spend(self) -> None:
        self.close_cycle()
        self._open = True

    def close_cycle(self) -> None:
        if not self._open:
            return
        self._open = False
        self.cycles += 1
        if self.on_cycle is not None:
            self.on_cycle()

    def read8(self, address: int) -> int:
        self.close_cycle()
        self.await_ready()
        address &= self.address_mask
        found = self.memory.read8(address) & 0xFF
        assert isinstance(found, int)
        if self.trace is not None:
            self.trace.append((address, found, "read"))
        self.spend()
        return found

    def write8(self, address: int, value: int) -> None:
        self.close_cycle()
        self.await_ready(write=True)
        address &= self.address_mask
        self.memory.write8(address, value & 0xFF)
        if self.trace is not None:
            self.trace.append((address, value & 0xFF, "write"))
        self.spend()

    def dead(self, address: int) -> None:
        self.read8(address)

    def read16(self, address: int) -> int:
        return self.read8(address) | (self.read8(address + 1) << 8)

    def read16_in_page(self, address: int) -> int:
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
        target = (base + index) & 0xFFFF
        uncorrected = (base & 0xFF00) | (target & 0x00FF)
        if kind != READ or uncorrected != target:
            self.dead(self.spare_for_index(base, target))
        return target

    def idles_after_opcode(self, opcode: int, mnemonic: str, mode: str) -> bool:
        return not MODE_SIZE[mode]

    def spare_for_index(self, base: int, target: int) -> int:
        return (base & 0xFF00) | (target & 0x00FF)

    def spare_in_page_zero(self, base: int) -> int:
        return base

    def modify_kind(self, mnemonic: str) -> str:
        return MODIFY

    def settle(self, address: int, held: int) -> None:
        self.write8(address, held)

    def operand(self, mode: str) -> int:
        if mode == "immediate":
            return self.fetch8()
        if mode == "accumulator":
            return self.a
        return self.read8(self.effective(mode))

    def unindexed_base(self, mode: str) -> tuple[int, int]:
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
        self.close_cycle()
        self.sample_pins()
        self.close_cycle()
        return self.cycles - started

    def run_for(self, cycles: int) -> int:
        spent = 0
        while spent < cycles:
            if self.held():
                self.held_cycle()
                spent += 1
            else:
                spent += self.step()
        return spent

    def run_until(self, predicate: Callable[[Cpu], bool], limit: int | None = None) -> Cpu:
        taken = 0
        while not predicate(self):
            self.step()
            taken += 1
            if limit is not None and taken >= limit:
                raise RunLimit(f"gave up after {taken} instructions at ${self.pc:04X}")
        return self

    def call(self, address: int, limit: int | None = None) -> Cpu:
        self.pc = address & 0xFFFF
        depth = 0
        taken = 0
        while True:
            mnemonic = self.table[self.read8(self.pc)][0]
            self.close_cycle()
            if mnemonic == "rts":
                if depth == 0:
                    return self
                depth -= 1
            elif mnemonic == "jsr":
                depth += 1
            self.step()
            taken += 1
            if limit is not None and taken >= limit:
                raise RunLimit(f"gave up after {taken} instructions at ${self.pc:04X}")

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
        hijacked = self.nmi_takes_over_break()
        self.nmi_seen = self.nmi_seen or hijacked
        self.pc = self.read16(NMI_VECTOR if hijacked else BREAK_VECTOR)

    def nmi_takes_over_break(self) -> bool:
        return "nmi" in self.package_pins and self.nmi_line and not self.nmi_seen

    def interrupt(self, vector: int) -> None:
        self.dead(self.pc)
        self.dead(self.pc)
        self.push16(self.pc)
        self.push8(self.status() & ~FLAG_B)
        self.i = True
        self.pc = self.read16(vector)

    def require(self, pin: str) -> None:
        if pin not in self.package_pins:
            raise NoSuchPin(
                f"the {self.model} has no {pin} pin; it brings out {', '.join(self.package_pins)}"
            )

    def await_ready(self, write: bool = False) -> None:
        if write and not self.stalls_on_write:
            return
        while not self.ready_line:
            self.spend()
            self.close_cycle()

    def sample_pins(self) -> bool:
        edge = self.nmi_line and not self.nmi_seen
        self.nmi_seen = self.nmi_line
        if edge:
            self.nmi()
            return True
        if self.irq_line:
            return self.irq()
        return False

    def irq(self) -> bool:
        self.require("irq")
        if self.i:
            return False
        self.interrupt(IRQ_VECTOR)
        self.close_cycle()
        return True

    def nmi(self) -> None:
        self.require("nmi")
        self.interrupt(NMI_VECTOR)
        self.close_cycle()

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
        self.read8(JAM_HIGH)
        self.read8(JAM_LOW)
        self.read8(JAM_LOW)
        self.jammed = True
        self.stopped = True

    def jam_cycle(self) -> None:
        self.read8(JAM_HIGH)

    def held(self) -> bool:
        return self.jammed

    def held_cycle(self) -> None:
        self.jam_cycle()
        self.close_cycle()

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
