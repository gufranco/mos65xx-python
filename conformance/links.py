"""Ask every address this project cites whether it still answers.

The readme names each document a claim rests on and links to where it can be
fetched. A link is the one part of that record which decays without anyone
touching the repository: a vendor reorganises a site, an archive moves a file,
and the citation quietly becomes a dead end. Nothing in the build notices,
because nothing in the build follows it.

So this walks the readme, collects every address in it, and asks each one
whether it is still there. It changes nothing on its own. The weekly job reads
the report and opens an issue when an address has genuinely gone, which is worth
a person reading, and stays quiet when the failure looks like weather.

The distinction matters more than it sounds. A host that times out once is not a
broken link, and a watcher that cannot tell the two apart teaches a reader to
ignore it. Only a status the server itself returned counts as gone.
"""

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
"""How many times a single address is asked before its silence is believed."""

AGENT = "source-watch (+https://github.com/gufranco/mos65xx-python)"

GONE = frozenset({404, 410})
"""The statuses that mean the server looked and the thing is not there.

Everything else a server returns is either fine or its own problem. A 403 is a
door held shut rather than an empty room, and a 500 is the host having a bad
day, so neither is reported as a broken link.
"""

SKIP = ("img.shields.io",)
"""Badge images, which answer for the badge rather than for anything cited."""


class Answer(NamedTuple):
    """What one address said when it was asked."""

    address: str
    verdict: str
    detail: str

    @property
    def broken(self) -> bool:
        return self.verdict == "gone"


def addresses(text: str | None = None) -> list[str]:
    """Every distinct address the readme names, in the order it names them."""
    found = ADDRESS.findall(README.read_text() if text is None else text)
    seen: dict[str, None] = {}
    for one in found:
        trimmed = one.rstrip(".,;:")
        if not any(host in trimmed for host in SKIP):
            seen.setdefault(trimmed, None)
    return list(seen)


def probe(address: str, opener: Any = None) -> Answer:
    """Ask one address, cheaply first and then less cheaply.

    A HEAD is free and most hosts answer it. Some do not: archive.org returns a
    server error for HEAD on a file it will happily serve, so a refusal on the
    cheap question is not an answer about the address. Falling back to a request
    for the first byte costs one byte and settles it.
    """
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
    """The survey as a workflow can consume it, broken addresses first."""
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
    """Print the survey. Exit non-zero only when an address is genuinely gone."""
    answers = survey()
    print(report(answers))
    return 1 if any(one.broken for one in answers) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
