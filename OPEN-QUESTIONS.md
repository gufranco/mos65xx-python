# Open questions

What this project does not know for certain, and what it would take to find out.

Everything here is a place where being faithful to the silicon is still a claim
rather than a measurement. The list is short because most of the surface is
settled: 17,900,000 recorded state cases and 17,590,080 recorded bus cycles agree
with this model exactly, and every figure taken from a manufacturer's page is
checked against a run rather than restated. What remains is the residue that
neither a document nor a recording can close.

## Why a recording cannot close these

The recordings this project is held to are themselves a model. They are very
good, they were made independently, and where they and a data sheet disagree the
recordings have usually turned out to be right. But a recording made by a program
is evidence about that program, not about silicon. Where a document and a
recording disagree and no third source exists, the honest position is that the
answer is unknown, and this file is where those live rather than being quietly
resolved in favour of whichever source is more convenient.

## What would settle almost all of them

One logic analyser on one real part, running a program written to provoke each
case. Every question below names the specific measurement, and most are a few
instructions long. Nothing here needs a die shot or a gate-level simulator: it
needs a board, a probe, and someone willing to run a dozen short programs.

The parts are still made. WDC sells the W65C02S and the W65C816S new.

## Where a document and the recordings disagree

A manufacturer printed one thing and every recorded case shows another. These are the ones a measurement would settle outright.

### The data bank register after a software interrupt in emulation mode

**The document says.** In the Emulation mode, the PBR and DBR registers are cleared to 00 when a hardware interrupt, BRK or COP is executed. In this case, previous contents of the PBR are not automatically saved.

Source: W65C816S Data Sheet, 8.11.2.

**The recordings say.** All 10,000 emulation BRK tests, all 10,000 emulation COP tests and all 10,000 native BRK tests leave the data bank register exactly as they found it. 9,960 of the emulation BRK tests start with a non-zero data bank, so the cases that would show a clear are present and none of them shows one. The program bank is zero afterwards in all 30,000, which is the half of the sentence both sources agree on.

**What this project does.** Clears the program bank and leaves the data bank alone, in both modes. The suite is the only evidence with a case count behind it, and the same caveat section is wrong about the native vector addresses and about which bank holds the (a,x) pointer, so its precision is not what its specificity suggests.

**What would settle it.** A program on a real part: set the data bank to something non-zero, drop into emulation mode, execute BRK, and have the handler push the data bank and read it back.

### Which address the NMOS 6502 puts on the bus during a taken branch

**The document says.** T2* PC + 2 + offset (w/o carry), OP CODE, R/W 1, Offset Added to Program Counter; T3** PC + 2 + offset (with carry), OP CODE, R/W 1, Carry Added. *Skip if branch not taken. **Skip if branch not taken; skip if branch operation doesn't cross page boundary.

Source: MCS6500 Microcomputer Family Hardware Manual, Appendix A.5.8.

**The recordings say.** A taken branch that stays inside its page spends its third cycle reading the instruction it is not going to run, at PC+2. A taken branch that leaves its page spends a fourth cycle at PC+2 with the offset added to the low byte only. So the address the manual gives for the third cycle is what the fourth cycle carries, and the address it gives for the fourth cycle never appears on the bus at all.

**What this project does.** Follows the recording: a dead read at PC+2 on any taken branch, and a second at the low-byte-only sum when the page changes. Every one of the 2,440,000 non-halting cases in the suite agrees, including 40,000 branch cases, which the manual's reading would fail.

**What would settle it.** Nothing needs settling about the behaviour. What is unsettled is whether the manual's two rows were transposed in print or describe an earlier part, and only a run on real silicon of that vintage would say.

### Which cycle of a taken branch carries which address

**The document says.** T2 PC + 2 + offset (w/o carry), Offset Added to Program Counter. T3 PC + 2 + offset (with carry), Carry Added.

Source: MCS6500 Hardware Manual, Appendix A, table A.5.8.

**The recordings say.** Every taken branch drives the unmodified program counter on its third cycle. In four hundred cases checked with a non-zero offset that stay inside a page, the third address is PC + 2 exactly, never PC + 2 + offset. On a crossing branch the fourth cycle carries PC + 2 + offset without carry, which is the address the table prints one row higher, and the corrected target is not reached until the opcode fetch of the next instruction.

**What this project does.** Drives the counter on the third cycle and the partially corrected address on the fourth, so both addresses appear one row later than the table prints them and the corrected target never appears inside the branch at all.

**What would settle it.** A program on a real part: place a branch so its target is on the next page, put a memory-mapped register at the partially corrected address, and see on which cycle it is read.

### How many cycles the reserved opcode 5C spends on a CMOS part

**The document says.** All are NOP's (reserved for future use). OpCode 5C, Bytes 3, Cycles 8.

Source: W65C02S Data Sheet, Table 7-1, the Execution of invalid OpCodes row.

**The recordings say.** Ten thousand cases per part, thirty thousand in all, and every one of them is four cycles: the opcode, the two operand bytes, and the second operand byte read again. No case anywhere in the three sets shows eight.

**What this project does.** Takes four, because that is the only shape any source states. The data sheet gives a count and no addresses, so following it would mean inventing four bus cycles nobody has written down, and inventing them is worse than recording that they are unknown. The other forty-three reserved opcodes match the same table exactly, which is why this one is treated as a single open question rather than as a reason to distrust the row.

**What would settle it.** A logic analyser on a real W65C02S executing 5C, which would give both the count and the four addresses the data sheet does not print. Nothing short of that can be implemented, because a count alone is not a bus trace.

## Where a document disagrees with itself

One publisher saying two things. The reading this project follows is argued in each entry, but only silicon closes it.

### The address on the bus during the discarded read of an indexed access

**The document says.** T3 ADL: BAL + index register / ADH: BAH + C. Carry is 0 or 1 as required from previous add operation.

Source: MCS6500 Hardware Manual, Appendix A, tables A.2.5, A.2.7, A.3.4 and A.4.4.

**And the same publisher also says.** T4 ADL: BAL + Y / ADH: BAH. Data (Discarded).

The same cycle of the same kind of access, written without the carry two pages later. The appendix gives the discarded read two different addresses.

**The recordings say.** Every crossing case in the suite puts the base high byte on the bus for that cycle, never the corrected one. If the corrected address were driven there, the read would land on the right byte and the appendix's own footnote, which says the data fetched in T3 is ignored when the page is crossed, would have nothing to ignore.

**What this project does.** Drives the base high byte with the index added only to the low byte, which is the A.3.6 form. That is the reading the suite carries, the reading the footnote in the other four tables requires, and the reading under which a store to a hardware register does not touch a second register one page below the one it names.

**What would settle it.** A program on a real part: point an indexed store at an address one byte below a page boundary so the index crosses it, put a memory-mapped register at the uncorrected address, and see whether the register is read.

### Whether the new program counter of an indexed indirect jump is a program address

**The document says.** 2a. Absolute Indexed Indirect (a,x), cycle 5: VDA 0, VPA 1, PBR,AA+X, New PCL.

Source: W65C816S Data Sheet, Table 6-7, groups 2a and 2b.

**And the same publisher also says.** 3b. Absolute Indirect (a), cycle 4: VDA 1, VPA 0, 0,AA, New PCL.

The same operation, reading a new program counter through a pointer, marked the other way two groups later. The two differ only in which bank holds the pointer: the program bank for the indexed form, bank zero for the plain one.

**The recordings say.** Every recorded case of both opcodes marks those cycles a valid data address and not a valid program address, which is the same way the recordings mark the plain indirect jump.

**What this project does.** Marks them a data address, following the recordings and the table's own treatment of the plain indirect jump. The table's other reading is defensible, since the pointer of the indexed form really does live in the program bank, but nothing else in the table draws that distinction and nothing recorded supports it.

**What would settle it.** A logic analyser on the VPA and VDA pins of a real W65C816S executing JMP (a,x). Those pins exist precisely so a system can tell the two apart, so the answer is directly observable on hardware and on nothing less.

## Where nobody wrote it down

Behaviour no manufacturer documented. The recordings are the only evidence, and a recording is evidence about the program that made it.

### Which address a CMOS 65C02 puts on the bus during its spare cycles, and how long three of its instructions take

**The document says.** Indexed addressing across page boundary: NMOS 6502, extra read of invalid address; W65C02S, extra read of last instruction byte. Read/Modify/Write instruction at effective address: NMOS 6502, one read and two write cycles; W65C02S, two read and one write cycle. Jump indirect, operand = XXFF: NMOS 6502, page address does not increment; W65C02S, page address increments, one additional cycle. Flags after decimal operation: NMOS 6502, invalid N, V and Z flags; W65C02S, valid flags. One additional cycle.

Source: W65C02S Data Sheet, Table 7-1 Microprocessor Operational Enhancements.

**The recordings say.** 7,630,080 cases agree with the caveats table, cycle for cycle. Two printed figures do not survive, and both are counts rather than addresses.

**What this project does.** Follows the caveats table where it speaks, which is everywhere the timing chart disagrees with it, and follows the recordings for the two counts above. Which means: the spare cycle of an indexed access re-reads the last byte of the instruction, a read-modify-write reads twice and writes once, an indirect jump spends its extra cycle on the address the older part's page-wrap bug would have used, decimal arithmetic costs a cycle, $5C takes four cycles rather than eight, and increment and decrement of an indexed absolute address always pay for indexing while the shifts and rotates pay only across a page.

**What would settle it.** For the two counts, a logic analyser on a real part running $5C and running DEC $2000,X with an index that stays inside the page. Nothing else here needs settling: the document's own caveats table and the recordings agree.

### The address of the extra cycle a CMOS 65C02 spends on decimal arithmetic

**The document says.** Add 1 cycle for decimal mode.

Source: W65C02S Data Sheet, Table 6-5 note 6, with 8.5 of the W65C816S data sheet for what an internal cycle's address means.

**The recordings say.** Every recorded decimal ADC and SBC spends its extra cycle reading 00007F, whatever the program counter, the operands or the flags are. Four cases at four different program counters all carry 00007F.

**What this project does.** Spends the extra cycle, and points it at the operand address rather than at the constant the recording carries. A decimal add on a 65c02 or a w65c02 takes three cycles here where the same add takes two on a 6502, which is the part the document settles. The address it drives is the one the part last had on the bus, because the document says an internal cycle's address may be invalid and the recording carries a placeholder rather than a measurement. conformance/cycles.py leaves that one cycle out of the comparison, narrowly and by opcode, and prints how many it left out.

**What would settle it.** A logic analyser on a real W65C02S during a decimal add. Until then the extra cycle is real and its address is not evidence, and a model that reproduced 00007F would be reproducing the recorder rather than the part.

## Where the evidence has not been run here

Not unknown to the world, unverified in this repository.

### Whether a multi-byte pointer read out of the direct page stays inside the page, in emulation mode with the direct register page aligned

**The document says.** When in the Emulation mode, the direct addressing range is 000000 to 0000FF, except for [Direct] and [Direct],Y addressing modes and the PEI instruction which will increment from 0000FE or 0000FF into the Stack area.

Source: W65C816S Data Sheet, 8.2.1 and 8.2.2.

**The recordings say.** Every emulation-mode file for all five pointer modes and for PEI, 41 files and 410,000 tests, filtered to the cases where the direct register is page aligned and the pointer starts at the end of the page, then read straight off the recorded cycle addresses.

**What this project does.** Follows the four measured cases exactly, and takes the document for the two the suite does not cover, which means (d) and (d),y wrap. The document's exception list is right about one of the four cases it covers, so it is not treated as a rule here, only as evidence where there is nothing else.

**What would settle it.** Six short programs on a real part, one per mode, each with the direct register page aligned and a pointer at FF, reading back the byte the part fetched. Until then this project's behaviour for (d) and (d),y is a document reading rather than a measurement, and is marked as such.

## What is not in question

So the boundary is visible rather than implied:

- **What every instruction does to registers, flags and memory.** Held to the
  recorded corpora for all six parts that have one, every opcode including the
  undocumented ones, with no failures.
- **How many cycles each instruction takes, and what is on the bus during each.**
  Held to those corpora cycle for cycle, and separately to Appendix A of the
  hardware manual, Appendix B of the programming manual, and Table 6-7 of the
  W65C816S data sheet.
- **Which parts exist and what separates them.** Read from the manufacturers'
  own family tables and checked against the model.
- **The undefined state at power on.** Not a question but a decision: nothing
  here starts cleared, because no machine does, and there is no parameter that
  changes that.

## What is deliberately not modelled

Absent rather than unknown, and absent on purpose:

- **The pins under load.** `irq()`, `nmi()` and `abort()` perform the documented
  sequence. No published corpus covers a pin asserted part way through an
  instruction, and this core finishes an instruction before it will take one.
- **Bus arbitration and wait states.** A model with no bus master and no slow
  memory has nothing to arbitrate.
