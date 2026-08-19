"""The 6502 opcode table, documented and otherwise, and a disassembler for it.

Every one of the two hundred and fifty six opcodes decodes to something. Fifty
six mnemonics are the instruction set the datasheet describes. The rest were
never documented and were never meant to work, and programs relied on them
anyway, so a core that treats them as undefined is wrong for the machines that
shipped.

They fall into three groups. Some are two documented instructions sharing one
cycle sequence, which is why one of them is an arithmetic shift and an or:
entirely predictable, and widely used. Some do nothing but burn cycles and are
used for exactly that. And a handful are unstable, meaning the value they produce
depends on how the silicon settles rather than on anything the programmer chose.
Those are still here, modelled the way the conformance suite measures them,
because leaving them out would decode a real byte to nothing.

The CMOS parts that followed removed all of it. Where the NMOS part has an
undocumented instruction the CMOS part has either a new documented one or a
no-operation of a stated length, so the two tables differ in more places than
they agree and are kept separately rather than patched from one another.
"""

MODE_SIZE = {
    "implied": 0,
    "accumulator": 0,
    "immediate": 1,
    "zeroPage": 1,
    "zeroPageX": 1,
    "zeroPageY": 1,
    "relative": 1,
    "indexedIndirectX": 1,
    "indirectIndexedY": 1,
    "zeroPageIndirect": 1,
    "absolute": 2,
    "absoluteX": 2,
    "absoluteY": 2,
    "indirect": 2,
    "indirectX": 2,
    "relativeBit": 2,
}

READS_MEMORY = frozenset(
    {
        "zeroPage",
        "zeroPageX",
        "zeroPageY",
        "absolute",
        "absoluteX",
        "absoluteY",
        "indexedIndirectX",
        "indirectIndexedY",
        "zeroPageIndirect",
    }
)

NMOS = (
    ("brk", "implied"),
    ("ora", "indexedIndirectX"),
    ("jam", "implied"),
    ("slo", "indexedIndirectX"),
    ("nop", "zeroPage"),
    ("ora", "zeroPage"),
    ("asl", "zeroPage"),
    ("slo", "zeroPage"),
    ("php", "implied"),
    ("ora", "immediate"),
    ("asl", "accumulator"),
    ("anc", "immediate"),
    ("nop", "absolute"),
    ("ora", "absolute"),
    ("asl", "absolute"),
    ("slo", "absolute"),
    ("bpl", "relative"),
    ("ora", "indirectIndexedY"),
    ("jam", "implied"),
    ("slo", "indirectIndexedY"),
    ("nop", "zeroPageX"),
    ("ora", "zeroPageX"),
    ("asl", "zeroPageX"),
    ("slo", "zeroPageX"),
    ("clc", "implied"),
    ("ora", "absoluteY"),
    ("nop", "implied"),
    ("slo", "absoluteY"),
    ("nop", "absoluteX"),
    ("ora", "absoluteX"),
    ("asl", "absoluteX"),
    ("slo", "absoluteX"),
    ("jsr", "absolute"),
    ("and", "indexedIndirectX"),
    ("jam", "implied"),
    ("rla", "indexedIndirectX"),
    ("bit", "zeroPage"),
    ("and", "zeroPage"),
    ("rol", "zeroPage"),
    ("rla", "zeroPage"),
    ("plp", "implied"),
    ("and", "immediate"),
    ("rol", "accumulator"),
    ("anc", "immediate"),
    ("bit", "absolute"),
    ("and", "absolute"),
    ("rol", "absolute"),
    ("rla", "absolute"),
    ("bmi", "relative"),
    ("and", "indirectIndexedY"),
    ("jam", "implied"),
    ("rla", "indirectIndexedY"),
    ("nop", "zeroPageX"),
    ("and", "zeroPageX"),
    ("rol", "zeroPageX"),
    ("rla", "zeroPageX"),
    ("sec", "implied"),
    ("and", "absoluteY"),
    ("nop", "implied"),
    ("rla", "absoluteY"),
    ("nop", "absoluteX"),
    ("and", "absoluteX"),
    ("rol", "absoluteX"),
    ("rla", "absoluteX"),
    ("rti", "implied"),
    ("eor", "indexedIndirectX"),
    ("jam", "implied"),
    ("sre", "indexedIndirectX"),
    ("nop", "zeroPage"),
    ("eor", "zeroPage"),
    ("lsr", "zeroPage"),
    ("sre", "zeroPage"),
    ("pha", "implied"),
    ("eor", "immediate"),
    ("lsr", "accumulator"),
    ("alr", "immediate"),
    ("jmp", "absolute"),
    ("eor", "absolute"),
    ("lsr", "absolute"),
    ("sre", "absolute"),
    ("bvc", "relative"),
    ("eor", "indirectIndexedY"),
    ("jam", "implied"),
    ("sre", "indirectIndexedY"),
    ("nop", "zeroPageX"),
    ("eor", "zeroPageX"),
    ("lsr", "zeroPageX"),
    ("sre", "zeroPageX"),
    ("cli", "implied"),
    ("eor", "absoluteY"),
    ("nop", "implied"),
    ("sre", "absoluteY"),
    ("nop", "absoluteX"),
    ("eor", "absoluteX"),
    ("lsr", "absoluteX"),
    ("sre", "absoluteX"),
    ("rts", "implied"),
    ("adc", "indexedIndirectX"),
    ("jam", "implied"),
    ("rra", "indexedIndirectX"),
    ("nop", "zeroPage"),
    ("adc", "zeroPage"),
    ("ror", "zeroPage"),
    ("rra", "zeroPage"),
    ("pla", "implied"),
    ("adc", "immediate"),
    ("ror", "accumulator"),
    ("arr", "immediate"),
    ("jmp", "indirect"),
    ("adc", "absolute"),
    ("ror", "absolute"),
    ("rra", "absolute"),
    ("bvs", "relative"),
    ("adc", "indirectIndexedY"),
    ("jam", "implied"),
    ("rra", "indirectIndexedY"),
    ("nop", "zeroPageX"),
    ("adc", "zeroPageX"),
    ("ror", "zeroPageX"),
    ("rra", "zeroPageX"),
    ("sei", "implied"),
    ("adc", "absoluteY"),
    ("nop", "implied"),
    ("rra", "absoluteY"),
    ("nop", "absoluteX"),
    ("adc", "absoluteX"),
    ("ror", "absoluteX"),
    ("rra", "absoluteX"),
    ("nop", "immediate"),
    ("sta", "indexedIndirectX"),
    ("nop", "immediate"),
    ("sax", "indexedIndirectX"),
    ("sty", "zeroPage"),
    ("sta", "zeroPage"),
    ("stx", "zeroPage"),
    ("sax", "zeroPage"),
    ("dey", "implied"),
    ("nop", "immediate"),
    ("txa", "implied"),
    ("ane", "immediate"),
    ("sty", "absolute"),
    ("sta", "absolute"),
    ("stx", "absolute"),
    ("sax", "absolute"),
    ("bcc", "relative"),
    ("sta", "indirectIndexedY"),
    ("jam", "implied"),
    ("sha", "indirectIndexedY"),
    ("sty", "zeroPageX"),
    ("sta", "zeroPageX"),
    ("stx", "zeroPageY"),
    ("sax", "zeroPageY"),
    ("tya", "implied"),
    ("sta", "absoluteY"),
    ("txs", "implied"),
    ("tas", "absoluteY"),
    ("shy", "absoluteX"),
    ("sta", "absoluteX"),
    ("shx", "absoluteY"),
    ("sha", "absoluteY"),
    ("ldy", "immediate"),
    ("lda", "indexedIndirectX"),
    ("ldx", "immediate"),
    ("lax", "indexedIndirectX"),
    ("ldy", "zeroPage"),
    ("lda", "zeroPage"),
    ("ldx", "zeroPage"),
    ("lax", "zeroPage"),
    ("tay", "implied"),
    ("lda", "immediate"),
    ("tax", "implied"),
    ("lxa", "immediate"),
    ("ldy", "absolute"),
    ("lda", "absolute"),
    ("ldx", "absolute"),
    ("lax", "absolute"),
    ("bcs", "relative"),
    ("lda", "indirectIndexedY"),
    ("jam", "implied"),
    ("lax", "indirectIndexedY"),
    ("ldy", "zeroPageX"),
    ("lda", "zeroPageX"),
    ("ldx", "zeroPageY"),
    ("lax", "zeroPageY"),
    ("clv", "implied"),
    ("lda", "absoluteY"),
    ("tsx", "implied"),
    ("las", "absoluteY"),
    ("ldy", "absoluteX"),
    ("lda", "absoluteX"),
    ("ldx", "absoluteY"),
    ("lax", "absoluteY"),
    ("cpy", "immediate"),
    ("cmp", "indexedIndirectX"),
    ("nop", "immediate"),
    ("dcp", "indexedIndirectX"),
    ("cpy", "zeroPage"),
    ("cmp", "zeroPage"),
    ("dec", "zeroPage"),
    ("dcp", "zeroPage"),
    ("iny", "implied"),
    ("cmp", "immediate"),
    ("dex", "implied"),
    ("sbx", "immediate"),
    ("cpy", "absolute"),
    ("cmp", "absolute"),
    ("dec", "absolute"),
    ("dcp", "absolute"),
    ("bne", "relative"),
    ("cmp", "indirectIndexedY"),
    ("jam", "implied"),
    ("dcp", "indirectIndexedY"),
    ("nop", "zeroPageX"),
    ("cmp", "zeroPageX"),
    ("dec", "zeroPageX"),
    ("dcp", "zeroPageX"),
    ("cld", "implied"),
    ("cmp", "absoluteY"),
    ("nop", "implied"),
    ("dcp", "absoluteY"),
    ("nop", "absoluteX"),
    ("cmp", "absoluteX"),
    ("dec", "absoluteX"),
    ("dcp", "absoluteX"),
    ("cpx", "immediate"),
    ("sbc", "indexedIndirectX"),
    ("nop", "immediate"),
    ("isc", "indexedIndirectX"),
    ("cpx", "zeroPage"),
    ("sbc", "zeroPage"),
    ("inc", "zeroPage"),
    ("isc", "zeroPage"),
    ("inx", "implied"),
    ("sbc", "immediate"),
    ("nop", "implied"),
    ("sbc", "immediate"),
    ("cpx", "absolute"),
    ("sbc", "absolute"),
    ("inc", "absolute"),
    ("isc", "absolute"),
    ("beq", "relative"),
    ("sbc", "indirectIndexedY"),
    ("jam", "implied"),
    ("isc", "indirectIndexedY"),
    ("nop", "zeroPageX"),
    ("sbc", "zeroPageX"),
    ("inc", "zeroPageX"),
    ("isc", "zeroPageX"),
    ("sed", "implied"),
    ("sbc", "absoluteY"),
    ("nop", "implied"),
    ("isc", "absoluteY"),
    ("nop", "absoluteX"),
    ("sbc", "absoluteX"),
    ("inc", "absoluteX"),
    ("isc", "absoluteX"),
)

UNDOCUMENTED = frozenset(
    {
        "alr",
        "anc",
        "ane",
        "arr",
        "dcp",
        "isc",
        "jam",
        "las",
        "lax",
        "lxa",
        "rla",
        "rra",
        "sax",
        "sbx",
        "sha",
        "shx",
        "shy",
        "slo",
        "sre",
        "tas",
    }
)

UNSTABLE = frozenset({"ane", "lxa", "sha", "shx", "shy", "tas"})


class Truncated(Exception):
    pass


class Instruction:
    """One decoded instruction and where it was found."""

    def __init__(self, address, opcode, mnemonic, mode, operand, size):
        self.address = address
        self.opcode = opcode
        self.mnemonic = mnemonic
        self.mode = mode
        self.operand = operand
        self.size = size

    @property
    def undocumented(self):
        return self.mnemonic in UNDOCUMENTED

    @property
    def unstable(self):
        return self.mnemonic in UNSTABLE

    def __repr__(self):
        return f"<{self.mnemonic} {self.mode} at {self.address:04X}>"


def operand_size(mode):
    """How many bytes follow the opcode."""
    return MODE_SIZE[mode]


def branch_target(address, size, operand):
    """Where a relative branch goes, counted from the instruction after it."""
    offset = operand - 0x100 if operand & 0x80 else operand
    return (address + size + offset) & 0xFFFF


def render(mode, operand, address, size):
    """The operand as a reader of assembly would write it."""
    if mode in ("implied", "accumulator"):
        return ""
    if mode == "immediate":
        return f"#${operand:02X}"
    if mode == "relative":
        return f"${branch_target(address, size, operand):04X}"
    if mode == "relativeBit":
        return f"${operand & 0xFF:02X},${branch_target(address, size, operand >> 8):04X}"
    if mode == "zeroPage":
        return f"${operand:02X}"
    if mode == "zeroPageX":
        return f"${operand:02X},X"
    if mode == "zeroPageY":
        return f"${operand:02X},Y"
    if mode == "zeroPageIndirect":
        return f"(${operand:02X})"
    if mode == "indexedIndirectX":
        return f"(${operand:02X},X)"
    if mode == "indirectIndexedY":
        return f"(${operand:02X}),Y"
    if mode == "absolute":
        return f"${operand:04X}"
    if mode == "absoluteX":
        return f"${operand:04X},X"
    if mode == "absoluteY":
        return f"${operand:04X},Y"
    if mode == "indirectX":
        return f"(${operand:04X},X)"
    return f"(${operand:04X})"


def decode(data, offset, address, table=NMOS):
    """One instruction, or a refusal when the bytes run out before it ends."""
    if offset >= len(data):
        raise Truncated(f"no opcode at {offset}")

    opcode = data[offset]
    mnemonic, mode = table[opcode]
    width = operand_size(mode)
    if offset + 1 + width > len(data):
        raise Truncated(f"{mnemonic} at {address:04X} needs {width} more bytes")

    operand = 0
    for index in range(width):
        operand |= data[offset + 1 + index] << (8 * index)

    return Instruction(address, opcode, mnemonic, mode, operand, 1 + width)


def disassemble(data, offset, address, count=None, table=NMOS, stop_at_return=False):
    """Instructions from that offset, until the bytes or the count run out."""
    produced = 0
    while offset < len(data) and (count is None or produced < count):
        try:
            found = decode(data, offset, address, table)
        except Truncated:
            return
        yield found
        produced += 1
        offset += found.size
        address = (address + found.size) & 0xFFFF
        if stop_at_return and found.mnemonic in ("rts", "rti", "jmp", "jam"):
            return
