# Contributing

## The short version

Evidence over assertion. A change that claims something is correct carries the
run that shows it, and a claim that cannot be checked is not ready.

## Before you open a pull request

Run every gate, and read the output rather than the exit code:

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
pnpm install --frozen-lockfile && pnpm run format:check
python3 -m coverage erase
for f in $(find . -name '*.test.py' -not -path './packages/*' | sort); do
  python3 -m coverage run -a "$f" || echo "FAILED $f"
done
python3 -m coverage report
```

Coverage is a hard gate at 100% statement and branch. A branch with no test
fails the build rather than lowering the number.

## Tests

A test file sits beside the module it covers and is named after it. Test bodies
carry no comments: arrange, act and assert are separated by one blank line each,
and the test name says what behaviour is being pinned.

Tests that need a file nobody can distribute are skipped rather than passed when
that file is absent, and they live apart from the rest so the coverage gate stays
meaningful on a runner that has nothing.

## Commits

Conventional Commits, subject under fifty characters, imperative mood. The body
explains what changed and why, wrapped at seventy two columns. Releases are cut
by semantic-release from those subjects, so the type is what decides the version.

## What will be sent back

- A file nobody can legally redistribute, or a digest of one fine enough to
  reconstruct it. Whole-file digests are welcome; per-block ones are not.
- A number in a document that no run produced.
- A behaviour changed without the corpus or the pinned digests moving with it.
- A test that asserts what the code does rather than what the hardware does.

## What is welcome without asking

Measurements. If you have cartridges, patches or hardware this has not been run
against, the most useful contribution is a run and what it found, especially a
disagreement.
