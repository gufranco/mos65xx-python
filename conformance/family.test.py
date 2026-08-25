"""That FAMILY.md still describes this package.

FAMILY.md is the standard the rest of the family is built to, so a name it
promises and this package does not have is worse than a missing feature: another
repository will be written against the promise. The file is identical in every
repository that carries it, which is what lets one test guard all of them.

Only the mechanical claims are checked here. Whether the reasoning is sound is a
review question; whether `run_for` exists is not.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import re
import subprocess
import sys
import tempfile
import tomllib
import types
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mos65xx  # noqa: E402

FAMILY = (ROOT / "FAMILY.md").read_text()

KIND = "Clocked part"
"""What this member models, in the words the membership table uses.

The table in FAMILY.md gives every member a kind, and the kind decides which of
these checks apply. A clocked part answers to all of them. A board, a format or
a tool has no clock to drive and no `Cpu` to hand back, so the section about
that is skipped and everything else is not: the record, the documents, the
tools and how it is written do not care whether the thing has a clock.

Skipping is not the same as passing. `ModelsAClockedPartTest` holds this string
to what the table says, so a member cannot quietly opt out of the interface by
calling itself something else.
"""

CLOCKED = KIND == "Clocked part"

SOLD_AS_A_COMPONENT = True
"""Whether this part could be bought and designed into something other than one machine.

A Z80 could, so naming the machine somebody put it in would turn this package
into a catalogue of that machine's parts wearing a processor's name. A cartridge
memory map could not: it exists only as part of one machine, names it because
that is what it models, and there is no more general thing to name instead.

The flag decides whether the machine sweep runs at all. It is written out rather
than inferred from an empty list of names, because an empty list and a list
nobody filled in look identical.
"""

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
    """One part, built the way the standard says every member builds one.

    A member that is not a clocked part has no `Cpu` at all, and the checks
    that call this are skipped there.
    """
    part: Part = PACKAGE.Cpu(PACKAGE.DEFAULT_MODEL)
    return part


def a_running_part() -> Part:
    """A part pointed at a field of no-operations, so a bound is what is tested.

    Left in scrambled memory a part reaches a halting opcode within a few dozen
    instructions, which is correct behaviour and useless for testing a limit.
    """
    part = PACKAGE.Cpu("65816", PACKAGE.Memory(image=bytes([0xEA] * 256)))
    part.pb = 0x00
    part.pc = 0x0000
    checked: Part = part
    return checked


class ModelsAClockedPartTest(unittest.TestCase):
    """That the kind this member claims is the kind the table gives it.

    The kind decides which checks run, so a member could otherwise skip the
    whole interface section by calling itself a format. Holding the string to
    the table means changing it means changing the standard, in every member,
    which is the point.
    """

    def row(self) -> str:
        pattern = rf"^\|\s*\[{re.escape(ROOT.name)}\]\([^)]*\)\s*\|(.+)\|(.+)\|\s*$"
        found = re.search(pattern, FAMILY, re.M)

        assert found is not None, f"{ROOT.name} is not in the membership table"
        return found.group(2).strip()

    def test_this_member_is_in_the_membership_table(self) -> None:
        self.assertIn(ROOT.name, FAMILY)

    def test_and_the_kind_it_declares_is_the_kind_the_table_gives_it(self) -> None:
        self.assertEqual(KIND, self.row())

    def test_the_table_only_uses_kinds_the_standard_explains(self) -> None:
        kinds = set(re.findall(r"\|\s*(Clocked part|Board|Format|Tool)\s*\|", FAMILY))

        self.assertTrue(kinds <= {"Clocked part", "Board", "Format", "Tool"})
        self.assertIn(KIND, kinds)

    def test_the_standard_says_what_a_kind_that_is_not_clocked_skips(self) -> None:
        self.assertIn("skips the section about a clock", FAMILY)


@unittest.skipUnless(CLOCKED, "not a clocked part")
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


@unittest.skipUnless(CLOCKED, "not a clocked part")
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

        with self.assertRaises(PACKAGE.RunLimit):
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

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_every_name_the_standard_promises_is_published(self) -> None:
        absent = [name for name in SURFACE if name not in PACKAGE.__all__]

        self.assertEqual(absent, [])

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_and_each_one_is_actually_reachable(self) -> None:
        absent = [name for name in SURFACE if not hasattr(PACKAGE, name)]

        self.assertEqual(absent, [])

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_the_part_a_caller_gets_back_is_called_Cpu(self) -> None:  # noqa: N802
        """The class, not just the call that builds it.

        `Cpu(...)` is a factory in all three, and what it hands back was called
        something else in one of them. That shows in a repr, in a traceback and
        in any annotation a caller writes, and nothing about the hardware asks
        for it.
        """
        built = PACKAGE.Cpu()

        self.assertEqual(type(built).__name__, "Cpu")

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_the_memory_type_is_reachable_without_a_private_import(self) -> None:
        for name in ("Memory", "SparseMemory"):
            self.assertIn(name, PACKAGE.__all__, name)

    def test_and_so_is_everything_it_can_raise(self) -> None:
        """Read from the errors module rather than a list somebody keeps in step.

        Every exception a caller can meet has to be importable by name, because
        `except` takes a name and one that cannot be imported can only be handled
        by catching everything.
        """
        errors = importlib.import_module(f"{PACKAGE.__name__}.errors")
        public = [
            name
            for name, held in vars(errors).items()
            if isinstance(held, type)
            and issubclass(held, Exception)
            and not name.startswith("_")
            and held.__module__ == errors.__name__
        ]

        self.assertTrue(public, "the errors module defines no exception")
        self.assertEqual([name for name in public if name not in PACKAGE.__all__], [])

    def test_nothing_is_promised_that_is_not_there(self) -> None:
        absent = [name for name in PACKAGE.__all__ if not hasattr(PACKAGE, name)]

        self.assertEqual(absent, [])


PACKAGE: Any = mos65xx
"""The package under test, deliberately untyped.

What a member publishes depends on what it models: a clocked part has a `Cpu`,
a `Memory` and a `RunLimit`, and a board, a format or a tool has none of them.
A checker cannot know which of those it is looking at, so naming the attributes
here would make it refuse a repository the standard never asked for one from.
The checks that reach for those attributes are skipped on members without them,
and every assertion below is made against the value at run time.
"""


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

    def test_and_there_is_something_to_check(self) -> None:
        """Or a standard naming no file would pass for one every member kept."""
        rows = re.findall(r"^\| `([^`]+)` \|", FAMILY, re.M)

        self.assertGreater(len([row for row in rows if row.endswith(".md")]), 0)


VARIANTS: dict[str, Any] = dict(getattr(PACKAGE, "MODELS", {}))
"""Every variant this package accepts, read from the package rather than listed.

A member that has a catalogue publishes it as `MODELS`, whatever the variants
are: three parts of a processor family, four cartridge layouts, two clocks. A
member that has none does not publish the name at all, and the checks below say
they were skipped rather than passing in silence.

Inferring the absence from an empty mapping is safe here, and it is not safe for
the machine names further down, because this one is read out of the package at
run time. An empty answer means the package publishes no catalogue. It cannot
mean somebody forgot to fill a list in, because there is no list to fill.
"""


def built(name: str, readme: str) -> bool:
    """Whether the readme shows that variant being passed to a call.

    A call rather than the bare name, because a name in prose tells a reader the
    variant exists and a call tells them how to reach it, and the second is what
    they came for.

    Which call it is differs between members and is deliberately not pinned. A
    clocked part hands back a `Cpu`, a board hands back a description of a
    layout, and a check that demanded one spelling would be describing one
    implementation rather than the promise every member makes.
    """
    return re.search(rf"""\w\(\s*["']{re.escape(name)}["']""", readme) is not None


@unittest.skipUnless(VARIANTS, "this package names no variants")
class DocumentedModelTest(unittest.TestCase):
    """That the readme shows how to reach every variant the package accepts.

    A variant nobody can find in the readme is a variant nobody uses.
    """

    def test_every_model_has_a_worked_construction(self) -> None:
        readme = (ROOT / "README.md").read_text()

        undocumented = [name for name in VARIANTS if not built(name, readme)]

        self.assertEqual(undocumented, [])

    def test_and_every_alias_is_named_beside_it(self) -> None:
        readme = (ROOT / "README.md").read_text()

        unnamed = [
            alias for model in VARIANTS.values() for alias in model.aliases if alias not in readme
        ]

        self.assertEqual(unnamed, [])

    def test_the_reader_of_that_tells_a_call_from_a_mention(self) -> None:
        """Driven both ways, because one that matched everything would also pass."""
        self.assertTrue(built("a-part", 'describe("a-part")'))
        self.assertTrue(built("a-part", "Cpu('a-part')"))
        self.assertFalse(built("a-part", "the a-part is covered here"))
        self.assertFalse(built("a-part", "`a-part`"))


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


def as_a_script(text: str) -> list[int]:
    """The line numbers where a conformance tool is invoked as a script."""
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if re.search(r"python3? conformance/[a-z_]+\.py", line)
    ]


class StandardIsKeptTest(unittest.TestCase):
    """That the conventions the standard added are the ones this repository follows.

    A standard is prose, and prose about code goes stale silently. These are the
    claims the file makes that a check can settle, so it settles them rather than
    trusting that a convention written down once is a convention still kept.
    """

    def test_the_standard_names_the_errors_module_as_the_one_home(self) -> None:
        self.assertIn("errors.py", FAMILY)

    def test_and_this_repository_has_one(self) -> None:
        self.assertTrue((Path(PACKAGE.__file__ or "").resolve().parent / "errors.py").exists())

    def test_the_standard_says_a_tool_runs_as_a_module(self) -> None:
        self.assertIn("python3 -m conformance.name", FAMILY)

    def test_and_no_workflow_runs_one_as_a_script(self) -> None:
        """The invocation is what actually decides, so it is what is read.

        Run as a script, the tool's own directory goes on the import path and a
        file there shadows a standard library module of the same name.
        """
        astray = [
            f"{path.name}:{number}"
            for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
            for number in as_a_script(path.read_text())
        ]

        self.assertEqual(astray, [])

    def test_and_no_document_tells_a_reader_to(self) -> None:
        astray = [
            name
            for name in ("README.md", "AGENTS.md", "CONTRIBUTING.md")
            if (ROOT / name).exists() and as_a_script((ROOT / name).read_text())
        ]

        self.assertEqual(astray, [])

    def test_the_reader_of_those_two_finds_a_script_invocation(self) -> None:
        """Both checks rest on one reader, so the reader is what is tested."""
        self.assertEqual(as_a_script("run: python conformance/speed.py\n"), [1])
        self.assertEqual(as_a_script("run: python3 -m conformance.speed\n"), [])
        self.assertEqual(as_a_script("a\nb\npython conformance/links.py\n"), [3])

    def test_the_standard_promises_a_throughput_floor(self) -> None:
        self.assertIn("throughput floor", FAMILY)

    def test_and_this_repository_has_one_with_a_floor_to_beat(self) -> None:
        from conformance import speed

        self.assertGreater(speed.FLOOR, 0)

    def test_the_floor_is_checked_outside_the_coverage_step(self) -> None:
        """Under a tracer the check measures the tracer, so it must not run there."""
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        self.assertIn("python -m conformance.speed", workflow)
        self.assertNotIn("coverage run -a conformance/speed.py", workflow)


@unittest.skipUnless(CLOCKED, "not a clocked part")
class SuppliedMemoryTest(unittest.TestCase):
    """That what a core runs on is handed in the same way in every package.

    The second parameter is the shared half: every core takes `Cpu(model,
    memory)`, keeps the one it is given, and builds its own when it is left out.
    What that argument is differs because the parts do, and the standard names
    the difference: one flat space called `memory` on the Z80 and the 65xx, three
    stores called `stores` on the uPD7725, which has three of them at three
    widths reached by three different registers.
    """

    def test_a_supplied_store_is_the_one_the_part_uses(self) -> None:
        own = PACKAGE.Memory(image=bytes([0xEA]) * 65536)

        built = PACKAGE.Cpu(PACKAGE.DEFAULT_MODEL, own)

        self.assertIs(built.memory, own)

    def test_and_one_is_built_when_the_argument_is_left_out(self) -> None:
        built = PACKAGE.Cpu(PACKAGE.DEFAULT_MODEL)

        self.assertIsNotNone(built.memory)

    def test_the_standard_names_this_part_spelling(self) -> None:
        """The spelling is a documented difference, so the document has to carry it."""
        self.assertIn("cpu.memory", FAMILY)


def still_holding(classes: Any) -> list[str]:
    """Every class that has a dictionary despite whatever it declared."""
    return [
        one.__qualname__
        for one in classes
        if any("__dict__" in vars(base) for base in one.__mro__[:-1])
    ]


class NoStrayAttributeTest(unittest.TestCase):
    """That a name a class does not have cannot be written to one.

    Without slots the write is accepted in silence: a stray attribute appears,
    the one the caller meant keeps whatever it held, and nothing reports that it
    went nowhere. The family has two spellings for one flag, `.i` on the eight
    bit 65xx parts and `.irq_disable` on the 65816, so reaching for the wrong one
    is a mistake somebody will make and the readme warned about it in prose for
    as long as it existed.

    Exceptions are exempt. They carry whatever a raiser attached and are never
    the thing a caller writes registers to.
    """

    def published(self) -> list[type]:
        found = []
        for name in dir(PACKAGE):
            held = getattr(PACKAGE, name)
            if isinstance(held, type) and not issubclass(held, BaseException):
                if held.__module__.startswith(PACKAGE.__name__):
                    found.append(held)
            elif isinstance(held, types.ModuleType) and held.__name__.startswith(PACKAGE.__name__):
                for attr, one in vars(held).items():
                    if attr.startswith("_"):
                        continue
                    if (
                        isinstance(one, type)
                        and one.__module__ == held.__name__
                        and not issubclass(one, BaseException)
                        and not getattr(one, "_is_protocol", False)
                    ):
                        found.append(one)
        return sorted(set(found), key=lambda one: one.__qualname__)

    def test_every_published_class_declares_what_it_holds(self) -> None:
        loose = [
            f"{one.__module__.split('.')[-1]}.{one.__qualname__}"
            for one in self.published()
            if "__slots__" not in vars(one)
        ]

        self.assertEqual(loose, [])

    def test_and_none_of_them_kept_a_dict_anyway(self) -> None:
        """A slotted class whose base is not slotted still has one, silently.

        Declaring the slots is not enough on its own. One unslotted class
        anywhere in the chain gives every subclass a dictionary back, and the
        guard is gone again with nothing to show it.
        """
        self.assertEqual(still_holding(self.published()), [])

    def test_and_one_that_did_would_be_named(self) -> None:
        class Loose:
            pass

        class Slotted(Loose):
            __slots__ = ()

        found = still_holding([Slotted])

        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].endswith("Slotted"), found[0])

    def test_there_are_classes_to_check(self) -> None:
        self.assertGreater(len(self.published()), 3)


SECTIONS = (
    "Install",
    "The interface",
    "Is it right",
    "Working on it",
    "References",
    "Citing this",
    "License",
)
"""The sections every readme carries, whatever the member models.

Seven, in this order, with anything a member adds sitting between the interface
and the evidence. A reader who learned where something lives in one member finds
it in the same place in the next, which is most of what a shared shape buys.
"""

CLOCKED_SECTIONS = (
    "Running it at a real speed",
    "Models",
    "Nothing starts clean",
)
"""Three more that only a clocked part has, in this order, after the interface.

Two others sit among them and are not listed because their titles name the part:
one about driving it a cycle at a time, where a Z80's cycle is a T state, and one
about reading a program without running it. Both are checked for separately.

A board, a format or a tool has no clock to pace, no power-on state to scramble
and no models to choose between, so it carries none of these and is not asked to.
"""

DIRECTIVE = ("noqa", "type:", "pragma", "ruff:", "mypy:", "isort:", "fmt:")
"""The comment forms a tool reads. Everything else is banned in source."""


def prose_comments(where: Path) -> list[str]:
    """Every comment in a source file that no tool parses.

    Reasoning belongs in a docstring, where it sits with the thing it explains and
    is read by anybody asking for help on it. A comment is the one part of a file
    nothing checks, so it is the one part free to drift.

    `**/*.py` never reaches into `__pycache__`, which holds `.pyc` and nothing
    else, so there is no directory to skip.
    """
    found = []
    for path in sorted(where.glob("**/*.py")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            bare = line.strip()
            if not bare.startswith("#"):
                continue
            body = bare.lstrip("#").strip()
            if body and not body.startswith(DIRECTIVE):
                found.append(f"{path.name}:{number}")
    return found


def mute_names(where: Path) -> list[str]:
    """Every test named for the function it calls rather than the behaviour.

    The floor is two words, which is as low as a floor goes. Length is not the
    measure: several names here are short because they continue the sentence
    their class began, which is the point of writing them that way.
    """
    found = []
    for path in sorted(where.glob("**/*.test.py")):
        for name in re.findall(r"^    def test_(\w+)", path.read_text(), re.M):
            if len(name.split("_")) < 2:
                found.append(f"{path.name}:test_{name}")
    return found


class WrittenTheSameWayTest(unittest.TestCase):
    """That this repository is written the way the others are.

    Not taste. Every item here was settled once across the family, and a member
    that drifts from it costs a reader the assumption that what they learned in
    one repository holds in the next.
    """

    def readme(self) -> str:
        return (ROOT / "README.md").read_text()

    def headings(self) -> list[str]:
        return re.findall(r"^## (.+)$", self.readme(), re.M)

    def test_the_readme_carries_the_sections_the_family_carries(self) -> None:
        missing = [one for one in SECTIONS if one not in self.headings()]

        self.assertEqual(missing, [])

    def test_and_in_the_order_the_family_carries_them(self) -> None:
        held = [one for one in self.headings() if one in SECTIONS]

        self.assertEqual(held, list(SECTIONS))

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_a_clocked_part_also_carries_the_three_a_clock_needs(self) -> None:
        missing = [one for one in CLOCKED_SECTIONS if one not in self.headings()]

        self.assertEqual(missing, [])

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_and_a_section_on_driving_it_a_cycle_at_a_time(self) -> None:
        """Named for the part: a Z80's cycle is a T state and it says so."""
        self.assertTrue(any(one.startswith("Driving it one") for one in self.headings()))

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_and_one_on_reading_a_program_without_running_it(self) -> None:
        self.assertIn("Reading without running", self.headings())

    def test_anything_it_adds_sits_between_the_interface_and_the_evidence(self) -> None:
        """So the spine reads the same in every member, whatever fills the middle."""
        held = self.headings()
        added = [one for one in held if one not in SECTIONS and one not in CLOCKED_SECTIONS]
        interface = held.index("The interface")
        evidence = held.index("Is it right")

        stray = [one for one in added if not interface < held.index(one) < evidence]

        self.assertEqual(stray, [])

    def test_the_readme_opens_with_what_was_measured(self) -> None:
        """A line of numbers somebody ran, before any prose about the part.

        It sits under the title block, so a reader who stops after the first
        screen still leaves knowing what was compared and how much of it failed.
        """
        held = self.readme().split("## ")[0]

        self.assertTrue(re.search(r"^\*\*[0-9,]+\*\* parts", held, re.M), held[:400])

    def test_and_says_how_much_of_it_failed(self) -> None:
        """A count of what was compared with no result is half a claim.

        A qualifier before the noun is allowed and is the stronger form, not the
        weaker one: "0 unexplained failures" beside a printed count of what was
        left out says more than a bare zero, which would have to hide the
        difference to stay true.
        """
        held = self.readme().split("## ")[0]

        self.assertTrue(
            re.search(r"\*\*0\*\* (?:\w+ )?(?:failures|disagreements)", held), held[:400]
        )

    def test_and_what_it_costs_to_install(self) -> None:
        held = self.readme().split("## ")[0]

        self.assertIn("no dependencies", held)

    def test_no_source_file_carries_a_comment_a_tool_does_not_read(self) -> None:
        self.assertEqual(prose_comments(Path(PACKAGE.__file__ or "").resolve().parent), [])

    def test_nor_does_any_conformance_file(self) -> None:
        self.assertEqual(prose_comments(ROOT / "conformance"), [])

    def test_the_reader_of_that_tells_a_directive_from_prose(self) -> None:
        """Fed both, because a reader that found nothing prints what a clean one does.

        Every line below is a form that turned up in this family: a directive on
        its own line, one with the reason a linter wants after it, a trailing
        comment that is part of a statement rather than a line of its own, and a
        divider of bare hashes. Only the sentence is prose.
        """
        with tempfile.TemporaryDirectory() as where:
            written = Path(where) / "sample.py"
            written.write_text(
                "# ruff: noqa: E501\n"
                "# noqa: E743 -- the register really is called l\n"
                "x = 1  # type: ignore[assignment]\n"
                "#\n"
                "# the accumulator is eight bits wide\n"
            )

            found = prose_comments(Path(where))

        self.assertEqual(found, ["sample.py:5"])

    def test_and_the_reader_of_names_tells_a_sentence_from_a_function(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            written = Path(where) / "sample.test.py"
            written.write_text(
                "class T:\n"
                "    def test_step(self) -> None:\n"
                "        pass\n"
                "\n"
                "    def test_a_step_costs_what_the_sheet_says(self) -> None:\n"
                "        pass\n"
            )

            found = mute_names(Path(where))

        self.assertEqual(found, ["sample.test.py:test_step"])

    def test_every_test_is_named_as_a_sentence_about_behaviour(self) -> None:
        """A name that states what the part does, not which function was called.

        It catches `test_step` and `test_irq`, which say nothing a failure
        message could use, and leaves the judgement of a good name to a reader.
        """
        self.assertEqual(mute_names(ROOT), [])

    def test_the_checker_is_strict_everywhere_the_family_is(self) -> None:
        held = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]

        self.assertTrue(held["mypy"]["strict"])
        self.assertEqual(held["coverage"]["report"]["fail_under"], 100)
        self.assertEqual(held["ruff"]["line-length"], 100)


MACHINES = {
    "zilog-z80-python": (
        "ZX Spectrum",
        "Game Boy",
        "GameBoy",
        "MSX",
        "Amstrad",
        "Master System",
        "Mega Drive",
        "Genesis",
        "TRS-80",
        "Sega",
        "Nintendo",
        "SNES",
    ),
    "mos65xx-python": (
        "NES",
        "SNES",
        "Super Famicom",
        "Famicom",
        "Nintendo",
        "Commodore 64",
        "C64",
        "VIC-20",
        "Apple II",
        "Atari 2600",
        "Atari 800",
        "BBC Micro",
    ),
    "upd7725": (
        "SNES",
        "Super Famicom",
        "Famicom",
        "Nintendo",
        "DSP-1",
        "DSP-2",
        "DSP-3",
        "DSP-4",
        "ST010",
        "ST011",
        "Seta",
        "console",
        "cartridge",
    ),
}
"""The machines and product names each member must not carry.

Named per repository because the list is: a Z80 went into different boxes than a
6502 did. The entries are specific products, never categories, because a category
is what an honest sentence about the part uses and flagging one would report
prose rather than a leak.
"""


NOT_THIS_PACKAGES_WORDS = ("conformance/family.test.py", "FAMILY.md")
"""Two files the machine sweep does not read, and why each is out of scope.

`conformance/family.test.py` is the list of names to search for, so finding them
there is finding the list. `FAMILY.md` is the standard every member carries
identically, and it describes members that model a cartridge memory map, an
image format and a board. Those exist only as part of one machine and name it
because that is what they model. A shared file cannot be held to one member's
vocabulary.
"""


def unquoted(text: str, suffix: str) -> str:
    """The same text with a record's quoted passages blanked out.

    A quote is a document's words, and a document is free to name whatever
    machine it likes. The rule here governs what this package says about the
    part, so a manufacturer's sentence about a disk controller is not a mention
    by this package. Blanking rather than dropping keeps every line number.
    """
    if suffix != ".json":
        return text
    try:
        record = json.loads(text)
    except json.JSONDecodeError:
        return text
    blanked = text
    for passage in _passages(record):
        if len(passage) > 8:
            blanked = blanked.replace(
                json.dumps(passage)[1:-1], " " * len(json.dumps(passage)[1:-1])
            )
    return blanked


def _passages(node: Any) -> list[str]:
    """Every string a record holds under a key naming it a quote."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key.endswith(("quote", "Quote")) and isinstance(value, str):
                found.append(value)
            elif key.endswith(("quotes", "Quotes")) and isinstance(value, list):
                found.extend(one for one in value if isinstance(one, str))
            elif key.endswith(("quotes", "Quotes")) and isinstance(value, dict):
                found.extend(one for one in value.values() if isinstance(one, str))
            else:
                found.extend(_passages(value))
    elif isinstance(node, list):
        for one in node:
            found.extend(_passages(one))
    return found


def machine_mentions(where: Path, names: tuple[str, ...], run: Any = None) -> list[str]:
    """Every tracked file that names a machine this part was put in.

    A processor is not the machine somebody put it in, and a package that names
    one becomes a catalogue of that machine's parts wearing a processor's name.

    Three things are out of scope and each says something. Untracked files are
    not checked, because what a copy of a document says is the document's
    business and it is not published from here. A record's quoted passages are
    not checked, for the same reason one step closer in. And the file declaring
    these names is not checked, because it is the list.
    """
    runner = subprocess.run if run is None else run
    listed = runner(
        ["git", "ls-files"], cwd=where, capture_output=True, text=True, check=False
    ).stdout.split()
    found = []
    for rel in listed:
        if rel in NOT_THIS_PACKAGES_WORDS:
            continue
        path = where / rel
        if path.suffix in {".png", ".jpg", ".ico", ".pdf"} or not path.is_file():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        searched = unquoted(text, path.suffix)
        for name in names:
            for hit in re.finditer(rf"(?<![\w-]){re.escape(name)}(?![\w-])", searched):
                found.append(f"{rel}:{text[: hit.start()].count(chr(10)) + 1} names {name}")
    return found


def imported_by(path: Path) -> set[str]:
    """Every module a source file imports, as written."""
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add("." * node.level + (node.module or ""))
    return found


def reaching_inside(names: Iterable[str], package: str) -> list[str]:
    """The imports in that set that come from this package rather than outside it.

    A relative import counts however deep it goes, and an absolute one counts
    when it is the package or a module under it. A package whose name merely
    begins the same way is somebody else's, which is why the dot is required.
    """
    return sorted(
        name
        for name in names
        if name.startswith(".") or name == package or name.startswith(package + ".")
    )


class ErrorsCloseNoCycleTest(unittest.TestCase):
    """That the one home for exceptions imports nothing from the package.

    Everything here raises, so everything here imports `errors`. If `errors`
    imports back, the cycle is closed and the order modules happen to load in
    decides whether an import works. The standard says it imports nothing from
    the package, and until now nothing checked the second half of that sentence.
    """

    def errors(self) -> Path:
        return Path(PACKAGE.__file__ or "").resolve().parent / "errors.py"

    def test_it_imports_nothing_from_this_package(self) -> None:
        self.assertEqual(reaching_inside(imported_by(self.errors()), PACKAGE.__name__), [])

    def test_the_reader_of_that_tells_the_package_from_the_standard_library(self) -> None:
        """Driven on both, because a filter that matched nothing would also pass."""
        held = {"__future__", "re", "typing", PACKAGE.__name__, f"{PACKAGE.__name__}.core", "."}

        self.assertEqual(
            reaching_inside(held, PACKAGE.__name__),
            [".", PACKAGE.__name__, f"{PACKAGE.__name__}.core"],
        )

    def test_and_a_package_whose_name_merely_starts_the_same_is_not_inside(self) -> None:
        """`z80asm` is somebody else's package, and so is `mos65xxtools`."""
        held = {f"{PACKAGE.__name__}asm", f"{PACKAGE.__name__}_tools"}

        self.assertEqual(reaching_inside(held, PACKAGE.__name__), [])

    def test_the_reader_of_that_sees_the_imports_that_are_there(self) -> None:
        """Or an empty answer would pass for a file it never opened."""
        with tempfile.TemporaryDirectory() as where:
            written = Path(where) / "sample.py"
            written.write_text(
                "from __future__ import annotations\nimport re\nfrom . import core\n"
            )

            found = imported_by(written)

        self.assertEqual(found, {"__future__", "re", "."})

    def test_and_would_name_one_reaching_back_into_the_package(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            written = Path(where) / "sample.py"
            written.write_text(f"from {PACKAGE.__name__}.core import Cpu\n")

            found = imported_by(written)

        self.assertIn(f"{PACKAGE.__name__}.core", found)


DOCUMENT_SUFFIXES = frozenset({".pdf", ".djvu", ".epub", ".rom", ".bin", ".img"})
"""Extensions that name a file somebody else owns rather than one written here."""


def unignored(where: Path, run: Any = None) -> list[str]:
    """Every path this repository's own ignore file leaves exposed.

    A machine-global ignore file is configured once and does not travel with a
    clone, so a path protected only there is exposed in every other checkout and
    in CI. Nothing shows locally, because the status a person reads has the
    global file applied. Reading it with that file switched off is the only way
    to see what a fresh clone would.
    """
    runner = subprocess.run if run is None else run
    done = runner(
        ["git", "-c", "core.excludesFile=/dev/null", "status", "--porcelain", "-uall"],
        cwd=where,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(
            f"git could not read the tree: {done.stderr.strip() or 'no reason given'}"
        )
    return sorted(line[3:] for line in done.stdout.splitlines() if line.startswith("??"))


AGENTS_SECTIONS = (
    "What this project is, in one paragraph",
    "The interface a caller drives",
    "The authority ladder",
    "What is settled and what is not",
    "Every gate, in the order to run them",
    "Conventions that are not negotiable",
    "Layout",
    "Things that will bite you",
    "Before calling anything finished",
    "What a change is expected to leave behind",
)
"""The sections every AGENTS.md carries, in the order it carries them.

A member may add sections of its own about the part it models. Those sit after
"What is settled and what is not", so the shared spine reads the same everywhere
and a reader who learned where something lives in one member finds it in the
same place in the next.
"""


SETTLED_SECTIONS = ("What is not in question", "What is deliberately not modelled")
"""Sections of OPEN-QUESTIONS.md that hold decisions rather than questions."""


def open_questions(where: Path | None = None) -> list[str]:
    """Every entry in OPEN-QUESTIONS.md that is actually an open question.

    Counting `###` headings counts the sections that exist to say what is not in
    doubt and what is left out on purpose. Those belong in the file and do not
    belong in a count of what is unsettled.
    """
    held = ((ROOT if where is None else where) / "OPEN-QUESTIONS.md").read_text()
    found: list[str] = []
    section = ""
    for line in held.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("### ") and section not in SETTLED_SECTIONS:
            found.append(line[4:].strip())
    return found


class BriefedTheSameWayTest(unittest.TestCase):
    """That the instructions read the same way across members.

    Not taste. Three members had three orders and one was missing the two
    sections that say what the interface is and what is settled, which are the
    two an agent reads first.
    """

    def agents(self) -> str:
        return (ROOT / "AGENTS.md").read_text()

    def held(self) -> list[str]:
        return re.findall(r"^## (.+)$", self.agents(), re.M)

    def test_it_carries_the_sections_the_family_carries(self) -> None:
        missing = [one for one in AGENTS_SECTIONS if one not in self.held()]

        self.assertEqual(missing, [])

    def test_and_in_the_order_the_family_carries_them(self) -> None:
        kept = [one for one in self.held() if one in AGENTS_SECTIONS]

        self.assertEqual(kept, list(AGENTS_SECTIONS))

    def test_anything_it_adds_of_its_own_sits_in_one_place(self) -> None:
        """After what is settled and before the gates, so the spine stays whole."""
        held = self.held()
        added = [one for one in held if one not in AGENTS_SECTIONS]
        gates = held.index("Every gate, in the order to run them")
        settled = held.index("What is settled and what is not")

        self.assertTrue(all(settled < held.index(one) < gates for one in added), added)

    def test_the_count_of_open_questions_is_the_count_there_is(self) -> None:
        """Two of the three said a number that had stopped being true."""
        claimed = re.search(r"\*\*Not settled: (\d+) things\*\*", self.agents())

        assert claimed is not None
        self.assertEqual(int(claimed.group(1)), len(open_questions()))

    def test_and_counts_questions_rather_than_headings(self) -> None:
        """A file that ends with what it deliberately leaves out is not four questions."""
        held = (ROOT / "OPEN-QUESTIONS.md").read_text()

        self.assertLessEqual(len(open_questions()), len(re.findall(r"^### ", held, re.M)))


class PublishesNamesNotModulesTest(unittest.TestCase):
    """That `__all__` lists what a caller uses rather than how it is arranged.

    A submodule is reachable whether or not it is listed, because importing a
    name out of one makes it an attribute of the package. Listing it therefore
    changes nothing except what `import *` binds, while presenting the
    arrangement of the code as part of the interface. The three members had
    three different answers to this: one published nine modules, one published
    four, and one published ten.
    """

    def test_no_module_is_published_as_a_name(self) -> None:
        published = sorted(
            name
            for name in PACKAGE.__all__
            if isinstance(getattr(PACKAGE, name, None), types.ModuleType)
        )

        self.assertEqual(published, [])

    def test_a_module_is_still_reachable_without_being_published(self) -> None:
        """Which is why removing them cost a caller nothing."""
        self.assertTrue(hasattr(PACKAGE, "errors"))
        self.assertNotIn("errors", PACKAGE.__all__)

    def test_there_are_names_published(self) -> None:
        self.assertGreater(len(PACKAGE.__all__), 10)


class CarriesNobodyElsesWorkTest(unittest.TestCase):
    """That nothing licensed to somebody else is in the repository or reachable from it.

    Documents live beside the code and are never committed, which is why every
    check that reads one says so when it cannot find it. The rule held by hand
    until a sweep found one member's own ignore file missing seven entries the
    others had, with build output protected only by a file configured on one
    machine.
    """

    def tracked(self) -> list[str]:
        listed = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
        )
        return listed.stdout.split()

    def test_no_document_is_committed(self) -> None:
        carried = sorted(
            rel for rel in self.tracked() if Path(rel).suffix.lower() in DOCUMENT_SUFFIXES
        )

        self.assertEqual(carried, [])

    def test_nor_is_anything_from_the_folder_they_live_in(self) -> None:
        self.assertEqual([rel for rel in self.tracked() if rel.startswith("docs/")], [])

    def test_there_are_tracked_files_to_look_through(self) -> None:
        """Or an empty listing would pass for a repository with nothing in it."""
        self.assertGreater(len(self.tracked()), 20)

    def test_the_ignore_file_here_covers_everything_on_its_own(self) -> None:
        """Without leaning on one configured on this machine and nowhere else."""
        self.assertEqual(unignored(ROOT), [])

    def test_the_reader_of_that_names_an_untracked_file(self) -> None:
        found = unignored(ROOT, self.saying("?? left/behind.txt\n M edited.py\n"))

        self.assertEqual(found, ["left/behind.txt"])

    def test_and_steps_over_one_that_is_merely_edited(self) -> None:
        found = unignored(ROOT, self.saying(" M edited.py\nA  added.py\n"))

        self.assertEqual(found, [])

    def test_a_run_that_failed_is_not_read_as_a_clean_tree(self) -> None:
        """An empty answer and a broken one look the same, so one of them raises."""

        def refused(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 128, stdout="", stderr="not a repository")

        with self.assertRaises(RuntimeError) as caught:
            unignored(ROOT, refused)

        self.assertIn("not a repository", str(caught.exception))

    def test_and_a_failure_with_nothing_to_say_still_raises(self) -> None:
        def mute(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 1, stdout="", stderr="")

        with self.assertRaises(RuntimeError):
            unignored(ROOT, mute)

    def saying(self, text: str) -> Any:
        def run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 0, stdout=text, stderr="")

        return run


class QuotedPassageTest(unittest.TestCase):
    """That a document's own words are blanked before the sweep reads a record.

    Without this the rule would ask a manufacturer to stop naming a disk
    controller in a sentence it printed in 1984.
    """

    def test_a_quote_is_blanked_and_the_line_numbers_survive(self) -> None:
        held = '{"quote": "the SNES is named here", "note": "and here too"}'

        found = unquoted(held, ".json")

        self.assertEqual(len(found), len(held))
        self.assertNotIn("SNES", found[: found.index("note")])
        self.assertIn("and here too", found)

    def test_a_plural_key_holding_a_list_is_blanked_as_well(self) -> None:
        held = '{"aboutQuotes": ["the SNES is named here", "and so it is here"]}'

        self.assertNotIn("SNES", unquoted(held, ".json"))

    def test_and_one_holding_a_map_of_numbered_notes(self) -> None:
        held = '{"noteQuotes": {"1": "the SNES is named here"}}'

        self.assertNotIn("SNES", unquoted(held, ".json"))

    def test_a_short_passage_is_left_alone(self) -> None:
        """Blanking a handful of characters would blank them everywhere else too."""
        held = '{"quote": "SNES", "note": "SNES"}'

        self.assertEqual(unquoted(held, ".json"), held)

    def test_a_file_that_is_not_a_record_is_read_as_it_stands(self) -> None:
        held = "the SNES is named here"

        self.assertEqual(unquoted(held, ".md"), held)

    def test_and_so_is_one_that_claims_to_be_and_is_not(self) -> None:
        """A malformed record is a finding for another check, not silence here."""
        held = "{this is not json at all, and it names the SNES"

        self.assertEqual(unquoted(held, ".json"), held)

    def test_a_value_that_is_not_a_passage_is_stepped_over(self) -> None:
        held = '{"quote": 5, "quotes": [1, 2], "noteQuotes": {"1": 3}, "cycles": [1]}'

        self.assertEqual(_passages(json.loads(held)), [])


@unittest.skipUnless(SOLD_AS_A_COMPONENT, "this part only existed inside one machine")
class NamesNoMachineTest(unittest.TestCase):
    """That this package does not name the machines its part went into.

    The rule is in FAMILY.md and was kept by hand until a sweep found five
    mentions of a product line in one member's own section of that file, and
    twenty uses of a word for a host that presumed which kind of machine it was.
    """

    def names(self) -> tuple[str, ...]:
        return MACHINES[PACKAGE.__name__ if PACKAGE.__name__ in MACHINES else ROOT.name]

    def test_no_tracked_file_names_one(self) -> None:
        self.assertEqual(machine_mentions(ROOT, self.names()), [])

    def test_the_sweep_would_report_one_if_it_were_there(self) -> None:
        """Driven against a name that is certainly present, so silence means checked."""
        found = machine_mentions(ROOT, ("README",))

        self.assertNotEqual(found, [])

    def test_a_name_inside_a_longer_word_is_not_a_mention(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            folder = Path(where)
            (folder / "a.md").write_text("SNESLIKE and pre-SNES-era are not mentions\n")
            found = machine_mentions(folder, ("SNES",), self.listing("a.md"))

        self.assertEqual(found, [])

    def test_but_the_bare_name_is(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            folder = Path(where)
            (folder / "a.md").write_text("first\nthis one names the SNES outright\n")
            found = machine_mentions(folder, ("SNES",), self.listing("a.md"))

        self.assertEqual(found, ["a.md:2 names SNES"])

    def test_a_file_that_is_not_text_is_stepped_over(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            folder = Path(where)
            (folder / "a.bin").write_bytes(b"\xff\xfe\x00SNES")
            found = machine_mentions(folder, ("SNES",), self.listing("a.bin"))

        self.assertEqual(found, [])

    def test_and_so_is_one_git_lists_that_is_not_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            found = machine_mentions(Path(where), ("SNES",), self.listing("gone.md"))

        self.assertEqual(found, [])

    def listing(self, *names: str) -> Any:
        def run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 0, stdout="\n".join(names), stderr="")

        return run


if __name__ == "__main__":
    unittest.main()
