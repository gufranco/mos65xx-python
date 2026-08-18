<div align="center">

<h1>65xx Family</h1>

<strong>Interpreters for the 65xx processor family, held to per-opcode conformance suites.</strong>

<br>
<br>

[![CI](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml)
[![Conformance](https://img.shields.io/badge/SingleStepTests-5%2C120%2C000%20%2F%205%2C120%2C000-brightgreen)](#conformance)
[![Coverage](https://img.shields.io/badge/coverage-100%25%20statement%20%2B%20branch-brightgreen)](#tests)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

<p align="center">
  <a href="#quick-start">Quick start</a> &nbsp;|&nbsp;
  <a href="#conformance">Conformance</a> &nbsp;|&nbsp;
  <a href="#what-nothing-starts-clean-means">Undefined state</a> &nbsp;|&nbsp;
  <a href="#models">Models</a> &nbsp;|&nbsp;
  <a href="https://github.com/gufranco/mos65xx-python/issues">Issues</a>
</p>

**256** opcodes · **92** mnemonics · **26** addressing modes · **5,120,000** conformance cases, **0** failures · **192** tests · **100%** statement and branch coverage

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

**Correctness is measured, never asserted.** The core is checked against [SingleStepTests](https://github.com/SingleStepTests/ProcessorTests), which carries 10,000 cases for each opcode in each of the processor's two modes. All 5,120,000 pass. When this core and the suite disagreed, the suite was right eleven times running, including on things no datasheet states plainly. Page wrapping, for one, is not uniform across addressing modes: indirect indexed by Y wraps inside its page and indexed indirect by X does not, and that is not a rule anybody would guess.

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

| Model | Address bits | Notes |
|:------|:------------:|:------|
| `65816` | 24 | WDC W65C816S. Aliases: `w65c816`, `w65c816s`, `65c816`, `65816s` |
| `65802` | 16 | WDC W65C802, the same core in a 6502 pin out. Bank registers exist and reach nothing outside the first bank. Aliases: `w65c802`, `65c802` |

The address bus is not cosmetic. The 65802 has sixteen address lines, so bank bits never leave the chip and a read of `$7E0012` lands on `$0012`.

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
#   512 files from ~/.cache/conformance-suites/65816/65816/v1
#   5120000 agreed, 0 did not
```

The suite is several gigabytes, so [`conformance/fetch.py`](conformance/fetch.py) takes a partial clone that skips blob history and a sparse checkout of only the directories [`conformance/suites.json`](conformance/suites.json) names.

Each case gives a full initial state, the bytes in memory, and the state one instruction later. [`conformance/singlestep.py`](conformance/singlestep.py) builds exactly that machine, steps once, and compares every register, both mode flags and every named byte. Memory outside the named bytes is scrambled rather than cleared, because the suite says nothing about those addresses and filling them with zeroes would make an undefined read look deliberate.

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
| `python3 conformance/singlestep.py <dir> [limit] [filter]` | Run the suite |

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

It does not, on this processor, and that is the interesting part. In native mode bit 4 is the index width and is pushed as it stands. In emulation mode the width bit does not exist and the bit reads as the break flag, set. Nothing has to force it: a processor in emulation mode always reports its index registers as narrow, so the bit is already set by the time the status is read. The suite confirms `COP` pushes it the same way `BRK` does.

</details>

<details>
<summary><strong>Why not use an existing Python 65816 emulator?</strong></summary>
<br>

The ones worth borrowing from are embedded in emulators and shaped by the machine around them. This is a standalone core with a conformance suite attached, so it can be a submodule in more than one project and stay correct in all of them.

</details>

## License

[MIT](LICENSE)
