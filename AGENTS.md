# Working in this repository

Read [FAMILY.md](FAMILY.md) first. It is the standard every member of this
family carries, byte for byte, and it decides most questions before they are
asked. What follows is only what is true of this member. [README.md](README.md)
is the document written for a person.

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
  change what a read answers mid-instruction. Only the clock's own thread stops:
  `irq()` or `nmi()` called while it is paused at an instruction boundary acts
  at once, as between two steps, and its cycles count in `cycles` without being
  ticks. Paused inside an instruction, or inside an interrupt entry, there is no
  such place, so the call raises `InsideInstruction` and changes nothing. A
  boundary whose lines will start an entry, an `nmi_line` edge not yet taken or
  an `irq_line` held with interrupts enabled, is not one either: the step is not
  finished, and the error names the pending line. `sampled_line()` decides this
  for `sample_pins()` and the refusal alike.

Three inputs are lines rather than events, each read where the data sheets say
the part reads them: `irq_line` as a level tested at instruction completion,
`nmi_line` on its transition, `ready_line` before every cycle, with the NMOS
carve-out for a write already on its way out. On the NMOS parts the first two
are polled where a simulation of the die polls them, as an instruction's last
cycle begins: `spend()` records the lines and the mask as each cycle opens,
`polled()` hands back what the last one recorded, a taken branch inside its page
holds what its operand cycle recorded, and a break skips the poll at its end.
The CMOS parts override `polled()` to read the lines at completion. The 65816
adds `abort_line`, latched once per instruction on the cycle it is held during;
`step()` snapshots the registers first and `roll_back()` restores them at the
end, keeping what 8.4.1 of the data sheet says survives, before taking the abort. `on_cycle`
is called once per cycle, at its end, after that cycle's activity and the work
that follows it.

Every cycle passes through `spend()` and nowhere else. `spend()` opens a cycle,
and `close_cycle()` is the only thing that closes one: it advances the cycle
count and calls `on_cycle`. It runs just before the next access, before the
interrupt lines are sampled and at the end of an instruction, so a clock that
stops on a cycle sees that cycle's access and the work done before the next one,
and a clock stopped on an instruction's last cycle leaves the part as `step()`
does. An access the host makes between instructions, `read8`, `write8` or a push
built on them, closes its own cycle at once, so the next `step()` and the next
tick never count it as their own. A counter kept in one method and a hook called from another drift the
first time somebody adds a cycle to only one of them, and nothing catches it.
Keep it that way.

## The authority ladder

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

**Not settled: 14 things**, each named in [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md)
with the measurement that would close it. Do not close one by argument.

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
snes-driver, snes-dsp, snes-mapper, snes-rom-image, snes-rtc, snes-star-ocean-nochip-fix
and zilog-z80. When one of them needs a pattern, the pattern is here:

| Thing                                            | Where it lives here                                                                                     |
| :----------------------------------------------- | :------------------------------------------------------------------------------------------------------ |
| Facts read from a manufacturer's document        | [`conformance/hardware.json`](conformance/hardware.json), each with its sentence                        |
| Where a document and a recording disagree        | [`conformance/divergences.json`](conformance/divergences.json), both readings, and what would settle it |
| Comparing state against a per-opcode corpus      | [`conformance/singlestep.py`](conformance/singlestep.py)                                                |
| Comparing the bus, cycle by cycle and pin by pin | [`conformance/cycles.py`](conformance/cycles.py)                                                        |
| Pinning and fetching a corpus nobody vendors     | [`conformance/fetch.py`](conformance/fetch.py) and [`conformance/suites.json`](conformance/suites.json) |
| Strict typing, every optional error class        | the `[tool.mypy]` block in `pyproject.toml`                                                             |

The one thing to copy first is the pair of JSON files. A number written into the
source is a claim nobody checks; a number in `hardware.json` with the sentence it came from
is one anybody can check, and the test beside it holds the code to it.

## Where the hardware facts live

[`conformance/hardware.json`](conformance/hardware.json) holds every fact read out
of a manufacturer's document, each with the sentence it came from and the date the
document was read. [`conformance/divergences.json`](conformance/divergences.json)
holds the two places where a document and the recorded cycles disagree, with the
case that shows it and what would settle it. Both are held to the code by tests
beside them, so neither can drift.

Add to those files rather than to the source when the fact is a hardware fact. A
number in the source is a claim nobody checks.

The datasheet is not always right. Its native vector table prints the emulation
addresses, and its caveat about which direct-page pointer reads stay inside the
page agrees with three of the four cases the suite can settle and is followed
for the fourth, which the suite contradicts. Read the cycle table and the pin
descriptions before the prose: both times the document contradicted itself,
those two were the ones that matched the silicon.

## Test cartridges

[`conformance/testroms.json`](conformance/testroms.json) lists every test
program written to exercise these parts, each pinned by SHA-256 and none of
them carried here.

**Two run, on the bare processor.** Klaus Dormann's instruction exercisers each
loop on one address when they stop, and his listing marks which address means
passed. [`conformance/exercisers.py`](conformance/exercisers.py) loads one, runs
it from `$0400` until the program counter stops moving, and compares where it
stopped with that address. The verdicts it reached are in
[`conformance/exercisers.json`](conformance/exercisers.json), and the tests
beside it replay them with no image present:

- `6502_functional_test.bin` as the 6502: passed at `$3469`, 30,646,177
  instructions.
- `65C02_extended_opcodes_test.bin` as the r65c02 and the w65c02: passed at
  `$24f1`, 21,986,986 instructions each. That build tests BBR, BBS, RMB and SMB
  in full, so the plain 65c02, which never had them, stops at the first BBR and
  is not run against it.

```bash
git clone https://github.com/Klaus2m5/6502_65C02_functional_tests.git /tmp/dormann
git -C /tmp/dormann checkout 7954e2dbb49c469ea286070bf46cdd71aeb29e4b
MOS65XX_EXERCISERS=/tmp/dormann python3 -m conformance.exercisers
```

Without the variable it runs nothing, says so and exits 2, and CI turns that
into a notice. CI fetches them at the pinned commit, so it runs both on every
push. Nothing watches that pin: the upstream last moved on 2020-01-05, and a
move has to be noticed by hand with `git ls-remote`.

**The rest wait on `snes-machine`**, a whole-machine member no plan names yet.
They are the 65816 tests that print their verdict on a screen, Peter Lemon's,
gilyon's, Shay Green's ADC and SBC tests and Sour's instruction timing test, and
the factory and service tests whose text names a CPU test. None of them reports
anything without the video hardware around the processor.

## Every gate, in the order to run them

```bash
ruff format --check .
ruff check .
uvx --python 3.12 --with types-setuptools==84.0.0.20260812 mypy==1.14.1
pnpm run format:check
uvx yamllint==1.38.0 --strict .
cov=(uvx --python 3.12 --from coverage==7.6.10 --with setuptools==84.0.0 coverage)
"${cov[@]}" erase
for f in $(find mos65xx conformance -name '*.test.py' | sort); do
  "${cov[@]}" run -a "$f" || echo "FAILED $f"
done
"${cov[@]}" report
```

The conformance run needs the suites, which are fetched rather than vendored:

```bash
python3 -m conformance.fetch
python3 -m conformance.singlestep
```

The die comparison runs only with a probe you build, because the simulation is
somebody else's work and nothing of it is carried here:

```bash
NETLIST=/path/to/probe python3 -m conformance.netlist
```

The probe is a small C program linked against perfect6502, verified at commit
`09fc542877a84318291aa42dab143a3e2c3db974`. It loads a program at `$0200` over
memory filled with `$EA`, points the reset vector at `$0200` and the IRQ and NMI
vectors at `$0300`, and prints one line per cycle, ` <n> <address> <data> <r|w>`
in hexadecimal. It answers four forms:

| Arguments                                | What it prints                                                                           |
| :--------------------------------------- | :--------------------------------------------------------------------------------------- |
| `<program hex> <cycles>`                 | The cycles from the first fetch at `$0200`                                               |
| `reset <program hex> <cycles>`           | The cycles from the release of reset, two half cycles each                               |
| `irq <program hex> <raised at> <cycles>` | As the first form, with node 103 pulled low at the start of cycle `<raised at>` and held |
| `nmi <program hex> <raised at> <cycles>` | As the first form, with node 1297 pulled low the same way                                |

A probe that predates the `reset` form reports the reset case as zero of eleven
cycles and exits 1, which is the runner refusing a probe it cannot use, not a
model failure.

## Conventions that are not negotiable

| Thing                                               | Rule                                                                                                                                                                                                                                                                           |
| :-------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Language                                            | Python only                                                                                                                                                                                                                                                                    |
| Comments                                            | None in source, and a docstring counts as one                                                                                                                                                                                                                                  |
| Test layout                                         | `<module>.test.py` beside the module it covers                                                                                                                                                                                                                                 |
| Coverage                                            | 100% statements and branches, enforced                                                                                                                                                                                                                                         |
| Types                                               | `mypy` at strict, plus every optional error class                                                                                                                                                                                                                              |
| Commits                                             | Conventional Commits, subject under 50 characters                                                                                                                                                                                                                              |
| Suites                                              | Fetched and pinned by commit, never vendored                                                                                                                                                                                                                                   |
| Documents                                           | Read, quoted and pinned by digest. Never committed: none is redistributable                                                                                                                                                                                                    |
| Undefined state                                     | Nothing starts cleared. Registers, flags and memory come up scrambled from the seed. `Cpu(model, fill=N)` is the family's one way to ask for a store holding one byte everywhere, for a run that must get through a few dozen instructions; it never clears registers or flags |
| Fidelity                                            | Where the part and convenience disagree, the part wins. A behaviour that exists only to make a test easier is a defect                                                                                                                                                         |
| Public API                                          | The two cores in this family present the same surface. `Cpu(name)`, `step()`, `reset()`, `irq()`, `nmi()`, `decode(data)`, `disassemble(data)`. A difference needs a hardware reason                                                                                           |
| [`mos65xx/mos6502.py`](mos65xx/mos6502.py) length   | Past 500 lines under the exemption for a single calculation engine sharing intermediate state: one `Cpu` whose opcode handlers share the registers, flags, pin lines and cycle state, and whose hooks the 65C02 overrides one by one                                           |
| [`mos65xx/wdc65816.py`](mos65xx/wdc65816.py) length | Past 500 lines under the same exemption: one `Cpu` whose opcode handlers share the register file, the width and emulation flags, the stack and the cycle state                                                                                                                 |

The linter's ignores in [`pyproject.toml`](pyproject.toml) carry no comments, so
their reasons live here:

- `N818`: some exceptions are control flow signals rather than failures. The
  standard library names those without the suffix too, and the ones that report
  a failure do end in `Error`.
- `N999` in tests: a test file sits beside its module and is named after it with
  a dot, so a module and its tests are read together.
- `T201` in `conformance/`: these are command line tools, and printing is their
  output.
- `BLE001` and `T201` in `environment.py`: a check that throws has to become a
  line in the report rather than end the run, and the report is the product.
- `BLE001` and `T201` in the doctor: it has to survive whatever a check throws
  and report it. A narrower catch would let a traceback take the rest of the
  report with it.

The coverage exclusions carry none either:

- `if __name__ == "__main__":`: the guard hands argv to a function that is
  itself tested, and importing the module to cover it would run the tool.
- `if TYPE_CHECKING:`: the block never runs. Python 3.14 drops it before
  coverage sees it and earlier versions do not, so counting it would make the
  gate mean something different on each runtime.
- `^\s*\.\.\.$` and `: \.\.\.$`: a protocol method's ellipsis is a contract the
  type checker reads and the runtime never runs.
- `@unittest\.skipUnless\(A_PART,`,
  `@unittest\.skipUnless\(A_PART and BUILDABLE,` and
  `^def accounts_for_a_reset\(` in the coverage exclusions: this member is not a
  part, so the family tests that build a `Chip` and account for its reset are
  skipped here and their bodies never run.

The formatter's ignores in [`.prettierignore`](.prettierignore) carry no
comments either, so their reasons live here:

- `pnpm-lock.yaml` and `package-lock.json`: the package manager writes them, in
  its own layout, on every install.
- `node_modules/`, `.venv/`, `venv/`, `build/`, `dist/` and `*.egg-info/`:
  installed or built, never written by hand.
- `.coverage`, `coverage.json`, `htmlcov/` and the tool caches: the output of a
  run, never committed.
- `docs/`, `specs/`, `.work/` and `.claude/`: local working material, never
  committed.

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
  exercisers.py  Klaus Dormann's exercisers, run to the address each one stops at
  exercisers.json  the verdicts they reached, and the commit they come from
  testroms.json  every test program that exercises these parts, and where each runs
```

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
shared() { sed '/^_Everything above this line/q' "$1"; }

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
