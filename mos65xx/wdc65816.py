from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import opcodes65816 as wdc65816
from .errors import InsideInstruction, RunLimit, Stopped, UnsupportedError, Waiting
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
BREAK_FLAG = 0x10
CYCLES_PER_MOVE = 7
PARTIAL_LIMIT = 4

NATIVE_VECTORS = {"irq": IRQ_VECTOR, "nmi": NMI_VECTOR, "abort": ABORT_VECTOR}
EMULATION_VECTORS = {
    "irq": EMULATION_IRQ_VECTOR,
    "nmi": EMULATION_NMI_VECTOR,
    "abort": EMULATION_ABORT_VECTOR,
}

ALWAYS_INDEXES = frozenset(
    {"sta", "stx", "sty", "stz", "asl", "lsr", "rol", "ror", "inc", "dec", "trb", "tsb"}
)

BANK_ZERO_MODES = frozenset({"direct", "directX", "directY", "stack"})


HALTED_PINS = "--------"


RESET_VECTOR = 0x00FFFC

RESET_CYCLES = 8

VECTOR_CYCLES = 2


class Cpu:
    __slots__ = (
        "_emulation",
        "_inside",
        "_open",
        "_resetting",
        "_s",
        "_unsampled",
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

        self.irq_line = False

        self.nmi_line = False

        self.nmi_seen = False

        self.on_cycle: Callable[[], None] | None = None
        self._open = False
        self._inside = False
        self._resetting = False
        self._unsampled = False

        self.trace: list[tuple[int | None, int | None, str]] | None = None
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
        self._resetting = True
        try:
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
        finally:
            self._resetting = False
        self.close_cycle()
        return self

    def status(self) -> int:
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
        if self.trace is not None:
            self.trace.append((None, None, HALTED_PINS))
        self.spend()

    def held(self) -> bool:
        return self.stopped or self.waiting

    def held_cycle(self) -> None:
        self.halt_cycle()
        self.close_cycle()

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

    def read8(self, address: int, data: bool = True, program: bool = False) -> int:
        self.close_cycle()
        self.await_ready()
        found = self.memory.read8(address & self.address_mask) & 0xFF
        assert isinstance(found, int)
        if self.trace is not None:
            self.trace.append(
                (address & self.address_mask, found, self.pins(data, program, self.pulling, False))
            )
        self.spend()
        if not (self._inside or self._resetting):
            self.close_cycle()
        return found

    def write8(self, address: int, value: int) -> None:
        self.close_cycle()
        self.await_ready(write=True)
        self.memory.write8(address & self.address_mask, value & 0xFF)
        if self.trace is not None:
            self.trace.append(
                (address & self.address_mask, value & 0xFF, self.pins(True, False, False, True))
            )
        self.spend()
        if not (self._inside or self._resetting):
            self.close_cycle()

    def internal(self, address: int, write: bool = False, value: int | None = None) -> None:
        if self.trace is not None:
            self.trace.append(
                (address & self.address_mask, value, self.pins(False, False, False, write))
            )
        self.spend()

    def opcode8(self) -> int:
        value = self.read8((self.pb << 16) | self.pc, data=True, program=True)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def vector16(self, address: int) -> int:
        self.pulling = True
        try:
            return self.read8(address) | (self.read8(address + 1) << 8)
        finally:
            self.pulling = False

    def read16(self, address: int) -> int:
        return self.read8(address) | (self.read8(address + 1) << 8)

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
        self.push8((value >> 8) & 0xFF)
        self.push8(value & 0xFF)

    def pull16(self) -> int:
        return self.pull8() | (self.pull8() << 8)

    def pull_flat(self, width: int) -> int:
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
        if not self.emulation:
            self.push16(value)
            return
        base = self._s
        self.write8(base, (value >> 8) & 0xFF)
        self.write8((base - 1) & 0xFFFF, value & 0xFF)
        self.s = (base - 2) & 0xFFFF

    def pull16_flat(self) -> int:
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
        return self.emulation and (self.d & 0xFF) == 0

    def direct(self, offset: int) -> int:
        if self.page_wraps:
            return (self.d & 0xFF00) | (offset & 0xFF)
        return (self.d + offset) & 0xFFFF

    def read_pointer(self, address: int, width: int, wraps_in_page: bool = False) -> int:
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
        return (self.pb << 16) | ((self.pc - 1) & 0xFFFF)

    def at_pc(self) -> int:
        return (self.pb << 16) | self.pc

    def unaligned(self) -> None:
        if self.d & 0xFF:
            self.internal(self.here())

    def crosses(self, base: int, index: int) -> bool:
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
            return (self.db << 16) | self.read_pointer(pointer, 2, wraps_in_page=True)
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
        offset = self.fetch8()
        self.internal(self.here())
        pointer = (self.s + offset) & 0xFFFF
        base = self.read_pointer(pointer, 2)
        self.internal((pointer + 1) & 0xFFFF)
        return ((self.db << 16) | base) + self.y

    def indexed(self, base: int, index: int, mnemonic: str) -> int:
        return self.indexed_from(base, index, mnemonic)

    def indexed_from(self, base: int, index: int, mnemonic: str) -> int:
        if mnemonic in ALWAYS_INDEXES or self.crosses(base, index):
            self.internal((self.db << 16) | (base & 0xFF00) | ((base + index) & 0xFF))
        return ((self.db << 16) | base) + index

    def operand(self, mode: str, mnemonic: str) -> int:
        wide = self.wide_for(mnemonic)
        if mode in IMMEDIATE_MODES:
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
        started = self.cycles
        if self.stopped:
            raise Stopped("the processor has been stopped")
        if self.waiting:
            raise Waiting("the processor is waiting for an interrupt")
        self.steps += 1
        self._inside = True
        try:
            opcode = self.opcode8()
            mnemonic, mode = OPCODES[opcode]
            if not wdc65816.MODE_SIZE[mode]:
                self.internal(self.at_pc())
            getattr(self, f"op_{mnemonic}")(mode)
        finally:
            self._inside = False
        self._unsampled = True
        try:
            self.close_cycle()
        finally:
            self._unsampled = False
        self.sample_pins()
        self.close_cycle()
        return self.cycles - started

    def call(self, address: int, limit: int | None = None) -> Cpu:
        self.pb = (address >> 16) & 0xFF
        self.pc = address & 0xFFFF
        depth = 0
        taken = 0
        while True:
            mnemonic = OPCODES[self.read8((self.pb << 16) | self.pc)][0]
            if mnemonic in ("rts", "rtl"):
                if depth == 0:
                    return self
                depth -= 1
            elif mnemonic in ("jsr", "jsl"):
                depth += 1
            self.step()
            taken += 1
            if limit is not None and taken >= limit:
                raise RunLimit(f"gave up after {taken} instructions at ${self.pc:04X}")

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
        self.op_jml(mode)

    def op_jml(self, mode: str) -> None:
        target = self.fetch24() if mode == "absoluteLong" else self.read_pointer(self.fetch16(), 3)
        self.pb = (target >> 16) & 0xFF
        self.pc = target & 0xFFFF

    def op_jsr(self, mode: str) -> None:
        if mode == "absolutePC":
            target = self.fetch16()
            self.internal(self.here())
            self.push16((self.pc - 1) & 0xFFFF)
            self.pc = target
            return
        low = self.fetch8()
        self.push16_flat(self.pc)
        high = self.fetch8()
        self.internal(self.here())
        pointer = ((low | (high << 8)) + self.x) & 0xFFFF
        self.pc = self.read_pointer((self.pb << 16) | pointer, 2)

    def op_jsl(self, mode: str) -> None:
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
        self.internal(self.at_pc())
        pulled = self.pull8()
        self.pc = self.pull16()
        if not self.emulation:
            self.pb = self.pull8()
        self.set_status(pulled)

    def _software_interrupt(self, native_vector: int, emulation_vector: int) -> None:
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
        self.clear_banks_for_interrupt()
        self.pc = self.vector16(vector)

    def clear_banks_for_interrupt(self) -> None:
        self.pb = 0x00
        if self._emulation:
            self.db = 0x00

    def interrupt(self, kind: str) -> bool:
        if self.stopped:
            return False
        self.waiting = False
        if self.masked(kind):
            return False
        self._inside = True
        try:
            self.enter(kind)
        finally:
            self._inside = False
        self.close_cycle()
        return True

    def enter(self, kind: str) -> None:
        vector = (EMULATION_VECTORS if self.emulation else NATIVE_VECTORS)[kind]
        if not self.emulation:
            self.push8(self.pb)
        self.push16(self.pc)
        self.push8(self.status() & ~BREAK_FLAG if self.emulation else self.status())
        self.irq_disable = True
        self.decimal = False
        self.clear_banks_for_interrupt()
        self.pc = self.vector16(vector)

    def await_ready(self, write: bool = False) -> None:
        while not self.ready_line:
            self.spend()
            self.close_cycle()

    def sampled_line(self) -> str | None:
        if self.nmi_line and not self.nmi_seen:
            return "nmi"
        if self.irq_line:
            return "irq"
        return None

    def sample_pins(self) -> bool:
        line = self.sampled_line()
        self.nmi_seen = self.nmi_line
        if line == "nmi":
            self.nmi()
            return True
        if line == "irq":
            return self.irq()
        return False

    def masked(self, kind: str) -> bool:
        return kind == "irq" and self.irq_disable

    def entry_pending(self) -> str | None:
        line = self.sampled_line() if self._unsampled else None
        if line is None or self.stopped or self.masked(line):
            return None
        return line

    def refuse_inside(self, line: str) -> None:
        if self._inside:
            raise InsideInstruction(line)
        pending = self.entry_pending()
        if pending is not None:
            raise InsideInstruction(line, pending)

    def irq(self) -> bool:
        self.refuse_inside("irq")
        return self.interrupt("irq")

    def nmi(self) -> bool:
        self.refuse_inside("nmi")
        return self.interrupt("nmi")

    def abort(self) -> bool:
        return self.interrupt("abort")

    def op_brk(self, mode: str) -> None:
        self._software_interrupt(BREAK_VECTOR, EMULATION_BREAK_VECTOR)

    def op_cop(self, mode: str) -> None:
        self._software_interrupt(COP_VECTOR, EMULATION_COP_VECTOR)

    def _block_move(self, direction: int) -> None:
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
        self.internal((self.pb << 16) | self.pc)
        self.pc = (self.pc + 1) & 0xFFFF

    def op_stp(self, mode: str) -> None:
        self.internal(self.at_pc())
        self.stopped = True

    def op_wai(self, mode: str) -> None:
        self.internal(self.at_pc())
        self.waiting = True
