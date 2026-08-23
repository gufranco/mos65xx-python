<div align="center">

<h1>65xx Family</h1>

<strong>Interpreters for the 65xx processor family, held to per-opcode conformance suites.</strong>

<br>
<br>

[![CI](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml)
[![Conformance](https://img.shields.io/badge/SingleStepTests-17%2C900%2C000%20%2F%2017%2C900%2C000-brightgreen)](#conformance)
[![Cycles](https://img.shields.io/badge/bus%20cycles-17%2C870%2C080%20compared-brightgreen)](#conformance)
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

**16** parts · **17,900,000** state cases and **17,870,080** cycle-exact cases, **0** failures · **256** opcodes each · **778** tests · **100%** statement and branch coverage

```python
from mos65xx import Cpu, SparseMemory

memory = SparseMemory()
memory.write8(0x008000, 0xA9)
memory.write8(0x008001, 0x42)

cpu = Cpu("65816", memory, reset=False)
cpu.pb, cpu.pc = 0x00, 0x8000
cpu.step()

print(hex(cpu.a & 0xFF))
```

```
0x42
```

---

## The problem

Most 65816 interpreters are written to run one program. They implement the opcodes that program uses, they wrap the direct page the way the first failing test demanded, and they start every register at zero. They work, right up until the day something reads a byte nobody wrote.

That last part is the one that bites. Hardware does not hand over a clean machine. A processor coming out of reset holds whatever its registers held, memory holds whatever pattern the parts it is built from settle into, and code that reads either before writing it is a bug. An interpreter whose memory begins at zero hides every one of those reads, so the bug looks like correct behaviour until it runs on a console.

## The solution

Two commitments, and every design decision here follows from one of them.

**Correctness is measured, never asserted.** Every core is checked against the per-opcode suite published for the part it models, 10,000 cases per opcode. All 17,900,000 pass, and the comparison goes further: 17,870,080 cases match the recorded bus activity cycle for cycle, address by address, and on the 65816 pin by pin. When a core and the suite disagreed, the suite was right every time, thirteen times running, including on things no datasheet states plainly. Page wrapping, for one, is not uniform across addressing modes: indirect indexed by Y wraps inside its page and indexed indirect by X does not, and that is not a rule anybody would guess.

One of them was a single case in 2,560,000. A jump to a subroutine pushes its return address between reading the two halves of its own destination, so when the stack has walked into the instruction the push overwrites the destination's high byte and the jump goes wherever the pushed byte says. Reading the destination first and pushing afterwards gives the same answer every other time.

Another was decimal subtraction on the CMOS parts. Both parts produce the same digits whenever both operands are valid decimal numbers, and nothing stops a program subtracting one that is not. The older part borrows out of the low digit into the high one; the newer subtracts in binary and corrects afterwards. Feed both `$FC` and they differ by a whole digit.

**Nothing starts clean, and nothing can be asked to.** Memory holds a reproducible scrambled pattern and there is no parameter that clears it. A reset sets only what the hardware itself defines and leaves the accumulator, the index registers and the low byte of the stack pointer holding what they held.

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

Every hardware fact this project relies on is in [`conformance/hardware.json`](conformance/hardware.json) with the sentence it was read from, every cycle of every NMOS addressing mode is in [`conformance/addressing-cycles.json`](conformance/addressing-cycles.json) as Appendix A prints it, and all 151 documented opcodes are in [`conformance/instruction-set.json`](conformance/instruction-set.json) as Appendix B prints them. Where a manufacturer's document and the recorded cycles disagree, [`conformance/divergences.json`](conformance/divergences.json) carries both and says what would settle it.

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
```

```
Ran 150 tests in 24.9s

OK
```

## Running at a real speed

A part does not run at "as fast as the host manages". It runs at whatever its
crystal says, and every instruction costs a known number of cycles. `step()`
returns what the instruction it ran cost, `cycles` is the running total, and
`run_for()` spends a budget of them so a host can hold the part to a real clock.

```python
import time

from mos65xx import Cpu

HERTZ = 1_789_773
SLICE = 0.02

cpu = Cpu("2a03")
per_slice = round(HERTZ * SLICE)
owed = 0

for _ in range(5):
    began = time.perf_counter()
    owed += per_slice
    owed -= cpu.run_for(owed)
    time.sleep(max(0.0, SLICE - (time.perf_counter() - began)))

print(cpu.cycles)
```

An instruction is not divisible, so `run_for()` almost always overshoots its
budget slightly and returns what it really spent. Carrying that overshoot into
the next slice, rather than throwing it away, is what stops a long run drifting
away from the wall clock.

A part that has halted still costs its host every cycle, so `run_for()` keeps
spending rather than raising. A jammed NMOS part goes on driving $FFFF, and a
65816 that has run STP or WAI produces cycles with no address and every output
line inactive, which is what the recordings show. `step()` raises instead, since
no further instruction will complete: `Stopped` for a part that needs a reset,
`Waiting` for one an interrupt will release.

## Reading without running

An interpreter has to be given a machine to run in. A survey of a ROM has nothing but the file, so reading and running are separate halves and only one of them needs a machine.

```python
from mos65xx import disassemble

rom = bytes.fromhex("a90048a5108d0021")

for instruction in disassemble(rom, offset=0, address=0x8C1234, count=3):
    print(f"{instruction.address:06X}  {instruction.text}")
```

```
8C1234  lda #$00
8C1236  pha
8C1237  lda $10
```

Operand width is not a property of the opcode. The same immediate load takes one byte or two depending on flags the processor set earlier, so `disassemble` carries `m` and `x` and tracks them across the instructions that change them. A disassembler that assumes sixteen bits produces plausible output that drifts one byte at a time until it is decoding operands as opcodes.

A run of bytes too short to complete its instruction raises `Truncated` rather than returning a guess.

## Models

The model is named at construction. `Cpu()` gives a 65816, and memory is optional.

```python
from mos65xx import Cpu, SparseMemory, describe

print(describe("w65c802").address_bits)

cpu = Cpu("65802", SparseMemory())
```

```
16
```

| Model | Address bits | Pins | Decimal | Notes |
|:------|:------------:|:-----|:-------:|:------|
| `6502` | 16 | IRQ, NMI, RDY | yes | MOS 6502. Aliases: `mos6502`, `nmos6502`, `6510`, `8500` |
| `6503` | 12 | IRQ, NMI | yes | Four kilobytes, on-chip clock. Aliases: `mos6503` |
| `6504` | 13 | IRQ | yes | Eight kilobytes, no non-maskable pin. Aliases: `mos6504` |
| `6505` | 12 | IRQ, RDY | yes | Four kilobytes, ready line, no non-maskable pin. Aliases: `mos6505` |
| `6506` | 12 | IRQ | yes | Four kilobytes, second clock output instead of ready. Aliases: `mos6506` |
| `6507` | 13 | RDY | yes | The same die in a smaller package, no interrupt pins at all. Aliases: `mos6507` |
| `6512` | 16 | IRQ, NMI, RDY | yes | The 6502 with the clock oscillator left off the die. Aliases: `mos6512` |
| `6513` | 12 | IRQ, NMI | yes | The 6503 on an external clock. Aliases: `mos6513` |
| `6514` | 13 | IRQ | yes | The 6504 on an external clock. Aliases: `mos6514` |
| `6515` | 12 | IRQ, RDY | yes | The 6505 on an external clock. Aliases: `mos6515` |
| `2a03` | 16 | IRQ, NMI, RDY | **no** | Ricoh 2A03 and 2A07. Aliases: `ricoh2a03`, `2a07`, `nes6502`, `famicom` |
| `65c02` | 16 | IRQ, NMI, RDY | yes | The base CMOS design. Aliases: `synertek65c02`, `cmos6502` |
| `r65c02` | 16 | IRQ, NMI, RDY | yes | Rockwell R65C02, adding thirty two single-bit instructions. Aliases: `rockwell65c02` |
| `w65c02` | 16 | IRQ, NMI, RDY | yes | WDC W65C02S, adding stop and wait. Aliases: `wdc65c02`, `w65c02s` |
| `65802` | 16 | IRQ, NMI, RDY | yes | WDC W65C802, the sixteen bit core in a 6502 pin out. Aliases: `w65c802`, `65c802` |
| `65816` | 24 | IRQ, NMI, RDY | yes | WDC W65C816S. Aliases: `w65c816`, `w65c816s`, `65c816`, `65816s` |

Three of those differences are the kind that produce a bug rather than a compile error.

The address bus is not cosmetic. The 65802 has sixteen address lines, so bank bits never leave the chip and a read of `$7E0012` lands on `$0012`. The 6507 has thirteen, so everything above eight kilobytes is a mirror of something below it.

Neither are the pins. The ten NMOS packages share one die and one instruction set, and what separates most of them is how far an address reaches and which interrupt lines the package brought out. A line that is not on the package is not a line a system can assert, so pulling one here raises rather than quietly taking the interrupt:

```python
from mos65xx import Cpu, SparseMemory

cpu = Cpu("6507", SparseMemory())
try:
    cpu.irq()
except Exception as refused:
    print(type(refused).__name__, refused, sep=": ")
```

```
NoSuchPin: the 6507 has no irq pin; it brings out rdy
```

Decimal mode is a property of the part. The Ricoh variant in the Famicom has the decimal adder left unwired, so the flag can be set and changes nothing. Code that sets it and expects decimal arithmetic is wrong, and the part will not say so.

And the undocumented instructions are not optional. A hundred and fifty one of the 6502's opcodes were never documented, programs used them anyway, and a core that treats them as undefined is wrong for the machines that shipped.

Revisions are separate models, including the ones that only fixed a bug, because a machine has whichever revision it was built with. The three CMOS parts differ in exactly two opcode columns and two opcodes: a bit-clear instruction on a part that does not have it is a no-operation, and nothing reports that the bit was never cleared.

> [!NOTE]
> A model is only listed once something measures it. Six are held to a suite of their own. The other ten name the part they narrow and are held to that part's suite plus a check that the narrowing, fewer address lines or fewer pins, is the only difference. Either way the fidelity is a measurement rather than a claim.

## What "nothing starts clean" means

```python
from mos65xx import Cpu, Memory, SparseMemory

print(hex(SparseMemory().read8(0x123456)))
print(SparseMemory().read8(0x123456) == SparseMemory().read8(0x123456))
print(Memory(size=0x1000).data == bytearray(0x1000))

cpu = Cpu("65816", Memory(size=0x1000000))
print(hex(cpu.a), hex(cpu.x), hex(cpu.y))
```

```
0x1d
True
False
0x6ceb 0xef 0xd8
```

A byte derived from the address, the same byte every time, and not zero. No
memory here compares equal to a run of zeroes and there is no argument that
would make one, because no board hands over a cleared one. The registers hold
what a reset left behind, which is reproducible from the seed and is not zero
either.

`SparseMemory` holds only what has been written and hashes the address for everything else, so a test that touches a dozen bytes does not pay for sixteen megabytes to stay unclean. Both take a `seed`, so a differential run against another implementation stays comparable. Neither takes a fill: an earlier version let a caller name a byte to fill with, and every use of it turned out to be a test quietly arranging for a read of unwritten memory to answer zero, which is the exact defect the scrambling exists to expose. `Memory` takes an `image` instead, which is what a board genuinely knows at power on, and leaves everything the image does not cover undefined.

### The appendix, cycle by cycle

Appendix A of the MCS6500 Hardware Manual prints the address bus, the data bus
and the read write line for every cycle of every addressing mode. It is the only
manufacturer statement of NMOS bus behaviour this project has found, so all
twenty-seven of its tables are in
[`conformance/addressing-cycles.json`](conformance/addressing-cycles.json) with
the manual's own address expressions rather than a paraphrase.
[`conformance/addressing_cycles.test.py`](conformance/addressing_cycles.test.py)
drives each shape and resolves those expressions against the run, so a row that
stops matching names the page it came from. That check needs no suite on the
machine.

Three of the tables say something the part does not do, and each is recorded
rather than quietly followed:

- The discarded read of an indexed access. Four tables give its high byte as
  `BAH + C`; the indirect Y store two pages later gives it as `BAH`, with no
  carry. Only the second matches the part, and only the second explains why the
  other four carry a footnote saying that read has to be ignored. This is the
  cycle that makes an indexed store to a hardware register touch a second
  register one page below the one it names.
- The branch table. Its two address rows sit one row lower than they run: the
  part drives the plain program counter on the third cycle, the partially
  corrected target on the fourth, and never reaches the corrected target inside
  the branch at all.
- The stack addresses of a pull, written as plain sums. They hold everywhere
  except across the edge of page one, which is exactly where a deep sequence of
  pushes leaves the pointer.

### The instruction set, as the manufacturer stated it

Appendix B of the MCS6500 Programming Manual gives each of the fifty-six
documented instructions its own page: the flags it touches, and for every
addressing mode the opcode, the byte count and the cycle count. That is a
hundred and fifty-one opcodes, which is the whole documented set, and all of
them are in
[`conformance/instruction-set.json`](conformance/instruction-set.json).

[`conformance/instruction_set.test.py`](conformance/instruction_set.test.py)
holds three separate things to it. The opcode table this project decodes with
has to name the same mnemonic, mode and length for every one. Each instruction
has to take the cycles the page prints, with the extra cycle appearing exactly
where the page marks a page crossing. And each of the two hundred and
fifty-seven flag rules that are absolute, this one is always reset, this one is
never touched, has to hold across twenty-four states.

Two rows are misprinted, and the record says so rather than following them.
`AND (Oper), Y` and `ORA (Oper), Y` are printed without the asterisk that marks
the page-crossing cycle, while the six other Group One instructions carry it and
while these same two carry it on their absolute indexed rows one line above. The
part takes the cycle on all eight.

### The opcodes the CMOS parts reserved

The NMOS parts leave forty-four opcodes undefined, and some of them stop the
part until it is reset, so nothing can be asserted about them. The CMOS parts
turned every one into a no-operation of a stated length, and the W65C02S data
sheet prints that length and timing for each. That is in
[`conformance/cmos-reserved.json`](conformance/cmos-reserved.json) and checked
by
[`conformance/cmos_reserved.test.py`](conformance/cmos_reserved.test.py).

The cell that carries the list has its own columns break part way down, so the
reading is settled by arithmetic rather than by layout: the six groups come to
forty-four opcodes, the same data sheet says the part has two hundred and
twelve, and the opcode matrix on an earlier page leaves exactly forty-four
blank. Three counts in one document agreeing is what fixes it.

Forty-three of the forty-four hold. The exception is `5C`, where the data sheet
says eight cycles and thirty thousand recorded cases across three parts all say
four. The data sheet gives a count and no addresses, so following it would mean
inventing four bus cycles nobody has written down. The four this project takes
are the ones the recordings show, and the disagreement is in
[`conformance/divergences.json`](conformance/divergences.json) with the one
measurement that would close it.

### Where the parts differ, from the one page that compares them

Most of what separates these parts has to be inferred from two documents that
never mention each other. Table 8-1 of the W65C816S data sheet is the exception:
it sets the NMOS part, both CMOS eight bit parts and the sixteen bit part in four
columns and says what each one does. Five of its rows are things this project can
drive, and all twenty cells are checked in
[`conformance/part-differences.json`](conformance/part-differences.json) and
[`conformance/part_differences.test.py`](conformance/part_differences.test.py).

`JMP (a)` with its vector at the top of a page gets three different answers. The
oldest part takes the high byte from the bottom of the same page, which is the
defect, and spends five cycles. The CMOS eight bit parts take it from the next
page and charge a sixth cycle for the fix. The sixteen bit part takes it from the
next page and still spends five.

Four of the five rows separate the parts, and every one of them separates them
the same way: the two CMOS eight bit parts on one side, the NMOS part and the
sixteen bit part together on the other. That holds for the shift of an indexed
absolute, for the indirect jump, for the extra cycle decimal arithmetic costs,
and for which address the discarded cycle of an indexed access lands on.

### Three revisions of one data sheet, and what changed between them

Three revisions of the W65C816S data sheet are pinned here, from 1994, 2004 and
2024. Reading all three answers a question a single revision cannot: which
claims are stable and which are an artefact of the copy someone happened to
download.

The comparison table is stable. Every cell of it is identical in 2004 and 2024,
twenty years apart, with only the section number moving from 8-1 to 7-1. A claim
taken from that table does not need a revision pinned beside it.

One sentence is not stable, and it lost information rather than gaining it. The
1994 revision lists the addressing modes that run past the emulation stack range
as `JSL; JSR(a,x); PEA, PEI, PER, PHD, PLD, RTL; d, s; (d,s), y`. The 2004 and
2024 revisions stop after `RTL`. The two that were dropped are the stack
relative modes, and they belong in the list: with the stack pointer at `01FF`, a
stack relative read lands at `0002FE` rather than wrapping, which the recorded
cycles confirm and this project reproduces. The earliest revision is the one
that describes the part.

### The sixteen bit part's bus, cycle by cycle

The 65816 had no rung one cycle check at all until now: its timing rested
entirely on a recording. Table 6-7 of its data sheet closes that. Across seven
pages it prints all eight output lines for every cycle of every addressing mode,
vector pull and memory lock included, and all forty-seven groups and three
hundred and twenty-eight rows are in
[`conformance/bus-operation.json`](conformance/bus-operation.json).

[`conformance/bus_operation.test.py`](conformance/bus_operation.test.py) drives
forty-four of the forty-seven and resolves the table's own address expressions
against each run. The three it does not drive are the two that never finish an
instruction, stop-the-clock and wait-for-interrupt, and the hardware interrupt
group, which a pin drives rather than an opcode.

The runs use eight bit registers, a direct register with no low byte and no
index crossing a page. That is the one configuration in which every note the
table carries is inactive, which matters because the Note column is a merged
cell whose row alignment cannot be recovered from the extracted text. Switching
any note on would mean guessing which row it belongs to.

Two hundred and fifty-seven of the two hundred and sixty-six rows reached match
exactly. The nine that do not fall into two classes, both recorded:

- Five rows carry an address that is only right when the register is sixteen
  bits. Each sits directly below a row that exists only in that wider form, and
  each names the byte that wider form would have left behind. The four
  read-modify-write modify cycles come out a byte high and the push a byte low,
  because the stack grows the other way. The table has no eight bit form of
  those rows.
- Four rows disagree about a pin rather than an address. The table marks the two
  bytes of a new program counter, fetched through an indexed pointer, as a valid
  program address. The part marks them a valid data address, and so does the
  table itself two groups later for the same operation through a pointer in bank
  zero. Only a logic analyser on the real pins can settle that one, and
  [`conformance/divergences.json`](conformance/divergences.json) says so.

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
  errors.py           the states no instruction gets a part out of, defined once
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
  cycles.py           holds every bus cycle to the suite rather than the end state
  suites.json         which suites, which commit
  hardware.json       what the datasheets print, fact by fact, with the sentence
  addressing-cycles.json  every cycle of every NMOS addressing mode, as printed
  instruction-set.json    every documented opcode, its length, timing and flags
  cmos-reserved.json      the 44 opcodes the CMOS parts left as no-operations
  part-differences.json   the one table that sets all four parts side by side
  bus-operation.json      all 8 output lines, every cycle, every 65816 mode
  divergences.json    where a document and the recorded cycles part, and why
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
| Cycle harness | [`conformance/cycles.test.py`](conformance/cycles.test.py) | Bus comparison, the refusals, placeholders counted apart |
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
| `python3 conformance/cycles.py <dir> --model 65816` | The same, for any of the eight parts |

## Project conventions

| Convention | Source |
|:-----------|:-------|
| Commit format | [Conventional Commits](https://www.conventionalcommits.org/) |
| Releases | [semantic-release](https://semantic-release.gitbook.io/), driven by [`.releaserc.json`](.releaserc.json) |
| Lint and format | [Ruff](https://docs.astral.sh/ruff/), configured in [`pyproject.toml`](pyproject.toml) |
| Types | [mypy](https://mypy.readthedocs.io/) at strict, configured in [`pyproject.toml`](pyproject.toml) |
| Test layout | `<module>.test.py` beside the module it covers |

## Versioning

This project follows [Semantic Versioning](https://semver.org/), and every release is tagged from `main` by semantic-release. See [releases](https://github.com/gufranco/mos65xx-python/releases).

> [!IMPORTANT]
> While the version is below `1.0.0`, the public interface may change on a minor release. Pin an exact version if that matters to you.

## FAQ

<details>
<summary><strong>Why is memory scrambled by default rather than zeroed?</strong></summary>
<br>

Because a console is. Code that reads a byte it never wrote is reading whatever the hardware settled on, and that read is a bug. Zero-filled memory makes the bug invisible: the value read is stable, plausible, and usually harmless, so the test passes and the console does not. Scrambling makes the read show up as what it is. Pass `` when you genuinely want zeroes, and the decision is then recorded in the code.

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

## What is still open

Nine questions remain where being faithful to the silicon is a claim rather than
a measurement, and each one names the measurement that would close it. They are
in [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md), kept in step with
[`conformance/divergences.json`](conformance/divergences.json) by a test, so the
file cannot quietly become a claim that this project knows more than it does.

Almost all of them would fall to one logic analyser on one real part running a
dozen short programs. The parts are still made.

## References

This project ships no documents. Every claim it makes about the hardware is
traced to something published by the people who made the parts, and that is
listed here so a reader can fetch the same file and check the same page.

Each row carries the page count and the first sixteen characters of the file's
SHA-256. Vendor links move, and a link that has rotted into a different revision
is easy to follow without noticing: the digest is what tells you whether the file
you fetched is the file these records were read from. The full digests are
checked locally by the manifest that manages them.

Every one of these is copyrighted by its publisher and is not redistributable, so
none of them is in this repository. WDC's notice is explicit about it, reserving
"the right of reproduction in whole or in part in any form". Individual sentences
are quoted in [`conformance/hardware.json`](conformance/hardware.json) with the
page they came from, which is fair use and is what makes the records checkable.

| Document | Date | Pages | SHA-256 |
|:---------|:-----|------:|:--------|
| [MOS Technology, Inc., *MCS6500 Microcomputer Family Hardware Manual*](https://archive.org/download/mcs-6500-family-hardware-manual-1976-01/MCS6500_family_hardware_manual_1976-01.pdf) | 1976-01 | 182 | `81ea570c9d68deff…` |
| [MOS Technology, Inc., *MCS6500 Microcomputer Family Programming Manual*](https://archive.org/download/6500-50A_MCS6500_Programming_Manual_1976_Jan/6500-50A_MCS6500_Programming_Manual_1976_Jan.pdf) | 1976-01 | 262 | `a2d54dd8b6557c7f…` |
| [MOS Technology, Inc., *MOS 6500 Microprocessors*](https://6502.org/documents/datasheets/mos/mos_6500_mpu_nov_1985.pdf) | 1985-11 | 12 | `ccd72376d1e5db1f…` |
| [MOS Technology, Inc., *MOS 6500 Microprocessors*](https://6502.org/documents/datasheets/mos/mos_6500_mpu_mar_1980.pdf) | 1980-03 | 12 | `a564c4de593ea178…` |
| [Synertek, Inc., *SY6500 Microprocessors*](https://6502.org/documents/datasheets/synertek/synertek_sy6500_microprocessors.pdf) | undated | 6 | `f20b50961df60bb0…` |
| [Synertek, Inc., *SY6500 Hardware Manual*](https://6502.org/documents/datasheets/synertek/synertek_hardware_manual.pdf) | undated | 178 | `9cd0991dcbb4a46b…` |
| [Rockwell International, *R65C00 Microprocessors: R65C02, R65C102 and R65C112*](https://6502.org/documents/datasheets/rockwell/rockwell_r65c00_microprocessors.pdf) | 1987-06 | 16 | `63deee76c8d0d4fa…` |
| [The Western Design Center, Inc., *W65C02S 8-bit Microprocessor Data Sheet*](https://westerndesigncenter.com/wdc/documentation/w65c02s.pdf) | 2022-04-08 | 32 | `a6af3ca9da45c8a0…` |
| [The Western Design Center, Inc., *W65C816S 8/16-bit Microprocessor Data Sheet*](https://datasheets.chipdb.org/Western%20Design/w65c816s.pdf) | 2004-06-14 | 62 | `60f21a3da0331273…` |
| [The Western Design Center, Inc., *W65C816S 8/16-bit Microprocessor Data Sheet*](https://6502.org/documents/datasheets/wdc/wdc_w65c816s_jul_1994.pdf) | 1994-07 | 72 | `823c2f286a97102f…` |
| [The Western Design Center, Inc., *W65C816S Datasheet*](https://westerndesigncenter.com/wdc/documentation/w65c816s.pdf) | 2024-03-13 | 55 | `b9177e1b045d2c8a…` |

The two coprocessor parts this family covers have no document of their own. What
stands in for one is recorded under `partsWithNoDocument` in the manifest, and
the reasoning is in [`conformance/divergences.json`](conformance/divergences.json).

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

**Settled: every cycle of every part, not just their number.** The eight-bit parts
put an address on the bus in every cycle they run, including the ones they spend
thinking, so the recorded list of accesses is timing and side effects at once. The
65816 does not: it lowers both address lines instead, and the recordings carry
those cycles with no value and the state of eight output pins.
`conformance/cycles.py` compares all of it, address by address, value by value,
read against write, pin by pin, in order. **17,870,080 cases agree**, across every
opcode of all eight parts.

The spare cycles are in, and they are not the same on every part. The NMOS parts
put a half-formed address on the bus while they work out a carry, write twice in
a read-modify-write, and read the pointer of an indirect jump wrongly at a page
end. The CMOS parts re-read the last byte of the instruction instead, read twice
and write once, spend an indirect jump's extra cycle on the address the older
part's bug would have used, and turn two whole columns of the opcode matrix into
one-cycle no-operations. Decimal arithmetic costs them a cycle it does not cost
the NMOS part.

A cycle count alone would not have caught any of that. A model can spend the right
number of cycles reading the wrong addresses, and the documents disagree with the
recordings about exactly that in five places, each one recorded in
[`conformance/divergences.json`](conformance/divergences.json) with the case that
shows it.

On the 65816 the pins are part of the comparison, and they catch things an address
would not. Memory lock goes low for the last three cycles of a read-modify-write,
or five when the accumulator is wide. The two width bits and the emulation bit
appear on every cycle, so a mode change is visible in the middle of an
instruction: a return from interrupt pulls a new status byte and the cycles that
follow still carry the old widths. And the modify cycle of a read-modify-write is
an internal cycle in native mode and a write in emulation mode, driving the byte
it just read at an address nothing answers, which is how a part compatible with
one that writes twice avoids writing twice.

**One kind of case sits outside the claim, counted and named.** Decimal add and
subtract with an immediate operand on the CMOS parts spend a cycle with no address
to compute, and the recordings fill it with a constant that no register produces:
about 10,000 cases per CMOS suite. That is a recorder's placeholder rather than a
measurement, so a case differing only there is counted apart instead of being
called a disagreement.

The instructions that halt the part used to sit outside it too, on the grounds
that what a halted part drives for the rest of a recording is a property of the
recording's length rather than of the instruction. Only the length is. The shape
is fixed and the recordings pin it down: a jammed NMOS part reads $FFFF, then
$FFFE twice, and drives $FFFF from there, in all 120,000 recorded cases without
one exception; a 65816 given STP or WAI spends three cycles and then drives no
address at all with every output line inactive, in all 40,000. Both are modelled
and both are compared over the whole recording, which brought 280,000 cases into
the claim and left nothing excluded as a halt.
