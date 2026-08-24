"""Which parts of the 65xx family this package covers, and what each one is.

A model is more than an opcode set. It is the address bus the part was given, the
instructions its maker added, and the mistakes its silicon shipped with. The
Ricoh part in the Famicom has decimal arithmetic disabled because the adder is
not wired for it. The 6507 in the Atari has thirteen address lines and no
interrupt pins. The NMOS parts execute undocumented opcodes that programs came to
rely on. None of that is a defect to be corrected here: a core that quietly fixes
a hardware bug is wrong for the machine that shipped it.

Adding a model means adding an entry here and holding it to a conformance suite.
A model with no suite behind it does not belong in this table, because then its
fidelity would be a claim rather than a measurement.

Ten of these have no suite of their own, and each says which part it narrows.
None is a different processor. Nine are the 6502 die in a smaller package, with
address lines left inside and, on most of them, one or both interrupt pins gone;
the 65802 is a 65816 in a forty pin part whose bank registers reach nothing
outside the first bank. What holds them is the suite of the part they narrow
plus a check that the narrowing is the only difference, so the claim is still
measured; it is measured against a sibling rather than against a recording of
its own.

A pin the package does not bring out is not a pin a system can assert, so
pulling one here raises rather than quietly taking the interrupt. That is the
whole of what separates the 6503, 6504, 6505 and 6506 from one another: they
have the same core, the same instructions and the same timing, and they differ
in how far an address reaches and which of the two interrupt lines survived the
pin count.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, override

from .errors import UnknownModelError


class Model:
    """One part of the family: what it is, what it reaches, and how to build it."""

    def __init__(
        self,
        name: str,
        summary: str,
        address_bits: int,
        data_bits: int,
        decimal: bool,
        core: Callable[..., Any],
        aliases: Iterable[str] = (),
        revision: str | None = None,
        narrows: str | None = None,
        pins: Iterable[str] = ("irq", "nmi", "rdy"),
        reset_cycles: int = 8,
    ) -> None:
        self.name = name
        self.summary = summary
        self.address_bits = address_bits
        self.data_bits = data_bits
        self.decimal = decimal
        self.core = core
        self.aliases = tuple(aliases)
        self.revision = revision
        self.narrows = narrows
        self.pins = tuple(pins)
        self.reset_cycles = reset_cycles
        """How long a reset takes on this part, counting the vector fetch.

        Eight everywhere the manufacturer said so: "the microprocessor will
        delay 6 cycles and then fetch the new program count vectors", which with
        the two cycles of that fetch is eight. WDC states a different figure for
        its own CMOS part, seven, and says nothing about the sixteen bit ones.
        Rockwell and Synertek state nothing at all, so their parts keep the
        figure of the design they are built from rather than borrowing WDC's.
        """

    @property
    def address_mask(self) -> int:
        return (1 << self.address_bits) - 1

    def build(self, memory: Any, **options: Any) -> Any:
        return self.core(self, memory, **options)

    @override
    def __repr__(self) -> str:
        return f"<Model {self.name}, {self.address_bits} address bits>"


def _build_6502(model: Model, memory: Any, **options: Any) -> Any:
    from .mos6502 import Cpu as Cpu6502

    cpu = Cpu6502(memory, decimal=model.decimal, **options)
    cpu.model = model.name
    cpu.address_mask = model.address_mask
    cpu.package_pins = model.pins
    cpu.reset_cycles = model.reset_cycles
    return cpu


def _build_65c02(model: Model, memory: Any, **options: Any) -> Any:
    from .mos65c02 import Cpu as Cpu65c02
    from .opcodes65c02 import TABLES

    assert model.revision is not None, (
        f"{model.name} names no revision, and the 65C02 tables key on one"
    )
    cpu = Cpu65c02(memory, table=TABLES[model.revision], decimal=model.decimal, **options)
    cpu.model = model.name
    cpu.address_mask = model.address_mask
    cpu.package_pins = model.pins
    cpu.reset_cycles = model.reset_cycles
    return cpu


def _build_65816(model: Model, memory: Any, **options: Any) -> Any:
    from .wdc65816 import Cpu as Cpu65816

    cpu = Cpu65816(memory, **options)
    cpu.model = model.name
    cpu.address_mask = model.address_mask
    cpu.package_pins = model.pins
    cpu.reset_cycles = model.reset_cycles
    return cpu


_CATALOGUE = (
    Model(
        name="6502",
        summary=(
            "MOS 6502. Eight bit registers, sixteen address lines, decimal arithmetic, "
            "and a hundred and fifty one undocumented opcodes that programs came to "
            "rely on. Its bugs are as well known as its instruction set."
        ),
        address_bits=16,
        data_bits=8,
        decimal=True,
        core=_build_6502,
        aliases=("mos6502", "nmos6502", "6510", "8500"),
    ),
    Model(
        name="6507",
        summary=(
            "MOS 6507. The same die in a smaller package, with thirteen address lines "
            "brought out and no interrupt pins, so it reaches eight kilobytes and "
            "everything above that is a mirror."
        ),
        address_bits=13,
        data_bits=8,
        decimal=True,
        core=_build_6502,
        narrows="6502",
        pins=("rdy",),
        aliases=("mos6507",),
    ),
    Model(
        name="6503",
        summary=(
            "MOS 6503. Twelve address lines and both interrupt pins, in a twenty eight pin "
            "package. Four kilobytes, and everything above that is a mirror."
        ),
        address_bits=12,
        data_bits=8,
        decimal=True,
        core=_build_6502,
        narrows="6502",
        pins=("irq", "nmi"),
        aliases=("mos6503",),
    ),
    Model(
        name="6504",
        summary=(
            "MOS 6504. Thirteen address lines and the request pin only, so a program on it "
            "cannot be interrupted by anything it cannot mask."
        ),
        address_bits=13,
        data_bits=8,
        decimal=True,
        core=_build_6502,
        narrows="6502",
        pins=("irq",),
        aliases=("mos6504",),
    ),
    Model(
        name="6505",
        summary=(
            "MOS 6505. Twelve address lines, the request pin and the ready line, with no "
            "non-maskable pin brought out."
        ),
        address_bits=12,
        data_bits=8,
        decimal=True,
        core=_build_6502,
        narrows="6502",
        pins=("irq", "rdy"),
        aliases=("mos6505",),
    ),
    Model(
        name="6506",
        summary=(
            "MOS 6506. Twelve address lines and the request pin, with the ready line spent on "
            "a second clock output instead."
        ),
        address_bits=12,
        data_bits=8,
        decimal=True,
        core=_build_6502,
        narrows="6502",
        pins=("irq",),
        aliases=("mos6506",),
    ),
    Model(
        name="6512",
        summary=(
            "MOS 6512. The 6502 with the clock oscillator left off the die, so the two phases "
            "come in on pins. Nothing a program can see differs."
        ),
        address_bits=16,
        data_bits=8,
        decimal=True,
        core=_build_6502,
        narrows="6502",
        pins=("irq", "nmi", "rdy"),
        aliases=("mos6512",),
    ),
    Model(
        name="6513",
        summary="MOS 6513. The 6503 driven by an external clock rather than its own.",
        address_bits=12,
        data_bits=8,
        decimal=True,
        core=_build_6502,
        narrows="6502",
        pins=("irq", "nmi"),
        aliases=("mos6513",),
    ),
    Model(
        name="6514",
        summary="MOS 6514. The 6504 driven by an external clock rather than its own.",
        address_bits=13,
        data_bits=8,
        decimal=True,
        core=_build_6502,
        narrows="6502",
        pins=("irq",),
        aliases=("mos6514",),
    ),
    Model(
        name="6515",
        summary="MOS 6515. The 6505 driven by an external clock rather than its own.",
        address_bits=12,
        data_bits=8,
        decimal=True,
        core=_build_6502,
        narrows="6502",
        pins=("irq", "rdy"),
        aliases=("mos6515",),
    ),
    Model(
        name="2a03",
        summary=(
            "Ricoh 2A03 and 2A07. The 6502 with the decimal adder left unwired, so the "
            "decimal flag can be set and changes nothing. Setting it and expecting "
            "decimal arithmetic is a bug this part will not report."
        ),
        address_bits=16,
        data_bits=8,
        decimal=False,
        core=_build_6502,
        aliases=("ricoh2a03", "2a07", "ricoh2a07", "nes6502", "famicom"),
    ),
    Model(
        name="65c02",
        summary=(
            "The base CMOS design, as Synertek and others shipped it. Every "
            "undocumented instruction is gone, replaced by new ones or by "
            "no-operations of stated length, and the jump through a pointer no "
            "longer reads its high byte from the wrong page."
        ),
        address_bits=16,
        data_bits=8,
        decimal=True,
        core=_build_65c02,
        aliases=("synertek65c02", "s65c02", "cmos6502"),
        revision="65c02",
    ),
    Model(
        name="r65c02",
        summary=(
            "Rockwell R65C02. The base design plus thirty two instructions for "
            "setting, clearing and branching on one bit of the first page. On a "
            "part without them the same bytes do nothing and say nothing."
        ),
        address_bits=16,
        data_bits=8,
        decimal=True,
        core=_build_65c02,
        aliases=("rockwell65c02", "rockwell"),
        revision="rockwell",
    ),
    Model(
        name="w65c02",
        summary=(
            "WDC W65C02S. Rockwell's instruction set plus two that stop the "
            "processor or hold it until an interrupt arrives."
        ),
        address_bits=16,
        data_bits=8,
        decimal=True,
        core=_build_65c02,
        aliases=("wdc65c02", "w65c02s"),
        revision="wdc",
        reset_cycles=7,
    ),
    Model(
        name="65816",
        summary=(
            "WDC W65C816S. Sixteen bit accumulator and index registers, twenty four "
            "address lines, and an emulation mode that behaves as a 6502 down to its "
            "stack and direct page wrapping."
        ),
        address_bits=24,
        data_bits=16,
        decimal=True,
        core=_build_65816,
        aliases=("w65c816", "w65c816s", "65c816", "65816s"),
    ),
    Model(
        name="65802",
        summary=(
            "WDC W65C802. The same core in a 6502 pin out, with sixteen address lines, "
            "so the bank registers exist but reach nothing outside the first bank."
        ),
        address_bits=16,
        data_bits=16,
        decimal=True,
        core=_build_65816,
        narrows="65816",
        aliases=("w65c802", "65c802"),
    ),
)

MODELS = {model.name: model for model in _CATALOGUE}

_BY_ALIAS = {}
for _model in _CATALOGUE:
    _BY_ALIAS[_model.name] = _model
    for _alias in _model.aliases:
        _BY_ALIAS[_alias] = _model


def _normalise(name: str) -> str:
    return str(name).strip().lower().replace("-", "").replace("_", "")


def describe(name: str) -> Model:
    """The model of that name, however it happens to be written."""
    found = _BY_ALIAS.get(_normalise(name))
    if found is None:
        raise UnknownModelError(
            f"{name} is not a model this family covers; it has {', '.join(sorted(MODELS))}"
        )
    return found
