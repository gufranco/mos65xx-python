import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PACKAGE = "mos65xx"

TEST_SUFFIX = ".test.py"


def modules(root: Path = ROOT) -> list[str]:
    return sorted(
        found.name
        for found in (root / PACKAGE).glob("*.py")
        if not found.name.endswith(TEST_SUFFIX)
    )


def audit(wheel: Path) -> list[str]:
    shipped = set(zipfile.ZipFile(wheel).namelist())
    faults = [
        f"ships a test: {name}"
        for name in sorted(shipped)
        if name.startswith(f"{PACKAGE}/") and name.endswith(TEST_SUFFIX)
    ]
    faults.extend(
        f"missing a module: {PACKAGE}/{name}"
        for name in modules()
        if f"{PACKAGE}/{name}" not in shipped
    )
    return faults


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 -m conformance.package <wheel>")
        return 2

    wheel = Path(argv[0])
    if not wheel.is_file():
        print(f"absent: {wheel}")
        return 1

    faults = audit(wheel)
    for fault in faults:
        print(fault)
    if faults:
        return 1

    print(f"{wheel.name}: {len(modules())} modules present, no test shipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
