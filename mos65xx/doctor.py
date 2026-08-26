"""Look at this machine and say what is actually here, so a report can be believed.

Almost everything that goes wrong with this package is one of three things: the
part is not the one the reporter thinks it is, the conformance suite it was
measured against is not the one that was meant, or there is no suite at all and
the run that looked like a pass never compared anything. All three are invisible
in a traceback, and none is something a reporter thinks to mention.

Sixteen parts share this package and they differ in address width, in whether a
decimal adder is wired at all, and in which interrupt pins the package brings
out. A result that looks wrong is very often the right answer from a different
part, so every one of them is listed rather than only the one in use.

So this looks, and prints what it found in a form that can be pasted into an
issue as it stands.

Two rules shape it. Nothing is hidden: a check that fails says what it saw, and a
check that itself throws is caught and reported as what it threw, named by type,
because a report that says everything is well on a machine where something is not
is worse than no report. And nothing is inferred: every line is something looked
at just now rather than something that ought to be true.

The suite definition sits in the conformance directory rather than in the
package, so an installed copy does not carry one. That is the ordinary case, and
it is also the case this runs in most often, so it is reported as ordinary rather
than raised.
"""

from __future__ import annotations

import json
import platform
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, override


def _version(where: Path | None = None) -> str:
    """The package version, read out of the file beside this one.

    Read rather than imported. Importing it would go through the package, and a
    package that will not import is one of the things this exists to report.
    """
    found = re.search(
        r"""VERSION\s*[:=][^"']*["']([^"']+)["']""",
        (where or Path(__file__).resolve().parent / "version.py").read_text(),
    )
    return found.group(1) if found else "unknown"


ROOT = Path(__file__).resolve().parent.parent

VERSION = _version()


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mos65xx import models  # noqa: E402
from mos65xx.memory import SparseMemory  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence

    from .mos6502 import Cpu

OLDEST_PYTHON = (3, 12)

DEFINITION = Path(__file__).resolve().parent.parent / "conformance" / "suites.json"
"""Where a checkout keeps the suite definition. An install has no such file."""

CACHE = Path.home() / ".cache" / "conformance-suites"
"""Where conformance/fetch.py puts a suite when told nowhere else."""


class Finding:
    """One thing that was looked at, and what was there."""

    def __init__(self, name: str, ok: bool, detail: str, advice: str | None = None) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail
        self.advice = advice

    @property
    def line(self) -> str:
        """The one-line form, which is what a reader scans."""
        return f"  {'ok  ' if self.ok else '   !'}  {self.name}: {self.detail}"

    @property
    def report(self) -> str:
        """The same, with what to do about it when there is something to do."""
        if self.ok or not self.advice:
            return self.line
        return f"{self.line}\n         {self.advice}"

    @override
    def __repr__(self) -> str:
        return f"<Finding {self.name} {'ok' if self.ok else 'not ok'}>"


def _python() -> Finding:
    return Finding(
        "python",
        sys.version_info[:2] >= OLDEST_PYTHON,
        f"{platform.python_version()} on {platform.system()} {platform.machine()}",
        f"this package needs {OLDEST_PYTHON[0]}.{OLDEST_PYTHON[1]} or newer",
    )


def _package() -> Finding:
    return Finding("package", True, f"mos65xx {VERSION}")


def _default_build(name: str) -> Cpu:
    core: Cpu = models.lookup(name).build(SparseMemory())
    return core


def _processor(name: str, build: Callable[[str], Cpu]) -> Finding:
    """Whether that part builds, saying exactly what stopped it if not.

    The properties reported are the ones that change what an instruction leaves
    behind or which pins exist to pull, so two people disagreeing about a result
    are usually holding two different parts rather than two different opinions.
    """
    try:
        cpu = build(name)
    except Exception as trouble:
        return Finding(
            name,
            False,
            f"{type(trouble).__name__}: {trouble}",
            "this is the core failing to build rather than anything to do with a"
            " suite; the line above is what it said",
        )
    described = models.lookup(name)
    return Finding(
        name,
        True,
        f"{described.address_bits}-bit address, {described.data_bits}-bit data,"
        f" {'decimal' if described.decimal else 'no decimal'},"
        f" {described.reset_cycles} reset cycles,"
        f" pins {'+'.join(described.pins)},"
        f" starts at ${cpu.pc:04X}",
    )


def _where() -> Finding:
    return Finding("looking in", True, str(CACHE))


def _read_definition(path: Path | str = DEFINITION) -> dict[str, Any]:
    with Path(path).open() as handle:
        held: dict[str, Any] = json.load(handle)
    return held


def _declared(read: Callable[[], dict[str, Any]] = _read_definition) -> Finding:
    """What the definition declares, or why it could not be read."""
    try:
        held = read()["suites"]
    except OSError:
        return Finding(
            "declared",
            True,
            "no suite definition beside the package, which is the normal state of an install",
        )
    except Exception as trouble:
        return Finding(
            "declared",
            False,
            f"{type(trouble).__name__}: {trouble}",
            "the definition is here but could not be read; the line above is what it said",
        )
    return Finding(
        "declared",
        bool(held),
        f"{len(held)} suites: " + ", ".join(str(one["name"]) for one in held),
    )


def _suites(
    read: Callable[[], dict[str, Any]] = _read_definition,
    cache: Path = CACHE,
) -> list[Finding]:
    """Every declared suite, and whether this machine has it.

    The count of files is the line that matters. A directory that exists and
    holds nothing is what a cancelled fetch leaves behind, and it reads as a
    present suite to anything that only checks the path.
    """
    try:
        held = read()["suites"]
    except OSError:
        return []
    except Exception as trouble:
        return [
            Finding(
                "suites",
                False,
                f"{type(trouble).__name__}: {trouble}",
                "the definition could not be read; the line above is what it said",
            )
        ]
    return [_suite(one, cache) for one in held]


def _suite(declared: dict[str, Any], cache: Path) -> Finding:
    name = str(declared["name"])
    where = cache / name / str(declared["path"])
    wanted = declared.get("files")
    try:
        present = len(list(where.glob("*.json")))
    except OSError as trouble:
        return Finding(f"suite {name}", False, f"could not be read: {trouble}")
    if not present:
        return Finding(
            f"suite {name}",
            True,
            "not fetched, which is the normal state of a fresh checkout",
            None,
        )
    short = isinstance(wanted, int) and present != wanted
    return Finding(
        f"suite {name}",
        not short,
        f"{present} files at {where}"
        + (f", and the definition names {wanted}" if short else "")
        + (f", pinned at {str(declared['commit'])[:7]}" if declared.get("commit") else ""),
        "a partial fetch measures the core against part of the suite and reports a"
        " pass; run conformance/fetch.py again"
        if short
        else None,
    )


def examine(
    build: Callable[[str], Cpu] = _default_build,
    read: Callable[[], dict[str, Any]] = _read_definition,
    cache: Path = CACHE,
) -> list[Finding]:
    """Everything worth looking at on this machine, in the order a reader wants it."""
    found = [_python(), _package()]
    found.extend(_processor(name, build) for name in sorted(models.MODELS))
    found.append(_where())
    found.append(_declared(read))
    found.extend(_suites(read, cache))
    return found


def report(found: Sequence[Finding]) -> list[str]:
    """The lines a person pastes into an issue."""
    unwell = [one for one in found if not one.ok]
    lines = [f"mos65xx {VERSION} on {platform.python_version()}, {platform.system()}", ""]
    lines.extend(one.report for one in found)
    lines.append("")
    if unwell:
        lines.append(f"  {len(unwell)} of {len(found)} checks did not pass")
    else:
        lines.append(f"  {len(found)} checks, nothing to report")
    return lines


def main(
    argv: Sequence[str] = (),
    examine: Callable[..., Sequence[Finding]] = examine,
    say: Callable[[str], object] = print,
) -> int:
    found = examine()
    for line in report(found):
        say(line)
    return 1 if any(not one.ok for one in found) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
