"""The CMOS tables, written as what they changed rather than as a second copy.

The CMOS part removed every undocumented instruction the NMOS part had and spent
the freed opcodes on real ones: a pointer mode with no index, a store of zero, a
branch that always takes, a test-and-set and a test-and-clear, pushes and pulls
for both index registers, and an increment of the accumulator on its own. What it
did not spend, it filled with no-operations of stated length, so that a program
running off the end of its code advances predictably instead of executing rubbish.

Three parts shipped and they are not the same part. The base CMOS design has none
of the bit instructions. Rockwell added thirty two of them, eight each of set,
clear, branch-if-set and branch-if-clear, in the two opcode columns the base
design had left as no-operations. WDC took Rockwell's and added two more that stop
the processor or make it wait for an interrupt.

Keeping all three matters because a machine has whichever one it was built with. A
program written for the Rockwell part running on the base part meets a
no-operation where it expected to clear a bit, and nothing reports it.

The tables are built by naming what changed against the NMOS table rather than by
writing two hundred and fifty six entries again. The difference is the interesting
part, and a second literal would hide it while inviting a transcription error.
"""

from __future__ import annotations

from typing import Any

from .opcodes6502 import NMOS

ONE_BYTE = "implied"
TWO_BYTE = "immediate"
THREE_BYTE = "absolute"
INDEXED_THREE_BYTE = "absoluteX"
"""The mode names carry the length, and for the opcodes nobody documented they
carry the shape too: the pair of columns the base part left empty behave as the
indexed forms of the two beside them, which is what the recorded cycles show and
what decides how many of them an instruction spends."""

CHANGED = {
    0x00: ("brk", "implied"),
    0x02: ("nop", TWO_BYTE),
    0x03: ("nop", ONE_BYTE),
    0x04: ("tsb", "zeroPage"),
    0x07: ("nop", "zeroPage"),
    0x0B: ("nop", ONE_BYTE),
    0x0C: ("tsb", "absolute"),
    0x0F: ("nop", THREE_BYTE),
    0x12: ("ora", "zeroPageIndirect"),
    0x13: ("nop", ONE_BYTE),
    0x14: ("trb", "zeroPage"),
    0x17: ("nop", "zeroPageX"),
    0x1A: ("inc", "accumulator"),
    0x1B: ("nop", ONE_BYTE),
    0x1C: ("trb", "absolute"),
    0x1F: ("nop", INDEXED_THREE_BYTE),
    0x22: ("nop", TWO_BYTE),
    0x23: ("nop", ONE_BYTE),
    0x27: ("nop", "zeroPage"),
    0x2B: ("nop", ONE_BYTE),
    0x2F: ("nop", THREE_BYTE),
    0x32: ("and", "zeroPageIndirect"),
    0x33: ("nop", ONE_BYTE),
    0x34: ("bit", "zeroPageX"),
    0x37: ("nop", "zeroPageX"),
    0x3A: ("dec", "accumulator"),
    0x3B: ("nop", ONE_BYTE),
    0x3C: ("bit", "absoluteX"),
    0x3F: ("nop", INDEXED_THREE_BYTE),
    0x42: ("nop", TWO_BYTE),
    0x43: ("nop", ONE_BYTE),
    0x47: ("nop", "zeroPage"),
    0x4B: ("nop", ONE_BYTE),
    0x4F: ("nop", THREE_BYTE),
    0x52: ("eor", "zeroPageIndirect"),
    0x53: ("nop", ONE_BYTE),
    0x57: ("nop", "zeroPageX"),
    0x5A: ("phy", "implied"),
    0x5B: ("nop", ONE_BYTE),
    0x5F: ("nop", INDEXED_THREE_BYTE),
    0x62: ("nop", TWO_BYTE),
    0x63: ("nop", ONE_BYTE),
    0x64: ("stz", "zeroPage"),
    0x67: ("nop", "zeroPage"),
    0x6B: ("nop", ONE_BYTE),
    0x6F: ("nop", THREE_BYTE),
    0x72: ("adc", "zeroPageIndirect"),
    0x73: ("nop", ONE_BYTE),
    0x74: ("stz", "zeroPageX"),
    0x77: ("nop", "zeroPageX"),
    0x7A: ("ply", "implied"),
    0x7B: ("nop", ONE_BYTE),
    0x7C: ("jmp", "indirectX"),
    0x7F: ("nop", INDEXED_THREE_BYTE),
    0x80: ("bra", "relative"),
    0x83: ("nop", ONE_BYTE),
    0x87: ("nop", "zeroPage"),
    0x89: ("bit", "immediate"),
    0x8B: ("nop", ONE_BYTE),
    0x8F: ("nop", THREE_BYTE),
    0x92: ("sta", "zeroPageIndirect"),
    0x93: ("nop", ONE_BYTE),
    0x97: ("nop", "zeroPageX"),
    0x9B: ("nop", ONE_BYTE),
    0x9C: ("stz", "absolute"),
    0x9E: ("stz", "absoluteX"),
    0x9F: ("nop", INDEXED_THREE_BYTE),
    0xA3: ("nop", ONE_BYTE),
    0xA7: ("nop", "zeroPage"),
    0xAB: ("nop", ONE_BYTE),
    0xAF: ("nop", THREE_BYTE),
    0xB2: ("lda", "zeroPageIndirect"),
    0xB3: ("nop", ONE_BYTE),
    0xB7: ("nop", "zeroPageX"),
    0xBB: ("nop", ONE_BYTE),
    0xBF: ("nop", INDEXED_THREE_BYTE),
    0xC3: ("nop", ONE_BYTE),
    0xC7: ("nop", "zeroPage"),
    0xCB: ("nop", ONE_BYTE),
    0xCF: ("nop", THREE_BYTE),
    0xD2: ("cmp", "zeroPageIndirect"),
    0xD3: ("nop", ONE_BYTE),
    0xD7: ("nop", "zeroPageX"),
    0xDA: ("phx", "implied"),
    0xDB: ("nop", "zeroPageX"),
    0xDF: ("nop", INDEXED_THREE_BYTE),
    0xE3: ("nop", ONE_BYTE),
    0xE7: ("nop", "zeroPage"),
    0xEB: ("nop", ONE_BYTE),
    0xEF: ("nop", THREE_BYTE),
    0xF2: ("sbc", "zeroPageIndirect"),
    0xF3: ("nop", ONE_BYTE),
    0xF7: ("nop", "zeroPageX"),
    0xFA: ("plx", "implied"),
    0xFB: ("nop", ONE_BYTE),
    0xFF: ("nop", INDEXED_THREE_BYTE),
}


def _with(table: Any, changes: Any) -> Any:
    built = list(table)
    for opcode, entry in changes.items():
        built[opcode] = entry
    return tuple(built)


CMOS = _with(NMOS, CHANGED)

BIT_INSTRUCTIONS = {}
for _bit in range(8):
    BIT_INSTRUCTIONS[0x07 + _bit * 0x10] = (f"rmb{_bit}", "zeroPage")
    BIT_INSTRUCTIONS[0x87 + _bit * 0x10] = (f"smb{_bit}", "zeroPage")
    BIT_INSTRUCTIONS[0x0F + _bit * 0x10] = (f"bbr{_bit}", "relativeBit")
    BIT_INSTRUCTIONS[0x8F + _bit * 0x10] = (f"bbs{_bit}", "relativeBit")

ROCKWELL = _with(CMOS, BIT_INSTRUCTIONS)

WDC = _with(ROCKWELL, {0xCB: ("wai", "implied"), 0xDB: ("stp", "implied")})

TABLES = {"65c02": CMOS, "rockwell": ROCKWELL, "wdc": WDC}
