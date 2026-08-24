<div align="center">

<h1>MOS 65xx</h1>

<strong>Interpreters for the 65xx family, from the 6502 to the 65816, driveable from a clock and held to a per-opcode suite for every cycle of every opcode.</strong>

<br>
<br>

[![CI](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml)
[![Conformance](https://img.shields.io/badge/SingleStepTests-17%2C900%2C000%20%2F%2017%2C900%2C000-brightgreen)](#is-it-right)
[![Cycles](https://img.shields.io/badge/bus%20cycles-17%2C870%2C080%20compared-brightgreen)](#is-it-right)
[![Coverage](https://img.shields.io/badge/coverage-100%25%20statement%20%2B%20branch-brightgreen)](#working-on-it)
[![Types](https://img.shields.io/badge/mypy-strict-blue)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

**16** parts · **17,900,000** state cases and **17,870,080** cycle-exact cases, **0** failures · **1,070** tests · **100%** statement and branch coverage · no dependencies

```python
from mos65xx import Cpu, SparseMemory

memory = SparseMemory()
memory.write8(0x008000, 0xA9)
memory.write8(0x008001, 0x42)

cpu = Cpu("65816", memory)
cpu.reset()
cpu.pb, cpu.pc = 0x00, 0x8000

cpu.step()

print(hex(cpu.a & 0xFF))
```

```
0x42
```

## Install

```bash
pip install git+https://github.com/gufranco/mos65xx-python.git
```

Python 3.12 or newer. Nothing else.

## The interface

Everything a caller touches. Nothing else is public.

| Call | Does | Returns |
|:--|:--|:--|
| `Cpu(model="65816", memory=None, **options)` | Builds a part, powered and not yet reset. Memory of its own if none is given | a `Cpu` |
| `cpu.reset(seed=...)` | Drives RESET. Costs the six delay cycles the manual names plus the two of the vector fetch | the `Cpu` |
| `cpu.step()` | Runs one instruction | cycles it cost |
| `cpu.run_for(cycles)` | Runs whole instructions until at least that many cycles have passed. Keeps clocking a part that has halted | cycles actually spent, usually a little over |
| `cpu.run_until(check, limit=None)` | Steps while `check(cpu)` is false. `limit` bounds the instructions and raises `RunLimit` | the `Cpu` |
| `cpu.call(address)` | Runs from an address until the routine there returns | the `Cpu` |
| `cpu.held()` | Whether the part can still begin an instruction: jammed, stopped or waiting | `bool` |
| `cpu.irq()` / `cpu.nmi()` / `cpu.abort()` | Pulls a line and acts on it now | `True` if taken |
| `cpu.status()` / `cpu.set_status(byte)` | The status register as a byte, the portable way across the family | `int` / nothing |
| `disassemble(data, offset, address, count)` | Reads bytes with no machine to run them in | `Instruction` objects with `.text` |
| `describe(model)` | The part behind a name, before building one | a `Model` |

| Pin or attribute | Is |
|:--|:--|
| `cpu.irq_line` | The request line as a level. "No interrupt will occur if the interrupt source is cleared prior to interrupt recognition", so a request withdrawn before the instruction ends is not taken |
| `cpu.nmi_line` | The non-maskable line. Edge sensitive: the transition interrupts, and holding it afterwards does not interrupt again |
| `cpu.ready_line` | High when the part may proceed. Held low it halts the part where it stands. The NMOS parts finish a write in progress and the CMOS parts do not |
| `cpu.cycles` / `cpu.steps` | Cycles since construction, across resets; instructions since the last reset |
| `cpu.a`, `.x`, `.y`, `.s`, `.pc` | The registers. The 65816 adds `.db`, `.pb`, `.d`, `.m8`, `.x8`, `.emulation` |
| `cpu.n`, `.v`, `.z`, `.c` | The flags that mean the same on every part, one attribute each rather than bits to mask |
| `cpu.stopped`, `.waiting`, `.jammed` | The three ways a part stops running, which are not one state |
| `cpu.trace` | Set it to a list and every bus cycle is appended: address, value, and on the 65816 eight output pins |
| `cpu.on_cycle` | Called once per cycle, after that cycle's bus activity |
| `cpu.package_pins` | Which interrupt lines this package actually brings out |

Options: `seed=` fixes the undefined state. The eight-bit cores also take `decimal=False` and `table=`, both set for you by name, so `Cpu("2a03")` is the normal way to ask.

**A part arrives powered, not reset**, because no board hands over one that has reset itself. Every register holds rubbish derived from the seed, the program counter included, so stepping it executes rubbish from a rubbish address. Call `reset()` to get a machine that runs a program.

**Two attribute names mean different things on different parts**, because both are idiomatic for the part they belong to and renaming either would make that part read wrongly.

| Name | On an eight-bit part | On the 65816 |
|:--|:--|:--|
| `.d` | the decimal flag, a `bool` | the direct page register, a 16-bit `int` |
| `.decimal` | whether the part has a decimal adder wired at all | the decimal flag |
| `.i` / `.irq_disable` | `.i` | `.irq_disable` |

Code meant for both should reach for `status()` and `set_status()`, which are the same byte everywhere.

## Running it at a real speed

A part runs at whatever its crystal says. `step()` reports what an instruction cost, so a host can hold the part to a real clock.

```python
import time

from mos65xx import Cpu

HERTZ = 1_789_773
SLICE = 0.02

cpu = Cpu("2a03")
cpu.reset()
per_slice = round(HERTZ * SLICE)
owed = 0

for _ in range(5):
    began = time.perf_counter()
    owed += per_slice
    owed -= cpu.run_for(owed)
    time.sleep(max(0.0, SLICE - (time.perf_counter() - began)))
```

An instruction cannot be cut in half, so `run_for()` overshoots and returns what it really spent. Carrying the overshoot into the next slice is what stops a long run drifting. A part that has halted still costs its host every cycle, so this keeps spending rather than raising: a jammed NMOS part goes on driving `$FFFF`, and a 65816 given `STP` or `WAI` produces cycles with no address and every line inactive.

## Driving it one cycle at a time

`Clock` stops the part between any two cycles, which is where a board changes what a read will answer.

```python
from mos65xx import Clock, Cpu, Memory

space = Memory(image=bytes([0xA5, 0x10]))
space.write8(0x0010, 0x11)
cpu = Cpu("6502", space)
cpu.reset()
cpu.pc = 0x0000
cpu.trace = []

with Clock(cpu) as clock:
    clock.tick()
    clock.tick()
    space.write8(0x0010, 0x99)
    clock.run_for(1)

print([(hex(address), hex(value)) for address, value, _ in cpu.trace])
```

```
[('0x0', '0xa5'), ('0x1', '0x10'), ('0x10', '0x99')]
```

The read picked up a byte written after the instruction had already begun. That is real suspension rather than a replay, and it is what makes the three pins above mean anything.

It is not free. An instruction is an ordinary call stack and Python cannot suspend one, so the clock runs the part on a thread and lets it block where the cycle is spent, which is what ares and bsnes do. Expect roughly fifty times slower than `step()`. Use `step()` for speed and `Clock` when the question is where a cycle falls.

## Models

The model is a constructor argument. Address bus width, instruction set and silicon defects live in the model rather than in a separate project.

| Build it with | Address bits | Pins | Decimal | Notes |
|:--|:--:|:--|:--:|:--|
| `Cpu("6502")` | 16 | IRQ, NMI, RDY | yes | MOS 6502. Aliases: `mos6502`, `nmos6502`, `6510`, `8500` |
| `Cpu("6503")` | 12 | IRQ, NMI | yes | Four kilobytes, on-chip clock. Aliases: `mos6503` |
| `Cpu("6504")` | 13 | IRQ | yes | Eight kilobytes, no non-maskable pin. Aliases: `mos6504` |
| `Cpu("6505")` | 12 | IRQ, RDY | yes | Four kilobytes, ready line, no non-maskable pin. Aliases: `mos6505` |
| `Cpu("6506")` | 12 | IRQ | yes | Four kilobytes, second clock output instead of ready. Aliases: `mos6506` |
| `Cpu("6507")` | 13 | RDY | yes | The same die in a smaller package, no interrupt pins at all. Aliases: `mos6507` |
| `Cpu("6512")` | 16 | IRQ, NMI, RDY | yes | The 6502 with the clock oscillator left off the die. Aliases: `mos6512` |
| `Cpu("6513")` | 12 | IRQ, NMI | yes | The 6503 on an external clock. Aliases: `mos6513` |
| `Cpu("6514")` | 13 | IRQ | yes | The 6504 on an external clock. Aliases: `mos6514` |
| `Cpu("6515")` | 12 | IRQ, RDY | yes | The 6505 on an external clock. Aliases: `mos6515` |
| `Cpu("2a03")` | 16 | IRQ, NMI, RDY | **no** | Ricoh 2A03 and 2A07, decimal adder unwired. Aliases: `ricoh2a03`, `2a07`, `ricoh2a07`, `nes6502`, `famicom` |
| `Cpu("65c02")` | 16 | IRQ, NMI, RDY | yes | The base CMOS design. Aliases: `synertek65c02`, `cmos6502` |
| `Cpu("r65c02")` | 16 | IRQ, NMI, RDY | yes | Rockwell R65C02, adding thirty two single-bit instructions. Aliases: `rockwell65c02` |
| `Cpu("w65c02")` | 16 | IRQ, NMI, RDY | yes | WDC W65C02S, adding stop and wait. Aliases: `wdc65c02`, `w65c02s` |
| `Cpu("65802")` | 16 | IRQ, NMI, RDY | yes | WDC W65C802, the sixteen bit core in a 6502 pin out. Aliases: `w65c802`, `65c802` |
| `Cpu("65816")` | 24 | IRQ, NMI, RDY | yes | WDC W65C816S. Aliases: `w65c816`, `w65c816s`, `65c816`, `65816s` |

Three of those differences produce a bug rather than a compile error. The address bus is not cosmetic: the 65802 has sixteen lines, so a read of `$7E0012` lands on `$0012`. Neither are the pins, so a line the package does not bring out raises rather than quietly taking the interrupt.

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

And decimal mode is a property of the part: the Ricoh variant has the adder unwired, so the flag can be set and changes nothing.

All 256 opcodes are implemented on every part, undocumented ones included. MOS documented a hundred and fifty one of them; the other hundred and five it never mentioned, programs used them anyway, and a core that treats them as undefined is wrong for the machines that shipped.

## Reading without running

A survey of a ROM has nothing but the file, so reading and running are separate halves.

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

Operand width is not a property of the opcode. The same immediate load takes one byte or two depending on flags set earlier, so `disassemble` carries `m` and `x` and tracks them. A disassembler that assumes sixteen bits produces plausible output that drifts one byte at a time until it is decoding operands as opcodes. A run too short to complete its instruction raises `Truncated` rather than returning a guess.

## Nothing starts clean

Memory and registers hold a reproducible scrambled pattern. There is no parameter that clears them and there will not be one: a read of a byte nothing wrote is a defect on real silicon, and memory that answers zero turns that defect into a passing test.

```python
from mos65xx import Cpu, Memory, SparseMemory

print(hex(SparseMemory().read8(0x123456)))
print(Memory(size=0x1000).data == bytearray(0x1000))

powered = Cpu("65816", Memory(size=0x1000000))
print(hex(powered.pc), powered.cycles)
```

```
0x1d
False
0xd8ef 0
```

`SparseMemory` derives an unwritten byte from its address, so a test that touches a dozen bytes does not pay for sixteen megabytes. Both take a `seed`, so a differential run against another implementation stays comparable. `Memory` takes an `image` instead of a fill, which is what a board genuinely knows at power on.

## Is it right

Every core is checked against the per-opcode suite published for the part it models, 10,000 cases per opcode: **17,900,000 cases, no failures**. The comparison then goes further and checks what the part put on the bus, cycle by cycle, address by address, and on the 65816 pin by pin: **17,870,080 cases, no failures**.

```bash
python3 -m conformance.fetch ~/.cache/conformance-suites
python3 -m conformance.singlestep ~/.cache/conformance-suites/6502/6502/v1 --model 6502
python3 -m conformance.cycles ~/.cache/conformance-suites/6502/6502/v1 --model 6502
```

Every eight-bit part drives an address in every cycle it runs, including the ones it spends thinking, so the recorded list of accesses is timing and side effects at once. The 65816 lowers both address lines instead, and those cycles are compared too, pins included. A cycle count alone would settle nothing: a model can spend the right number of cycles reading the wrong addresses.

Instructions that halt the part are compared as well. A jammed NMOS part reads `$FFFF`, then `$FFFE` twice, and drives `$FFFF` from there, in all 120,000 recorded cases without one exception. One kind of case sits outside the claim and is counted and named: decimal add and subtract with an immediate operand on the CMOS parts spend a cycle whose recorded address is a constant no register produces, which is a recorder's placeholder rather than a measurement.

When a core and the suite disagreed, the suite was right every time, including on things no datasheet states plainly. Page wrapping is not uniform across addressing modes: indirect indexed by Y wraps inside its page and indexed indirect by X does not, and that is not a rule anybody would guess.

The suite commit is pinned so a build is reproducible, and a weekly job runs against whatever upstream holds now and opens a pull request or an issue.

Where a document and the recordings disagree, both are kept. [`conformance/hardware.json`](conformance/hardware.json) holds every fact taken from a manufacturer's page with the sentence it came from; [`conformance/addressing-cycles.json`](conformance/addressing-cycles.json) and [`conformance/instruction-set.json`](conformance/instruction-set.json) hold Appendix A and Appendix B as printed; [`conformance/divergences.json`](conformance/divergences.json) holds every place two sources part, with what would settle it.

**Fifteen questions remain** where being faithful is a claim rather than a measurement, and each names the measurement that would close it: [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md). Almost all would fall to one logic analyser on one real part running a dozen short programs. The parts are still made.

## Working on it

```bash
python3 -m coverage erase
for file in $(find mos65xx conformance -name '*.test.py' | sort); do
  python3 -m coverage run -a "$file"
done
python3 -m coverage report
```

`python -m mos65xx.doctor` says what is actually on this machine: the parts, what makes each one different, and whether the files this repository cannot carry are here and whole. It is what an issue asks for, because a report is only as good as what it says about the machine that produced it.

Tests sit beside the module they cover, named `<module>.test.py`. Coverage is 100% of statements and branches, enforced. Types are `mypy` at strict. Commits follow [Conventional Commits](https://www.conventionalcommits.org/), and releases are cut by [semantic-release](https://semantic-release.gitbook.io/).

[`AGENTS.md`](AGENTS.md) is the document for an agent working here. [`FAMILY.md`](FAMILY.md) is the standard this repository shares with [zilog-z80-python](https://github.com/gufranco/zilog-z80-python), kept identical in both.

```
mos65xx/
  models.py        what each part is: address bus, instruction set, defects
  errors.py        the states no instruction gets a part out of, defined once
  memory.py        memory that holds what it held
  clock.py         driving a part one cycle at a time
  mos6502.py       the eight bit core
  mos65c02.py      the CMOS core, which is that one with its bugs fixed
  wdc65816.py      the sixteen bit core
  opcodes*.py      one opcode table and disassembler per part
conformance/
  suites.json      which corpora, at which commit
  singlestep.py    running them, state by state
  cycles.py        running them, bus cycle by bus cycle
  hardware.json    what the manufacturers printed, fact by fact
  divergences.json where sources part
```

## References

This project ships no documents. Every claim about the hardware is traced to something published by the people who made the parts, listed here so a reader can fetch the same file and check the same page. Each row gives the page count and the first sixteen characters of the file's SHA-256, because vendor links move and a link that has rotted into a different revision is easy to follow without noticing. Compute the full digest with `shasum -a 256 <file>`.

Every one of these is copyrighted by its publisher and not redistributable, which is why none is in this repository. Individual sentences are quoted in [`conformance/hardware.json`](conformance/hardware.json) with the page they came from.

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

Two parts have no data sheet of their own. Ricoh never published one for the **2A03**, so the MOS documents cover the core it is built from and the suite records the part separately because its decimal adder is not wired. WDC's **W65C802** is the 65816 core in a forty pin package with sixteen address lines, and none of the three W65C816S revisions mentions it, so the 65816 documents cover the core and only the packaging is undocumented.

The corpora come from [SingleStepTests](https://github.com/SingleStepTests), pinned by commit in [`conformance/suites.json`](conformance/suites.json).

## Citing this

[CITATION.cff](CITATION.cff) is kept in step with the released version by the same script that stamps the package, so the version it names is the version that shipped. GitHub renders it as a Cite this repository button.

## License

[MIT](LICENSE)
