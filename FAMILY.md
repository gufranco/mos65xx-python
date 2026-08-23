# The family standard

Two repositories, held to one standard. They are the reference the rest of the
workspace will be brought up to, so where they differ from each other the
difference has to be something the hardware forces, not something nobody got
round to.

| Repository | What it models |
|:--|:--|
| [mos65xx-python](https://github.com/gufranco/mos65xx-python) | The 65xx family: sixteen parts, from the 6502 to the 65816 |
| [zilog-z80-python](https://github.com/gufranco/zilog-z80-python) | The Z80: three parts, NMOS and CMOS |

## The authority ladder

Every factual question is answered by the highest rung that has an answer, and a
lower rung never overrules a higher one.

1. **Manufacturer documentation.** Read page by page, not searched for keywords.
   Every document is listed in the README's References section with its page
   count and digest, and every fact taken from one is recorded with the sentence
   it came from and the page it was on.
2. **The part itself.** A measurement on real silicon. Neither repository rests
   on one yet, which is exactly what `OPEN-QUESTIONS.md` is for.
3. **A recording from an independent implementation.** A pinned conformance
   corpus. Strong evidence, and still evidence about the program that produced
   it rather than about a chip.
4. **Anything else.** Another emulator, a community write-up, a primer. A source
   with no measurement behind it is not cited at all.

When rungs one and three disagree and rung two is silent, the answer is
**unknown**. It goes in `divergences.json` with the measurement that would close
it, and from there into `OPEN-QUESTIONS.md`. Picking the more convenient source
and moving on is the one thing neither repository does.

## Fidelity over convenience

The purpose is a model of a processor, not an emulator that is pleasant to use.
Where the two pull apart, the processor wins.

- **Nothing starts cleared.** Memory and registers hold a reproducible scrambled
  pattern. There is no parameter that zeroes them and there will not be one: a
  read of a byte nothing wrote is a defect on real silicon, and memory that
  answers zero turns that defect into a passing test.
- **Bugs are features.** A part's defects are modelled, not corrected. A core
  that quietly fixes a hardware bug is wrong for the machine that shipped it.
- **Revisions are separate parts.** Including the ones that only fixed a bug.
- **A discarded read is a real cycle.** Anything a part puts on the bus, the
  model puts on the bus, including the accesses that exist only as side effects.

## What every repository carries

| File | Holds |
|:--|:--|
| `README.md` | The document for a person, including a References section naming every source with its digest |
| `AGENTS.md` | The document for an agent. `CLAUDE.md` points at it so the two cannot drift |
| `OPEN-QUESTIONS.md` | Every place fidelity is still a claim, and the measurement that would close it |
| `conformance/hardware.json` | What the manufacturers printed, fact by fact, with the sentence |
| `conformance/divergences.json` | Where sources part, with a status and a severity |
| `conformance/links.py` | The weekly check that every cited address still answers |

## One interface across the family

A caller moving between the two should not have to relearn anything the hardware
does not force.

```python
cpu = Cpu("z80")  # or Cpu("6502"), Cpu("w65c02"), Cpu("65816")
cpu = Cpu("6502", memory)  # memory is optional; without one the part gets its own
cpu.step()
cpu.reset()
cpu.irq()
cpu.nmi()

decode(data)
disassemble(data)
```

Differences that are allowed, because the parts differ: the Z80 takes a vector on
`irq()` and has a separate `Ports` space; the 65816 has `abort()` and a bank
register. Everything else matches.

## Conventions that are not negotiable

| Thing | Rule |
|:------|:-----|
| Language | Python only |
| Comments | None in source. Docstrings carry the reasoning |
| Test layout | `<module>.test.py` beside the module it covers |
| Test shape | Arrange, blank line, one act, blank line, assert. No section labels |
| Coverage | 100% statements and branches, enforced |
| Types | `mypy` at strict, plus every optional error class |
| Commits | Conventional Commits, subject under 50 characters |
| Corpora | Fetched and pinned by commit, never vendored |
| Documents | Read and pinned by digest, never committed: none is redistributable |
| ROMs and dumps | Never committed, in any form, for any reason |

## What a conformance runner must report

A count of what it checked, not a bare pass. A runner that parsed nothing and
found no failures exits zero and looks identical to one that checked everything,
so the count is what separates coverage from silence.
