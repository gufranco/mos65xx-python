# Working in this repository

This file is for a coding agent. A person reading it will not be harmed, but
[README.md](README.md) is the document written for them.

## What this project is, in one paragraph

The 6502, the 65C02 and the 65816: a disassembler and an execution core for each,
held to the SingleStepTests corpora, which are the strongest per-instruction
oracle that exists for these parts.

## The interface a caller drives

The part is powered and not reset when it is built. `reset()` is the caller's to
call, because no board hands over a processor that has reset itself.

Three ways to run it, sharing one place where a cycle is spent:

- `step()` runs one instruction and returns the cycles it cost.
- `run_for(cycles)` spends a budget of them and overshoots, because an
  instruction cannot be cut in half. It keeps clocking a part that has halted,
  because a halted part still costs its host every cycle.
- `Clock(cpu).tick()` advances exactly one cycle and stops, on a thread, because
  Python cannot suspend a call stack. Fifty times slower and the only way to
  change what a read answers mid-instruction.

Three inputs are lines rather than events, each read where the data sheets say
the part reads them: `irq_line` as a level tested at instruction completion,
`nmi_line` on its transition, `ready_line` before every cycle, with the NMOS
carve-out for a write already on its way out. `on_cycle` is called once per
cycle, after that cycle's activity.

Every cycle passes through `spend()` and nowhere else. A counter kept in one
method and a hook called from another drift the first time somebody adds a cycle
to only one of them, and nothing catches it. Keep it that way.

## The authority ladder

Every factual question is answered by the highest rung that has an answer, and a
lower rung never overrules a higher one.

1. **Manufacturer documentation.** What MOS, Commodore, Synertek, Rockwell and
   WDC printed. Every document is listed in the README's References section with
   its digest, and every fact taken from one is in
   [`conformance/hardware.json`](conformance/hardware.json) with the sentence it
   came from and the page it was on.
2. **The part itself.** A measurement on real silicon. Nothing in this repository
   rests on one yet, which is why
   [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) exists.
3. **A recording from an independent implementation.** The SingleStepTests
   corpora, pinned by commit in
   [`conformance/suites.json`](conformance/suites.json). Ten thousand cases per
   opcode, covering the undocumented opcodes no datasheet describes.
4. **Anything else.** Another emulator, a community write-up, a primer. Where one
   of these and a higher rung disagree, the higher rung decides, and a source
   with no measurement behind it is not cited at all.

Where rung one and rung three disagree and rung two is silent, the answer is
**unknown**. Record it in [`conformance/divergences.json`](conformance/divergences.json)
with the measurement that would close it. Do not pick the more convenient source
and move on.

## What is settled and what is not

**Settled: every instruction's effect on state.** The corpora check registers,
flags and every byte of memory an instruction touched, across every opcode
including the undocumented ones. That is as strong as instruction-level evidence
gets.

**Settled: cycles.** [`conformance/cycles.py`](conformance/cycles.py) compares
every bus cycle of every case against the recorded one, address by address and
line by line, across all eight parts. 17,870,080 comparisons, no failures. The
65816 comparison includes the two address qualifiers, the vector pull and memory
lock, because the corpus carries them.

**Settled: the manufacturers' own tables.** Appendix A of the hardware manual,
Appendix B of the programming manual, Table 6-7 of the W65C816S data sheet and
the reserved-opcode row of the W65C02S data sheet are each recorded and driven,
so a claim about timing is checkable without any corpus on the machine.

**Not settled:** nine things, each named in [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md)
with the measurement that would close it. Do not close one by argument.

## Every gate, in the order to run them

```bash
ruff format --check .
ruff check .
mypy
pnpm run format:check
for f in $(find mos65xx conformance -name '*.test.py' | sort); do python3 "$f"; done
python3 -m coverage report
```

The conformance run needs the suites, which are fetched rather than vendored:

```bash
python3 -m conformance.fetch
python3 -m conformance.singlestep
```

## The cycle claim, and what it rests on

Every part is held to the bus, not only to state:

```bash
python3 -m conformance.cycles <suite>/65816/v1 --model 65816
```

17,870,080 cases agree, across all eight parts. On the eight-bit parts every cycle
is a bus cycle, so the comparison covers timing and side effects at once. On the
65816 it also covers eight output pins per cycle, and cycles where the part drives
no valid address at all.

Where a spare cycle reads is a property of the part, not of the addressing mode,
and the two eight-bit families disagree about every one of them. The hooks that
carry the difference are `spare_for_index`, `spare_in_page_zero`, `settle`,
`modify_kind` and `idles_after_opcode`. Add a part by overriding those rather than
by copying an addressing mode.

On the 65816 the equivalents are `internal` for a cycle nothing answers, `pins`
for the output lines, and the `locked` and `pulling` flags for memory lock and
vector pull. A cycle that is not emitted through `read8`, `write8` or `internal`
does not exist as far as the comparison is concerned.

The weekly watcher still tracks only the 65816 repository's pin. The 65x02
repository carries five of the six suites and its pin is not watched, so a bump
there has to be noticed by hand.

Two rules for touching any of this. A dummy access is a cycle, so it goes through
`read8` or `write8` rather than around them, or it will not appear on the bus. And
a change to where a spare cycle reads changes what the part touches, so it is held
to the state suites as well as the cycle one.

## This repository is the family reference

Eight sibling projects are held to the standard this one sets: nec-upd7725,
snes-driver, snes-dsp, snes-mapper, snes-rom-image, snes-rtc, star-ocean-nochip-fix
and zilog-z80. When one of them needs a pattern, the pattern is here:

| Thing | Where it lives here |
|:--|:--|
| Facts read from a manufacturer's document | [`conformance/hardware.json`](conformance/hardware.json), each with its sentence |
| Where a document and a recording disagree | [`conformance/divergences.json`](conformance/divergences.json), both readings, and what would settle it |
| Comparing state against a per-opcode corpus | [`conformance/singlestep.py`](conformance/singlestep.py) |
| Comparing the bus, cycle by cycle and pin by pin | [`conformance/cycles.py`](conformance/cycles.py) |
| Pinning and fetching a corpus nobody vendors | [`conformance/fetch.py`](conformance/fetch.py) and [`conformance/suites.json`](conformance/suites.json) |
| Requirements with checkable scenarios | [`specs/current/`](specs/current/) |
| Strict typing, every optional error class | the `[tool.mypy]` block in `pyproject.toml` |

The one thing to copy first is the pair of JSON files. A number in a docstring is
a claim nobody checks; a number in `hardware.json` with the sentence it came from
is one anybody can check, and the test beside it holds the code to it.

## Where the hardware facts live

[`conformance/hardware.json`](conformance/hardware.json) holds every fact read out
of a manufacturer's document, each with the sentence it came from and the date the
document was read. [`conformance/divergences.json`](conformance/divergences.json)
holds the two places where a document and the recorded cycles disagree, with the
case that shows it and what would settle it. Both are held to the code by tests
beside them, so neither can drift.

Add to those files rather than to a docstring when the fact is a hardware fact. A
number in a docstring is a claim nobody checks.

The datasheet is not always right. Its native vector table prints the emulation
addresses, and its caveat about which direct-page pointer reads stay inside the
page is contradicted by three of the four cases the suite can settle. Read the
cycle table and the pin descriptions before the prose: both times the document
contradicted itself, those two were the ones that matched the silicon.

## Things that will bite you

**A figure taken from a document is read twice.** Almost every document behind
these projects is a photograph of a printed book. Its text layer, where it has
one, was produced by somebody else's recogniser and prints `lhe` for `the`; the
page read as an image now is cleaner but drops a lone digit and misses a faint
line outright. Read it both ways and record what both agree on. `FAMILY.md`, under
"Reading a document that is a photograph", carries the traps and what the record
has to hold. Skipping this is how a timing table came to name forty three of its
rows after the text sitting next to them.

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
| Documents | Read, quoted and pinned by digest. Never committed: none is redistributable |
| Undefined state | Nothing starts cleared and nothing can be asked to. There is no fill parameter and there will not be one |
| Fidelity | Where the part and convenience disagree, the part wins. A behaviour that exists only to make a test easier is a defect |
| Public API | The two cores in this family present the same surface. `Cpu(name)`, `step()`, `reset()`, `irq()`, `nmi()`, `decode(data)`, `disassemble(data)`. A difference needs a hardware reason |

## Layout

```
mos65xx/
  mos6502.py     the NMOS core, including the undocumented opcodes
  mos65c02.py    the CMOS core, which inherits from it
  wdc65816.py    the 16-bit core, which does not
  opcodes*.py    one opcode table and disassembler per part
  memory.py      flat and sparse memories that start filled, never cleared
  models.py      the family, by name and alias
  errors.py      the halt states, one definition shared by every core
conformance/
  suites.json    which corpora, at which commit
  fetch.py       getting them
  singlestep.py  running them, state by state
  cycles.py      running them, bus cycle by bus cycle
  hardware.json  what the manufacturers printed, with the sentence
  divergences.json  where a document and a recording part, and what would settle it
  links.py       the weekly check that every cited address still answers
specs/current/   what this does now, as requirements with scenarios
```

## Before calling anything finished

[`FAMILY.md`](FAMILY.md) carries a checklist under "What a new repository has to
have before it is a member". Every line on it was a defect found in one of these
repositories and fixed in all of them, so it is the list of things that have
actually gone wrong here rather than a list of good intentions. Read it before
adding a surface, and read it again before saying a change is done.

A change to `FAMILY.md` is a change to every member. Nothing here can catch it
being made in one of them and forgotten in the others, because a test in this
repository cannot see the others, so the check is a command rather than a suite:

```sh
shared() { sed '/^\*Everything above this line/q' "$1"; }

grep -o 'github\.com/[^/]*/\([a-z0-9-]*\))' FAMILY.md | sed 's|.*/||; s|)||' | sort -u |
while read -r member; do
  other="../$member/FAMILY.md"
  [ -f "$other" ] || { echo "not on this machine: $member"; continue; }
  cmp <(shared FAMILY.md) <(shared "$other") && echo "match: $member"
done
```

The members come from the table at the top of `FAMILY.md` rather than from a
glob over the parent directory. Several repositories beside these carry a copy
of this file because somebody started from one. Those are working notes: they
bind nothing, they are not expected to match, and a sweep that reports them as
drifted invites somebody to edit a file that was never a member.

The marker line at the end of the shared part is what bounds the comparison, so
nothing here carries a line number that has to be maintained alongside the file
it counts. Run this after any edit, and read the output rather than the exit
code: a loop over a pattern that matched nothing prints nothing and succeeds.

Two rules from that file are worth repeating because they are the ones skipped
most often, and skipping them is how the rest of the list got written:

**A check nobody has seen fail is not known to work.** Drive it, once,
deliberately, against input that should fail it. Three checks in this family
reported clean while the thing they guarded was broken, and each was believed
because the run stayed green.

**Silence and success produce the same output.** A check that found no files, no
documents or no records exits zero exactly like one that examined everything.
Print what was examined, and say so when the answer is nothing.

## What a change is expected to leave behind

A gate that would have caught the bug. A change to instruction behaviour also runs
the corpora, because that is the only thing here that can tell you whether it is
right.
