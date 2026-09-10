# Numbers

Every constant in the ledger: where it comes from, and what changes if it moves.
Constants the brief fixed are marked **given**; the rest are mine and defended
as choices.

---

<a id="fee"></a>

## Overdraft fee — AED 25.00 (`OVERDRAFT_FEE`, 2500 minor)

**Given** — `OVERDRAFT_FEE` (ledger/core.py:41). Not chosen, but load-bearing,
and closer to a cliff edge than it looks.

The fee is itself a value-dated entry, so a fee on Day 2 lowers every later
closing balance and can trigger the next fee. On this stream Day 3 closes at
+5.00 — 30.00 of raw balance, less the 25.00 fee dated into Day 2. The margin
is exactly 5.00.

| fee | Day 3 outcome | fees assessed |
|-----|---------------|---------------|
| 12.50 (half) | +17.50 | Days 2, 4, 5 |
| 25.00 (given) | +5.00 | Days 2, 4, 5 |
| 30.00 | 0.00 — not negative | Days 2, 4, 5 |
| **30.01** | **−0.01** | **Days 2, 3, 4, 5** |
| 50.00 (double) | −20.00 | Days 2, 3, 4, 5 |

So halving it changes no outcome at all, and raising it by 5.01 adds a fourth
fee. The interesting sensitivity is upward, not downward, and it is a threshold
rather than a slope — which is exactly the shape of behaviour that makes a
compounding fee schedule hazardous. Whether this cascade is intended is a
policy question the brief does not answer (AMBIGUITIES A2); this ledger
implements compounding because a fee is an entry, and entries count.

---

<a id="rate"></a>

## Daily interest rate — 0.04% per day (`DAILY_INTEREST_RATE`, `Fraction(4, 10_000)`)

**Given** — `DAILY_INTEREST_RATE` (ledger/core.py:42). Held as an exact
rational, never as `0.0004`, which is not representable in binary floating
point.

| rate | capitalised (ACC-001) | daily accruals |
|------|----------------------|----------------|
| 0.02% (half) | 0.35 AED | 0.05 0.05 0.12 0.05 0.04 0.04 |
| 0.04% (given) | 0.70 AED | 0.10 0.09 0.25 0.10 0.08 0.08 |
| 0.08% (double) | 1.40 AED | 0.20 0.18 0.50 0.19 0.17 0.16 |

Halving the rate does not halve the reconciliation problem — it sharpens it.
At 0.04% the independently-rounded days sum to 0.69 against a true 0.70, a gap
of one fils. At 0.02% the true total is 0.351 → 0.35, while the days round
independently to 0.36: the gap flips sign. That is the argument against
criterion 8 in one line — the discarded remainder is not even reliably in the
bank's favour, it is just unaccounted for.

The denominator is 10,000 rather than a percentage times a percentage, so the
rate is stated in the same units the regulation would state it in and no
conversion happens in code.

---

## Window — 6 days (`WINDOW`)

**Given.** It matters only because interest capitalises at its end: a longer
window means more daily accruals apportioned into one credit, and more scope
for the rounding gap to grow. Halving it to three days would end the window
before E7 ever arrives, removing every interesting case in the exercise.

---

## Currency scales — AED 2, BHD 3 (`EXPONENT`)

**Given** by ISO 4217, not by preference. They are held in one registry keyed
by currency and never stored on an entry, so two AED entries cannot disagree
about what a minor unit is.

Halving is not meaningful; changing is. AED at 1 decimal would make the fee
25.0 and lose the fils that criterion 8 turns on. BHD at 2 would make 10.00 / 3
= 3.34 / 3.33 / 3.33 — same structure, different remainder. The three-decimal
BHD is in the brief precisely because it does not behave like AED, and a ledger
that assumed two decimals would produce plausible wrong numbers rather than an
error.

---

## Instalments — 3 (`Credit.instalments`)

**Given** for E10. The remainder is 1 minor unit: 10,000 fils ÷ 3 = 3,333 each
with 1 left over. Any divisor that does not divide 10,000 exposes the same
question; 3 is simply the smallest one that does it visibly. Two instalments
would divide exactly and hide the issue entirely, which is presumably why it is
three.

---

<a id="rounding"></a>

## Rounding: half away from zero, applied once (`round_half_up`)

**Chosen.** Half-even is the better default when many values are rounded
independently and the bias needs to cancel. Here exactly one value is rounded
per account per period — the interest total — so there is no accumulation for
half-even to protect against, and half-up is what a published rate promises a
customer.

The choice is deliberately made small. Rounding happens once, at one call site.
Everything else is exact: fees are integer constants, splits are integer
division with the remainder placed, and daily accruals are `Fraction` until the
moment they are apportioned.

---

## Apportionment tie-break: earliest index (`apportion`, `allocate`)

**Chosen.** ACC-001's Day 4, Day 5 and Day 6 accruals have identical remainders
of 0.0040 and one spare fils to place. Day 4 takes it.

The value of the rule is not fairness, it is determinism: a ledger that cannot
reproduce its own published figures from its own log cannot be reconciled.
"Largest remainder, ties to the earliest index" survives replay, does not
depend on dict iteration order or sort stability elsewhere, and is one sentence
to an auditor. Rotating the tie-break across periods would be fairer over time
and would cost that reproducibility unless the rotation state were itself
persisted — which is more machinery than a spare fils justifies.

---

## Default fee policy — `RETROACTIVE` (`FeePolicy`)

**Chosen**, and the single most consequential choice in the repository: it
moves 75.00 AED of fees and 0.08 AED of interest. Both policies are
implemented and tested; the reasoning is in AMBIGUITIES A1 and the flaw it
carries is in `tests/test_known_gap.py`.

---

## Zero is neither positive nor negative

**Chosen** where the brief was silent. Interest requires a strictly positive
closing balance; a fee requires a strictly negative one. ACC-002 rests at
exactly 0.000 for four days and attracts neither.

Choosing otherwise would put four overdraft fees on an account that has done
nothing — and those fees could not even be denominated, since the fee schedule
is written in AED and the account is BHD (AMBIGUITIES A9).

---

<a id="absent"></a>

## Constants deliberately absent

**No authorisation expiry window.** A real one is scheme- and
merchant-category-dependent, from roughly 24 hours to 30 days. Inventing a
number here would be inventing business data. Auth-B is declined so nothing
depends on it in this window; the consequence of the omission is enumerated in
the architecture document.

**No over-settlement tolerance.** Production caps settlements at some band
above the authorisation before routing to exception. The band is a scheme rule,
not something to guess (AMBIGUITIES A11).

**No FX rate.** See AMBIGUITIES A9. A missing rate raises rather than defaults.
