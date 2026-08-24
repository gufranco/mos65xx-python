"""That FAMILY.md still describes this package.

FAMILY.md is the standard the rest of the family is built to, so a name it
promises and this package does not have is worse than a missing feature: another
repository will be written against the promise. The file is identical in every
repository that carries it, which is what lets one test guard all of them.

Only the mechanical claims are checked here. Whether the reasoning is sound is a
review question; whether `run_for` exists is not.
"""

from __future__ import annotations

import inspect
import re
import sys
import types
import unittest
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mos65xx  # noqa: E402

FAMILY = (ROOT / "FAMILY.md").read_text()

INTERFACE = (
    "step",
    "run_for",
    "run_until",
    "reset",
    "irq",
    "nmi",
    "held",
)

COUNTERS = ("cycles", "steps")


class Part(Protocol):
    """The interface FAMILY.md promises, as something a type checker can hold.

    Writing it out is the point rather than a formality: this is the promise in a
    form another repository can import and check itself against, and a core that
    drifts from it stops satisfying the protocol before anybody reads the prose.
    """

    cycles: int
    steps: int

    def step(self) -> int: ...

    def run_for(self, cycles: int) -> int: ...

    def run_until(self, predicate: Any, limit: int | None = None) -> Any: ...

    def reset(self) -> Any: ...

    def held(self) -> bool: ...


def a_part() -> Part:
    part: Part = mos65xx.Cpu(mos65xx.DEFAULT_MODEL)
    return part


def a_running_part() -> Part:
    """A part pointed at a field of no-operations, so a bound is what is tested.

    Left in scrambled memory a part reaches a halting opcode within a few dozen
    instructions, which is correct behaviour and useless for testing a limit.
    """
    part = mos65xx.Cpu("65816", mos65xx.Memory(image=bytes([0xEA] * 256)))
    part.pb = 0x00
    part.pc = 0x0000
    checked: Part = part
    return checked


class PromisedInterfaceTest(unittest.TestCase):
    def test_every_call_the_standard_names_exists_here(self) -> None:
        part = a_part()

        absent = [name for name in INTERFACE if not hasattr(part, name)]

        self.assertEqual(absent, [])

    def test_and_every_counter(self) -> None:
        part = a_part()

        absent = [name for name in COUNTERS if not hasattr(part, name)]

        self.assertEqual(absent, [])

    def test_the_standard_names_each_of_them(self) -> None:
        unnamed = [name for name in INTERFACE + COUNTERS if name not in FAMILY]

        self.assertEqual(unnamed, [])


class PromisedBehaviourTest(unittest.TestCase):
    def test_a_step_reports_what_it_cost(self) -> None:
        part = a_running_part()

        cost = part.step()

        self.assertIsInstance(cost, int)

    def test_a_budget_reports_what_it_spent(self) -> None:
        part = a_running_part()

        spent = part.run_for(64)

        self.assertGreaterEqual(spent, 64)

    def test_the_budget_parameter_is_named_for_the_family(self) -> None:
        named = list(inspect.signature(a_part().run_for).parameters)

        self.assertEqual(named, ["cycles"])

    def test_the_tally_survives_a_reset(self) -> None:
        part = a_running_part()
        part.run_for(64)
        before = part.cycles

        part.reset()

        self.assertGreaterEqual(part.cycles, before)

    def test_a_bounded_run_gives_up_rather_than_hanging(self) -> None:
        part = a_running_part()

        with self.assertRaises(mos65xx.RunLimit):
            part.run_until(lambda _: False, limit=32)

    def test_a_running_part_is_not_held(self) -> None:
        part = a_part()

        self.assertFalse(part.held())


SURFACE = (
    "Cpu",
    "DEFAULT_MODEL",
    "MODELS",
    "UNSET_SEED",
    "Clock",
    "ClockClosed",
    "RunLimit",
    "UnknownModelError",
    "describe",
)
"""Names the standard promises a caller finds in every package of the family.

The memory type is not here because it is named for the part: this one has
%s. What the standard requires is that
a caller can reach it without importing a private module, which is what
`test_the_memory_type_is_reachable_without_a_private_import` checks.

`scramble` is not here either, and for a sharper reason. Two of the three fill a
buffer with the pattern and hand it over, so they have a function to publish. The
Z80 core derives each byte from the seed and the address at the moment it is read
and never builds a buffer at all, so there is nothing to publish and adding one
would mean building something the core does not need. A standard that promised it
would be describing two implementations rather than one interface.
"""


class PublishedSurfaceTest(unittest.TestCase):
    """That everything the standard names is importable from the package itself.

    A name that exists on a module inside the package but not on the package is
    not published. It works, so nothing fails, and a caller who finds it is
    relying on a path that is free to move. A sibling package had six such names.
    """

    def test_every_name_the_standard_promises_is_published(self) -> None:
        absent = [name for name in SURFACE if name not in mos65xx.__all__]

        self.assertEqual(absent, [])

    def test_and_each_one_is_actually_reachable(self) -> None:
        absent = [name for name in SURFACE if not hasattr(mos65xx, name)]

        self.assertEqual(absent, [])

    def test_the_memory_type_is_reachable_without_a_private_import(self) -> None:
        for name in ("Memory", "SparseMemory"):
            self.assertIn(name, mos65xx.__all__, name)

    def test_and_so_is_everything_it_can_raise(self) -> None:
        for name in ("Truncated", "Stopped", "Waiting"):
            self.assertIn(name, mos65xx.__all__, name)

    def test_nothing_is_promised_that_is_not_there(self) -> None:
        absent = [name for name in mos65xx.__all__ if not hasattr(mos65xx, name)]

        self.assertEqual(absent, [])


PACKAGE = mos65xx


class OneDefinitionTest(unittest.TestCase):
    """That no exception in the package is defined in two places under one name.

    The standard calls this out because of how quietly it fails. Two exception
    classes under one name both work, both are tested, and `except ThatName`
    written against one of them sails straight past the other. This package
    shipped exactly that: two `Truncated` classes, one per decoder, with the
    package exporting one of them, so catching it missed every case the other
    raised.

    Exceptions only, and deliberately. Two core classes under one name in two
    modules is ordinary and safe, because nobody catches a core: the caller
    reaches them through a factory and the one that needed a public name of its
    own already has one. An exception is different precisely because its name is
    the thing a caller writes down.

    The runtime is asked rather than the text, because `__module__` says where a
    class was defined and an import cannot fake it. Every module file is imported
    rather than only the ones the package exposes as attributes: a module left out
    of the package's own import list is exactly where a second definition hides,
    and asking `dir()` would walk straight past it.
    """

    def modules(self) -> list[Any]:
        """Every module file in the package, imported whether or not it is exposed."""
        import importlib

        found = []
        for path in sorted(Path(PACKAGE.__file__ or "").resolve().parent.glob("*.py")):
            if path.name.endswith(".test.py") or path.name == "__init__.py":
                continue
            found.append(importlib.import_module(f"{PACKAGE.__name__}.{path.stem}"))
        return found

    def defined(self, package: Any = None) -> dict[str, list[str]]:
        held = self.modules() if package is None else [getattr(package, n) for n in dir(package)]
        found: dict[str, list[str]] = {}
        for module in held:
            if not isinstance(module, types.ModuleType):
                continue
            for one in vars(module).values():
                if not isinstance(one, type) or not issubclass(one, BaseException):
                    continue
                if one.__module__ != module.__name__:
                    continue
                found.setdefault(one.__qualname__, []).append(module.__name__)
        return {name: sorted(set(where)) for name, where in found.items()}

    def test_no_exception_name_is_defined_twice(self) -> None:
        twice = {name: where for name, where in self.defined().items() if len(where) > 1}

        self.assertEqual(twice, {})

    def test_every_exception_a_caller_can_meet_is_published(self) -> None:
        """One a caller cannot import is one they cannot catch by name.

        `except` takes a name, so an exception reachable through the public
        interface and absent from the package is a failure a caller can only
        handle by catching everything. A leading underscore is how a genuinely
        internal one says so.
        """
        hidden = [
            name
            for name in self.defined()
            if not name.startswith("_") and name not in PACKAGE.__all__
        ]

        self.assertEqual(hidden, [])

    def test_there_are_exceptions_to_check(self) -> None:
        self.assertGreater(len(self.defined()), 2)

    def test_an_exception_imported_into_a_module_is_not_counted_as_defined_there(
        self,
    ) -> None:
        """Where a class was written is what matters, not where it can be read.

        Pointing several modules at one definition is the fix for a name defined
        twice, so a check that counted an import as a definition would report the
        fix as the fault it was meant to cure.
        """
        home: Any = types.ModuleType("home")
        borrower: Any = types.ModuleType("borrower")
        held = type("Borrowed", (Exception,), {"__module__": "home"})
        home.Borrowed = held
        borrower.Borrowed = held
        package: Any = types.ModuleType("package")
        package.home = home
        package.borrower = borrower

        self.assertEqual(self.defined(package), {"Borrowed": ["home"]})


class SharedFileTest(unittest.TestCase):
    def test_the_standard_names_every_file_this_repository_must_carry(self) -> None:
        rows = re.findall(r"^\| `([^`]+)` \|", FAMILY, re.M)
        promised = [row for row in rows if "/" in row or row.endswith(".md")]

        missing = [row for row in promised if not (ROOT / row).exists()]

        self.assertEqual(missing, [])


class DocumentedModelTest(unittest.TestCase):
    """That the readme shows how to build every part the package accepts.

    A model nobody can find in the readme is a model nobody uses. The check is
    for the constructor call rather than the bare name, because a name in prose
    tells a reader the part exists and a call tells them how to reach it, and the
    second is what they came for.
    """

    def test_every_model_has_a_worked_construction(self) -> None:
        readme = (ROOT / "README.md").read_text()

        undocumented = [name for name in mos65xx.MODELS if f'Cpu("{name}")' not in readme]

        self.assertEqual(undocumented, [])

    def test_and_every_alias_is_named_beside_it(self) -> None:
        readme = (ROOT / "README.md").read_text()

        unnamed = [
            alias
            for model in mos65xx.MODELS.values()
            for alias in model.aliases
            if alias not in readme
        ]

        self.assertEqual(unnamed, [])


class ClaimedCountTest(unittest.TestCase):
    """That the number of tests the readme advertises is the number there are.

    It went stale four times before this existed, every time by somebody adding
    tests and not thinking about a badge line. A count in prose is a claim about
    the repository, and a claim nothing checks is one that drifts silently until
    a reader believes something false.

    Counted from the source rather than by running the suites, because a test
    that runs every other test to check a number would cost minutes to answer a
    question worth milliseconds. The two agree: `unittest` reports one test per
    `def test_`, and nothing here generates cases at runtime.
    """

    def counted(self) -> int:
        """Every test in the directories the pipeline runs, and nowhere else.

        Scoped rather than swept for a reason. `docs/` is not in the repository,
        so a sweep of the whole tree counts files a fresh checkout does not have
        and the number disagrees with itself depending on which machine asks.
        """
        return sum(
            len(re.findall(r"^\s+def test_", found.read_text(), re.M))
            for directory in ("mos65xx", "conformance")
            for found in sorted((ROOT / directory).glob("**/*.test.py"))
        )

    def test_the_readme_advertises_the_number_of_tests_there_are(self) -> None:
        readme = (ROOT / "README.md").read_text()
        claimed = re.search(r"\*\*([\d,]+)\*\* tests", readme)

        assert claimed is not None
        self.assertEqual(int(claimed.group(1).replace(",", "")), self.counted())


if __name__ == "__main__":
    unittest.main()
