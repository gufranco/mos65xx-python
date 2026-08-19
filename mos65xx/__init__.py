"""Interpreters for the 65xx family, with the model chosen at construction.

The family shares its addressing modes, its flag rules and its decimal quirks,
so one package covers all of it and the differences live in the model rather than
in separate projects. A model is not only an opcode set: it is also the bugs. The
NMOS parts have undocumented instructions that programs relied on, the Ricoh part
has decimal arithmetic disabled, and the 65816 carries page and stack wrapping
rules that are not even consistent between its own addressing modes. A core that
quietly corrects any of that is wrong for the machine that shipped it.

    from mos65xx import Cpu, SparseMemory

    cpu = Cpu(SparseMemory(), model="65816")

Nothing starts clean. Memory is scrambled unless a caller asks otherwise, and a
reset sets only what the hardware itself defines, leaving the rest holding what
it held.

Reading is the other half of running. `disassemble` walks bytes without executing
them, which is what anything surveying a ROM needs: an interpreter has to be
given a machine to run in, and a survey has nothing but the file.
"""

from . import mos6502, opcodes6502
from .memory import Memory, SparseMemory, scramble
from .models import MODELS, UnknownModelError, describe
from .opcodes65816 import (
    FLAG_DEPENDENT,
    MODE_SIZE,
    OPCODES,
    Truncated,
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
    STEP_LIMIT,
    UNSET_SEED,
    StepLimit,
    Stopped,
    UnsupportedError,
)
from .wdc65816 import Cpu as Cpu65816

__version__ = VERSION

DEFAULT_MODEL = "65816"


def Cpu(memory, model=DEFAULT_MODEL, **options):  # noqa: N802
    """A processor of the named model, sharing one interface across the family."""
    return describe(model).build(memory, **options)


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
    "STEP_LIMIT",
    "UNSET_SEED",
    "Cpu",
    "Cpu65816",
    "Memory",
    "SparseMemory",
    "StepLimit",
    "Stopped",
    "Truncated",
    "UnknownModelError",
    "UnsupportedError",
    "__version__",
    "apply_flags",
    "branch_target",
    "decode",
    "describe",
    "disassemble",
    "mos6502",
    "opcodes6502",
    "operand_size",
    "render",
    "scramble",
]
