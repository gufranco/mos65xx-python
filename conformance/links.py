from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parent.parent

README = ROOT / "README.md"

ADDRESS = re.compile(r"https?://[^\s)\"'<>\\]+")

TIMEOUT = 30

ATTEMPTS = 3

AGENT = "source-watch (+https://github.com/gufranco/mos65xx-python)"

GONE = frozenset({404, 410})

SKIP = ("img.shields.io",)


class Answer(NamedTuple):
    address: str
    verdict: str
    detail: str

    @property
    def broken(self) -> bool:
        return self.verdict == "gone"


def addresses(text: str | None = None) -> list[str]:
    found = ADDRESS.findall(README.read_text() if text is None else text)
    seen: dict[str, None] = {}
    for one in found:
        trimmed = one.rstrip(".,;:")
        if not any(host in trimmed for host in SKIP):
            seen.setdefault(trimmed, None)
    return list(seen)


def probe(address: str, opener: Any = None) -> Answer:
    fetch = opener or urllib.request.urlopen
    last = ""
    for attempt in range(ATTEMPTS):
        for method, headers in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
            request = urllib.request.Request(address, method=method)
            request.add_header("User-Agent", AGENT)
            for key, value in headers.items():
                request.add_header(key, value)
            try:
                with fetch(request, timeout=TIMEOUT) as answer:
                    return Answer(address, "ok", str(answer.status))
            except urllib.error.HTTPError as refusal:
                if refusal.code in GONE:
                    return Answer(address, "gone", str(refusal.code))
                last = f"{method} {refusal.code}"
            except Exception as trouble:  # noqa: BLE001
                last = f"{method} {type(trouble).__name__}"
        if attempt + 1 < ATTEMPTS:
            continue
    return Answer(address, "unreachable", last)


def survey(found: Sequence[str] | None = None, opener: Any = None) -> list[Answer]:
    return [probe(one, opener) for one in (addresses() if found is None else found)]


def report(answers: Iterable[Answer]) -> str:
    held = list(answers)
    return json.dumps(
        {
            "checked": len(held),
            "gone": [one.address for one in held if one.broken],
            "unreachable": [one.address for one in held if one.verdict == "unreachable"],
            "answers": [one._asdict() for one in held],
        },
        indent=2,
    )


def main(argv: Sequence[str]) -> int:
    answers = survey()
    print(report(answers))
    return 1 if any(one.broken for one in answers) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
