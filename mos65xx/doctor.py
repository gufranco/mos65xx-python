from __future__ import annotations

import json
import platform
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, override


def installed_version(where: Path | None = None) -> str:
    found = re.search(
        r"""VERSION\s*[:=][^"']*["']([^"']+)["']""",
        (where or Path(__file__).resolve().parent / "version.py").read_text(),
    )
    return found.group(1) if found else "unknown"


ROOT = Path(__file__).resolve().parent.parent

VERSION = installed_version()


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mos65xx import environment, models  # noqa: E402
from mos65xx.memory import SparseMemory  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence

    from .mos6502 import Cpu

OLDEST_PYTHON = (3, 12)

DEFINITION = Path(__file__).resolve().parent.parent / "conformance" / "suites.json"

CACHE = Path.home() / ".cache" / "conformance-suites"


class Finding:
    def __init__(self, name: str, ok: bool, detail: str, advice: str | None = None) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail
        self.advice = advice

    @property
    def line(self) -> str:
        return f"  {'ok  ' if self.ok else '   !'}  {self.name}: {self.detail}"

    @property
    def report(self) -> str:
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
    try:
        cpu = build(name)
        cpu.reset()
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
        f" resets to ${cpu.pc:04X}",
    )


def _where() -> Finding:
    return Finding("looking in", True, str(CACHE))


def read_definition(path: Path | str = DEFINITION) -> dict[str, Any]:
    with Path(path).open() as handle:
        held: dict[str, Any] = json.load(handle)
    return held


def check_declared(read: Callable[[], dict[str, Any]] = read_definition) -> Finding:
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


def check_suites(
    read: Callable[[], dict[str, Any]] = read_definition,
    cache: Path = CACHE,
) -> list[Finding]:
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
    return [check_suite(one, cache) for one in held]


def check_suite(declared: dict[str, Any], cache: Path) -> Finding:
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
    read: Callable[[], dict[str, Any]] = read_definition,
    cache: Path = CACHE,
) -> list[Finding]:
    found = [_python(), _package()]
    found.extend(_processor(name, build) for name in sorted(models.MODELS))
    found.append(_where())
    found.append(check_declared(read))
    found.extend(check_suites(read, cache))
    return found


def report(found: Sequence[Finding]) -> list[str]:
    unwell = [one for one in found if not one.ok]
    lines = [f"mos65xx {VERSION} on {platform.python_version()}, {platform.system()}", ""]
    lines.append("  the machine")
    lines.extend(environment.lines(ROOT))
    lines.append("")
    lines.append("  this package")
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
