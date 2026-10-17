from __future__ import annotations

import ast
import importlib
import inspect
import json
import posixpath
import re
import subprocess
import sys
import tempfile
import tokenize
import tomllib
import types
import unittest
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Protocol

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mos65xx  # noqa: E402

FAMILY = (ROOT / "FAMILY.md").read_text()

KIND = "Clocked part"

CLOCKED = KIND == "Clocked part"

PACKAGE: Any = mos65xx

A_MODEL = sorted(PACKAGE.MODELS)[0] if hasattr(PACKAGE, "MODELS") else ""


def why_it_cannot_build_here() -> str | None:
    asked = getattr(PACKAGE, "why_not", None)
    return asked() if callable(asked) else None


BUILDABLE = why_it_cannot_build_here() is None


A_PART = KIND == "Part"


SOLD_AS_A_COMPONENT = True

INTERFACE = (
    "step",
    "run_for",
    "run_until",
    "reset",
    "held",
)

INTERRUPT_LINES = ("irq", "nmi")

COUNTERS = ("cycles", "steps")


class Part(Protocol):
    cycles: int
    steps: int

    def step(self) -> int: ...

    def run_for(self, cycles: int) -> int: ...

    def run_until(self, predicate: Any, limit: int | None = None) -> Any: ...

    def reset(self) -> Any: ...

    def held(self) -> bool: ...


def a_part() -> Part:
    part: Part = PACKAGE.Cpu(A_MODEL)
    return part


def store_attribute() -> str:
    part = PACKAGE.Cpu(A_MODEL)
    found = [name for name in ("memory", "stores") if getattr(part, name, None) is not None]
    assert found, "a clocked part keeps its store on `memory` or on `stores`"
    return found[0]


def accounts_for_one_interrupt(node: Any) -> bool:
    if isinstance(node, dict):
        if any("interrupt" in str(key).lower() for key in node):
            return True
        return any(accounts_for_one_interrupt(one) for one in node.values())
    if isinstance(node, list):
        return any(accounts_for_one_interrupt(one) for one in node)
    return "interrupt" in str(node).lower()


def at_the_start(part: Any) -> None:
    held = getattr(part, "registers", part)
    held.pc = 0x0000


def a_running_part() -> Part:
    part = PACKAGE.Cpu(A_MODEL, fill=0)
    at_the_start(part)
    checked: Part = part
    return checked


class ModelsAClockedPartTest(unittest.TestCase):
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

    def test_and_every_interrupt_line_the_part_has(self) -> None:
        part = a_part()

        absent = [name for name in INTERRUPT_LINES if not hasattr(part, name)]

        self.assertEqual(absent, [])

    def test_and_the_record_accounts_for_what_lines_it_names(self) -> None:
        self.assertTrue(accounts_for_one_interrupt(json.loads(RECORD.read_text())))

    def test_a_record_naming_an_interrupt_as_a_key_is_read(self) -> None:
        self.assertTrue(accounts_for_one_interrupt({"facts": {"interruptVector": 4}}))

    def test_and_one_naming_it_only_in_a_sentence(self) -> None:
        self.assertTrue(accounts_for_one_interrupt({"notStated": ["what the interrupt pin does"]}))

    def test_and_one_naming_it_inside_a_list(self) -> None:
        self.assertTrue(accounts_for_one_interrupt([{"note": "one interrupt line"}]))

    def test_and_a_record_that_never_mentions_one_is_reported(self) -> None:
        self.assertFalse(
            accounts_for_one_interrupt({"facts": {"window": [1, 2]}, "note": "a part"})
        )

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

    def test_a_reset_hands_the_part_back(self) -> None:
        part = a_part()

        self.assertIs(part.reset(), part)

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
    "MODELS",
    "UNSET_SEED",
    "Clock",
    "ClockClosed",
    "RunLimit",
    "UnknownModelError",
)


PART_SURFACE = (
    "Chip",
    "MODELS",
    "Model",
    "UnknownModelError",
)


def buildable_variants(package: Any = None, variants: Any = None) -> list[str]:
    known = VARIANTS if variants is None else variants
    asked = getattr(PACKAGE if package is None else package, "available", None)
    if not callable(asked):
        return sorted(known)
    held = asked()
    if not isinstance(held, Mapping):
        return sorted(known)
    return sorted(name for name in known if name in held)


class BuildableVariantTest(unittest.TestCase):
    NAMED: ClassVar[dict[str, object]] = {"one": object(), "two": object()}

    class Silent:
        pass

    class Odd:
        @staticmethod
        def available() -> int:
            return 7

    class Partial:
        @staticmethod
        def available() -> dict[str, int]:
            return {"two": 1}

    def test_a_member_that_publishes_no_catalogue_can_build_everything_it_names(self) -> None:
        self.assertEqual(buildable_variants(self.Silent(), self.NAMED), ["one", "two"])

    def test_and_so_can_one_whose_catalogue_is_not_a_mapping(self) -> None:
        self.assertEqual(buildable_variants(self.Odd(), self.NAMED), ["one", "two"])

    def test_a_member_holding_one_file_can_build_that_one(self) -> None:
        self.assertEqual(buildable_variants(self.Partial(), self.NAMED), ["two"])


class PublishedSurfaceTest(unittest.TestCase):
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
        built = PACKAGE.Cpu(A_MODEL)

        self.assertEqual(type(built).__name__, "Cpu")

    @unittest.skipUnless(A_PART and BUILDABLE, "no part can be built here")  # pragma: no cover
    def test_a_part_is_built_by_Chip_taking_the_model_first(self) -> None:  # noqa: N802
        built = PACKAGE.Chip(A_MODEL)

        self.assertEqual(type(built).__name__, "Chip")

    @unittest.skipUnless(A_PART and BUILDABLE, "no part can be built here")  # pragma: no cover
    def test_and_it_takes_a_model_by_name(self) -> None:
        for name in buildable_variants():
            self.assertEqual(PACKAGE.Chip(name).model, name, name)

    @unittest.skipUnless(A_PART, "not a part in the sense this checks")  # pragma: no cover
    def test_and_refuses_a_name_no_model_goes_by(self) -> None:
        with self.assertRaises(PACKAGE.UnknownModelError):
            PACKAGE.Chip("no model goes by this name")

    @unittest.skipUnless(A_PART and BUILDABLE, "no part can be built here")  # pragma: no cover
    def test_a_part_that_holds_what_it_held_offers_a_reset(self) -> None:
        self.assertTrue(callable(getattr(PACKAGE.Chip(A_MODEL), "reset", None)))

    @unittest.skipUnless(A_PART and BUILDABLE, "no part can be built here")  # pragma: no cover
    def test_and_that_reset_hands_the_part_back(self) -> None:
        built = PACKAGE.Chip(A_MODEL)

        self.assertIs(built.reset(), built)

    @unittest.skipUnless(A_PART, "not a part in the sense this checks")  # pragma: no cover
    def test_and_what_that_reset_does_is_accounted_for(self) -> None:
        self.assertTrue(accounts_for_a_reset(json.loads(RECORD.read_text())))

    @unittest.skipUnless(A_PART, "not a part in the sense this checks")  # pragma: no cover
    def test_the_reader_of_that_finds_a_reset_named_as_a_key(self) -> None:
        self.assertTrue(accounts_for_a_reset({"facts": {"resetPulseCycles": {"value": 4}}}))

    @unittest.skipUnless(A_PART, "not a part in the sense this checks")  # pragma: no cover
    def test_and_one_named_only_in_a_sentence(self) -> None:
        self.assertTrue(accounts_for_a_reset({"notStated": ["what the RESET line does"]}))

    @unittest.skipUnless(A_PART, "not a part in the sense this checks")  # pragma: no cover
    def test_and_reports_a_record_that_never_mentions_one(self) -> None:
        self.assertFalse(accounts_for_a_reset({"facts": {"window": [1, 2]}, "note": "a chip"}))

    @unittest.skipUnless(A_PART, "not a part in the sense this checks")  # pragma: no cover
    def test_every_name_a_part_promises_is_published(self) -> None:
        absent = [name for name in PART_SURFACE if name not in PACKAGE.__all__]

        self.assertEqual(absent, [])

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_the_store_type_is_reachable_without_a_private_import(self) -> None:
        held = getattr(PACKAGE.Cpu(A_MODEL), store_attribute())

        self.assertIn(type(held).__name__, PACKAGE.__all__)

    def test_and_so_is_everything_it_can_raise(self) -> None:
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


class OneDefinitionTest(unittest.TestCase):
    def modules(self) -> list[Any]:
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
        hidden = [
            name
            for name in self.defined()
            if not name.startswith("_") and name not in PACKAGE.__all__
        ]

        self.assertEqual(hidden, [])

    def test_there_are_exceptions_to_check(self) -> None:
        self.assertGreater(len(self.modules()), 0)
        self.assertGreater(len(self.defined()), 0)

    def test_an_exception_imported_into_a_module_is_not_counted_as_defined_there(
        self,
    ) -> None:
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


def declared(node: Any) -> dict[str, Any]:
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


def quoted_sentences(node: Any) -> int:
    if isinstance(node, dict):
        held = sum(1 for key in node if "quote" in str(key).lower())
        return held + sum(quoted_sentences(one) for one in node.values())
    if isinstance(node, list):
        return sum(quoted_sentences(one) for one in node)
    return 0


QUOTED = quoted_sentences(json.loads(RECORD.read_text())) if RECORD.is_file() else 0


class OneVocabularyForADocumentTest(unittest.TestCase):
    def record(self) -> Any:
        return json.loads(RECORD.read_text())

    def test_the_standard_asks_for_a_documents_block(self) -> None:
        self.assertIn("`documents` block", FAMILY)

    def test_the_record_declares_its_sources_in_one(self) -> None:
        self.assertIsInstance(self.record().get("documents"), dict)

    def test_every_source_declared_anywhere_names_the_file_it_is(self) -> None:
        held = declared(self.record())

        nameless = sorted(key for key, one in held.items() if not one.get("file"))

        self.assertEqual(nameless, [])

    def test_every_citation_names_one_of_them(self) -> None:
        held = self.record()
        keys = set(declared(held))

        astray = sorted({named for _, named in cited(held) if named not in keys})

        self.assertEqual(astray, [])

    def test_there_is_a_record_to_check(self) -> None:
        held = self.record()

        self.assertGreater(len([key for key in held if key != "documents"]), 0)

    def test_the_reader_of_that_finds_a_citation_wherever_it_sits(self) -> None:
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
        held = {"documents": {"manual": {"file": "book1.pdf", "through": "snes-graphics-python"}}}

        borrowed = {key: one["through"] for key, one in declared(held).items() if "through" in one}

        self.assertEqual(borrowed, {"manual": "snes-graphics-python"})

    def test_an_empty_block_is_a_declaration_and_not_a_missing_one(self) -> None:
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
    def an_entry_point(self, path: Path) -> bool:
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
        return {
            path.stem
            for path in Path(PACKAGE.__file__ or "").resolve().parent.glob("*.py")
            if not path.name.endswith(".test.py") and path.stem != "__init__"
        }

    def imported(self, where: Path | None = None) -> set[str]:
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
        where = Path(tempfile.mkdtemp()) / "quiet.py"
        where.write_text("VALUE = 1\n")

        self.assertFalse(self.an_entry_point(where))

    def test_the_reader_of_that_counts_a_module_a_sibling_imports(self) -> None:
        where = Path(tempfile.mkdtemp())
        (where / "one.py").write_text(f"from {PACKAGE.__name__} import held\n")

        self.assertIn("held", self.imported(where))

    def test_and_one_reached_only_by_a_relative_import(self) -> None:
        where = Path(tempfile.mkdtemp())
        (where / "one.py").write_text("from . import sibling\n")

        self.assertIn("sibling", self.imported(where))

    def test_and_does_not_count_a_module_reached_only_by_its_own_test(self) -> None:
        where = Path(tempfile.mkdtemp())
        (where / "stranded.test.py").write_text("from . import stranded\n")

        self.assertNotIn("stranded", self.imported(where))

    def test_and_a_module_reached_by_its_full_dotted_name(self) -> None:
        where = Path(tempfile.mkdtemp())
        (where / "one.py").write_text(f"import {PACKAGE.__name__}.reached\n")

        self.assertIn("reached", self.imported(where))

    def test_and_ignores_a_module_from_somewhere_else_entirely(self) -> None:
        where = Path(tempfile.mkdtemp())
        (where / "one.py").write_text("from json import loads\n")

        self.assertNotIn("loads", self.imported(where))


class EveryLinkResolvesTest(unittest.TestCase):
    LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

    def documents(self) -> list[Path]:
        held = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return [ROOT / one for one in held.stdout.split()]

    def tracked(self) -> set[str]:
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
        found = []
        for target in self.LINK.findall(where.read_text()):
            held = target.split("#", 1)[0].split(" ", 1)[0]
            if not held or "://" in held or held.startswith(("mailto:", "#")):
                continue
            found.append(held)
        return found

    def said_from_the_root(self, inside: PurePosixPath, target: str) -> str:
        return posixpath.normpath(str(inside / target)).rstrip("/")

    def unresolved(self, where: Path, known: set[str]) -> list[str]:
        inside = PurePosixPath(where.parent.relative_to(ROOT))
        return [
            f"{where.relative_to(ROOT)} -> {one}"
            for one in self.targets(where)
            if self.said_from_the_root(inside, one) not in known
        ]

    def test_every_markdown_file_here_is_checked(self) -> None:
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

    def test_a_link_out_of_a_subdirectory_resolves_to_what_it_names(self) -> None:
        held = self.said_from_the_root(PurePosixPath("cartridges"), "../manifest.json")

        self.assertEqual(held, "manifest.json")

    def test_and_one_that_climbs_past_the_root_still_resolves_to_nothing(self) -> None:
        held = self.said_from_the_root(PurePosixPath("."), "../outside.json")

        self.assertEqual(held, "../outside.json")

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
        self.assertNotIn("specs/current", self.tracked())


class NothingOutsideTheStandardLibraryTest(unittest.TestCase):
    def declared_submodules(self, root: Path | None = None) -> set[str]:
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
        where = Path(tempfile.mkdtemp()) / "one.py"
        where.write_text("import json\nimport numpy\nfrom yaml import safe_load\n")

        held = self.imports(where)

        self.assertEqual(sorted(held - set(sys.stdlib_module_names)), ["numpy", "yaml"])

    def test_and_reads_a_relative_import_as_the_package_itself(self) -> None:
        where = Path(tempfile.mkdtemp()) / "one.py"
        where.write_text("from . import sibling\nfrom .errors import Refused\n")

        self.assertEqual(self.imports(where), set())


class EveryQuoteIsCheckableTest(unittest.TestCase):
    @unittest.skipUnless(QUOTED, "this record quotes nothing")
    def test_a_record_that_quotes_ships_a_checker_for_it(self) -> None:
        self.assertTrue((ROOT / "conformance" / "quotes.py").is_file())

    @unittest.skipUnless(QUOTED, "this record quotes nothing")
    def test_and_the_pipeline_runs_it(self) -> None:
        held = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        self.assertIn("conformance.quotes", held)

    def test_the_reader_of_that_counts_a_quote_however_its_key_is_spelled(self) -> None:
        self.assertEqual(quoted_sentences({"a": {"quote": "x"}, "b": {"countRangeQuote": "y"}}), 2)

    def test_and_counts_none_in_a_record_that_quotes_nothing(self) -> None:
        self.assertEqual(quoted_sentences({"facts": {"window": [1, 2]}, "note": "a chip"}), 0)


class EveryRecordStatesItsAuthorityTest(unittest.TestCase):
    def record(self) -> Any:
        return json.loads(RECORD.read_text())

    def authority(self) -> Any:
        held = self.record().get("authority")
        return held if isinstance(held, dict) else {}

    def test_the_record_states_the_order_it_answers_in(self) -> None:
        self.assertTrue(self.authority().get("order"))

    def test_and_the_order_is_a_list_of_rungs_rather_than_a_sentence(self) -> None:
        self.assertIsInstance(self.authority().get("order"), list)

    def test_and_says_why_it_is_that_order(self) -> None:
        self.assertTrue(str(self.authority().get("why", "")).strip())

    def test_the_record_names_what_this_member_is_held_to(self) -> None:
        held = self.authority().get("comparedAgainst")
        assert isinstance(held, dict)

        self.assertTrue(str(held.get("what", "")).strip())

    def test_and_the_runner_that_does_the_comparing_is_here(self) -> None:
        held = self.authority().get("comparedAgainst")
        assert isinstance(held, dict)

        self.assertTrue((ROOT / str(held.get("runner"))).is_file(), held.get("runner"))

    def test_the_standard_carries_the_ladder_this_is_measured_against(self) -> None:
        self.assertIn("The authority ladder", FAMILY)

    def test_a_record_with_no_ladder_at_all_is_reported(self) -> None:
        held = {"note": "layouts, pinned to the figures", "documents": {}}

        self.assertEqual(held.get("authority"), None)


class SharedFileTest(unittest.TestCase):
    NAMED = re.compile(r"^\| `([^`]+)` \|", re.M)

    FILE = re.compile(r"[./]")

    def promised(self) -> list[str]:
        return [row for row in self.NAMED.findall(FAMILY) if self.FILE.search(row)]

    def test_the_standard_names_every_file_this_repository_must_carry(self) -> None:
        missing = [row for row in self.promised() if not (ROOT / row).exists()]

        self.assertEqual(missing, [])

    def test_and_there_is_something_to_check(self) -> None:
        self.assertGreater(len(self.promised()), 6)

    def test_a_file_named_with_no_directory_in_it_is_still_required(self) -> None:
        self.assertIn("CITATION.cff", self.promised())


def accounts_for_a_reset(node: Any) -> bool:  # pragma: no cover
    if isinstance(node, dict):
        if any("reset" in str(key).lower() for key in node):
            return True
        return any(accounts_for_a_reset(one) for one in node.values())
    if isinstance(node, list):
        return any(accounts_for_a_reset(one) for one in node)
    return "reset" in str(node).lower()


def catalogue(package: Any = None) -> dict[str, Any]:
    held = PACKAGE if package is None else package
    for name in sorted(getattr(held, "__all__", ())):
        found = getattr(held, name, None)
        if not isinstance(found, dict) or not found:
            continue
        if all(hasattr(one, "name") and hasattr(one, "aliases") for one in found.values()):
            return dict(found)
    return {}


VARIANTS: dict[str, Any] = catalogue()


def built(name: str, readme: str) -> bool:
    return re.search(rf"""\w\(\s*["']{re.escape(name)}["']""", readme) is not None


@unittest.skipUnless(VARIANTS, "this package names no variants")
class DocumentedModelTest(unittest.TestCase):
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
        self.assertTrue(built("a-part", 'Chip("a-part")'))
        self.assertTrue(built("a-part", "Cpu('a-part')"))
        self.assertFalse(built("a-part", "the a-part is covered here"))
        self.assertFalse(built("a-part", "`a-part`"))


class CatalogueReaderTest(unittest.TestCase):
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
        held = self.package(MODELS={"z80": self.variant("z80")})

        self.assertEqual(sorted(catalogue(held)), ["z80"])

    def test_and_over_a_mapping_with_nothing_in_it(self) -> None:
        held = self.package(EMPTY={}, MODELS={"z80": self.variant("z80")})

        self.assertEqual(sorted(catalogue(held)), ["z80"])

    def test_and_over_a_mapping_whose_entries_are_not_variants(self) -> None:
        held = self.package(SIZES={"small": 8, "large": 64})

        self.assertEqual(catalogue(held), {})

    def test_a_package_publishing_no_catalogue_answers_with_nothing(self) -> None:
        held = self.package(decode=len)

        self.assertEqual(catalogue(held), {})

    def test_and_so_does_one_publishing_nothing_at_all(self) -> None:
        self.assertEqual(catalogue(types.ModuleType("bare")), {})


class ClaimedCountTest(unittest.TestCase):
    def counted(self) -> int:
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
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if re.search(r"python3? conformance/[a-z_]+\.py", line)
    ]


class StandardIsKeptTest(unittest.TestCase):
    def test_the_standard_names_the_errors_module_as_the_one_home(self) -> None:
        self.assertIn("errors.py", FAMILY)

    def test_and_this_repository_has_one(self) -> None:
        self.assertTrue((Path(PACKAGE.__file__ or "").resolve().parent / "errors.py").exists())

    def test_the_standard_says_a_tool_runs_as_a_module(self) -> None:
        self.assertIn("python3 -m conformance.name", FAMILY)

    def test_and_no_workflow_runs_one_as_a_script(self) -> None:
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
        self.assertEqual(as_a_script("run: python conformance/speed.py\n"), [1])
        self.assertEqual(as_a_script("run: python3 -m conformance.speed\n"), [])
        self.assertEqual(as_a_script("a\nb\npython conformance/links.py\n"), [3])

    def test_the_standard_promises_a_throughput_floor(self) -> None:
        self.assertIn("throughput floor", FAMILY)

    def test_and_this_repository_has_one_with_a_floor_to_beat(self) -> None:
        from conformance import speed

        self.assertGreater(speed.FLOOR, 0)

    def test_and_it_is_this_repository_s_floor(self) -> None:
        from conformance import speed

        held = Path(speed.__file__ or "").resolve()

        self.assertEqual(held, ROOT / "conformance" / "speed.py", held)

    def test_the_floor_is_checked_outside_the_coverage_step(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        self.assertIn("python -m conformance.speed", workflow)
        self.assertNotIn("coverage run -a conformance/speed.py", workflow)


@unittest.skipUnless(CLOCKED, "not a clocked part")
class SuppliedMemoryTest(unittest.TestCase):
    def test_a_supplied_store_is_the_one_the_part_uses(self) -> None:
        where = store_attribute()
        own = getattr(PACKAGE.Cpu(A_MODEL), where)

        built = PACKAGE.Cpu(A_MODEL, own)

        self.assertIs(getattr(built, where), own)

    def test_and_one_is_built_when_the_argument_is_left_out(self) -> None:
        built = PACKAGE.Cpu(A_MODEL)

        self.assertIsNotNone(getattr(built, store_attribute()))

    def test_the_standard_names_this_part_spelling(self) -> None:
        self.assertIn(f"cpu.{store_attribute()}", FAMILY)


def still_holding(classes: Any) -> list[str]:
    return [
        one.__qualname__
        for one in classes
        if any("__dict__" in vars(base) for base in one.__mro__[:-1])
    ]


class NoStrayAttributeTest(unittest.TestCase):
    def published(self) -> list[type]:
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

CLOCKED_SECTIONS = (
    "Running it at a real speed",
    "Models",
    "Nothing starts clean",
)

DIRECTIVE = ("noqa", "type:", "pragma", "ruff:", "mypy:", "isort:", "fmt:")

TEST_MARKERS = ("Arrange", "Act", "Assert")


def prose_comments(where: Path) -> list[str]:
    found = []
    for path in sorted(where.glob("**/*.py")):
        with path.open("rb") as opened:
            for token in tokenize.tokenize(opened.readline):
                if token.type != tokenize.COMMENT:
                    continue
                body = token.string.lstrip("#").strip()
                if body and not body.startswith(DIRECTIVE) and body not in TEST_MARKERS:
                    found.append(f"{path.name}:{token.start[0]}")
    return found


def mute_names(where: Path) -> list[str]:
    found = []
    for path in sorted(where.glob("**/*.test.py")):
        for name in re.findall(r"^    def test_(\w+)", path.read_text(), re.M):
            if len(name.split("_")) < 2:
                found.append(f"{path.name}:test_{name}")
    return found


TRANSLATIONS = ("README.ja.md", "README.zh-Hans.md", "README.zh-HK.md")

READMES = ("README.md", *TRANSLATIONS)

FENCE = re.compile(r"^```.*?^```$", re.M | re.S)

LINK = re.compile(r"\]\(([^)\s]+)\)")

UNDER_TAGLINE = re.compile(r"^# .+\n\n(?:.+\n)+\n(.+)$", re.M)


def fenced(text: str) -> list[str]:
    return FENCE.findall(text)


def heading_levels(text: str) -> list[int]:
    return [len(marks) for marks in re.findall(r"^(#{1,6}) ", FENCE.sub("", text), re.M)]


def switcher(text: str) -> str:
    found = UNDER_TAGLINE.search(FENCE.sub("", text))
    return found.group(1) if found else ""


def body_links(text: str) -> list[str]:
    unfenced = FENCE.sub("", text)
    return sorted(LINK.findall(unfenced.replace(switcher(text), "", 1)))


def switcher_gaps(name: str, text: str) -> list[str]:
    linked = set(LINK.findall(switcher(text)))
    others = [one for one in READMES if one != name]
    return [one for one in others if one not in linked] + [name] * (name in linked)


class TranslatedTest(unittest.TestCase):
    def english(self) -> str:
        return (ROOT / "README.md").read_text()

    def translated(self) -> dict[str, str]:
        return {name: (ROOT / name).read_text() for name in TRANSLATIONS if (ROOT / name).is_file()}

    def test_every_translation_is_there(self) -> None:
        # Arrange
        expected = list(TRANSLATIONS)

        # Act
        held = sorted(self.translated())

        # Assert
        self.assertEqual(held, sorted(expected))

    def test_every_readme_links_the_other_three_under_its_tagline(self) -> None:
        # Arrange
        held = {"README.md": self.english(), **self.translated()}

        # Act
        gaps = {name: switcher_gaps(name, text) for name, text in held.items()}

        # Assert
        self.assertEqual({name: gap for name, gap in gaps.items() if gap}, {})

    def test_every_translation_keeps_the_english_headings_level_by_level(self) -> None:
        # Arrange
        expected = heading_levels(self.english())

        # Act
        held = {name: heading_levels(text) for name, text in self.translated().items()}

        # Assert
        self.assertEqual({name: levels for name, levels in held.items() if levels != expected}, {})

    def test_every_translation_carries_the_english_code_byte_for_byte(self) -> None:
        # Arrange
        expected = fenced(self.english())

        # Act
        held = {name: fenced(text) for name, text in self.translated().items()}

        # Assert
        self.assertEqual([name for name, code in held.items() if code != expected], [])

    def test_every_translation_links_where_the_english_links(self) -> None:
        # Arrange
        expected = body_links(self.english())

        # Act
        held = {name: body_links(text) for name, text in self.translated().items()}

        # Assert
        self.assertEqual([name for name, links in held.items() if links != expected], [])

    def test_a_heading_inside_a_code_block_is_not_counted(self) -> None:
        # Arrange
        text = "# Title\n\n```bash\n# not a heading\n```\n\n## Part\n"

        # Act
        levels = heading_levels(text)

        # Assert
        self.assertEqual(levels, [1, 2])

    def test_a_switcher_that_links_to_itself_is_reported(self) -> None:
        # Arrange
        text = "# Title\n\nWhat it is.\n\n[English](README.md) | [日本語](README.ja.md) | 简体中文 | [HK](README.zh-HK.md)\n"

        # Act
        gaps = switcher_gaps("README.ja.md", text)

        # Assert
        self.assertEqual(gaps, ["README.zh-Hans.md", "README.ja.md"])

    def test_a_switcher_above_the_title_is_reported_missing(self) -> None:
        # Arrange
        text = "[日本語](README.ja.md) | [简体中文](README.zh-Hans.md) | [HK](README.zh-HK.md)\n\n# Title\n\nWhat it is.\n\nBody.\n"

        # Act
        gaps = switcher_gaps("README.md", text)

        # Assert
        self.assertEqual(gaps, ["README.ja.md", "README.zh-Hans.md", "README.zh-HK.md"])

    def test_a_readme_with_no_title_carries_no_switcher(self) -> None:
        # Arrange
        text = "[日本語](README.ja.md)\n\nBody.\n"

        # Act
        found = switcher(text)

        # Assert
        self.assertEqual(found, "")

    def test_the_switcher_line_is_not_compared_as_a_body_link(self) -> None:
        # Arrange
        text = "# Title\n\nWhat it is.\n\n[日本語](README.ja.md)\n\nSee [LICENSE](LICENSE).\n"

        # Act
        links = body_links(text)

        # Assert
        self.assertEqual(links, ["LICENSE"])


ANCHOR = re.compile(r'<a id="([^"]+)"></a>')


def slug(title: str) -> str:
    lowered = re.sub(r"[`*_\[\]()]", "", title).strip().lower()
    return re.sub(r"[^\w\- ]", "", lowered).replace(" ", "-")


def landings(text: str) -> set[str]:
    unfenced = FENCE.sub("", text)
    titled = {slug(title) for title in re.findall(r"^#{1,6} (.+)$", unfenced, re.M)}
    return titled | set(ANCHOR.findall(unfenced))


def in_page_links(text: str) -> set[str]:
    return set(re.findall(r"\]\(#([^)\s]+)\)", FENCE.sub("", text)))


class InPageLinkTest(unittest.TestCase):
    def test_every_in_page_link_in_every_readme_lands(self) -> None:
        # Arrange
        held = {name: (ROOT / name).read_text() for name in READMES if (ROOT / name).is_file()}

        # Act
        stray = {name: sorted(in_page_links(text) - landings(text)) for name, text in held.items()}

        # Assert
        self.assertEqual({name: links for name, links in stray.items() if links}, {})

    def test_a_translated_heading_lands_through_an_anchor(self) -> None:
        # Arrange
        text = '<a id="models"></a>\n\n## モデル\n\nSee [the models](#models).\n'

        # Act
        stray = in_page_links(text) - landings(text)

        # Assert
        self.assertEqual(stray, set())


class WrittenTheSameWayTest(unittest.TestCase):
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
        self.assertTrue(any(one.startswith("Driving it one") for one in self.headings()))

    @unittest.skipUnless(CLOCKED, "not a clocked part")
    def test_and_one_on_reading_a_program_without_running_it(self) -> None:
        self.assertIn("Reading without running", self.headings())

    def test_anything_it_adds_sits_between_the_interface_and_the_evidence(self) -> None:
        held = self.headings()
        added = [one for one in held if one not in SECTIONS and one not in CLOCKED_SECTIONS]
        interface = held.index("The interface")
        evidence = held.index("Is it right")

        stray = [one for one in added if not interface < held.index(one) < evidence]

        self.assertEqual(stray, [])

    def test_the_readme_opens_with_what_was_measured(self) -> None:
        held = self.readme().split("## ")[0]

        self.assertTrue(re.search(r"^\*\*[0-9,]+\*\* [a-z]", held, re.M), held[:400])

    def test_and_says_how_much_of_it_failed(self) -> None:
        held = self.readme().split("## ")[0]

        self.assertTrue(
            re.search(r"\*\*0\*\* (?:\w+ )?(?:failures|disagreements)", held), held[:400]
        )

    def test_and_what_it_costs_to_install(self) -> None:
        held = self.readme().split("## ")[0]

        self.assertIn("no dependencies", held)

    def test_no_source_file_carries_a_comment_a_tool_does_not_read(self) -> None:
        self.assertEqual(prose_comments(Path(PACKAGE.__file__ or "").resolve().parent), [])

    def test_a_bare_test_marker_is_not_prose(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        (where / "sample.py").write_text("# Arrange\nx = 1\n# Act now\n# Assert\n")

        # Act
        found = prose_comments(where)

        # Assert
        self.assertEqual(found, ["sample.py:3"])

    def test_nor_does_any_conformance_file(self) -> None:
        self.assertEqual(prose_comments(ROOT / "conformance"), [])

    def test_the_reader_of_that_tells_a_directive_from_prose(self) -> None:
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
        self.assertEqual(mute_names(ROOT), [])

    def test_the_checker_is_strict_everywhere_the_family_is(self) -> None:
        held = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]

        self.assertTrue(held["mypy"]["strict"])
        self.assertEqual(held["coverage"]["report"]["fail_under"], 100)
        self.assertEqual(held["ruff"]["line-length"], 100)

    def test_a_protocol_stub_is_excluded_from_the_count_both_ways(self) -> None:
        also = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["coverage"]["report"]
        patterns = also.get("exclude_also", [])

        inline = [one for one in patterns if re.search(one, "    def step(self) -> int: ...")]
        alone = [one for one in patterns if re.search(one, "        ...")]

        self.assertTrue(inline, patterns)
        self.assertTrue(alone, patterns)

    def test_and_a_pattern_that_matches_neither_would_be_reported(self) -> None:
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
    "arm6": (
        "3DO",
        "Archimedes",
        "RiscPC",
        "Risc PC",
        "Newton",
        "SNES",
        "Super Famicom",
        "Famicom",
        "Nintendo",
        "ST018",
        "ST010",
        "ST011",
        "Seta",
        "console",
        "cartridge",
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


NOT_THIS_PACKAGES_WORDS = ("conformance/family.test.py", "FAMILY.md")


def unquoted(text: str, suffix: str) -> str:
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
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add("." * node.level + (node.module or ""))
    return found


def reaching_inside(names: Iterable[str], package: str) -> list[str]:
    return sorted(
        name
        for name in names
        if name.startswith(".") or name == package or name.startswith(package + ".")
    )


class ErrorsCloseNoCycleTest(unittest.TestCase):
    def errors(self) -> Path:
        return Path(PACKAGE.__file__ or "").resolve().parent / "errors.py"

    def test_it_imports_nothing_from_this_package(self) -> None:
        self.assertEqual(reaching_inside(imported_by(self.errors()), PACKAGE.__name__), [])

    def test_the_reader_of_that_tells_the_package_from_the_standard_library(self) -> None:
        held = {"__future__", "re", "typing", PACKAGE.__name__, f"{PACKAGE.__name__}.core", "."}

        self.assertEqual(
            reaching_inside(held, PACKAGE.__name__),
            [".", PACKAGE.__name__, f"{PACKAGE.__name__}.core"],
        )

    def test_and_a_package_whose_name_merely_starts_the_same_is_not_inside(self) -> None:
        held = {f"{PACKAGE.__name__}asm", f"{PACKAGE.__name__}_tools"}

        self.assertEqual(reaching_inside(held, PACKAGE.__name__), [])

    def test_the_reader_of_that_sees_the_imports_that_are_there(self) -> None:
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


def unignored(where: Path, run: Any = None) -> list[str]:
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


SETTLED_SECTIONS = ("What is not in question", "What is deliberately not modelled")


def open_questions(where: Path | None = None) -> list[str]:
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
        held = self.held()
        added = [one for one in held if one not in AGENTS_SECTIONS]
        gates = held.index("Every gate, in the order to run them")
        settled = held.index("What is settled and what is not")

        self.assertTrue(all(settled < held.index(one) < gates for one in added), added)

    def test_the_count_of_open_questions_is_the_count_there_is(self) -> None:
        claimed = re.search(r"\*\*Not settled: (\d+) things\*\*", self.agents())

        assert claimed is not None
        self.assertEqual(int(claimed.group(1)), len(open_questions()))

    def test_and_counts_questions_rather_than_headings(self) -> None:
        held = (ROOT / "OPEN-QUESTIONS.md").read_text()

        self.assertLessEqual(len(open_questions()), len(re.findall(r"^### ", held, re.M)))


class PublishesNamesNotModulesTest(unittest.TestCase):
    def test_no_module_is_published_as_a_name(self) -> None:
        published = sorted(
            name
            for name in PACKAGE.__all__
            if isinstance(getattr(PACKAGE, name, None), types.ModuleType)
        )

        self.assertEqual(published, [])

    def test_a_module_is_still_reachable_without_being_published(self) -> None:
        self.assertTrue(hasattr(PACKAGE, "errors"))
        self.assertNotIn("errors", PACKAGE.__all__)

    def test_there_are_names_published(self) -> None:
        self.assertGreater(len(PACKAGE.__all__), 0)


class CarriesNobodyElsesWorkTest(unittest.TestCase):
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
        self.assertGreater(len(self.tracked()), 20)

    def test_the_ignore_file_here_covers_everything_on_its_own(self) -> None:
        self.assertEqual(unignored(ROOT), [])

    def test_the_reader_of_that_names_an_untracked_file(self) -> None:
        found = unignored(ROOT, self.saying("?? left/behind.txt\n M edited.py\n"))

        self.assertEqual(found, ["left/behind.txt"])

    def test_and_steps_over_one_that_is_merely_edited(self) -> None:
        found = unignored(ROOT, self.saying(" M edited.py\nA  added.py\n"))

        self.assertEqual(found, [])

    def test_a_run_that_failed_is_not_read_as_a_clean_tree(self) -> None:

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
        held = '{"quote": "SNES", "note": "SNES"}'

        self.assertEqual(unquoted(held, ".json"), held)

    def test_a_file_that_is_not_a_record_is_read_as_it_stands(self) -> None:
        held = "the SNES is named here"

        self.assertEqual(unquoted(held, ".md"), held)

    def test_and_so_is_one_that_claims_to_be_and_is_not(self) -> None:
        held = "{this is not json at all, and it names the SNES"

        self.assertEqual(unquoted(held, ".json"), held)

    def test_a_value_that_is_not_a_passage_is_stepped_over(self) -> None:
        held = '{"quote": 5, "quotes": [1, 2], "noteQuotes": {"1": 3}, "cycles": [1]}'

        self.assertEqual(_passages(json.loads(held)), [])


@unittest.skipUnless(SOLD_AS_A_COMPONENT, "this part only existed inside one machine")
class NamesNoMachineTest(unittest.TestCase):
    def names(self) -> tuple[str, ...]:
        return MACHINES[PACKAGE.__name__ if PACKAGE.__name__ in MACHINES else ROOT.name]

    def test_no_tracked_file_names_one(self) -> None:
        self.assertEqual(machine_mentions(ROOT, self.names()), [])

    def test_the_sweep_would_report_one_if_it_were_there(self) -> None:
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


DIVERGENCES = ROOT / "conformance" / "divergences.json"

DIVERGENCE_STATUS = (
    "open",
    "narrowed",
    "acknowledged",
    "closed",
    "notADisagreement",
    "notModelled",
)

DIVERGENCE_SEVERITY = (
    "contradiction",
    "high",
    "medium",
    "low",
    "unstated",
    "unchecked",
    "outOfScope",
)

DIVERGENCE_SOURCES = (
    "document",
    "reference",
    "recording",
    "corpus",
    "cartridges",
    "microcode",
    "neither",
)


def divergence_entries(where: Path) -> list[Any]:
    if not where.is_file():
        return []
    held = json.loads(where.read_text())
    for value in held.values():
        if isinstance(value, list):
            return list(value)
    return []


def outside_vocabulary(entries: Any, field: str, allowed: Any) -> list[str]:
    return sorted({str(one.get(field)) for one in entries if one.get(field) not in allowed})


class DivergenceRecordTest(unittest.TestCase):
    @property
    def entries(self) -> Any:
        return divergence_entries(DIVERGENCES)

    def test_there_is_a_record_to_check(self) -> None:
        self.assertTrue(self.entries)

    def test_every_entry_says_where_it_stands(self) -> None:
        self.assertEqual(outside_vocabulary(self.entries, "status", DIVERGENCE_STATUS), [])

    def test_every_entry_says_how_much_it_costs(self) -> None:
        self.assertEqual(outside_vocabulary(self.entries, "severity", DIVERGENCE_SEVERITY), [])

    def test_every_entry_says_what_this_package_followed(self) -> None:
        self.assertEqual(outside_vocabulary(self.entries, "packageFollows", DIVERGENCE_SOURCES), [])

    def test_a_value_nobody_agreed_on_is_caught(self) -> None:
        found = outside_vocabulary([{"status": "mostly open"}], "status", DIVERGENCE_STATUS)

        self.assertEqual(found, ["mostly open"])

    def test_a_field_left_out_entirely_is_caught(self) -> None:
        found = outside_vocabulary([{}], "severity", DIVERGENCE_SEVERITY)

        self.assertEqual(found, ["None"])

    def test_a_record_that_is_not_here_reads_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            found = divergence_entries(Path(where) / "divergences.json")

        self.assertEqual(found, [])

    def test_a_record_with_no_list_in_it_reads_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            path = Path(where) / "divergences.json"
            path.write_text('{"note": "nothing here yet"}')
            found = divergence_entries(path)

        self.assertEqual(found, [])


def stamped_paths(script: Path) -> list[str]:
    if not script.is_file():
        return []
    return sorted(set(re.findall(r"\$\{root\}/([^\"'\s]+)", script.read_text())))


def released_assets(config: Path) -> list[str]:
    if not config.is_file():
        return []
    document = json.loads(config.read_text())
    for plugin in document.get("plugins", []):
        if isinstance(plugin, list) and plugin and plugin[0] == "@semantic-release/git":
            return [str(asset) for asset in plugin[1].get("assets", [])]
    return []


def unreleased(stamped: Iterable[str], released: Iterable[str]) -> list[str]:
    committed = set(released)
    return [path for path in stamped if path not in committed]


class EveryStampedFileIsReleasedTest(unittest.TestCase):
    SCRIPT = "scripts/set-version.sh"

    CONFIG = ".releaserc.json"

    def test_the_release_commits_every_file_the_script_stamps(self) -> None:
        stamped = stamped_paths(ROOT / self.SCRIPT)
        released = released_assets(ROOT / self.CONFIG)

        self.assertEqual(unreleased(stamped, released), [])

    def test_and_there_is_something_to_check(self) -> None:
        self.assertGreaterEqual(len(stamped_paths(ROOT / self.SCRIPT)), 2)

    def test_a_path_the_release_leaves_out_is_reported(self) -> None:
        found = unreleased(["pkg/version.py", "CITATION.cff"], ["pkg/version.py"])

        self.assertEqual(found, ["CITATION.cff"])

    def test_a_script_that_is_not_here_stamps_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            found = stamped_paths(Path(where) / "set-version.sh")

        self.assertEqual(found, [])

    def test_a_script_that_names_no_target_stamps_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            path = Path(where) / "set-version.sh"
            path.write_text("#!/usr/bin/env bash\nprintf 'nothing to do\\n'\n")
            found = stamped_paths(path)

        self.assertEqual(found, [])

    def test_a_release_config_that_is_not_here_releases_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            found = released_assets(Path(where) / ".releaserc.json")

        self.assertEqual(found, [])

    def test_a_config_with_no_git_plugin_releases_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            path = Path(where) / ".releaserc.json"
            path.write_text('{"plugins": ["@semantic-release/github", [], ["@other", {}]]}')
            found = released_assets(path)

        self.assertEqual(found, [])

    def test_a_git_plugin_naming_no_asset_releases_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            path = Path(where) / ".releaserc.json"
            path.write_text('{"plugins": [["@semantic-release/git", {}]]}')
            found = released_assets(path)

        self.assertEqual(found, [])


def recorded_version(module: Path) -> str | None:
    if not module.is_file():
        return None
    found = re.search(r'^VERSION = "([^"]*)"$', module.read_text(), re.M)
    return found.group(1) if found else None


def cited_version(citation: Path) -> str | None:
    if not citation.is_file():
        return None
    found = re.search(r"^version: (.*)$", citation.read_text(), re.M)
    return found.group(1).strip() if found else None


class TheVersionAndTheCitationAgreeTest(unittest.TestCase):
    def stamped(self) -> list[str]:
        return stamped_paths(ROOT / "scripts" / "set-version.sh")

    def module(self) -> Path:
        named = [one for one in self.stamped() if one.endswith("version.py")]
        return ROOT / named[0] if named else ROOT / "version.py"

    def test_the_script_stamps_exactly_one_version_module(self) -> None:
        named = [one for one in self.stamped() if one.endswith("version.py")]

        self.assertEqual(len(named), 1, named)

    def test_the_package_reports_a_version(self) -> None:
        self.assertIsNotNone(recorded_version(self.module()))

    def test_the_citation_publishes_a_version(self) -> None:
        self.assertIsNotNone(cited_version(ROOT / "CITATION.cff"))

    def test_the_two_say_the_same_thing(self) -> None:
        self.assertEqual(recorded_version(self.module()), cited_version(ROOT / "CITATION.cff"))

    def test_a_module_that_is_not_here_reports_no_version(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            found = recorded_version(Path(where) / "version.py")

        self.assertIsNone(found)

    def test_a_module_with_no_assignment_reports_no_version(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            path = Path(where) / "version.py"
            path.write_text("RELEASE = '1.2.3'\n")
            found = recorded_version(path)

        self.assertIsNone(found)

    def test_a_citation_that_is_not_here_publishes_no_version(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            found = cited_version(Path(where) / "CITATION.cff")

        self.assertIsNone(found)

    def test_a_citation_with_no_version_line_publishes_none(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            path = Path(where) / "CITATION.cff"
            path.write_text("cff-version: 1.2.0\ntitle: something\n")
            found = cited_version(path)

        self.assertIsNone(found)


DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def is_bare_string(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def documents_its_holder(body: list[ast.stmt], index: int) -> bool:
    opens_the_body = index == 0
    follows_an_assignment = index > 0 and isinstance(body[index - 1], (ast.Assign, ast.AnnAssign))
    return is_bare_string(body[index]) and (opens_the_body or follows_an_assignment)


def documentation_strings(text: str) -> list[int]:
    holders = [node for node in ast.walk(ast.parse(text)) if isinstance(node, DOCUMENTED)]
    return sorted(
        holder.body[index].lineno
        for holder in holders
        for index in range(len(holder.body))
        if documents_its_holder(holder.body, index)
    )


def tracked_python_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [ROOT / one for one in listed]


class NoDocumentationStringTest(unittest.TestCase):
    def test_no_tracked_file_carries_a_documentation_string(self) -> None:
        # Arrange
        files = tracked_python_files()

        # Act
        found = [
            f"{path.relative_to(ROOT)}:{line}"
            for path in files
            for line in documentation_strings(path.read_text())
        ]

        # Assert
        self.assertEqual(found, [])

    def test_and_there_are_files_to_check(self) -> None:
        # Arrange
        minimum = 5

        # Act
        files = tracked_python_files()

        # Assert
        self.assertGreater(len(files), minimum)

    def test_a_module_class_and_function_string_are_each_found(self) -> None:
        # Arrange
        text = '"""M."""\n\n\nclass A:\n    """C."""\n\n\ndef f() -> None:\n    """F."""\n'

        # Act
        found = documentation_strings(text)

        # Assert
        self.assertEqual(found, [1, 5, 9])

    def test_a_string_after_an_assignment_is_found(self) -> None:
        # Arrange
        text = 'LIMIT = 3\n"""What the limit is."""\n'

        # Act
        found = documentation_strings(text)

        # Assert
        self.assertEqual(found, [2])

    def test_a_string_used_as_a_value_is_not_one(self) -> None:
        # Arrange
        text = 'NAME = "a value"\nprint("a call")\n'

        # Act
        found = documentation_strings(text)

        # Assert
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
