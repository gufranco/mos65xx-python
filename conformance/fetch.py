"""Fetch the conformance suites this core is held to.

The suites are large, from a hundred megabytes to several gigabytes, and they are
not carried in this repository. This brings down only what is needed: a partial
clone that skips blob history and a sparse checkout that takes only the
directories `suites.json` names.

They are pinned by commit. A build that resolves whatever upstream happens to
hold today is not reproducible, and a change made upstream would turn this
repository red with no commit of its own to explain it. The weekly workflow is
where a newer suite is tried, and it proposes a bump rather than taking one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFINITION = ROOT / "suites.json"

PROBE_TIMEOUT = 60
"""Seconds to wait on a question upstream should answer immediately."""

FETCH_TIMEOUT = 3600
"""Seconds to wait on a transfer that is measured in gigabytes."""


def definitions(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Every suite this core declares, as written down.

    The default is resolved on the call rather than bound into the signature. A
    default evaluated at import time freezes the original path into the function,
    so pointing `DEFINITION` elsewhere would appear to work and would quietly go
    on reading the original file.
    """
    with Path(path or DEFINITION).open() as handle:
        held = json.load(handle)["suites"]
    assert isinstance(held, list), f"{path or DEFINITION} declares no list of suites"
    return held


def checkout_command(
    suite: Mapping[str, Any], directory: Path, commit: str | None = None
) -> list[list[str]]:
    """The git steps that bring one suite down, without its history or blobs."""
    wanted = commit or suite["commit"]
    where = str(directory)
    return [
        ["git", "init", "-q", where],
        ["git", "-C", where, "remote", "add", "origin", suite["repository"]],
        ["git", "-C", where, "sparse-checkout", "init", "--cone"],
        ["git", "-C", where, "sparse-checkout", "set", *suite["sparse"]],
        [
            "git",
            "-C",
            where,
            "fetch",
            "-q",
            "--depth=1",
            "--filter=blob:none",
            "origin",
            wanted,
        ],
        ["git", "-C", where, "checkout", "-q", "FETCH_HEAD"],
    ]


def _git_environment() -> dict[str, str]:
    """Git that never stops to ask a question.

    A prompt for credentials waits for a terminal that a scheduled job does not
    have, so the job hangs rather than failing. Refusing the prompt turns that
    into an error the caller can report.
    """
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def latest_commit(suite: Mapping[str, Any], timeout: int = PROBE_TIMEOUT) -> str | None:
    """What upstream is at now, or nothing if it cannot be reached in time."""
    try:
        found = subprocess.run(
            ["git", "ls-remote", suite["repository"], "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=_git_environment(),
        )
    except subprocess.TimeoutExpired:
        return None
    if found.returncode or not found.stdout.strip():
        return None
    return found.stdout.split()[0]


def fetch(
    suite: Mapping[str, Any],
    directory: Path,
    commit: str | None = None,
    quiet: bool = True,
    timeout: int = FETCH_TIMEOUT,
) -> Any:
    """Bring one suite down into a directory, returning where its tests live."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for step in checkout_command(suite, directory, commit):
        try:
            done = subprocess.run(
                step,
                capture_output=quiet,
                text=True,
                check=False,
                timeout=timeout,
                env=_git_environment(),
            )
        except subprocess.TimeoutExpired:
            raise SystemExit(
                f"fetching {suite['name']} gave up after {timeout}s at {' '.join(step)}"
            ) from None
        if done.returncode:
            raise SystemExit(f"fetching {suite['name']} failed at {' '.join(step)}\n{done.stderr}")
    return directory / suite["path"]


def main(argv: Sequence[str], definition: Any = None) -> int:
    directory = (
        Path(argv[0])
        if argv and not argv[0].startswith("-")
        else (Path.home() / ".cache" / "conformance-suites")
    )
    use_latest = "--latest" in argv

    for suite in definitions(definition):
        commit = latest_commit(suite) if use_latest else suite["commit"]
        if commit is None:
            print(f"  {suite['name']}: cannot reach {suite['repository']}")
            return 1
        where = fetch(suite, directory / suite["name"], commit)
        print(f"{suite['name']} {commit} {where}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
