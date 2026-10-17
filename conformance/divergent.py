from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

WIDE_MODEL = "65816"

INDEXED_INDIRECT_OPCODES = frozenset({"01", "21", "41", "61", "81", "a1", "c1", "e1"})

SOFTWARE_INTERRUPT_OPCODES = frozenset({"00", "02"})

FOLDED_PUSH = 0x0001FF

FLAT_PUSH = 0x0000FF

Difference = tuple[str, Any, Any]

Cycle = tuple[int | None, int | None, str]


def pulls_past_the_top_of_page_one(opcode: str, initial: Mapping[str, Any]) -> bool:
    return opcode == "ab" and (int(initial["s"]) & 0xFF) == 0xFF


def pushes_past_the_bottom_of_page_one(opcode: str, initial: Mapping[str, Any]) -> bool:
    return opcode == "fc" and (int(initial["s"]) & 0xFF) == 0x00


def reads_a_pointer_across_the_direct_page_edge(opcode: str, initial: Mapping[str, Any]) -> bool:
    if opcode not in INDEXED_INDIRECT_OPCODES or int(initial["d"]) & 0xFF:
        return False
    at = (int(initial.get("pbr", 0)) << 16) | ((int(initial["pc"]) + 1) & 0xFFFF)
    operand = dict(initial["ram"]).get(at)
    return operand is not None and (int(operand) + int(initial["x"])) & 0xFF == 0xFF


def clears_a_data_bank_the_recording_keeps(opcode: str, initial: Mapping[str, Any]) -> bool:
    return opcode in SOFTWARE_INTERRUPT_OPCODES and int(initial.get("dbr", 0)) != 0


DIVERGENT = (
    (
        "the stack address of a one byte pull at the top of emulation page one",
        pulls_past_the_top_of_page_one,
    ),
    (
        "whether a multi-byte pointer read out of the direct page stays inside the page,"
        " in emulation mode with the direct register page aligned",
        reads_a_pointer_across_the_direct_page_edge,
    ),
)

EXCUSED_FIELDS = (
    (
        "the data bank register after a software interrupt in emulation mode",
        clears_a_data_bank_the_recording_keeps,
        frozenset({"dbr"}),
    ),
    (
        "the stack addresses of an indexed indirect subroutine call at the bottom of emulation"
        " page one",
        pushes_past_the_bottom_of_page_one,
        frozenset({f"${FOLDED_PUSH:06X}", f"${FLAT_PUSH:06X}"}),
    ),
)

EXCUSED_ADDRESSES = (
    (
        "the stack addresses of an indexed indirect subroutine call at the bottom of emulation"
        " page one",
        pushes_past_the_bottom_of_page_one,
        (FOLDED_PUSH, FLAT_PUSH),
    ),
)


def emulated_opcode(test: Mapping[str, Any], model: str) -> str:
    if model != WIDE_MODEL or int(test["initial"].get("e", 0)) != 1:
        return ""
    return str(test["name"]).split()[0]


def recorded_divergence(test: Mapping[str, Any], model: str) -> str:
    opcode = emulated_opcode(test, model)
    initial = test["initial"]
    return next((subject for subject, applies in DIVERGENT if applies(opcode, initial)), "")


def excused_fields(test: Mapping[str, Any], model: str) -> frozenset[str]:
    opcode = emulated_opcode(test, model)
    initial = test["initial"]
    found = (fields for _, applies, fields in EXCUSED_FIELDS if applies(opcode, initial))
    return next(found, frozenset())


def unexplained(test: Mapping[str, Any], wrong: list[Difference], model: str) -> list[Difference]:
    excused = excused_fields(test, model)
    return [one for one in wrong if one[0] not in excused]


def excused_address(test: Mapping[str, Any], model: str) -> tuple[int, int] | None:
    opcode = emulated_opcode(test, model)
    initial = test["initial"]
    found = (pair for _, applies, pair in EXCUSED_ADDRESSES if applies(opcode, initial))
    return next(found, None)


def differs_only_where_excused(
    test: Mapping[str, Any], model: str, want: Sequence[Cycle], seen: Sequence[Cycle]
) -> bool:
    pair = excused_address(test, model)
    if pair is None or len(want) != len(seen):
        return False
    apart = [(one, other) for one, other in zip(want, seen, strict=True) if one != other]
    return bool(apart) and all(
        (one[0], other[0]) == pair and one[1:] == other[1:] for one, other in apart
    )
