from __future__ import annotations

import functools
import hashlib
import sys
import threading
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mos65xx  # noqa: E402

EIGHT_BIT = bytes.fromhex(
    "A9 2A 85 20 E6 20 A2 03 CA D0 FD 20 00 03 0A 48 68 18 69 11 9D 30 00 EA 38 E9 05 A8"
)

SIXTEEN_BIT = bytes.fromhex(
    "18 FB C2 30 A9 34 12 85 20 E6 20 A2 03 00 CA D0 FD 20 00 03 0A 48 68 E2 20 EB 9D 30 00 EA"
)

INSTRUCTIONS = 22

SUBROUTINE = 0x0300

RETURN = 0x60

NOP = 0xEA

WIDE = ("65816", "65802")

PATIENCE_SECONDS = 10.0

REGISTERS = ("a", "x", "y", "s", "pc", "d", "db", "pb", "emulation", "m8", "x8", "cycles", "steps")


def within(call: Callable[[], Any]) -> tuple[str, Any]:
    outcome: list[tuple[str, Any]] = []

    def attempt() -> None:
        try:
            outcome.append(("returned", call()))
        except Exception as raised:  # noqa: BLE001
            outcome.append(("raised", raised))

    worker = threading.Thread(target=attempt, daemon=True)
    worker.start()
    worker.join(PATIENCE_SECONDS)
    return outcome[0] if outcome else ("still running", None)


def a_program(model: str, memory: Any = None) -> Any:
    wide = model in WIDE
    space = memory if memory is not None else mos65xx.Memory(fill=NOP)
    for address, value in enumerate(SIXTEEN_BIT if wide else EIGHT_BIT):
        space.write8(address, value)
    space.write8(SUBROUTINE, RETURN)
    cpu = mos65xx.Cpu(model, space)
    cpu.pc = 0x0000
    cpu.s = 0x01FF if wide else 0xFF
    cpu.set_status(0x00)
    if wide:
        cpu.pb = cpu.db = cpu.d = 0x00
    cpu.trace = []
    return cpu


def observed(cpu: Any) -> tuple[Any, ...]:
    return (
        tuple(getattr(cpu, name, None) for name in REGISTERS),
        cpu.status(),
        cpu.held(),
        tuple(cpu.trace),
        hashlib.sha256(bytes(cpu.memory.data)).hexdigest(),
    )


def after_steps(model: str, instructions: int) -> tuple[int, tuple[Any, ...]]:
    cpu = a_program(model)
    spent = sum(cpu.step() for _ in range(instructions))
    return spent, observed(cpu)


def after_ticks(model: str, budget: int, closing: bool) -> tuple[Any, ...]:
    cpu = a_program(model)
    clock = mos65xx.Clock(cpu)
    try:
        clock.run_for(budget)
        if closing:
            clock.close()
        return observed(cpu)
    finally:
        clock.close()


def every_prefix_stepped() -> dict[str, list[tuple[Any, ...]]]:
    return {
        model: [after_steps(model, count)[1] for count in range(1, INSTRUCTIONS + 1)]
        for model in mos65xx.MODELS
    }


def every_prefix_ticked(closing: bool) -> dict[str, tuple[str, Any]]:
    def ticked(model: str) -> list[tuple[Any, ...]]:
        return [
            after_ticks(model, after_steps(model, count)[0], closing)
            for count in range(1, INSTRUCTIONS + 1)
        ]

    return {model: within(functools.partial(ticked, model)) for model in mos65xx.MODELS}


class Watched:
    __slots__ = ("cpu", "inner", "paused", "seen")

    def __init__(self) -> None:
        self.inner = mos65xx.Memory(fill=NOP)
        self.cpu: Any = None
        self.paused = 0
        self.seen: list[tuple[int, int]] = []

    def noted(self, address: int) -> int:
        self.seen.append((self.paused, len(self.cpu.trace)))
        return address

    def read8(self, address: int) -> int:
        return int(self.inner.read8(self.noted(address)))

    def write8(self, address: int, value: int) -> None:
        if self.cpu is None:
            self.inner.write8(address, value)
            return
        self.inner.write8(self.noted(address), value)

    def pause(self) -> None:
        self.paused += 1


def watched_run(model: str) -> list[tuple[int, int]]:
    memory = Watched()
    cpu = a_program(model, memory)
    memory.cpu = cpu
    cpu.on_cycle = memory.pause
    for _ in range(INSTRUCTIONS):
        cpu.step()
    return memory.seen


INTERRUPTING = ("6502", "65c02", "65816")

LINES = ("irq", "nmi")


def refusal(line: str) -> str:
    return (
        f"{line}() was called inside an instruction; tick the clock to the instruction "
        f"boundary, or set {line}_line, which the part samples when the instruction completes"
    )


def attempted(call: Callable[[], Any]) -> tuple[str, str]:
    try:
        call()
    except mos65xx.InsideInstruction as refused:
        return "refused", str(refused)
    return "taken", ""


def offered_between_steps(model: str, line: str) -> tuple[int, tuple[Any, ...]]:
    cpu = a_program(model)
    cpu.step()
    outcome = attempted(getattr(cpu, line))
    spent = cpu.step()
    return spent, (outcome, observed(cpu))


def offered_to_a_paused_clock(model: str, line: str, ticks: int, afterwards: int) -> Any:
    cpu = a_program(model)
    clock = mos65xx.Clock(cpu)
    try:
        clock.run_for(ticks)
        outcome = attempted(getattr(cpu, line))
        clock.run_for(afterwards)
        return outcome, observed(cpu)
    finally:
        clock.close()


def at_a_boundary(line: str) -> dict[str, tuple[str, Any]]:
    def offered(model: str) -> Any:
        afterwards, _ = offered_between_steps(model, line)
        return offered_to_a_paused_clock(model, line, after_steps(model, 1)[0], afterwards)

    return {model: within(functools.partial(offered, model)) for model in INTERRUPTING}


def inside_an_instruction(line: str) -> dict[str, tuple[str, Any]]:
    def offered(model: str) -> Any:
        first = after_steps(model, 1)[0]
        rest = after_steps(model, 2)[0] - first - 1
        return offered_to_a_paused_clock(model, line, first + 1, rest)

    return {model: within(functools.partial(offered, model)) for model in INTERRUPTING}


LAST_TWO_CYCLES = 2


def entered_through_the_line(model: str) -> tuple[int, tuple[Any, ...]]:
    cpu = a_program(model)
    cpu.irq_line = True
    spent = cpu.step()
    return spent, observed(cpu)


def inside_an_entry_the_line_began() -> dict[str, tuple[str, Any]]:
    def offered(model: str) -> Any:
        spent, _ = entered_through_the_line(model)
        cpu = a_program(model)
        cpu.irq_line = True
        clock = mos65xx.Clock(cpu)
        try:
            clock.run_for(spent - LAST_TWO_CYCLES)
            outcome = attempted(cpu.irq)
            clock.run_for(LAST_TWO_CYCLES)
            return outcome, observed(cpu)
        finally:
            clock.close()

    return {model: within(functools.partial(offered, model)) for model in INTERRUPTING}


def refusal_while_pending(line: str, pending: str) -> str:
    return (
        f"{line}() was called while an entry through {pending}_line is pending; tick the clock "
        f"through that entry, or set {line}_line, which the part samples when the instruction "
        "completes"
    )


def holding(model: str, pending: str) -> Any:
    cpu = a_program(model)
    setattr(cpu, f"{pending}_line", True)
    return cpu


def entered_after_the_first_instruction(model: str, pending: str) -> tuple[int, tuple[Any, ...]]:
    cpu = holding(model, pending)
    before = cpu.cycles
    cpu.step()
    return cpu.cycles - before, observed(cpu)


def pending_at_a_boundary(offered: str, pending: str) -> dict[str, tuple[str, Any]]:
    def offer(model: str) -> Any:
        boundary = after_steps(model, 1)[0]
        spent, _ = entered_after_the_first_instruction(model, pending)
        cpu = holding(model, pending)
        clock = mos65xx.Clock(cpu)
        try:
            clock.run_for(boundary)
            outcome = attempted(getattr(cpu, offered))
            clock.run_for(spent - boundary)
            return outcome, observed(cpu)
        finally:
            clock.close()

    return {model: within(functools.partial(offer, model)) for model in INTERRUPTING}


INTERRUPTS_DISABLED = 0x04


def held_but_masked(model: str) -> Any:
    cpu = holding(model, "irq")
    cpu.set_status(INTERRUPTS_DISABLED)
    return cpu


def masked_between_steps(model: str) -> tuple[int, tuple[Any, ...]]:
    cpu = held_but_masked(model)
    cpu.step()
    outcome = attempted(cpu.nmi)
    spent = cpu.step()
    return spent, (outcome, observed(cpu))


def masked_at_a_boundary() -> dict[str, tuple[str, Any]]:
    def offer(model: str) -> Any:
        afterwards, _ = masked_between_steps(model)
        cpu = held_but_masked(model)
        clock = mos65xx.Clock(cpu)
        try:
            clock.run_for(after_steps(model, 1)[0])
            outcome = attempted(cpu.nmi)
            clock.run_for(afterwards)
            return outcome, observed(cpu)
        finally:
            clock.close()

    return {model: within(functools.partial(offer, model)) for model in INTERRUPTING}


def refused_between_ticks() -> Any:
    cpu = a_program("6507")
    clock = mos65xx.Clock(cpu)
    try:
        clock.run_for(after_steps("6507", 1)[0])
        return cpu.nmi()
    finally:
        clock.close()


class TheLastCycleOfAnInstructionFinishesItTest(unittest.TestCase):
    def test_a_clock_leaves_the_state_steps_leave_on_every_part(self) -> None:
        # Arrange
        expected = {model: ("returned", states) for model, states in every_prefix_stepped().items()}

        # Act
        found = every_prefix_ticked(closing=False)

        # Assert
        self.assertEqual(found, expected)

    def test_and_so_does_a_clock_closed_on_that_cycle(self) -> None:
        # Arrange
        expected = {model: ("returned", states) for model, states in every_prefix_stepped().items()}

        # Act
        found = every_prefix_ticked(closing=True)

        # Assert
        self.assertEqual(found, expected)


class EveryAccessStaysOnItsOwnCycleTest(unittest.TestCase):
    def test_no_access_is_made_before_the_cycle_ahead_of_it_has_paused(self) -> None:
        # Arrange
        models = list(mos65xx.MODELS)

        # Act
        seen = {model: watched_run(model) for model in models}

        # Assert
        self.assertEqual(
            {model: [paused for paused, _ in pairs] for model, pairs in seen.items()},
            {model: [due for _, due in pairs] for model, pairs in seen.items()},
        )


class AnInterruptOfferedToAPausedClockTest(unittest.TestCase):
    def test_an_irq_at_an_instruction_boundary_is_taken_as_between_steps(self) -> None:
        # Arrange
        expected = {
            model: ("returned", offered_between_steps(model, "irq")[1]) for model in INTERRUPTING
        }

        # Act
        found = at_a_boundary("irq")

        # Assert
        self.assertEqual(found, expected)

    def test_an_irq_inside_an_instruction_is_refused_and_leaves_no_trace(self) -> None:
        # Arrange
        expected = {
            model: ("returned", (("refused", refusal("irq")), after_steps(model, 2)[1]))
            for model in INTERRUPTING
        }

        # Act
        found = inside_an_instruction("irq")

        # Assert
        self.assertEqual(found, expected)

    def test_an_nmi_at_an_instruction_boundary_is_taken_as_between_steps(self) -> None:
        # Arrange
        expected = {
            model: ("returned", offered_between_steps(model, "nmi")[1]) for model in INTERRUPTING
        }

        # Act
        found = at_a_boundary("nmi")

        # Assert
        self.assertEqual(found, expected)

    def test_an_nmi_inside_an_instruction_is_refused_and_leaves_no_trace(self) -> None:
        # Arrange
        expected = {
            model: ("returned", (("refused", refusal("nmi")), after_steps(model, 2)[1]))
            for model in INTERRUPTING
        }

        # Act
        found = inside_an_instruction("nmi")

        # Assert
        self.assertEqual(found, expected)

    def test_an_irq_inside_an_entry_the_line_began_is_refused_and_leaves_no_trace(self) -> None:
        # Arrange
        expected = {
            model: ("returned", (("refused", refusal("irq")), entered_through_the_line(model)[1]))
            for model in INTERRUPTING
        }

        # Act
        found = inside_an_entry_the_line_began()

        # Assert
        self.assertEqual(found, expected)

    def test_a_pending_nmi_edge_at_a_boundary_refuses_irq_and_leaves_no_trace(self) -> None:
        # Arrange
        expected = {
            model: (
                "returned",
                (
                    ("refused", refusal_while_pending("irq", "nmi")),
                    entered_after_the_first_instruction(model, "nmi")[1],
                ),
            )
            for model in INTERRUPTING
        }

        # Act
        found = pending_at_a_boundary("irq", "nmi")

        # Assert
        self.assertEqual(found, expected)

    def test_an_irq_line_held_with_interrupts_enabled_at_a_boundary_refuses_nmi_and_leaves_no_trace(
        self,
    ) -> None:
        # Arrange
        expected = {
            model: (
                "returned",
                (
                    ("refused", refusal_while_pending("nmi", "irq")),
                    entered_after_the_first_instruction(model, "irq")[1],
                ),
            )
            for model in INTERRUPTING
        }

        # Act
        found = pending_at_a_boundary("nmi", "irq")

        # Assert
        self.assertEqual(found, expected)

    def test_an_irq_line_held_while_masked_leaves_nmi_taken_as_between_steps(self) -> None:
        # Arrange
        expected = {model: ("returned", masked_between_steps(model)[1]) for model in INTERRUPTING}

        # Act
        found = masked_at_a_boundary()

        # Assert
        self.assertEqual(found, expected)

    def test_and_a_line_the_package_lacks_is_refused_at_once(self) -> None:
        # Arrange
        expected = "the 6507 has no nmi pin; it brings out rdy"

        # Act
        kind, raised = within(refused_between_ticks)

        # Assert
        self.assertEqual(
            (kind, type(raised).__name__, str(raised)), ("raised", "NoSuchPin", expected)
        )


if __name__ == "__main__":
    unittest.main()
