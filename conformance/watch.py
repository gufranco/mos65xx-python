import importlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFINITION = ROOT / "suites.json"


class Disagreement(Exception): ...


def declared(path: Path | str | None = None) -> list[dict[str, Any]]:
    with Path(path or DEFINITION).open() as handle:
        suites: list[dict[str, Any]] = json.load(handle)["suites"]
    return suites


def by_repository(suites: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
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
