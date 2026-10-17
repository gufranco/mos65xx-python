# MOS 65xx

Sixteen parts of the 65xx family in Python, from the MOS 6502 to the WDC W65C816S, advanced one bus cycle at a time and held to the SingleStepTests per-opcode suites and to the manufacturers' data sheets.

English &nbsp;|&nbsp; [日本語](README.ja.md) &nbsp;|&nbsp; [简体中文](README.zh-Hans.md) &nbsp;|&nbsp; [繁體中文（香港）](README.zh-HK.md)

[![CI](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/gufranco/mos65xx-python)](https://github.com/gufranco/mos65xx-python/releases)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**16** parts, **17,900,000** state cases and **17,870,080** cycle-exact cases compared, **0** unexplained failures, **1,358** tests, **100%** statement and branch coverage, no dependencies

```python
from mos65xx import Cpu, SparseMemory

memory = SparseMemory()
for address, value in enumerate(bytes.fromhex("18fbc230a93412")):
    memory.write8(0x8000 + address, value)
memory.write8(0xFFFC, 0x00)
memory.write8(0xFFFD, 0x80)

cpu = Cpu("65816", memory)
cpu.reset()
costs = [cpu.step() for _ in range(4)]

print(costs, hex(cpu.a), cpu.emulation, cpu.m8)
print(cpu.steps, cpu.cycles)
```

```
[2, 2, 3, 3] 0x1234 False False
4 18
```

The program at `$8000` is `CLC`, `XCE`, `REP #$30` and `LDA #$1234`. `reset()` costs 8 cycles and loads the program counter from the vector at `$FFFC`. `CLC` and `XCE` leave emulation mode, `REP` widens the accumulator and the index registers, and the load then takes a 16-bit operand. Each `step()` returns the cycles its instruction spent, 10 for the four together, and `cycles` reads 18 because it also counts the 8 the reset spent.

## Install

| Requirement | Version |
|:--|:--|
| Python | 3.12 or newer |
| git | Any, to clone |

```bash
git clone https://github.com/gufranco/mos65xx-python.git
cd mos65xx-python
python3 mos65xx/doctor.py
```

The package imports nothing outside the standard library. `pip install git+https://github.com/gufranco/mos65xx-python.git` installs it with a `mos65xx-doctor` command that runs the same report.

The doctor checks the machine, builds and resets every part, and reports which conformance suites are fetched. It runs as a file rather than with `-m`, so it still reports when the package will not import. It ends with one line. Paste its whole output into any bug report.

```
  26 checks, nothing to report
```

Releases follow [Semantic Versioning](https://semver.org/) and are cut from the commit history by semantic-release. Every release is tagged and listed on the [releases page](https://github.com/gufranco/mos65xx-python/releases).

## The interface

`Cpu(model, memory=None, fill=None, **options)` builds one part, powered and not reset. `model` is required, and leaving it out raises `UnknownModelError` with every name accepted. The sixteen names and their aliases are in [Models](#models). Case, `-` and `_` in a name are ignored. `memory` is any object with `read8(address)` and `write8(address, value)`. Without it the part gets a `SparseMemory`, or a 16 MB `Memory` filled with `fill` when `fill` is given.

| Option | Parts | Effect |
|:--|:--|:--|
| `seed=` | All | Seeds the scrambled power-on registers. Default `UNSET_SEED` |
| `decimal=` | 8-bit | Whether a decimal adder is wired. The model sets it, and only the `2a03` sets it false |
| `table=` | 8-bit | The opcode table. The model sets it |

### Calls

| Call | Effect | Returns |
|:--|:--|:--|
| `reset(seed=UNSET_SEED)` | Drives RESET: six cycles, then two to read the vector at `$FFFC`. The W65C02S takes five and two. Clears `steps`, sets the interrupt disable flag, and on the CMOS parts clears the decimal flag. The 65816 also enters emulation mode with 8-bit registers, `d`, `db` and `pb` at 0 | The part |
| `step()` | Runs one instruction, then samples the interrupt lines | Cycles spent, interrupt entry included |
| `run_for(cycles)` | Runs whole instructions until at least `cycles` have passed. A halted part spends one cycle per call to `held_cycle()` | Cycles spent, which can exceed `cycles` |
| `run_until(check, limit=None)` | Steps while `check(part)` is false. Raises `RunLimit` after `limit` instructions | The part |
| `call(address, limit=None)` | Jumps to `address` and steps until the matching `RTS`, or `RTL` on the 65816, is next. Nested calls are counted | The part |
| `held()` | Whether the part is jammed, stopped or waiting | `bool` |
| `held_cycle()` | One cycle of a halted part. A jammed NMOS part reads `$FFFF`. The other parts spend a cycle with no bus access | Nothing |
| `irq()` | Takes an interrupt request now unless the interrupt disable flag is set | `True` if taken |
| `nmi()` | Takes a non-maskable interrupt now | Nothing on 8-bit parts, `True` on the 65816 |
| `abort()` | 65816 only. Takes an abort now | `True` if taken |
| `status()` | The status register as a byte | `int` |
| `set_status(byte)` | Sets every flag from a byte | Nothing |
| `set_emulation(flag)` | 65816 only. Enters or leaves emulation mode, which forces 8-bit registers and a stack in page one | Nothing |
| `read8(address)` / `write8(address, value)` | One bus cycle through the part's address lines, traced and counted | The byte read, or nothing |
| `power_on(seed)` | Scrambles the registers again, as at construction | Nothing |

On a part whose package does not bring a line out, `irq()` and `nmi()` raise `NoSuchPin`. The 65816 and 65802 bring out all three lines.

### State

| Attribute | Meaning |
|:--|:--|
| `a`, `x`, `y`, `s`, `pc` | The registers. On the 65816 `a`, `x`, `y` and `s` hold 16 bits |
| `db`, `pb`, `d` | 65816 only. Data bank, program bank and the direct page register |
| `n`, `v`, `z`, `c` | The flags with the same meaning on every part, one `bool` each |
| `i`, `d`, `b`, `decimal` | 8-bit parts. Interrupt disable, the decimal flag, the break flag, and whether a decimal adder is wired |
| `irq_disable`, `decimal`, `m8`, `x8`, `emulation` | 65816 only. Interrupt disable, the decimal flag, 8-bit accumulator, 8-bit index registers, emulation mode |
| `irq_line` | The request line as a level. It is sampled after each instruction, so a request withdrawn before then is not taken |
| `nmi_line` | The non-maskable line. A low-to-high change interrupts once, and holding it high does not interrupt again |
| `ready_line` | While false, a read spends cycles until it is true again, so a host clears it from `on_cycle`. The CMOS parts and the 65816 hold writes the same way, and the NMOS parts do not |
| `cycles` | Cycles since construction. A reset adds to it |
| `steps` | Instructions since the last reset |
| `stopped`, `jammed`, `waiting` | The three halt states. `jammed` is NMOS only, `waiting` is the CMOS parts and the 65816 |
| `trace` | Set it to a list and every bus cycle is appended as `(address, value, kind)`. `kind` is `read` or `write` on 8-bit parts, and on the 65816 eight pin letters: data, program, vector pull, write, emulation, `m`, `x`, memory lock. A 65816 internal cycle records `None` as its value except the modify cycle in emulation mode, and a halted cycle records `(None, None, "--------")` |
| `on_cycle` | Called once per cycle, after that cycle's bus activity |
| `model` | The canonical model name |
| `package_pins` | The interrupt and ready lines the package brings out, such as `("irq", "nmi", "rdy")` |
| `address_mask` | The address lines the package brings out. A 6507 reads `$F234` at `$1234` |
| `reset_cycles` | Cycles a reset spends, 8 or 7 |
| `memory` | The memory object |
| `cycle_budget` | 65816 only. When set, `MVN` and `MVP` move only as many bytes as fit in that many cycles |

```python
from mos65xx import Cpu, Memory

space = Memory(size=0x10000, fill=0xEA)
for address, value in {0xFFFC: 0x00, 0xFFFD: 0x02, 0xFFFE: 0x00, 0xFFFF: 0x30}.items():
    space.write8(address, value)
space.write8(0xFFFA, 0x00)
space.write8(0xFFFB, 0x40)
space.write8(0x0200, 0x58)

cpu = Cpu("6502", space).reset()
cpu.irq_line = True
print(cpu.step(), hex(cpu.pc))
cpu.irq_line = False
cpu.nmi_line = True
print(cpu.step(), hex(cpu.pc))
print(cpu.step(), hex(cpu.pc))
```

```
9 0x3000
9 0x4000
2 0x4001
```

`CLI` at `$0200` clears the interrupt disable flag with the request line held, so the same step takes the interrupt through `$FFFE`: 2 cycles for `CLI`, 7 for the entry. Raising the non-maskable line interrupts once through `$FFFA`. The third step runs a `NOP` with the line still high.

### Errors

| Error | Raised when |
|:--|:--|
| `UnknownModelError` | `Cpu()` gets no name, or a name no model or alias goes by |
| `NoSuchPin` | `irq()` or `nmi()` on an 8-bit part whose package does not bring that line out |
| `RunLimit` | `run_until()` or `call()` reaches its `limit` |
| `Stopped` | `step()` on a part that executed `STP` or jammed |
| `Waiting` | `step()` on a part that executed `WAI`. A subclass of `Stopped`. `irq()` and `nmi()` release it |
| `ClockClosed` | `tick()` on a closed `Clock` |
| `Truncated` | `decode()` runs out of bytes before the instruction ends |
| `UnsupportedError` | An opcode table names an instruction or addressing mode the core has no handler for |

### Module contents

| Name | Content |
|:--|:--|
| `MODELS` | The sixteen `Model` records, keyed by canonical name |
| `Model` | `name`, `summary`, `address_bits`, `data_bits`, `decimal`, `pins`, `reset_cycles`, `aliases`, `narrows`, `revision`, `address_mask`, and `build(memory, **options)` |
| `Clock(cpu)` | Runs a part one cycle at a time. See [Driving it one cycle at a time](#driving-it-one-cycle-at-a-time) |
| `Memory(size=0x1000000, image=None, seed=UNSET_SEED, fill=None)` | A flat byte array, scrambled from `seed`, filled with `fill`, then overlaid with `image`. Its bytes are `data` |
| `SparseMemory(seed=UNSET_SEED)` | 24 bits of address space that stores only what was written. Its written bytes are `cells` |
| `scramble(size, seed=UNSET_SEED)` | The scrambled `bytearray` both memories and every part start from |
| `UNSET_SEED` | The default seed, `0x5A5A5A5A` |
| `Cpu65816(memory, seed=UNSET_SEED)` | The 65816 core class, for type checks |
| `OPCODES`, `MODE_SIZE`, `FLAG_DEPENDENT` | The 65816 opcode table as `(mnemonic, mode)` pairs, operand bytes per mode, and the two modes whose width follows `m` or `x` |
| `decode(data, offset=0, address=0, m=True, x=True)` | One 65816 `Instruction`: `address`, `offset`, `opcode`, `mnemonic`, `mode`, `operand`, `size`, `text` |
| `disassemble(data, offset=0, address=0, count=None, m=True, x=True, stop_at_return=False)` | A list of 65816 instructions, tracking `REP` and `SEP`. It stops at the last whole instruction |
| `operand_size(mode, m, x)`, `branch_target(address, size, operand, width)`, `render(mode, operand, address, size, width)`, `apply_flags(instruction, m, x)` | The steps `decode` and `disassemble` are built from |
| `FLAG_C`, `FLAG_Z`, `FLAG_I`, `FLAG_D`, `FLAG_X`, `FLAG_M`, `FLAG_V`, `FLAG_N` | The 65816 status bits, `0x01` to `0x80` |
| `__version__` | The installed version |

The 8-bit opcode tables live in two modules. `mos65xx.opcodes6502` has `NMOS`, `decode(data, offset, address, table=NMOS)` and `disassemble(data, offset, address, count=None, table=NMOS, stop_at_return=False)`, which yields instructions with `undocumented` and `unstable` properties. `mos65xx.opcodes65c02.TABLES` holds the `65c02`, `rockwell` and `wdc` tables.

```python
import mos65xx
from mos65xx import MODELS, Cpu, NoSuchPin, RunLimit, SparseMemory, UnknownModelError

for name in ("6502", "6507", "2a03", "65802"):
    model = MODELS[name]
    print(name, model.address_bits, model.data_bits, model.decimal, model.pins, model.reset_cycles)

print(Cpu("Rockwell65C02").model, Cpu("w65c816s").model)

try:
    Cpu("z80")
except UnknownModelError as refused:
    print(refused)

try:
    Cpu("6507", SparseMemory()).nmi()
except NoSuchPin as refused:
    print(refused)

try:
    Cpu("6502", fill=0xEA).run_until(lambda part: part.a == 0x99, limit=100)
except RunLimit as refused:
    print(refused)
```

```
6502 16 8 True ('irq', 'nmi', 'rdy') 8
6507 13 8 True ('rdy',) 8
2a03 16 8 False ('irq', 'nmi', 'rdy') 8
65802 16 16 True ('irq', 'nmi', 'rdy') 8
r65c02 65816
z80 is not a model this family covers; it has 2a03, 6502, 6503, 6504, 6505, 6506, 6507, 6512, 6513, 6514, 6515, 65802, 65816, 65c02, r65c02, w65c02
the 6507 has no nmi pin; it brings out rdy
gave up after 100 instructions at $31D0
```

### Command-line tools

| Command | Arguments | Exit codes |
|:--|:--|:--|
| `python3 mos65xx/doctor.py` | None | 0 when every check passes, 1 otherwise |
| `python3 -m conformance.fetch` | `[directory] [--latest]`. Default `~/.cache/conformance-suites`. `--latest` takes each upstream head instead of the pin | 0, or 1 when an upstream cannot be reached |
| `python3 -m conformance.singlestep` | `<suite directory> [tests per file] [filter] [--model name]`. Default model `65816` | 0 when every case agrees or no suite is there, 1 on a disagreement, 2 on bad arguments |
| `python3 -m conformance.cycles` | The same as `singlestep` | The same as `singlestep` |
| `python3 -m conformance.documents` | `[--check] [--only substring]` | 0 when every digest matches, 1 when one is refused or the arguments are wrong |
| `python3 -m conformance.quotes` | None | 0 when every quote is found in its document or no document is here, 1 otherwise |
| `python3 -m conformance.speed` | `[--instructions N] [--repeats N]`. Defaults 200,000 and 7 | 0 above the floor of 700,000 cycles per second, 1 below, 2 on bad arguments |
| `python3 -m conformance.netlist` | None. Reads the `NETLIST` variable | 0 when every case agrees or no simulation is configured, 1 otherwise |
| `python3 -m conformance.links` | None | 0, or 1 when a cited address answers 404 or 410 |
| `python3 -m conformance.watch` | `[definition] [--moved]` | 0, or 1 when the definitions cannot be read or disagree |
| `python3 -m conformance.package` | `<wheel>` | 0 when every module is in the wheel and no test is, 1 otherwise, 2 with no argument |

## Running it at a real speed

`step()` and `run_for()` report the cycles spent, so a host can hold the part to a crystal. A Ricoh 2A03 runs at 1,789,773 Hz.

```python
import time

from mos65xx import Cpu

HERTZ = 1_789_773
SLICE = 0.02

cpu = Cpu("2a03", fill=0xEA).reset()
per_slice = round(HERTZ * SLICE)
owed = 0

for _ in range(4):
    began = time.perf_counter()
    owed += per_slice
    owed -= cpu.run_for(owed)
    print(per_slice, owed, cpu.cycles)
    time.sleep(max(0.0, SLICE - (time.perf_counter() - began)))
```

```
35795 -1 35804
35795 0 71598
35795 -1 107394
35795 0 143188
```

Memory filled with `NOP` runs 2 cycles per instruction, and a slice of 35,795 cycles is odd. `run_for()` cannot cut an instruction in half, so it overshoots by one cycle. Carrying the debt into the next slice keeps the total within one cycle of the clock. A halted part still spends every cycle it is given: a jammed NMOS part keeps reading `$FFFF`, and a 65816 after `STP` or `WAI` produces cycles with no address.

## Driving it one cycle at a time

`Clock(cpu)` stops the part between any two cycles, where a board changes what a later read will answer.

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

`LDA $10` had fetched its opcode and operand when the byte at `$0010` changed, and its third cycle read the new value.

| Call | Effect |
|:--|:--|
| `tick()` | Runs the part to the end of its next cycle and returns the clock's cycle count |
| `run_for(cycles)` | `cycles` ticks. Returns the clock's cycle count |
| `close()` | Stops the worker thread and restores the part's `on_cycle` |
| `cycles`, `closed`, `cpu` | Ticks so far, whether it is closed, the part it drives |

A `Clock` is a context manager and an iterator that yields one tick at a time. A halted part keeps ticking through `held_cycle()`. Python cannot suspend a call stack, so the clock runs the part on a worker thread and hands control across two semaphores every cycle. Use `step()` for throughput and `Clock` when the question is which cycle something happens in.

## Models

The model decides the address lines, the interrupt lines, the decimal adder and the instruction set.

| Build it with | Address bits | Pins | Decimal | Part | Aliases |
|:--|:--:|:--|:--:|:--|:--|
| `Cpu("6502")` | 16 | IRQ, NMI, RDY | Yes | MOS 6502 | `mos6502`, `nmos6502`, `6510`, `8500` |
| `Cpu("6503")` | 12 | IRQ, NMI | Yes | MOS 6503 | `mos6503` |
| `Cpu("6504")` | 13 | IRQ | Yes | MOS 6504 | `mos6504` |
| `Cpu("6505")` | 12 | IRQ, RDY | Yes | MOS 6505 | `mos6505` |
| `Cpu("6506")` | 12 | IRQ | Yes | MOS 6506, a second clock output in place of RDY | `mos6506` |
| `Cpu("6507")` | 13 | RDY | Yes | MOS 6507 | `mos6507` |
| `Cpu("6512")` | 16 | IRQ, NMI, RDY | Yes | MOS 6512, the 6502 on an external two-phase clock | `mos6512` |
| `Cpu("6513")` | 12 | IRQ, NMI | Yes | MOS 6513, the 6503 on an external clock | `mos6513` |
| `Cpu("6514")` | 13 | IRQ | Yes | MOS 6514, the 6504 on an external clock | `mos6514` |
| `Cpu("6515")` | 12 | IRQ, RDY | Yes | MOS 6515, the 6505 on an external clock | `mos6515` |
| `Cpu("2a03")` | 16 | IRQ, NMI, RDY | No | Ricoh 2A03 and 2A07 | `ricoh2a03`, `2a07`, `ricoh2a07`, `nes6502`, `famicom` |
| `Cpu("65c02")` | 16 | IRQ, NMI, RDY | Yes | The base CMOS design | `synertek65c02`, `s65c02`, `cmos6502` |
| `Cpu("r65c02")` | 16 | IRQ, NMI, RDY | Yes | Rockwell R65C02, adding 32 single-bit instructions | `rockwell65c02`, `rockwell` |
| `Cpu("w65c02")` | 16 | IRQ, NMI, RDY | Yes | WDC W65C02S, adding `STP` and `WAI` | `wdc65c02`, `w65c02s` |
| `Cpu("65802")` | 16 | IRQ, NMI, RDY | Yes | WDC W65C802, the 65816 core with 16 address lines | `w65c802`, `65c802` |
| `Cpu("65816")` | 24 | IRQ, NMI, RDY | Yes | WDC W65C816S | `w65c816`, `w65c816s`, `65c816`, `65816s` |

The eleven NMOS models share one core, the three 65C02 models share a second, and the 65816 and 65802 share a third. A narrower package reaches less: the 65802 reads `$7E0012` at `$0012`, and a 6507 reads `$F234` at `$1234`. On the 2A03 the decimal flag can be set and changes nothing.

```python
from mos65xx import Cpu, SparseMemory

memory = SparseMemory()
memory.write8(0x0012, 0x5A)
memory.write8(0x7E0012, 0xA5)

for name in ("65816", "65802"):
    print(name, hex(Cpu(name, memory).read8(0x7E0012)))

for name in ("6502", "2a03"):
    cpu = Cpu(name, SparseMemory())
    cpu.a, cpu.c, cpu.d = 0x19, False, True
    cpu.add_with_carry(0x01)
    print(name, hex(cpu.a))
```

```
65816 0xa5
65802 0x5a
6502 0x20
2a03 0x1a
```

All 256 opcodes run on every 8-bit part. MOS documented a hundred and fifty one of them. The other hundred and five run as the suites record them, `JAM` included, and [`conformance/instruction-set.json`](conformance/instruction-set.json) holds the documented split as Appendix B prints it.

## Reading without running

`disassemble()` reads bytes with no part to run them in.

```python
from mos65xx import disassemble
from mos65xx.opcodes6502 import NMOS, render
from mos65xx.opcodes6502 import disassemble as disassemble8
from mos65xx.opcodes65c02 import TABLES

for instruction in disassemble(bytes.fromhex("c230a9341260"), address=0x018000):
    print(f"{instruction.address:06X}  {instruction.size}  {instruction.text}")

code = bytes.fromhex("a9ff8f3412")
for table in (NMOS, TABLES["wdc"]):
    for found in disassemble8(code, 0, 0xC000, table=table):
        operand = render(found.mode, found.operand, found.address, found.size)
        print(f"{found.address:04X}  {found.mnemonic} {operand}  {found.undocumented}")
```

```
018000  2  rep #$30
018002  3  lda #$1234
018005  1  rts
C000  lda #$FF  False
C002  sax $1234  True
C000  lda #$FF  False
C002  bbs0 $34,$C017  False
```

On the 65816 the width of an immediate operand depends on flags set earlier. `disassemble` starts with `m` and `x` set and follows every `REP` and `SEP`, so after `REP #$30` the load takes two operand bytes. The same 8-bit bytes decode as the undocumented `SAX` on an NMOS part and as `BBS0` on a W65C02S.

## Nothing starts clean

Registers and memory power up holding a reproducible scrambled pattern, so a program that reads a byte nothing wrote gets a byte that is not zero. Registers have no option that clears them. A memory is cleared only when built with `fill`.

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

`SparseMemory` derives an unwritten byte from its address and seed, so a test that touches a dozen bytes stores a dozen. Both memories and every part take a `seed`, so a run against another implementation repeats exactly. `Memory` takes an `image`, which is what a board holds at power on.

## Is it right

Every core is compared with the SingleStepTests suite recorded for its part, 10,000 cases per opcode across six suites: 65816, 6502, nes6502, synertek65c02, rockwell65c02 and wdc65c02. The state comparison checks registers, flags and every byte of memory each case touched: **17,900,000 cases, no unexplained failures**. The cycle comparison checks every bus cycle in order, address by address and read against write, and on the 65816 the eight pins as well: **17,870,080 cases, no unexplained failures**.

```bash
python3 -m conformance.fetch ~/.cache/conformance-suites
python3 -m conformance.singlestep ~/.cache/conformance-suites/6502/6502/v1 --model 6502
python3 -m conformance.cycles ~/.cache/conformance-suites/6502/6502/v1 --model 6502
```

Both totals are derived from [`conformance/suites.json`](conformance/suites.json), and a test holds this page to them. The wdc65c02 suite ships the files for `WAI` and `STP` empty. The cycle total leaves out 29,920 CMOS decimal cases whose extra cycle is recorded at a constant address no register produces. Both runners leave out thirty-seven 65816 cases by condition and print how many they left out: the suite and the data sheet disagree about where a one-byte pull lands when the emulation stack pointer is at the top of page one, and this core follows the data sheet.

[`conformance/hardware.json`](conformance/hardware.json) holds every fact taken from a manufacturer's page, with the sentence and the page it came from, and tests hold the code to them. [`conformance/addressing-cycles.json`](conformance/addressing-cycles.json) and [`conformance/instruction-set.json`](conformance/instruction-set.json) hold Appendix A of the hardware manual and Appendix B of the programming manual as printed. [`conformance/divergences.json`](conformance/divergences.json) records 19 places where two sources disagree, what this package follows, and what would settle each. `python3 -m conformance.quotes` finds every quoted sentence in its document.

The suites are pinned by commit. A weekly job runs them at each upstream head and opens a pull request when the newer suite passes or an issue when it fails. [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) lists 16 questions the documents and the suites do not settle, each with the measurement on a real part that would close it.

## Working on it

| Need | Where |
|:--|:--|
| Every gate and the order to run them | [CONTRIBUTING.md](CONTRIBUTING.md) |
| The same material for a coding agent | [AGENTS.md](AGENTS.md) |
| The standard this repository shares with the rest of the family | [FAMILY.md](FAMILY.md) |
| Bug reports | [GitHub Issues](https://github.com/gufranco/mos65xx-python/issues) |
| Security reports | [SECURITY.md](SECURITY.md) |

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
uvx --python 3.12 mypy==1.14.1
python3 mos65xx/mos6502.test.py
```

Each module has a test file beside it, named after it, and each runs on its own as above. Coverage is a hard gate at 100% statement and branch.

## References

Every document below is copyrighted by its publisher and none is in this repository. [`conformance/documents.json`](conformance/documents.json) carries each one's full SHA-256, byte count and address. `python3 -m conformance.documents` downloads all twelve into `docs/`, which git ignores, and refuses any file whose digest does not match. `--check` verifies what is already there.

| Document | Date | Pages | SHA-256 |
|:--|:--|--:|:--|
| [MOS Technology, Inc., *MCS6500 Microcomputer Family Hardware Manual*](https://archive.org/download/mcs-6500-family-hardware-manual-1976-01/MCS6500_family_hardware_manual_1976-01.pdf) | 1976-01 | 182 | `81ea570c9d68deff64d67365bdf24534df93a8c62121e53036aeac6a557cea23` |
| [MOS Technology, Inc., *MCS6500 Microcomputer Family Programming Manual*](https://archive.org/download/6500-50A_MCS6500_Programming_Manual_1976_Jan/6500-50A_MCS6500_Programming_Manual_1976_Jan.pdf) | 1976-01 | 262 | `a2d54dd8b6557c7f2f275b4ddaa9180b5754274a762df122d79392f03264b483` |
| [MOS Technology, Inc., *MOS 6500 Microprocessors*](https://6502.org/documents/datasheets/mos/mos_6500_mpu_nov_1985.pdf) | 1985-11 | 12 | `ccd72376d1e5db1fb13777de538417f4799ab38e1f746452f9695465c422dcd7` |
| [MOS Technology, Inc., *MOS 6500 Microprocessors*](https://6502.org/documents/datasheets/mos/mos_6500_mpu_mar_1980.pdf) | 1980-03 | 12 | `a564c4de593ea178868a43eaf7e00fe7d3460016d2a7880d20eb756f2bf2d030` |
| [Synertek, Inc., *SY6500 Microprocessors*](https://6502.org/documents/datasheets/synertek/synertek_sy6500_microprocessors.pdf) | Undated | 6 | `f20b50961df60bb0e1980f271ad49b4b788c46a143127ccc58e8d3ce84d99193` |
| [Synertek, Inc., *SY6500 Hardware Manual*](https://6502.org/documents/datasheets/synertek/synertek_hardware_manual.pdf) | Undated | 178 | `9cd0991dcbb4a46bf63747528282ad175ed15e1957d08bd755ef14b978b67a1c` |
| [Rockwell International, *R65C00 Microprocessors: R65C02, R65C102 and R65C112*](https://6502.org/documents/datasheets/rockwell/rockwell_r65c00_microprocessors.pdf) | 1987-06 | 16 | `63deee76c8d0d4faee7bb8f9c50ff21662c73f2e82093ebacfb284f527faf134` |
| [The Western Design Center, Inc., *W65C02S 8-bit Microprocessor Data Sheet*](https://westerndesigncenter.com/wdc/documentation/w65c02s.pdf) | 2022-04-08 | 32 | `a6af3ca9da45c8a03504c94c7399cb6b08f15ce14185dd3e1e880433cdaa8cf5` |
| [The Western Design Center, Inc., *W65C816S 8/16-bit Microprocessor Data Sheet*](https://datasheets.chipdb.org/Western%20Design/w65c816s.pdf) | 2004-06-14 | 62 | `60f21a3da0331273c6b92963ba7660408ab1ba3cf9dca2e37b1e55e7950ff313` |
| [The Western Design Center, Inc., *W65C816S 8/16-bit Microprocessor Data Sheet*](https://6502.org/documents/datasheets/wdc/wdc_w65c816s_jul_1994.pdf) | 1994-07 | 72 | `823c2f286a97102fc3695596f7c03e26e2f01cff0f45023dc3bb71688e689bc7` |
| [The Western Design Center, Inc., *W65C816S Datasheet*](https://westerndesigncenter.com/wdc/documentation/w65c816s.pdf) | 2024-03-13 | 55 | `b9177e1b045d2c8a801d1b23619abb4e5b29b88868fa491df7296dbc0b13447e` |
| [The Western Design Center, Inc., David Eyes and Ron Lichty, *Programming the 65816, including the 6502, 65C02 and 65802*](https://github.com/gilligan/snesdev/blob/master/docs/programming_the_65816.pdf) | 2007 | 469 | `dbccafcc47d6e53436bdc1c0049b3c54ffacfc9034a4041a7d92b6e6c5d72bb5` |

Ricoh published no data sheet for the 2A03, so the MOS documents cover the core it is built from. None of the three W65C816S revisions mentions the W65C802, so the 65816 documents cover its core and its package is undocumented.

The suites come from [SingleStepTests](https://github.com/SingleStepTests), pinned by commit in [`conformance/suites.json`](conformance/suites.json). The publisher names no generating implementation for any of them, so they rank below a manufacturer's statement.

## Citing this

[CITATION.cff](CITATION.cff) is updated with each release by the script that stamps the package version.

## License

MIT. See [LICENSE](LICENSE).
