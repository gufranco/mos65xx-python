# Working in this repository

This file is for a coding agent. A person reading it will not be harmed, but
[README.md](README.md) is the document written for them.

## What this project is, in one paragraph

The 6502, the 65C02 and the 65816: a disassembler and an execution core for each,
held to the SingleStepTests corpora, which are the strongest per-instruction
oracle that exists for these parts.

## The authority ladder

Every factual question is answered by the highest rung that has an answer, and a
lower rung never overrules a higher one.

1. **Manufacturer documentation.** The WDC and MOS datasheets for anything they
   print: addressing modes, flag rules, cycle counts, what a page boundary does.
2. **The SingleStepTests corpora**, pinned by commit in
   [`conformance/suites.json`](conformance/suites.json). Ten thousand cases per
   opcode for the 65816, generated against real behaviour, and they cover the
   undocumented opcodes that no datasheet describes at all.
3. **Nothing else.** Another emulator is a third-rung source. Where it and the
   corpora disagree, the corpora decide.

## What is settled and what is not

**Settled: every instruction's effect on state.** The corpora check registers,
flags and every byte of memory an instruction touched, across every opcode
including the undocumented ones. That is as strong as instruction-level evidence
gets.

**Not settled: cycles.** This core does not count them. The corpora carry
per-cycle bus activity, address by address, and this project reads only the
*length* of that list, as a budget for the block-move instructions. So the data
needed to make these cores genuinely cycle-accurate is already downloaded on
every conformance run and is not being checked.

Closing that is the largest piece of outstanding work in this family of projects.
It means every instruction emitting its bus cycles in order, and the runner
comparing them against `test["cycles"]`. Do not claim cycle accuracy here until
that comparison runs and passes.

## Every gate, in the order to run them

```bash
ruff format --check .
ruff check .
mypy
pnpm run format:check
for f in mos65xx/*.test.py conformance/*.test.py; do python3 "$f"; done
python3 -m coverage report
```

The conformance run needs the suites, which are fetched rather than vendored:

```bash
python3 conformance/fetch.py
python3 conformance/singlestep.py
```

## Things that will bite you

**Import conformance modules package-qualified.** `from conformance import fetch`,
never `importlib.import_module("fetch")` with the directory on the path. The
importlib form gives the checker a bare module object with no attributes, so every
access reads as missing and an assignment to one is an error.
`conformance/__init__.py` exists to make the qualified form work.

**The three cores do not share a base class except where they do.** `mos65c02.Cpu`
inherits from `mos6502.Cpu`, and `wdc65816.Cpu` inherits from nothing. Marking a
65816 method as an override is wrong and the checker says so.

**Run on the oldest Python supported.** Annotations are evaluated eagerly before
3.14 and lazily from 3.14 on.

**A checker complaint is not always the code's fault.** A branch flagged as
unreachable here turned out to be a real feature that a too-narrow annotation had
hidden, and deleting it broke a test. Read the branch before believing the
annotation.

## Conventions that are not negotiable

| Thing | Rule |
|:------|:-----|
| Language | Python only |
| Comments | None in source. Docstrings carry the reasoning |
| Test layout | `<module>.test.py` beside the module it covers |
| Coverage | 100% statements and branches, enforced |
| Types | `mypy` at strict, plus every optional error class |
| Commits | Conventional Commits, subject under 50 characters |
| Suites | Fetched and pinned by commit, never vendored |

## Layout

```
mos65xx/
  mos6502.py     the NMOS core, including the undocumented opcodes
  mos65c02.py    the CMOS core, which inherits from it
  wdc65816.py    the 16-bit core, which does not
  opcodes*.py    one opcode table and disassembler per part
  memory.py      flat and sparse memories that start filled, never cleared
  models.py      the family, by name and alias
conformance/
  suites.json    which corpora, at which commit
  fetch.py       getting them
  singlestep.py  running them
specs/current/   what this does now, as requirements with scenarios
```

## What a change is expected to leave behind

A gate that would have caught the bug. A change to instruction behaviour also runs
the corpora, because that is the only thing here that can tell you whether it is
right.
