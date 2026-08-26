"""Interpreters for the 65xx family, with the model chosen at construction.

The family shares its addressing modes, its flag rules and its decimal quirks,
so one package covers all of it and the differences live in the model rather than
in separate projects. A model is not only an opcode set: it is also the bugs. The
NMOS parts have undocumented instructions that programs relied on, the Ricoh part
has decimal arithmetic disabled, and the 65816 carries page and stack wrapping
rules that are not even consistent between its own addressing modes. A core that
quietly corrects any of that is wrong for the machine that shipped it.

    from mos65xx import Cpu, SparseMemory

    cpu = Cpu("65816", SparseMemory())

Nothing starts clean. Memory is scrambled unless a caller asks otherwise, and a
reset sets only what the hardware itself defines, leaving the rest holding what
it held.

Reading is the other half of running. `disassemble` walks bytes without executing
them, which is what anything surveying a ROM needs: an interpreter has to be
given a machine to run in, and a survey has nothing but the file.
"""

from __future__ import annotations

from typing import Any

from . import models as models
from . import mos65c02 as mos65c02
from . import mos6502 as mos6502
from . import opcodes65c02 as opcodes65c02
from . import opcodes6502 as opcodes6502
from .clock import Clock
from .errors import (
    ClockClosed,
    NoSuchPin,
    RunLimit,
    Stopped,
    Truncated,
    UnknownModelError,
    UnsupportedError,
    Waiting,
)
from .memory import Memory, SparseMemory, scramble
from .models import MODELS, Model
from .opcodes65816 import (
    FLAG_DEPENDENT,
    MODE_SIZE,
    OPCODES,
    apply_flags,
    branch_target,
    decode,
    disassemble,
    operand_size,
    render,
)
from .version import VERSION
from .wdc65816 import (
    FLAG_C,
    FLAG_D,
    FLAG_I,
    FLAG_M,
    FLAG_N,
    FLAG_V,
    FLAG_X,
    FLAG_Z,
    UNSET_SEED,
)
from .wdc65816 import Cpu as Cpu65816

__version__ = VERSION


def Cpu(  # noqa: N802
    model: str | None = None,
    memory: Any = None,
    fill: int | None = None,
    **options: Any,
) -> Any:
    """A processor of the named model, sharing one interface across the family.

    The model comes first because it is the thing a caller always knows and
    memory is the thing they often do not care about yet. Omitting it hands back
    a part with memory of its own, scrambled rather than cleared, which is what a
    board holds before anything has written to it.

    `fill` is the one way across this family to ask for a store holding one byte
    everywhere. It is not what a board hands over and it is not the default: a
    caller asking for zeroes is asking for something no machine does, so they
    have to say so. What it is for is a run that has to get through a few dozen
    instructions without meeting an opcode that stops the part, which is what
    every check of a cycle budget needs and what scrambled memory cannot give.
    """
    if fill is not None and memory is None:
        memory = Memory(fill=fill)
    return models.lookup(model).build(SparseMemory() if memory is None else memory, **options)


__all__ = [
    "FLAG_C",
    "FLAG_D",
    "FLAG_DEPENDENT",
    "FLAG_I",
    "FLAG_M",
    "FLAG_N",
    "FLAG_V",
    "FLAG_X",
    "FLAG_Z",
    "MODELS",
    "MODE_SIZE",
    "OPCODES",
    "UNSET_SEED",
    "Clock",
    "ClockClosed",
    "Cpu",
    "Cpu65816",
    "Memory",
    "Model",
    "NoSuchPin",
    "RunLimit",
    "SparseMemory",
    "Stopped",
    "Truncated",
    "UnknownModelError",
    "UnsupportedError",
    "Waiting",
    "__version__",
    "apply_flags",
    "branch_target",
    "decode",
    "disassemble",
    "operand_size",
    "render",
    "scramble",
]
