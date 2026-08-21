## What this changes

One or two sentences. What is different afterwards, and why it needed to be.

## How it was checked

Paste the output rather than describing it. A claim that the tests pass is not
evidence that they did.

```text
```

- [ ] `ruff format --check .` and `ruff check .` are clean
- [ ] `mypy` reports nothing
- [ ] Every test file runs, and coverage is 100% of statements and branches
- [ ] `conformance/hardware.test.py` still holds every figure to its document

## If this changes what a processor does

Six suites, and every one of them:

```bash
python3 conformance/fetch.py ~/.cache/suite
for name in 65816 6502 nes6502 synertek65c02 rockwell65c02 wdc65c02; do
  python3 conformance/singlestep.py ~/.cache/suite/"${name}"/*/v1
done
```

They do not all come from the same repository, and running one is not running the
others. That is the mistake the watcher made for as long as it existed.

## If this changes a pin

Say which repository moved and paste the run for every suite that repository
carries. A pin that moves while one of its suites was never re-run is a pin
nobody checked.

## What it does not carry

- [ ] No firmware, no ROM, and no fragment of either
- [ ] Nothing that says where to obtain them
