# In-memory account ledger core

An append-only, value-dated ledger for two accounts over a six-day window. No
web layer, no persistence, no database, no dependencies beyond `pytest`.

Start with **REJECTED.md** — five of the eight stated acceptance criteria are
wrong, and that document is the substance of the submission. **AMBIGUITIES.md**
records every question the brief left open and what each answer costs.
**NUMBERS.md** covers the constants, and **SOURCES.md** records what the
jurisdiction-specific claims rest on and where the checked material ends.

## Running it

Python 3.12 or newer.

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[test]'

make test      # full suite: 70 pass, 1 xfail (the deliberate one)
make run       # replay the six days and print the report
make run-pit   # the same replay under the alternative fee policy
make gap       # run the failing test unmasked, so it shows red
make complexity  # cognitive complexity gate (complexipy) + McCabe report (radon)
make check       # both
```

`make complexity` needs the dev extra: `pip install -e '.[dev]'`. It gates
cognitive complexity at 15 per function and reports cyclomatic complexity
alongside, because the two metrics disagree in useful ways -- a flat function
with many branches scores badly on McCabe and fine on cognitive, and deep
nesting does the reverse.

Without a virtualenv, `PYTHONPATH=. python3 -m pytest` works too — the package
has no runtime dependencies.

## Reading the report

```
Restated at end of Day 6 (all entries, by value date)
  day           ACC-001           ACC-002
    2        225.00 AED         0.000 BHD
```

The table at the top is the ledger **as it reads now**: for each day, the sum
of every entry with `value_date <= day`, with all six days of knowledge in
hand. This is the balance the fee rule is defined against.

```
Day 2
  closed at         ACC-001  250.00 AED
  restated          ACC-001  225.00 AED  (backdated entries arrived after this close)
  fee               ACC-001  -25.00 AED  (assessed on Day 5, value-dated Day 2)
  authorisation     Auth-A  ACTIVE  (200.00 AED)
  error             none
```

Then one block per day:

- **closed at** — the balance as it stood when that day actually closed. Day 2
  closed at +250.00; nothing then known made it negative.
- **restated** — printed only when the two differ. E7 arrived on Day 5
  value-dated Day 2 and rewrote history. Both numbers are needed to explain a
  fee to anyone: the first is what the customer's statement said, the second is
  why they were charged.
- **fee** — value-dated into the day it is shown under, with the day it was
  actually assessed on in brackets. Under the default policy all three fees are
  assessed on Day 5, dated into Days 2, 4 and 5.
- **authorisation** — the state of every authorisation known as of that day:
  `ACTIVE`, `SETTLED`, `RELEASED` or `DECLINED`.
- **error** — declines, force posts and rejected instructions. E6 settles an
  authorisation that never existed and is force-posted; E8 is declined.

```
Interest
  ACC-001  daily: 0.10  0.09  0.25  0.10  0.08  0.08
  ACC-001  capitalised on Day 6: 0.70 AED
```

The daily figures are a decomposition of the single capitalised credit, not six
independent roundings — they sum to it exactly, by construction. Day 4's exact
accrual is 0.0940 and appears as 0.10 because that is where the remainder was
placed. See AMBIGUITIES A5.

## The failing test

`tests/test_known_gap.py` fails on purpose and carries its explanation inline.
It shows that overdraft assessment in this design depends on the *arrival
order* of events rather than on the log itself: the same entries produce three
fees or none depending on whether a correction is booked before or after
midnight. It is marked `xfail(strict=True)` so the suite stays green while the
failure stays visible — `make gap` runs it unmasked.

## Part 2 — architecture document

`doc/architecture.tex` is the source; `doc/architecture.pdf` is the built
three-page document that is submitted. Rebuild with `make doc` (needs a LaTeX
toolchain).

## Layout

```
ledger/money.py    Money as integer minor units; exact allocation and apportionment
ledger/events.py   The input stream: booking day and value date, kept separate
ledger/core.py     The append-only log and every view derived from it
ledger/replay.py   The six-day replay and the report
tests/             Primitives, the replay, one test per criterion, and the gap
doc/               Architecture & trade-offs document (LaTeX source and PDF)
```

## Design in one paragraph

Money is an `int` in a currency's own minor units, inseparable from its
currency; the scale lives in one registry rather than on each entry, and no
`float` appears anywhere. The log is append-only — balances, hold states and
authorisation outcomes are all derived by scanning it, never stored in a field
that could drift. Corrections are new entries: E9 posts a contra credit, it
does not remove E7. Because a value-dated entry can change a day that has
already closed, the ledger keeps two views of every day and reports both.
