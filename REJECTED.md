# Refused criteria, and approaches abandoned mid-build

## Verdict

**Five of the eight stated criteria are wrong.** Each refusal is backed by a
test in `tests/test_criteria.py` that asserts the criterion false rather than
encoding it.

### Refused — 2, 4, 6, 7, 8

**[Criterion 2](#c2) — "E7 causes exactly one overdraft fee, on Day 2"**

Three fees, value-dated Days 2, 4 and 5. Worth reading first: it is false
under *either* resolution of the backdating question, so refusing it costs no
bet on my own interpretation. Under the other reading there is one fee, but on
Day 5.

**[Criterion 4](#c4) — "An unmatched settlement must be rejected and the funds
must not leave the account"**

It is a force post, and a routine one. The scheme has already paid the
merchant; declining does not keep the money, it only puts the ledger out of
step with the clearing file.

**[Criterion 6](#c6) — "After E9, all balances and fees return to their pre-E7
values"**

The fees stand — a reversal is a new contra entry, not a deletion, and fee
refund is a policy nobody specified. So the balance does not return either:
Day 2 reads 225.00, not 250.00.

**[Criterion 7](#c7) — "The three BHD instalments must each be BHD 3.334"**

That is 10.002. The correct split is 3.334 / 3.333 / 3.333.

**[Criterion 8](#c8) — "The interest rounding remainder is discarded"**

Contradicts the brief's own non-negotiable rule, and the remainder is real on
this data: independently rounded days sum to 0.69 against a true 0.70.

### True, but its premise never occurs — 5

**[Criterion 5](#c5) — "If Auth-B is approved, its hold reduces available
balance but not ledger balance"**

The property is real and implemented. But Auth-B is **declined** — available
balance is −335.00 by the time E8 is processed — so the criterion describes a
branch this stream never reaches. Flagged rather than refused: a conditional
with a false antecedent is not a false statement.

### Correct — 1, 3

Criterion 1 (Day 2 restates to −370.00) and criterion 3 (the Day 4 settlement
of Auth-A is accepted) are right and get no section below. They are tested in
`tests/test_criteria.py` like the rest.

---

## Part 1 — the criteria, one at a time

<a id="c2"></a>

### Criterion 2 — "E7 causes exactly one overdraft fee to be assessed, on Day 2" — REFUSED

False under either reading of the backdating rule, which is what makes this a
safe refusal rather than a bet on my own interpretation.

E7 is a 620.00 debit value-dated into Day 2. It drags every closing balance
from Day 2 onward down by 620.00:

| day | before E7 | after E7 | after the fees that follow |
|-----|-----------|----------|----------------------------|
| 2   | +250.00   | −370.00  | −395.00 → **fee**          |
| 3   | +650.00   | +30.00   | +5.00 (survives)           |
| 4   | +285.00   | −335.00  | −360.00 → **fee**          |
| 5   | +285.00   | −335.00  | −385.00 → **fee**          |

Under the retroactive policy that is **three** fees, not one. Day 3 escapes
only because the Day 2 fee is itself value-dated into Day 2 and so is already
inside Day 3's balance — a detail worth stating, because a fee that did not
compound into later days would leave Day 3 at +30.00 and change nothing else.

Under the point-in-time policy — a closed day stays closed — Day 2 never
reopens, and the fee falls on **Day 5**, the first day that closes negative
with E7 in hand. That is one fee, but not on Day 2.

So the criterion is wrong on the count, or wrong on the day, and there is no
resolution of the ambiguity under which it is right.

<a id="c4"></a>

### Criterion 4 — "Any settlement referencing an authorization ID not present in the ledger must be rejected and the funds must not leave the account" — REFUSED

E6 is a settlement for Auth-Z with no preceding authorisation. That is not a
malformed message; it is a **force post**, and it is routine: an offline or
stand-in authorisation the issuer never saw, a card-present floor-limit
transaction, an authorisation that expired before the acquirer presented, or a
clearing record whose authorisation was lost in a network incident.

By the time the record reaches the ledger the scheme has already guaranteed
the merchant payment. Rejecting it does not keep the money in the account; it
only means the bank's books disagree with the clearing file it has already
settled against, and the difference lands in a suspense account for someone to
find later. "The funds must not leave the account" describes an outcome the
ledger has no power to produce.

**What this ledger does instead** — `_force_post` (ledger/core.py:446) —
books the settlement in full, flags it
`unmatched: force post`, and records a `FORCE_POSTED` decision so it surfaces
in the day's errors and can be routed to exception handling. It is allowed to
drive the balance negative, and any resulting overdraft fee is assessed
normally — the customer's recourse is dispute and chargeback, not a silent
refusal at the ledger boundary.

The one thing I would add before production, and did not build: a force post
should not be accepted unconditionally. It should be matched against a
scheme-supplied clearing reference and an amount tolerance, and one that fails
those checks should go to suspense rather than to the customer's account.

<a id="c6"></a>

### Criterion 6 — "After E9, all balances and fees return to their pre-E7 values" — REFUSED

Two separate errors.

**Fees do not rewind.** The ledger is append-only. E9 is a new contra credit
of +620.00 value-dated Day 2; it does not remove E7, and nothing in it removes
the three fee entries either.

Whether a fee is refunded when the entry that caused it is reversed is a
*policy* decision — many banks refund on a fee-reversal request, some refund
automatically, some do not refund at all — and no such policy was stated. I
refuse to invent one silently, so the fees stand and the question is raised in
AMBIGUITIES.md.

**Balances therefore do not return either.** Because the fees stand, Day 2
closes at **225.00**, not the pre-E7 250.00, and Day 6 at 210.70 rather than
the 285.80 the account would have reached had E7 never been booked.

Even if fees were refunded, "return to their pre-E7 values" would still be the
wrong description of what an append-only ledger does. The balance may again
*equal* its earlier value; the ledger does not return to an earlier state. Four
entries now stand where one did, and the audit trail is the point.

<a id="c7"></a>

### Criterion 7 — "The three BHD instalments in E10 must each be BHD 3.334" — REFUSED

3.334 × 3 = 10.002. BHD 10.000 does not divide into three equal parts at three
decimal places, and crediting 3.334 three times would put 0.002 BHD into the
account that the event never carried — money created by a rounding rule.

Correct split: **3.334 / 3.333 / 3.333**, summing to exactly 10.000, by
`allocate` (ledger/money.py:104). The
remainder is placed on the first instalment by a fixed rule, so the same input
always produces the same instalments and a replay reconciles.

<a id="c8"></a>

### Criterion 8 — "If the rounded daily interest accruals do not sum to the capitalized total, the remainder is discarded" — REFUSED

This contradicts the non-negotiable rule stated in the same brief: *the rounded
daily accruals must sum exactly to the capitalized total*. Both cannot hold.

It is not a theoretical conflict on this data. ACC-001's exact daily accruals
are 0.1000, 0.0900, 0.2500, 0.0940, 0.0840, 0.0840 — a true total of 0.7020,
which capitalises to **0.70**. Round each day independently and you get
0.10 + 0.09 + 0.25 + 0.09 + 0.08 + 0.08 = **0.69**. One fils is unaccounted for.

Discarding it is wrong for a reason beyond the contradiction: the error is not
random. Half-up rounding of positive accruals biases in one direction, so a
discard policy leaks value the same way every day, on every account, forever —
and the ledger stops balancing against the interest expense it books. This
ledger apportions instead — `apportion` (ledger/money.py:133): the capitalised
credit is the rounded true total,
and the published daily figures are fitted to it by largest remainder.

<a id="c5"></a>

### Criterion 5 — "If Auth-B is approved, its hold reduces available balance but not ledger balance" — ACCEPTED, WITH ITS PREMISE DENIED

The statement is true and the ledger implements it: a hold is a memo item
against available balance and posts nothing.

But **Auth-B is never approved.** By the time E8 is processed on Day 5, E7 has
already landed and ACC-001's available balance is −335.00. Applying a 90.00
hold would take it to −425.00, and the stated rule approves only if available
balance remains at or above zero. Auth-B is declined; the criterion describes a
branch this stream never reaches.

I am flagging rather than refusing it, because a conditional whose antecedent
is false is not a false statement. It is listed here so that the distinction is
on the record: if the grader intended Auth-B to be approved, then either the
ordering of E7 and E8 or the approval rule is different from what I read.

---

## Approaches abandoned mid-build

**A running-balance field on the account.** The obvious optimisation, written
first and deleted within minutes. A cached balance is a balance *as of a
processing moment*, and this ledger's whole difficulty is that a value-dated
entry changes days that are already closed. Every balance here is derived by
scanning entries with `value_date <= day`. That is O(entries) per query and
plainly wrong at scale — addressed in the architecture document, not papered
over here.

**Rejecting the unmatched settlement.** Implemented as written in criterion 4
before working through what rejection would actually mean for the clearing
position. Replaced with force-posting; the reasoning is above.

**Rounding each daily accrual independently.** The first interest
implementation rounded per day and summed. It produced 0.69 against a true
total of 0.70 and quietly failed the brief's own reconciliation rule. Replaced
with largest-remainder apportionment against the rounded true total.

**Processing events in the order the brief lists them.** The stream lists E10
(booked Day 5) after E9 (booked Day 6). Following the listing literally means
Day 5 closes without E10 in it and E10 arrives during Day 6 — Day 6 knowledge
retroactively entering a Day 5 close. Replaced with booking-day ordering,
preserving listed order within a day. This changes nothing on this data, since
E10 is on the other account; it would matter the moment the two interacted.

**Mutable hold objects with a `state` field.** A `Hold` with a state I could
reassign was simpler to write and quietly violated the append-only rule for the
one part of the model where state genuinely transitions. Replaced with an
append-only log of `HoldEvent` transitions, with the current state derived as
the last transition on or before a given day.

**Single-entry postings.** The first working ledger posted one signed entry
per event: a credit to a customer account came from nowhere and a fee debited
the customer without crediting anything. Every customer-facing number in this
repository was already correct at that point, which is exactly what made it
worth changing — the balances were right and the book could not be *proved*
right.

There was no trial balance, no way to see where the force-posted 180.00 had
gone, and §2 of the architecture document was discussing reconciliation
against a general ledger that this design had no structure to reconcile with.
Replaced with validated two-sided postings and a minimal chart. The customer
balances did not move; the difference is that now they cannot silently drift.

**The operation type on the posting.** `Entry` carried a `kind` field --
`CREDIT`, `FEE`, `SETTLEMENT` and so on -- and it was wrong in a way visible
from the code rather than only in principle: the contra leg of a credit was a
*negative* amount labelled `CREDIT`, and the contra leg of a debit a positive
one labelled `DEBIT`. The field described the event while sitting on the
posting, so it contradicted half the entries it annotated.

Moved to a `Transaction` record, which is where facts true of every leg belong
-- value date, booking date, operation type, the event that caused it. An entry
is now an account and a signed amount and nothing else. The test that matters:
a loan or a term deposit should be a new chart entry and a new posting rule,
never a new member of an enum inside the ledger core, and that only stays true
while the core's own records are free of product vocabulary.

The change cost about an hour because the commit path had been built for it --
postings were already grouped and validated as a set, so the transaction needed
an identity rather than a migration.

**Appending postings one at a time.** The natural way to write the double-
entry change was to keep the existing `_post` and call it twice. Rejected: an
event that raises between its two legs would leave a one-sided entry in an
append-only log, where nothing can remove it.

The commit path buffers the postings, validates that they sum to zero in every
currency, and only then appends — so an unbalanced transaction leaves no trace
rather than half of one. It also happens to be the seam a `Transaction` record
needs later, which made the more careful version the cheaper one.

**`Decimal` for money.** Dropped in favour of `int` minor units plus `Fraction`
for intermediate interest. `Decimal` carries a context — precision and rounding
mode set outside the ledger, at import time, by whoever got there first — and
that is exactly the kind of ambient global I do not want deciding what a
customer is charged.

**A single restated balance per day in the report.** The first report printed
each day's balance as it reads now. That hides the entire point of the
exercise: Day 2 closed at +250.00 and now reads 225.00, and an operator needs
both numbers to explain the fee. The report prints the close-time snapshot and
the restated figure whenever they differ.
