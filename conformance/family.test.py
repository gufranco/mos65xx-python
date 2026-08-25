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
import tokenize
import tomllib
import types
import unittest
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
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

A_PART = KIND == "Part"
"""Something that answers accesses without running a program.

Its constructor is `Chip(model, ...)`, the same shape as `Cpu(model, memory)` and
named for what it is rather than for what it does. A part that executes nothing
should not be built by something called `Cpu`.
"""

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
        kinds = set(re.findall(r"\|\s*(Clocked part|Part|Board|Format|Tool)\s*\|", FAMILY))

        self.assertTrue(kinds <= {"Clocked part", "Part", "Board", "Format", "Tool"})
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


PART_SURFACE = (
    "Chip",
    "DEFAULT_MODEL",
    "MODELS",
    "Model",
    "UnknownModelError",
    "describe",
)
"""Names the standard promises a caller finds in every part of the family.

Smaller than the processor surface because a part has no clock, no run limit and
no counters. What it keeps is the catalogue: even the member with one model
publishes it, so a caller moving between members writes the same call and a name
that does not exist is refused rather than quietly ignored.
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

    @unittest.skipUnless(A_PART, "not a part in the sense this checks")  # pragma: no cover
    def test_a_part_is_built_by_Chip_taking_the_model_first(self) -> None:  # noqa: N802
        """The same shape as `Cpu(model, memory)`, under the name this kind has.

        Two of these were built by `describe(name).build(store)` and by a class
        named for the one chip it modelled, so a caller moving between members
        wrote a different call in each. The model comes first for the same reason
        it does on a processor: it is the thing a caller always knows.
        """
        built = PACKAGE.Chip()

        self.assertEqual(type(built).__name__, "Chip")

    @unittest.skipUnless(A_PART, "not a part in the sense this checks")  # pragma: no cover
    def test_and_it_takes_a_model_by_name(self) -> None:
        for name in sorted(VARIANTS):
            self.assertEqual(PACKAGE.Chip(name).model, name, name)

    @unittest.skipUnless(A_PART, "not a part in the sense this checks")  # pragma: no cover
    def test_and_refuses_a_name_no_model_goes_by(self) -> None:
        """A typo that builds the default part is worse than one that fails."""
        with self.assertRaises(PACKAGE.UnknownModelError):
            PACKAGE.Chip("no model goes by this name")

    @unittest.skipUnless(A_PART, "not a part in the sense this checks")  # pragma: no cover
    def test_every_name_a_part_promises_is_published(self) -> None:
        absent = [name for name in PART_SURFACE if name not in PACKAGE.__all__]

        self.assertEqual(absent, [])

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
        """Or a sweep that imported nothing would report no duplicate names.

        Presence rather than a count. The members range from one chip with a
        single refusal to a family of sixteen processors, so a floor high enough
        to mean anything for the second would refuse the first for being small,
        and being small is not a defect.
        """
        self.assertGreater(len(self.modules()), 0)
        self.assertGreater(len(self.defined()), 0)

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


RECORD = ROOT / "conformance" / "hardware.json"
"""The record every fact taken from a document is written into."""


def declared(node: Any) -> dict[str, Any]:
    """Every document a record declares, wherever it declares them.

    Walked rather than read from the top, because where the block sits is
    arrangement and not vocabulary. One member has two parts with different data
    sheets and declares each part's beside it, which says something the top level
    could not. What the rule is actually about is that there is one namespace of
    keys and that a citation names one of them.
    """
    found: dict[str, Any] = {}
    if isinstance(node, dict):
        held = node.get("documents")
        if isinstance(held, dict):
            found.update(held)
        for value in node.values():
            found.update(declared(value))
    elif isinstance(node, list):
        for one in node:
            found.update(declared(one))
    return found


def cited(node: Any, where: str = "") -> list[tuple[str, str]]:
    """Every place in a record that names a document, with the path to it.

    Walked for the same reason: a record is arranged the way the part is, one
    keyed by pin, one by core, one by register file. What every one of them
    shares is the key `document` on the fact that cites one.
    """
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        named = node.get("document")
        if isinstance(named, str):
            found.append((where or ".", named))
        for name, value in node.items():
            found += cited(value, f"{where}.{name}")
    elif isinstance(node, list):
        for index, one in enumerate(node):
            found += cited(one, f"{where}[{index}]")
    return found


class OneVocabularyForADocumentTest(unittest.TestCase):
    """That a document is named one way, so a check can follow the name.

    Held in one field, a key here, a file name there and a prose title with the
    section glued on somewhere else, nothing can check any of them: a check
    written against keys skips the rest in silence and reports a clean run over
    the part it understood.

    Eight of the ten members carried a single `document` object, or a source
    named only in prose, while the standard asked for a `documents` block. None
    of them reported it, because this check did not exist.

    A member with no document at all declares an empty block rather than no
    block. That is the difference between saying there is nothing to cite and
    saying nothing, and for two of these parts the absence of any manufacturer
    document is the most important thing the record has to say.
    """

    def record(self) -> Any:
        return json.loads(RECORD.read_text())

    def test_the_standard_asks_for_a_documents_block(self) -> None:
        self.assertIn("`documents` block", FAMILY)

    def test_the_record_declares_its_sources_in_one(self) -> None:
        self.assertIsInstance(self.record().get("documents"), dict)

    def test_every_source_declared_anywhere_names_the_file_it_is(self) -> None:
        """Two scans of one book paginate differently, so a page needs a file."""
        held = declared(self.record())

        nameless = sorted(key for key, one in held.items() if not one.get("file"))

        self.assertEqual(nameless, [])

    def test_every_citation_names_one_of_them(self) -> None:
        held = self.record()
        keys = set(declared(held))

        astray = sorted({named for _, named in cited(held) if named not in keys})

        self.assertEqual(astray, [])

    def test_there_is_a_record_to_check(self) -> None:
        """A file holding only an empty block would satisfy every line above."""
        held = self.record()

        self.assertGreater(len([key for key in held if key != "documents"]), 0)

    def test_the_reader_of_that_finds_a_citation_wherever_it_sits(self) -> None:
        """Driven against a shape no member has, so it is the walk being tested."""
        held = {
            "facts": {"pin": {"document": "sheet", "page": 6}},
            "parts": [{"timing": [{"document": "book"}]}],
            "note": "not a citation",
        }

        self.assertEqual(
            sorted(cited(held)),
            [(".facts.pin", "sheet"), (".parts[0].timing[0]", "book")],
        )

    def test_and_finds_a_block_declared_beside_a_part(self) -> None:
        held = {
            "documents": {"a": {"file": "a.pdf"}},
            "parts": [{"documents": {"b": {"file": "b.pdf"}}}],
        }

        self.assertEqual(sorted(declared(held)), ["a", "b"])

    def test_a_block_declared_beside_a_part_is_read_as_well_as_a_top_level_one(
        self,
    ) -> None:
        """Two makers, two blocks. Where it sits is arrangement, not vocabulary."""
        held = {
            "documents": {},
            "parts": [
                {"documents": {"sheet": {"file": "a.pdf"}}},
                {"documents": {"book": {"file": "b.pdf"}}},
            ],
        }

        self.assertEqual(sorted(declared(held)), ["book", "sheet"])

    def test_a_source_reached_through_a_sibling_still_has_to_name_the_sibling(
        self,
    ) -> None:
        """A digest somebody else read is a pin, and a reader has to know whose."""
        held = {"documents": {"manual": {"file": "book1.pdf", "through": "snes-graphics-python"}}}

        borrowed = {key: one["through"] for key, one in declared(held).items() if "through" in one}

        self.assertEqual(borrowed, {"manual": "snes-graphics-python"})

    def test_an_empty_block_is_a_declaration_and_not_a_missing_one(self) -> None:
        """Three members have no document, and that absence is the claim."""
        held = {"documents": {}, "facts": {"pin": 1}}

        self.assertIsInstance(held.get("documents"), dict)
        self.assertEqual(declared(held), {})
        self.assertEqual(cited(held), [])

    def test_a_record_citing_a_key_that_is_not_declared_is_reported(self) -> None:
        held = {"documents": {"sheet": {"file": "a.pdf"}}, "facts": {"document": "elsewhere"}}

        astray = sorted({named for _, named in cited(held) if named not in set(declared(held))})

        self.assertEqual(astray, ["elsewhere"])

    def test_and_a_source_with_no_file_beside_it_is_reported(self) -> None:
        held = {"documents": {"sheet": {"title": "a manual with no file named"}}}

        nameless = sorted(key for key, one in declared(held).items() if not one.get("file"))

        self.assertEqual(nameless, ["sheet"])


class EveryModuleIsReachedTest(unittest.TestCase):
    """That no module sits in the package with nothing reaching it.

    A module nothing imports and the package does not publish is dead, and dead
    code is worse than absent code when it holds names that also live somewhere
    real. One member carried a `dump.py` defining `read` and `has_copier_stub`
    beside the published ones in `header.py`, superseded by a sibling repository
    and left behind. Both READMEs described it as not exported and not imported,
    which is a defect written down rather than fixed.

    Nothing else catches it. The linter sees a module it was never asked about,
    the type checker checks it and finds it sound, coverage measures it and finds
    it tested, and the one-definition check above is exceptions-only for reasons
    of its own. Every gate passes on code no caller can run.

    Reached means one of two things, and the second is why this reads imports
    rather than asking `dir()`. A module the package binds as an attribute is
    reached by a caller. A module only ever imported by a sibling module is
    reached too, and never appears on the package.

    Test files do not count, and that is the whole difficulty. A dead module
    usually has a test file beside it, written when the module was alive, and it
    is the only thing left importing it. Counting that would make the module look
    reached by the very file that proves nobody else needs it, which is exactly
    what this check found when it was first written and first run.

    A module nobody imports is reached anyway when a person runs it. The doctor
    is exactly that: it is deliberately importable by nothing, because it has to
    survive a package that will not import, and it is run as a file. What makes
    it an entry point rather than dead code is a `__main__` guard, so that is
    what this looks for rather than the doctor's name.
    """

    def an_entry_point(self, path: Path) -> bool:
        """Whether a module is meant to be run rather than imported."""
        return any(
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            for node in ast.walk(ast.parse(path.read_text()))
        )

    def entry_points(self) -> set[str]:
        return {
            path.stem
            for path in Path(PACKAGE.__file__ or "").resolve().parent.glob("*.py")
            if not path.name.endswith(".test.py") and self.an_entry_point(path)
        }

    def modules(self) -> set[str]:
        """Every module file in the package, by stem."""
        return {
            path.stem
            for path in Path(PACKAGE.__file__ or "").resolve().parent.glob("*.py")
            if not path.name.endswith(".test.py") and path.stem != "__init__"
        }

    def imported(self, where: Path | None = None) -> set[str]:
        """Every module name any file in the repository imports, however written."""
        held = ROOT if where is None else where
        name = PACKAGE.__name__
        found: set[str] = set()
        for path in sorted(held.glob("**/*.py")):
            if "node_modules" in path.parts or path.name.endswith(".test.py"):
                continue
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if not (node.level or (node.module or "").split(".")[0] == name):
                        continue
                    if node.module:
                        found.add(node.module.rsplit(".", 1)[-1])
                    found.update(one.name for one in node.names)
                elif isinstance(node, ast.Import):
                    for one in node.names:
                        if one.name.split(".")[0] == name:
                            found.add(one.name.rsplit(".", 1)[-1])
        return found

    def test_every_module_in_the_package_is_reached_by_something(self) -> None:
        published = set(PACKAGE.__all__) | {
            name for name in dir(PACKAGE) if isinstance(getattr(PACKAGE, name), types.ModuleType)
        }

        stranded = sorted(self.modules() - published - self.imported() - self.entry_points())

        self.assertEqual(stranded, [])

    def test_the_doctor_is_reached_by_being_run_rather_than_imported(self) -> None:
        self.assertIn("doctor", self.entry_points())

    def test_a_module_with_no_main_guard_is_not_an_entry_point(self) -> None:
        """So the carve-out cannot be claimed by a module nobody can run."""
        where = Path(tempfile.mkdtemp()) / "quiet.py"
        where.write_text("VALUE = 1\n")

        self.assertFalse(self.an_entry_point(where))

    def test_the_reader_of_that_counts_a_module_a_sibling_imports(self) -> None:
        """Driven against a tree of its own, so it is the walk being tested."""
        where = Path(tempfile.mkdtemp())
        (where / "one.py").write_text(f"from {PACKAGE.__name__} import held\n")

        self.assertIn("held", self.imported(where))

    def test_and_one_reached_only_by_a_relative_import(self) -> None:
        where = Path(tempfile.mkdtemp())
        (where / "one.py").write_text("from . import sibling\n")

        self.assertIn("sibling", self.imported(where))

    def test_and_does_not_count_a_module_reached_only_by_its_own_test(self) -> None:
        """The case this check exists for, and the one it first got wrong."""
        where = Path(tempfile.mkdtemp())
        (where / "stranded.test.py").write_text("from . import stranded\n")

        self.assertNotIn("stranded", self.imported(where))

    def test_and_a_module_reached_by_its_full_dotted_name(self) -> None:
        """The dotted form rather than the from-import one, which nothing here writes.

        Both reach a module. Only one of them is written in this family, so the
        other would go unread by a walk built from what the source happens to
        contain, and a module reached only that way would read as stranded.
        """
        where = Path(tempfile.mkdtemp())
        (where / "one.py").write_text(f"import {PACKAGE.__name__}.reached\n")

        self.assertIn("reached", self.imported(where))

    def test_and_ignores_a_module_from_somewhere_else_entirely(self) -> None:
        where = Path(tempfile.mkdtemp())
        (where / "one.py").write_text("from json import loads\n")

        self.assertNotIn("loads", self.imported(where))


class EveryLinkResolvesTest(unittest.TestCase):
    """That a link to a file in this repository points at a file that is here.

    The link survey beside this one asks the network whether an address still
    answers. Nothing asked the same question of a link that never leaves the
    repository, and three members linked their readme's "Citing this" section to
    a `CITATION.cff` that was not there, under a sentence promising a script kept
    it in step with the release. Every gate passed. A reader following it got a
    404 on the project's own front page.

    Markdown that renders is not markdown that resolves, which is what makes this
    invisible: GitHub shows the link as a link whether or not the target exists,
    and only a reader clicking it finds out.

    Anchors are dropped before resolving, because `file.md#section` is a link to
    `file.md`. A bare `#section` is a link within one document and is left alone.
    """

    LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

    def documents(self) -> list[Path]:
        """Every markdown file this repository tracks, wherever it sits."""
        held = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return [ROOT / one for one in held.stdout.split()]

    def tracked(self) -> set[str]:
        """Every path this repository tracks, and every directory along the way.

        Tracked rather than present, because the two differ on exactly the
        machine that matters. `specs/` and `docs/` are ignored here, so a link
        into one resolves on the author's disk and 404s for everybody who clones.
        One member linked its agent brief at `specs/current/` and only CI said so.
        """
        held = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        found: set[str] = set()
        for one in held.stdout.split():
            found.add(one)
            for parent in PurePosixPath(one).parents:
                if str(parent) != ".":
                    found.add(str(parent))
        return found

    def targets(self, where: Path) -> list[str]:
        """Every link in that file that names something in this repository."""
        found = []
        for target in self.LINK.findall(where.read_text()):
            held = target.split("#", 1)[0].split(" ", 1)[0]
            if not held or "://" in held or held.startswith(("mailto:", "#")):
                continue
            found.append(held)
        return found

    def unresolved(self, where: Path, known: set[str]) -> list[str]:
        """Those of them the repository does not track, said against its root."""
        inside = PurePosixPath(where.parent.relative_to(ROOT))
        return [
            f"{where.relative_to(ROOT)} -> {one}"
            for one in self.targets(where)
            if str(inside / one).rstrip("/") not in known
        ]

    def test_every_markdown_file_here_is_checked(self) -> None:
        """So a run over nothing cannot read as a run that found nothing."""
        named = {one.name for one in self.documents()}

        self.assertTrue({"README.md", "AGENTS.md", "FAMILY.md"} <= named, named)

    def test_and_every_link_into_this_repository_resolves(self) -> None:
        known = self.tracked()

        missing = sorted(one for held in self.documents() for one in self.unresolved(held, known))

        self.assertEqual(missing, [])

    def test_a_link_to_something_the_repository_does_not_track_is_reported(self) -> None:
        held = ROOT / "README.md"

        self.assertEqual(len(self.unresolved(held, set())), len(self.targets(held)))

    def test_a_link_to_something_it_does_track_is_not(self) -> None:
        held = ROOT / "README.md"

        self.assertEqual(self.unresolved(held, self.tracked()), [])

    def test_an_anchor_is_dropped_before_the_file_is_looked_for(self) -> None:
        where = Path(tempfile.mkdtemp()) / "one.md"
        where.write_text("see [a section](FAMILY.md#somewhere)\n")

        self.assertEqual(self.targets(where), ["FAMILY.md"])

    def test_and_a_link_within_one_document_is_left_alone(self) -> None:
        where = Path(tempfile.mkdtemp()) / "one.md"
        where.write_text("see [above](#somewhere)\n")

        self.assertEqual(self.targets(where), [])

    def test_an_address_on_the_network_is_not_this_check_s_business(self) -> None:
        where = Path(tempfile.mkdtemp()) / "one.md"
        where.write_text("see [a site](https://example.com/page)\n")

        self.assertEqual(self.targets(where), [])

    def test_a_path_this_repository_ignores_does_not_count_as_resolved(self) -> None:
        """The case only CI saw: a link into `specs/`, which is never tracked."""
        self.assertNotIn("specs/current", self.tracked())


class NothingOutsideTheStandardLibraryTest(unittest.TestCase):
    """That the readme's "no dependencies" is a fact rather than a habit.

    Every readme in the family advertises it, and for a while only some members
    checked it. Those built a bill of materials from a fresh environment holding
    the package and nothing else, and failed the release when a second name
    turned up. The three that consume a sibling as a submodule cannot do that,
    because a wheel built from one installs and then raises on its first import,
    so they publish no packaging block at all and had nothing holding the claim.

    Reading the imports holds every member to it the same way, needs no
    environment, and runs on a machine with no network. What it allows is the
    standard library, the package itself, `conformance` beside it, and the
    submodules this repository declares in `.gitmodules`, which are vendored
    rather than depended on.

    `conformance` is allowed because it is a directory this repository ships, not
    something fetched. One doctor reads the exhaustive check from it to say
    whether that check can run here, which is the doctor doing its job.
    """

    def declared_submodules(self, root: Path | None = None) -> set[str]:
        """Every sibling this repository carries, by the package name it provides.

        Read from `.gitmodules` rather than from a list here, so a member that
        gains or drops a submodule needs no edit. It takes a root so it can be
        driven against a repository shaped like one that has them, which three
        members do and the other seven do not.
        """
        where = ROOT if root is None else root
        held = where / ".gitmodules"
        if not held.is_file():
            return set()
        found = set()
        for line in held.read_text().splitlines():
            if not line.strip().startswith("path = "):
                continue
            name = line.strip().removeprefix("path = ").strip()
            for path in sorted((where / name).glob("*/__init__.py")):
                found.add(path.parent.name)
        return found

    def imports(self, where: Path) -> set[str]:
        """Every top-level module name imported by a file."""
        found: set[str] = set()
        for node in ast.walk(ast.parse(where.read_text())):
            if isinstance(node, ast.Import):
                found.update(one.name.split(".")[0] for one in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                found.add(node.module.split(".")[0])
        return found

    def test_the_package_imports_nothing_it_does_not_ship(self) -> None:
        allowed = (
            set(sys.stdlib_module_names)
            | {PACKAGE.__name__, "conformance"}
            | self.declared_submodules()
        )

        outside = sorted(
            f"{path.name}: {name}"
            for path in Path(PACKAGE.__file__ or "").resolve().parent.glob("*.py")
            if not path.name.endswith(".test.py")
            for name in self.imports(path)
            if name not in allowed
        )

        self.assertEqual(outside, [])

    def test_and_the_readme_says_so(self) -> None:
        self.assertIn("no dependencies", (ROOT / "README.md").read_text())

    def test_a_submodule_is_allowed_because_it_is_carried_rather_than_fetched(
        self,
    ) -> None:
        """Driven against a repository shaped like the three that have them."""
        where = Path(tempfile.mkdtemp())
        (where / ".gitmodules").write_text(
            '[submodule "sibling-python"]\n\tpath = sibling-python\n'
            "\turl = https://example.invalid/sibling.git\n"
        )
        (where / "sibling-python" / "sibling").mkdir(parents=True)
        (where / "sibling-python" / "sibling" / "__init__.py").write_text("")

        self.assertEqual(self.declared_submodules(where), {"sibling"})

    def test_and_a_repository_with_none_declares_none(self) -> None:
        self.assertEqual(self.declared_submodules(Path(tempfile.mkdtemp())), set())

    def test_the_reader_of_that_sees_an_import_from_outside(self) -> None:
        """Driven against a file written for it, so it is the walk being tested."""
        where = Path(tempfile.mkdtemp()) / "one.py"
        where.write_text("import json\nimport numpy\nfrom yaml import safe_load\n")

        held = self.imports(where)

        self.assertEqual(sorted(held - set(sys.stdlib_module_names)), ["numpy", "yaml"])

    def test_and_reads_a_relative_import_as_the_package_itself(self) -> None:
        where = Path(tempfile.mkdtemp()) / "one.py"
        where.write_text("from . import sibling\nfrom .errors import Refused\n")

        self.assertEqual(self.imports(where), set())


class SharedFileTest(unittest.TestCase):
    """That every file the standard's table names is here.

    The table is the list, so adding a row is how a file becomes required. What
    counts as a row naming a file is anything with a directory in it or an
    extension on it. The first version of this asked for a slash or a `.md`,
    which quietly excused `CITATION.cff`: the row was added, the file was absent
    in three members, and this check said nothing. A neighbouring check caught it
    only because the readme happened to link to it.
    """

    NAMED = re.compile(r"^\| `([^`]+)` \|", re.M)

    FILE = re.compile(r"[./]")

    def promised(self) -> list[str]:
        return [row for row in self.NAMED.findall(FAMILY) if self.FILE.search(row)]

    def test_the_standard_names_every_file_this_repository_must_carry(self) -> None:
        missing = [row for row in self.promised() if not (ROOT / row).exists()]

        self.assertEqual(missing, [])

    def test_and_there_is_something_to_check(self) -> None:
        """Or a standard naming no file would pass for one every member kept."""
        self.assertGreater(len(self.promised()), 6)

    def test_a_file_named_with_no_directory_in_it_is_still_required(self) -> None:
        """The exclusion that let three members ship without a citation file."""
        self.assertIn("CITATION.cff", self.promised())


def catalogue(package: Any = None) -> dict[str, Any]:
    """The mapping of variants that package publishes, whatever it calls it.

    Found by shape rather than by name. A member calls its catalogue whatever the
    thing it models is called, `MODELS` for parts and `FORMATS` for layouts, and
    a check keyed to one name does not fail on the other: it finds nothing, skips
    itself, and reports a clean run over a catalogue it never looked at. That is
    how seven graphics formats went unchecked.

    The shape is a mapping from a name to something carrying that same name and a
    tuple of aliases, which is what every catalogue in the family is and what the
    checks below actually need.

    It takes a package so it can be handed one that should fail it. Which of its
    branches a member exercises depends on what that member happens to publish
    and on where the catalogue's name sorts, so left driven only by the package
    it lives in, two of them are never taken anywhere.
    """
    held = PACKAGE if package is None else package
    for name in sorted(getattr(held, "__all__", ())):
        found = getattr(held, name, None)
        if not isinstance(found, dict) or not found:
            continue
        if all(hasattr(one, "name") and hasattr(one, "aliases") for one in found.values()):
            return dict(found)
    return {}


VARIANTS: dict[str, Any] = catalogue()
"""Every variant this package accepts, read from the package rather than listed.

A member that has none publishes no such mapping, and the checks below say they
were skipped rather than passing in silence.

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


class CatalogueReaderTest(unittest.TestCase):
    """That the reader finds a catalogue by shape and steps over what is not one.

    Driven against packages built here rather than against this one. Which
    branches a real package exercises depends on what it publishes and on where
    its catalogue's name sorts, so a reader left to be driven by its own package
    has branches nobody has ever taken.
    """

    def package(self, **published: Any) -> Any:
        held: Any = types.ModuleType("published")
        held.__all__ = sorted(published)
        for name, one in published.items():
            setattr(held, name, one)
        return held

    def variant(self, name: str) -> Any:
        return type("Variant", (), {"name": name, "aliases": ()})()

    def test_it_finds_a_catalogue_whatever_the_package_calls_it(self) -> None:
        held = self.package(FORMATS={"4bpp": self.variant("4bpp")})

        self.assertEqual(sorted(catalogue(held)), ["4bpp"])

    def test_and_finds_it_under_any_other_name(self) -> None:
        held = self.package(MODELS={"z80": self.variant("z80")})

        self.assertEqual(sorted(catalogue(held)), ["z80"])

    def test_it_steps_over_a_published_name_that_is_not_a_mapping(self) -> None:
        held = self.package(DEFAULT_MODEL="z80", MODELS={"z80": self.variant("z80")})

        self.assertEqual(sorted(catalogue(held)), ["z80"])

    def test_and_over_a_mapping_with_nothing_in_it(self) -> None:
        held = self.package(EMPTY={}, MODELS={"z80": self.variant("z80")})

        self.assertEqual(sorted(catalogue(held)), ["z80"])

    def test_and_over_a_mapping_whose_entries_are_not_variants(self) -> None:
        """A package can publish a lookup table that is not a catalogue."""
        held = self.package(SIZES={"small": 8, "large": 64})

        self.assertEqual(catalogue(held), {})

    def test_a_package_publishing_no_catalogue_answers_with_nothing(self) -> None:
        held = self.package(decode=len)

        self.assertEqual(catalogue(held), {})

    def test_and_so_does_one_publishing_nothing_at_all(self) -> None:
        self.assertEqual(catalogue(types.ModuleType("bare")), {})


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

    def test_and_it_is_this_repository_s_floor(self) -> None:
        """Not one belonging to a member this one consumes as a submodule.

        A member with a submodule on the import path has two packages called
        `conformance` reachable at once, and whichever sits earlier on the path
        wins. Put the submodule first and this check imports the wrong floor,
        finds a positive number, and passes: it was measuring a package this
        repository does not own. That is what it did, in two members, until this
        line existed.
        """
        from conformance import speed

        held = Path(speed.__file__ or "").resolve()

        self.assertEqual(held, ROOT / "conformance" / "speed.py", held)

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
        """Every class this package hands a caller, whether directly or through a module.

        The first condition is one test rather than two nested ones because the
        inner one has no false case in a member that publishes only its own
        classes, and a branch nothing can take reads as a gap in the gate. A type
        from outside the package now falls through to the second condition, which
        is false for it, so the outcome is unchanged.
        """
        found = []
        for name in dir(PACKAGE):
            held = getattr(PACKAGE, name)
            if (
                isinstance(held, type)
                and not issubclass(held, BaseException)
                and held.__module__.startswith(PACKAGE.__name__)
            ):
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
        """Or a package publishing no class would pass for one that slotted them all."""
        self.assertGreater(len(self.published()), 0)


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

    Read with the tokeniser rather than a line at a time. A docstring is free to
    carry a line beginning with a hash, and it usually does exactly where the
    docstring is worth reading: a worked example with the answer written beside
    it. A reader that cannot tell the two apart reports a module's own example as
    a comment, which is a finding against the one thing this rule is trying to
    encourage.

    `**/*.py` never reaches into `__pycache__`, which holds `.pyc` and nothing
    else, so there is no directory to skip.
    """
    found = []
    for path in sorted(where.glob("**/*.py")):
        with path.open("rb") as opened:
            for token in tokenize.tokenize(opened.readline):
                if token.type != tokenize.COMMENT:
                    continue
                body = token.string.lstrip("#").strip()
                if body and not body.startswith(DIRECTIVE):
                    found.append(f"{path.name}:{token.start[0]}")
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

        It opens with a count and the word for what is being counted, and the
        word is the member's own: a processor covers parts, a board covers
        layouts, a header fix covers images. Demanding one noun would make every
        member that is not a processor write down something it does not model.
        """
        held = self.readme().split("## ")[0]

        self.assertTrue(re.search(r"^\*\*[0-9,]+\*\* [a-z]", held, re.M), held[:400])

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
        divider of bare hashes, and a hash inside a docstring, which is not a
        comment at all however much it looks like one. Only the sentence is prose.
        """
        with tempfile.TemporaryDirectory() as where:
            written = Path(where) / "sample.py"
            written.write_text(
                "# ruff: noqa: E501\n"
                "# noqa: E743 -- the register really is called l\n"
                "x = 1  # type: ignore[assignment]\n"
                "#\n"
                "# the accumulator is eight bits wide\n"
                "def f() -> None:\n"
                '    """One worked line, with the answer beside it.\n'
                "\n"
                "        resolve(address).region\n"
                "        # 'work-ram', not cartridge\n"
                '    """\n'
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

    def test_a_protocol_stub_is_excluded_from_the_count_both_ways(self) -> None:
        """A pattern is checked against a line rather than read for plausibility.

        These live in a TOML literal string, where a doubled backslash is two
        characters rather than an escape, so a pattern can look right in the file
        and match nothing at all. Two members shipped exactly that, and it stayed
        invisible because the newest runtime drops a protocol's stub before
        coverage sees it and the older ones the pipeline runs do not. The gate
        then meant one thing locally and another in CI.
        """
        also = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["coverage"]["report"]
        patterns = also.get("exclude_also", [])

        inline = [one for one in patterns if re.search(one, "    def step(self) -> int: ...")]
        alone = [one for one in patterns if re.search(one, "        ...")]

        self.assertTrue(inline, patterns)
        self.assertTrue(alone, patterns)

    def test_and_a_pattern_that_matches_neither_would_be_reported(self) -> None:
        """Driven against the doubled form the two members actually shipped."""
        doubled = r"^\\s*\\.\\.\\.$"

        self.assertIsNone(re.search(doubled, "        ..."))


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
        """Or an empty list would pass for one holding no module."""
        self.assertGreater(len(PACKAGE.__all__), 0)


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
