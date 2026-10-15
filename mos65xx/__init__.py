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
