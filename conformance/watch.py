"""Ask every upstream this project is pinned to where it is now.

The six suites here do not come from one place. The 65816 cases live in
ProcessorTests and the other five live in 65x02, so a watcher that probes the
first definition and stops has been reporting on one suite and silently ignoring
five. That is worse than not watching at all, because the badge of a green
watcher reads as coverage.

So this groups the definitions by repository, probes each group once, and reports
what moved. A repository is probed once however many suites use it, and a suite
cannot fall out of the survey without the count in the tests changing.

The workflow consumes the output as a matrix. Keeping the logic here rather than
inline in YAML means it is covered by the same gate as everything else, and means
a mistake in it fails a test rather than a scheduled run nobody reads.
"""

import importlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFINITION = ROOT / "suites.json"


class Disagreement(Exception):
    """One repository pinned to two different commits by two suites."""


def declared(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Every suite this project is held to, as written down."""
    with Path(path or DEFINITION).open() as handle:
        suites: list[dict[str, Any]] = json.load(handle)["suites"]
    return suites


def by_repository(suites: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The suites grouped by where they come from, in the order they appear.

    Two suites from one repository must agree about the commit. They always do,
    because they are checked out together, and a disagreement would mean one of
    them is being fetched at a commit the other was never tested against.
    """
    groups: dict[str, dict[str, Any]] = {}
    for suite in suites:
        repository = suite["repository"]
        found = groups.get(repository)
        if found is None:
            groups[repository] = {
                "repository": repository,
                "pinned": suite["commit"],
                "suites": [suite["name"]],
            }
            continue
        if found["pinned"] != suite["commit"]:
            raise Disagreement(
                f"{repository} is pinned to {found['pinned']} by {found['suites'][0]}"
                f" and to {suite['commit']} by {suite['name']}"
            )
        found["suites"].append(suite["name"])
    return list(groups.values())


def survey(
    suites: Sequence[Mapping[str, Any]],
    ask: Callable[[Mapping[str, Any]], str | None] | None = None,
) -> list[dict[str, Any]]:
    """Where each repository is now, beside where this project has it pinned.

    An upstream that cannot be reached is reported as not moved rather than as
    moved, because a scheduled job that opens a pull request every time a network
    call fails is a job somebody turns off.
    """
    if ask is None:
        ask = _upstream
    found = []
    for group in by_repository(suites):
        latest = ask(group)
        found.append(
            {**group, "latest": latest or "", "moved": bool(latest) and latest != group["pinned"]}
        )
    return found


def _upstream(group: Mapping[str, Any]) -> str | None:
    """What that repository's default branch points at, through the fetcher.

    Imported here rather than at the top because the fetcher reaches the network
    and everything else in this module does not. A caller that supplies its own
    `ask` never loads it.
    """
    sys.path.insert(0, str(ROOT))
    fetch = importlib.import_module("fetch")

    commit: str | None = fetch.latest_commit(group)
    return commit


def main(
    argv: Sequence[str],
    ask: Callable[[Mapping[str, Any]], str | None] | None = None,
) -> int:
    only_moved = "--moved" in argv
    given = [argument for argument in argv if not argument.startswith("-")]

    try:
        suites = declared(given[0] if given else None)
        found = survey(suites, ask)
    except OSError as error:
        print(f"cannot read the suite definitions: {error}")
        return 1
    except Disagreement as error:
        print(f"the definitions disagree: {error}")
        return 1

    print(json.dumps([group for group in found if group["moved"] or not only_moved]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
