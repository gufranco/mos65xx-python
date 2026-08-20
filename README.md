<div align="center">

<h1>65xx Family</h1>

<strong>Interpreters for the 65xx processor family, held to per-opcode conformance suites.</strong>

<br>
<br>

[![CI](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml)
[![Conformance](https://img.shields.io/badge/SingleStepTests-5%2C120%2C000%20%2F%205%2C120%2C000-brightgreen)](#conformance)
[![Coverage](https://img.shields.io/badge/coverage-100%25%20statement%20%2B%20branch-brightgreen)](#tests)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](pyproject.toml)
[![Types](https://img.shields.io/badge/mypy-strict-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

<p align="center">
  <a href="#quick-start">Quick start</a> &nbsp;|&nbsp;
  <a href="#conformance">Conformance</a> &nbsp;|&nbsp;
  <a href="#what-nothing-starts-clean-means">Undefined state</a> &nbsp;|&nbsp;
  <a href="#models">Models</a> &nbsp;|&nbsp;
  <a href="https://github.com/gufranco/mos65xx-python/issues">Issues</a>
</p>

**8** parts · **17,900,000** conformance cases, **0** failures · **256** opcodes each · **346** tests · **100%** statement and branch coverage

```python
from mos65xx import Cpu, SparseMemory

memory = SparseMemory()
memory.write8(0x008000, 0xA9)
memory.write8(0x008001, 0x42)

cpu = Cpu(memory, model="65816", reset=False)
cpu.pb, cpu.pc = 0x00, 0x8000
cpu.step()

cpu.a & 0xFF
# 0x42
```

---

## The problem

Most 65816 interpreters are written to run one program. They implement the opcodes that program uses, they wrap the direct page the way the first failing test demanded, and they start every register at zero. They work, right up until the day something reads a byte nobody wrote.

That last part is the one that bites. Hardware does not hand over a clean machine. A processor coming out of reset holds whatever its registers held, memory holds whatever pattern the parts it is built from settle into, and code that reads either before writing it is a bug. An interpreter whose memory begins at zero hides every one of those reads, so the bug looks like correct behaviour until it runs on a console.

## The solution

Two commitments, and every design decision here follows from one of them.

**Correctness is measured, never asserted.** Every core is checked against the per-opcode suite published for the part it models, 10,000 cases per opcode. All 17,900,000 pass. When a core and the suite disagreed, the suite was right every time, thirteen times running, including on things no datasheet states plainly. Page wrapping, for one, is not uniform across addressing modes: indirect indexed by Y wraps inside its page and indexed indirect by X does not, and that is not a rule anybody would guess.

One of them was a single case in 2,560,000. A jump to a subroutine pushes its return address between reading the two halves of its own destination, so when the stack has walked into the instruction the push overwrites the destination's high byte and the jump goes wherever the pushed byte says. Reading the destination first and pushing afterwards gives the same answer every other time.

Another was decimal subtraction on the CMOS parts. Both parts produce the same digits whenever both operands are valid decimal numbers, and nothing stops a program subtracting one that is not. The older part borrows out of the low digit into the high one; the newer subtracts in binary and corrects afterwards. Feed both `$FC` and they differ by a whole digit.

**Nothing starts clean.** Memory is filled with a reproducible scrambled pattern unless a caller asks for something else in writing. A reset sets only what the hardware itself defines and leaves the accumulator, the index registers and the low byte of the stack pointer holding what they held.

<table>
<tr>
<td width="50%" valign="top">

### Every opcode, no gaps

All 256 are implemented. The 65816 defines all of them: it has no undocumented instructions, and `$42 WDM` is reserved rather than illegal and behaves as a two byte no operation.

</td>
<td width="50%" valign="top">

### Undefined state stays undefined

`SparseMemory` derives an unwritten byte from its address, so an unwritten read is arbitrary, reproducible, and not zero, at no allocation cost.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### One family, one interface

The model is a constructor argument. Differences in address bus width, instruction set and silicon defects live in the model rather than in a separate project.

</td>
<td width="50%" valign="top">

### The oracle is pinned, and watched

The suite commit is pinned so a build is reproducible. A weekly job runs against whatever upstream holds now and opens a pull request or an issue.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### Interruptible block moves

`MVN` and `MVP` are the one instruction meant to be interrupted. Given a cycle budget they copy what fits, rewind onto their own opcode, and resume exactly where they stopped.

</td>
<td width="50%" valign="top">

### No dependencies

Pure Python, standard library only. The release tooling is the sole `node_modules`, and it never ships.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### The pins, not just the opcodes

`irq()`, `nmi()` and, on the 65816, `abort()` take the interrupt the way the pin does: the return address is the next instruction, the pushed status says which pin it was, and emulation mode pushes one byte fewer. A request refused by the disable flag still ends a wait.

</td>
<td width="50%" valign="top">

### Read from the datasheets

Every hardware fact this project relies on is in [`conformance/hardware.json`](conformance/hardware.json) with the sentence it was read from. Where a manufacturer's document and the recorded cycles disagree, [`conformance/divergences.json`](conformance/divergences.json) carries both and says what would settle it.

</td>
</tr>
</table>

## Quick start

### Prerequisites

| Tool | Version | Install |
|:-----|:--------|:--------|
| Python | >= 3.12 | [python.org](https://www.python.org/downloads/) |

### Setup

```bash
git clone https://github.com/gufranco/mos65xx-python.git
cd mos65xx-python
```

### Verify

```bash
python3 mos65xx/wdc65816.test.py
# Ran 86 tests in 22.9s
# OK
```

## Reading without running

An interpreter has to be given a machine to run in. A survey of a ROM has nothing but the file, so reading and running are separate halves and only one of them needs a machine.

```python
from mos65xx import disassemble

for instruction in disassemble(rom, offset=0x1234, address=0x8C1234, count=3):
    print(instruction.address, instruction.mnemonic, instruction.operand)
```

Operand width is not a property of the opcode. The same immediate load takes one byte or two depending on flags the processor set earlier, so `disassemble` carries `m` and `x` and tracks them across the instructions that change them. A disassembler that assumes sixteen bits produces plausible output that drifts one byte at a time until it is decoding operands as opcodes.

A run of bytes too short to complete its instruction raises `Truncated` rather than returning a guess.

## Models

The model is chosen at construction. `Cpu(memory)` gives a 65816.

```python
from mos65xx import Cpu, SparseMemory, describe

describe("w65c802").address_bits
# 16

cpu = Cpu(SparseMemory(), model="65802")
```

| Model | Address bits | Decimal | Notes |
|:------|:------------:|:-------:|:------|
| `6502` | 16 | yes | MOS 6502. Aliases: `mos6502`, `nmos6502`, `6510`, `8500` |
| `6507` | 13 | yes | The same die in a smaller package. Aliases: `mos6507` |
| `2a03` | 16 | **no** | Ricoh 2A03 and 2A07. Aliases: `ricoh2a03`, `2a07`, `nes6502`, `famicom` |
| `65c02` | 16 | yes | The base CMOS design. Aliases: `synertek65c02`, `cmos6502` |
| `r65c02` | 16 | yes | Rockwell R65C02, adding thirty two single-bit instructions. Aliases: `rockwell65c02` |
| `w65c02` | 16 | yes | WDC W65C02S, adding stop and wait. Aliases: `wdc65c02`, `w65c02s` |
| `65802` | 16 | yes | WDC W65C802, the sixteen bit core in a 6502 pin out. Aliases: `w65c802`, `65c802` |
| `65816` | 24 | yes | WDC W65C816S. Aliases: `w65c816`, `w65c816s`, `65c816`, `65816s` |

Three of those differences are the kind that produce a bug rather than a compile error.

The address bus is not cosmetic. The 65802 has sixteen address lines, so bank bits never leave the chip and a read of `$7E0012` lands on `$0012`. The 6507 has thirteen, so everything above eight kilobytes is a mirror of something below it.

Decimal mode is a property of the part. The Ricoh variant in the Famicom has the decimal adder left unwired, so the flag can be set and changes nothing. Code that sets it and expects decimal arithmetic is wrong, and the part will not say so.

And the undocumented instructions are not optional. A hundred and fifty one of the 6502's opcodes were never documented, programs used them anyway, and a core that treats them as undefined is wrong for the machines that shipped.

Revisions are separate models, including the ones that only fixed a bug, because a machine has whichever revision it was built with. The three CMOS parts differ in exactly two opcode columns and two opcodes: a bit-clear instruction on a part that does not have it is a no-operation, and nothing reports that the bit was never cleared.

> [!NOTE]
> A model is only listed once a conformance suite backs it. A model with no suite behind it would make its fidelity a claim rather than a measurement.

## What "nothing starts clean" means

```python
from mos65xx import Cpu, Memory, SparseMemory

SparseMemory().read8(0x123456)
# some byte derived from the address; the same byte every time; not zero

Memory(size=0x1000).data == bytearray(0x1000)
# False

Memory(size=0x1000, fill=0).data == bytearray(0x1000)
# True, because a caller asked for it in writing

cpu = Cpu(Memory(size=0x1000000, fill=0))
cpu.a, cpu.x, cpu.y
# whatever a reset leaves behind, reproducible from the seed, not zero
```

`SparseMemory` holds only what has been written and hashes the address for everything else, so a test that touches a dozen bytes does not pay for sixteen megabytes to stay unclean. Both take a `seed`, so a differential run against another implementation stays comparable.

## Conformance

```bash
python3 conformance/fetch.py ~/.cache/conformance-suites

python3 conformance/singlestep.py ~/.cache/conformance-suites/65816/65816/v1
#   512 files, as a 65816
#   5120000 agreed, 0 did not

python3 conformance/singlestep.py ~/.cache/conformance-suites/6502/6502/v1 --model 6502
#   256 files, as a 6502
#   2560000 agreed, 0 did not

python3 conformance/singlestep.py ~/.cache/conformance-suites/nes6502/nes6502/v1 --model 2a03
#   256 files, as a 2a03
#   2560000 agreed, 0 did not

python3 conformance/singlestep.py ~/.cache/conformance-suites/wdc65c02/wdc65c02/v1 --model w65c02
#   256 files, as a w65c02
#   2540000 agreed, 0 did not
```

The WDC suite is twenty thousand cases short of the others because two of its instructions stop the processor, and a suite that runs one instruction and compares the result has nothing to compare when the processor does not come back.

The suite is several gigabytes, so [`conformance/fetch.py`](conformance/fetch.py) takes a partial clone that skips blob history and a sparse checkout of only the directories [`conformance/suites.json`](conformance/suites.json) names.

Each case gives a full initial state, the bytes in memory, and the state one instruction later. [`conformance/singlestep.py`](conformance/singlestep.py) builds exactly that machine, steps once, and compares every register the part has and every named byte. Only the registers a case names are set, because a suite for a part with fewer of them names fewer of them. Memory outside the named bytes is scrambled rather than cleared, because the suite says nothing about those addresses and filling them with zeroes would make an undefined read look deliberate.

### How the pin is kept honest

| When | What runs | On disagreement |
|:-----|:----------|:----------------|
| Pull request | 1,000 cases per opcode against the pinned commit | Fails the check |
| Push to `main` | All 20,000 cases per opcode against the pinned commit | Fails the check |
| Weekly | All cases against whatever upstream holds now | Opens a pull request if it passes, an issue naming the opcodes if it does not |

A pinned oracle keeps a build reproducible and stops an upstream edit from turning this repository red with no commit of its own to explain it. It is also how a repository stops noticing that the thing judging it has moved. [`.github/workflows/suite-watch.yml`](.github/workflows/suite-watch.yml) closes that gap without ever moving the pin on its own.

## Project structure

```
mos65xx/
  __init__.py         the family, and the model chosen at construction
  models.py           what each part is: address bus, instruction set, defects
  memory.py           memory that holds what it held
  wdc65816.py         the 65816 core
  opcodes65816.py     the opcode table and a disassembler
  opcodes6502.py      the same for the eight bit parts, undocumented opcodes included
  opcodes65c02.py     what the CMOS parts changed, written as the difference
  mos6502.py          the eight bit core
  mos65c02.py         the CMOS core, which is that one with its bugs fixed
  version.py          rewritten by the release job and by nothing else
conformance/
  fetch.py            partial, sparse, pinned checkout of the suites
  singlestep.py       runs the suite and reports what disagreed
  suites.json         which suites, which commit
```

Each module has its tests beside it as `<module>.test.py`, so a module and the cases that pin its behaviour are read together.

## Tests

```bash
for f in mos65xx/*.test.py conformance/*.test.py; do python3 "$f"; done
```

| Suite | File | Covers |
|:------|:-----|:-------|
| Core | [`mos65xx/wdc65816.test.py`](mos65xx/wdc65816.test.py) | Every opcode in four register-width states, addressing, arithmetic, decimal, stack, block moves, interrupts, reset |
| Opcode table | [`mos65xx/opcodes65816.test.py`](mos65xx/opcodes65816.test.py) | Decoding, width-dependent operand size, disassembly |
| Memory | [`mos65xx/memory.test.py`](mos65xx/memory.test.py) | Scrambled fills, sparse derivation, address wrapping, seeding |
| Models | [`mos65xx/models.test.py`](mos65xx/models.test.py) | The catalogue, alias matching, address masking |
| Conformance harness | [`conformance/singlestep.test.py`](conformance/singlestep.test.py) | State construction, comparison, reporting, the command line |
| Cycle harness | [`conformance/cycles.test.py`](conformance/cycles.test.py) | Bus comparison, the refusals, halts counted apart |
| Hardware facts | [`conformance/hardware.test.py`](conformance/hardware.test.py) | Every recorded datasheet fact against the code |
| Divergences | [`conformance/divergences.test.py`](conformance/divergences.test.py) | Each recorded disagreement, driven |
| Suite fetch | [`conformance/fetch.test.py`](conformance/fetch.test.py) | Checkout shape, timeouts, failure reporting, against a real git repository |

Nothing is stubbed. The fetch tests run git against a repository built in a temporary directory, because a stand-in for git would only prove the stand-in works.

Coverage is enforced at 100% of statements and branches by [`pyproject.toml`](pyproject.toml), so a new branch without a test fails the build rather than quietly lowering the number.

## Development

| Command | Description |
|:--------|:------------|
| `ruff format .` | Format |
| `ruff check .` | Lint |
| `python3 -m coverage run -a <file>` | Run one test file under coverage |
| `python3 -m coverage report` | Coverage, which fails below 100% |
| `python3 conformance/fetch.py <dir>` | Fetch the pinned suites |
| `python3 conformance/singlestep.py <dir> [limit] [filter]` | Run the suite against state |
| `python3 conformance/cycles.py <dir> --model 6502` | Run the suite against the bus, cycle by cycle |

## Project conventions

| Convention | Source |
|:-----------|:-------|
| Commit format | [Conventional Commits](https://www.conventionalcommits.org/) |
| Releases | [semantic-release](https://semantic-release.gitbook.io/), driven by [`.releaserc.json`](.releaserc.json) |
| Lint and format | [Ruff](https://docs.astral.sh/ruff/), configured in [`pyproject.toml`](pyproject.toml) |
| Test layout | `<module>.test.py` beside the module it covers |

## Versioning

This project follows [Semantic Versioning](https://semver.org/), and every release is tagged from `main` by semantic-release. See [releases](https://github.com/gufranco/mos65xx-python/releases).

> [!IMPORTANT]
> While the version is below `1.0.0`, the public interface may change on a minor release. Pin an exact version if that matters to you.

## FAQ

<details>
<summary><strong>Why is memory scrambled by default rather than zeroed?</strong></summary>
<br>

Because a console is. Code that reads a byte it never wrote is reading whatever the hardware settled on, and that read is a bug. Zero-filled memory makes the bug invisible: the value read is stable, plausible, and usually harmless, so the test passes and the console does not. Scrambling makes the read show up as what it is. Pass `fill=0` when you genuinely want zeroes, and the decision is then recorded in the code.

</details>

<details>
<summary><strong>Why is page wrapping different between addressing modes?</strong></summary>
<br>

Because the hardware is. Indirect indexed by Y wraps its pointer inside the page; indexed indirect by X does not. The same split runs through the long indirect modes and `PEI`. This is not a rule any datasheet states in one place; it was read off the suite, one addressing mode at a time.

</details>

<details>
<summary><strong>Does a block move run to completion in one step?</strong></summary>
<br>

Only when nothing limits it. Set `cycle_budget` and `MVN` or `MVP` copies what fits at seven cycles a byte, then rewinds the program counter over its own three bytes so the same instruction is fetched again. A move of sixty thousand bytes is sixty thousand executions of one instruction, which is exactly how the hardware makes it interruptible.

</details>

<details>
<summary><strong>Why does bit 4 of the pushed status differ between BRK and an interrupt?</strong></summary>
<br>

For `BRK` and `COP` it does not, and that is the interesting part. In native mode bit 4 is the index width and is pushed as it stands. In emulation mode the width bit does not exist and the bit reads as the break flag, set. Nothing has to force it: a processor in emulation mode always reports its index registers as narrow, so the bit is already set by the time the status is read. The suite confirms `COP` pushes it the same way `BRK` does.

A pin is the other half of the answer. The cycle table's note against the cycle that pushes the status for `ABORT`, `IRQ`, `NMI` and `RES` reads "BRK bit 4 equals \"0\" in Emulation mode", so a hardware interrupt clears it, and in emulation mode that clear bit is the only thing a handler can look at to tell a pin from a break.

</details>

<details>
<summary><strong>Why not use an existing Python 65816 emulator?</strong></summary>
<br>

The ones worth borrowing from are embedded in emulators and shaped by the machine around them. This is a standalone core with a conformance suite attached, so it can be a submodule in more than one project and stay correct in all of them.

</details>

## License

[MIT](LICENSE)

## What is settled, and what is not

**Settled: what every instruction does to state.** The SingleStepTests corpora,
pinned by commit, check registers, flags and every byte of memory an instruction
touched, across every opcode including the undocumented ones no datasheet
describes. That is as strong as instruction-level evidence for these parts gets.

**Read, not inferred: what the manufacturers printed.** The W65C816S data sheet
and the MCS6500 family hardware manual were read end to end, and every fact this
project takes from them is in [`conformance/hardware.json`](conformance/hardware.json)
with its sentence. That reading found a defect, a missing feature, a vector table
that is wrong in the datasheet itself, and two places where the document and the
recorded cycles disagree. The disagreements are in
[`conformance/divergences.json`](conformance/divergences.json), measured, with
what would settle them.

**Not settled by anything here: the pins under load.** `irq()`, `nmi()` and
`abort()` perform the documented sequence, and no published suite covers a
hardware interrupt on these parts, so they rest on the datasheet rather than on a
recording. The abort pin's rollback of the instruction it interrupts is not
modelled at all, and the code says so where it lives.

**Settled for the NMOS parts: every cycle, not just their number.** The 6502 puts
an address on the bus in every cycle it runs, including the ones it spends
thinking, so the recorded list of accesses is its timing and its side effects at
once. `conformance/cycles.py` compares that list address by address, value by
value, read against write, in order. All 2,440,000 non-halting cases in the pinned
6502 suite agree, across all 256 opcodes. The dummy reads are in: the discarded
pointer read of `(zp,X)`, the read at the half-formed address when an index
crosses a page, the second write a read-modify-write performs, the stack read
before a pull, and the instruction a taken branch does not run.

A cycle count alone would not have caught any of that. A model can spend the right
number of cycles reading the wrong addresses, and two of the three sources
disagreed about exactly that.

**Not settled: the CMOS parts and the 65816.** The CMOS parts spend their spare
cycles at different addresses, write once rather than twice in a
read-modify-write, and take an extra cycle on decimal arithmetic. Every one of
those differences is now measured, per mode, with the case that shows it, in
[`conformance/divergences.json`](conformance/divergences.json). None is
implemented, so the runner refuses those parts rather than reporting a comparison
it cannot make. The 65816 needs more than addresses: its recordings carry pin
states and cycles with no access at all.

**The 12 halting opcodes are outside the claim.** A jam stops the part, and what a
stopped part drives for the rest of a recording is a property of the recording's
length. Those cases are counted and reported separately rather than skipped
quietly.

## Project conventions

| Convention | Source |
|:--|:--|
| Commit format | [Conventional Commits](https://www.conventionalcommits.org/) |
| Formatting and lint | [ruff](https://docs.astral.sh/ruff/), configured in [`pyproject.toml`](pyproject.toml) |
| Types | [mypy](https://mypy.readthedocs.io/) at strict, configured in [`pyproject.toml`](pyproject.toml) |
| Tests | Beside the module, named `<module>.test.py` |
| Agent instructions | [`AGENTS.md`](AGENTS.md) |
| Current behaviour | [`specs/current/`](specs/current/), requirements with checkable scenarios |
