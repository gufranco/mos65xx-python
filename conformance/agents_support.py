"""Ask agents.md which agents read AGENTS.md, and report any this record does not name.

This repository keeps one instruction file. Most agents read it directly. The
rest each look for a file of their own, so each of those gets a pointer saying
where the instructions are, and agent-files.json is the list of both.

That list ages the moment a new agent ships, and nothing in a build notices: a
tool this repository has never heard of reads nothing, and the silence looks the
same as being covered. So this walks the adopter list published on agents.md and
reports every name the record does not already hold.

It changes nothing on its own. The weekly job reads the report and opens a pull
request adding the new names, because a name on that list means the agent reads
AGENTS.md and therefore needs no file here, which is a change small enough to
propose rather than merely mention. An agent that does not read AGENTS.md never
appears on that page, so its pointer is added by hand: the page says which tools
read the file and never says what a tool that does not would read instead.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

RECORD = ROOT / "conformance" / "agent-files.json"

PAGE = "https://agents.md/"

NAME = re.compile(r'<span class="text-xl font-semibold[^"]*">([^<]+)</span>')

TIMEOUT = 30

ATTEMPTS = 3

AGENT = "agents-watch (+https://github.com/gufranco/mos65xx-python)"

FEWEST = 10
"""Below this many names the page is treated as unread rather than as shrunk.

The list is a marquee rendered from markup that can change shape. A parser that
silently matches nothing would report every agent as removed, which reads as a
catastrophe and is really a selector that stopped matching.
"""


def held() -> dict[str, Any]:
    """The record, as data."""
    loaded: dict[str, Any] = json.loads(RECORD.read_text())
    return loaded


def fetch(address: str = PAGE, opener: Any = None) -> str:
    """The page, or an empty string when the host would not answer.

    The opener is a parameter so a test can answer without a network, the same
    way the link survey beside this file does it.
    """
    reader = opener or urllib.request.urlopen
    request = urllib.request.Request(address, headers={"User-Agent": AGENT})
    for _ in range(ATTEMPTS):
        try:
            with reader(request, timeout=TIMEOUT) as answer:
                body: bytes = answer.read()
                return body.decode("utf-8", "replace")
        except (urllib.error.URLError, OSError):
            continue
    return ""


def names_in(page: str) -> list[str]:
    """Every agent named on the page, in the order it prints them, once each."""
    found: list[str] = []
    for raw in NAME.findall(page):
        name = html.unescape(raw).strip()
        if name and name not in found:
            found.append(name)
    return found


def compare(page: str, record: dict[str, Any]) -> dict[str, Any]:
    """What the page says against what the record holds."""
    listed = names_in(page)
    known = set(record["readsAgentsFile"]["names"])
    if len(listed) < FEWEST:
        return {"read": False, "found": len(listed), "new": [], "gone": []}
    return {
        "read": True,
        "found": len(listed),
        "new": [name for name in listed if name not in known],
        "gone": sorted(known - set(listed)),
    }


def report(opener: Any = None, record: dict[str, Any] | None = None) -> tuple[dict[str, Any], int]:
    """The comparison, and what a caller should exit with."""
    result = compare(fetch(opener=opener), held() if record is None else record)
    if not result["read"]:
        return result, 0
    return result, 1 if result["new"] else 0


def main(opener: Any = None, record: dict[str, Any] | None = None) -> int:
    result, status = report(opener, record)
    print(json.dumps(result, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main())
