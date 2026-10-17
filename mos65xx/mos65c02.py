from __future__ import annotations

from typing import Any, override

from .errors import Waiting
from .mos6502 import MODIFY, READ, STACK_PAGE, WRITE
from .mos6502 import Cpu as Nmos
from .opcodes65c02 import CMOS

SINGLE_CYCLE_NOPS = frozenset(
    opcode for opcode in range(0x100) if opcode & 0x0F in (0x03, 0x0B)
) - {0xCB}

SHORTCUT_MODIFIES = frozenset({"asl", "lsr", "rol", "ror"})


class Cpu(Nmos):
    __slots__ = ("waiting",)

    @override
    def __init__(self, memory: Any, table: Any = CMOS, **options: Any) -> None:
        self.waiting = False
        super().__init__(memory, table=table, **options)
        self.model = "65c02"

    @override
    def reset(self, seed: int | None = None) -> Nmos:
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
        return READ if mnemonic in SHORTCUT_MODIFIES else MODIFY

    @override
    def spare_for_index(self, base: int, target: int) -> int:
        return (self.pc - 1) & 0xFFFF

    @override
    def settle(self, address: int, held: int) -> None:
        self.dead(address)

    @override
    def idles_after_opcode(self, opcode: int, mnemonic: str, mode: str) -> bool:
        if mnemonic == "nop" and mode == "implied":
            return opcode not in SINGLE_CYCLE_NOPS
        return super().idles_after_opcode(opcode, mnemonic, mode)

    def spent_on_decimal(self, mode: str) -> int:
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
    def nmi_takes_over_break(self) -> bool:
        return False

    @override
    def interrupt(self, vector: int) -> None:
        super().interrupt(vector)
        self.d = False

    @override
    def irq(self) -> bool:
        self.waiting = False
        return super().irq()

    @override
    def nmi(self) -> None:
        self.waiting = False
        super().nmi()

    @override
    def op_nop(self, mode: str) -> None:
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
        if self.waiting:
            raise Waiting("the processor is waiting for an interrupt")
        return super().step()

    @override
    def await_ready(self, write: bool = False) -> None:
        self.stalls_on_write = True
        super().await_ready(write)

    @override
    def held(self) -> bool:
        return self.stopped or self.waiting

    @override
    def held_cycle(self) -> None:
        self.spend()

    def modify_bit(self, bit: int, set_it: bool) -> None:
        address = self.effective("zeroPage")
        value = self.read8(address)
        self.settle(address, value)
        self.write8(address, value | (1 << bit) if set_it else value & ~(1 << bit) & 0xFF)

    def branch_on_bit(self, bit: int, wanted: bool) -> None:
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
