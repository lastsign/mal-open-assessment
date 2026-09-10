# Ambiguities

Every question the brief did not settle, how this ledger answers it, and what
would change if the answer is wrong. Ordered by how much money moves.

---

## A1. Does a day that has already closed reopen when a backdated entry lands?

**The gap.** The fee rule is written in value-date terms — *"that day's closing
ledger balance (all entries with value_date ≤ that day)"* — which is a function
of the entry set, not of when the ledger learned anything. But it also says the
fee is *"assessed once per day per account"*, which is the language of a batch
that runs at a close. E7 arrives on Day 5 value-dated Day 2, so the two
readings diverge and take every number with them.

**Resolution.** Both are implemented, behind `FeePolicy`. The default is
`RETROACTIVE`: when a backdated entry lands, days from that value date forward
are re-evaluated in ascending order and any missing fee is assessed with the
value date of the day it belongs to.

| | fees | Day 6 close | capitalised interest |
|---|---|---|---|
| `retroactive` (default) | Day 2, Day 4, Day 5 | 210.70 AED | 0.70 AED |
| `point-in-time` | Day 5 only | 260.78 AED | 0.78 AED |

**Why this default.** The instruction *"booked with value_date equal to the day
assessed"* is otherwise dead text. If fees could only ever be assessed for the
current day, the fee's value date would always equal its booking date and there
would be nothing to specify. Requiring a value date only makes sense if a fee
can be dated into a day other than the one it is booked on.

**What is uncomfortable about it.** No real bank re-runs a closed fee cycle in
place; it books an adjustment, and the customer's Day 2 statement still shows
+250.00 with no visible reason for the charge. `tests/test_known_gap.py`
carries the deeper problem: under this policy the fee outcome depends on
*arrival order*, not on the log.

**If the intended answer is point-in-time:** run `--policy point-in-time`.
Every criterion refusal in REJECTED.md survives the switch.

---

## A2. Is the overdraft fee itself part of the balance that triggers the next fee?

**The gap.** The fee is booked with a value date, so it is an entry like any
other — but nothing says whether fee entries feed the assessment that produces
more fees.

**Resolution.** Yes. A fee is an ordinary debit and compounds into every later
day's closing balance. Retroactive assessment therefore walks days in ascending
order, because a fee dated Day 2 changes whether Day 3 needs one.

**What turns on it.** Day 3 closes at +5.00 — it would be +30.00 without the
Day 2 fee, and positive either way, so on this data nothing changes. Had E7
been 645.00 instead of 620.00, this choice alone would decide whether Day 3
takes a fee. Excluding fees from the base would also make the fee schedule
non-compounding, which is a kinder policy than most and not one I can assume.

---

## A3. Stream order versus booking day: E10 is listed after E9 but booked earlier

**The gap.** The brief says "replayed in this order" and then lists E10 (booked
Day 5) after E9 (booked Day 6).

**Resolution.** Events are processed in booking-day order, preserving listed
order within a day. E10 is therefore processed on Day 5, before E9.

**Why.** Taking the listing literally means Day 5 closes without E10 in it and
E10 arrives mid-Day-6 — Day 6 knowledge entering a Day 5 close, which is the
one thing a value-dated ledger must never do.

**What turns on it.** Nothing here: E10 is the only ACC-002 event and the
accounts never interact. It would matter immediately if they did, and I would
rather have the rule stated than be right by luck.

---

## A4. Which balances does interest accrue on — final, or as-known-at-close?

**The gap.** Interest capitalises at the end of Day 6, when everything is
known, but it accrues *daily* on each day's closing balance, and those balances
have been restated since.

**Resolution.** Final knowledge. All six daily accruals are computed at the end
of Day 6 from the restated closing balances, including fee entries and the E9
reversal, under both fee policies.

**Why.** Value-date semantics have to be applied consistently or not at all. If
Day 2's *fee* is decided on its restated balance (A1), Day 2's *interest*
cannot be decided on a stale one.

**What turns on it.** The whole interest figure. Accruing on close-time
snapshots under the default policy would give 0.10 + 0.10 + 0.26 + 0.11 + 0 + …
— a different total and a different apportionment.

---

## A5. What exactly is "the capitalized total"?

**The gap.** *"The rounded daily accruals must sum exactly to the capitalized
total"* is satisfiable two ways: define the total as the sum of independently
rounded days (trivially true, silently lossy), or compute the true total and
fit the daily figures to it.

**Resolution.** The capitalised credit is the exact sum of daily accruals,
rounded once: 0.7020 → **0.70 AED**. The published daily figures are then
apportioned to sum to 70 fils by largest remainder.

**Why.** The first reading makes the rule a tautology and quietly loses one
fils per account per period, always in the same direction. Criterion 8 in the
brief proposes exactly that loss, which reads as a deliberate check on whether
the tautology gets noticed.

**Consequence worth stating.** A published daily figure need not equal that day
alone, rounded. Day 4's exact accrual is 0.0940 and it is published as 0.10,
because that is where the apportionment placed the remainder. The daily figures
are a decomposition of the credit, not six independent roundings.

---

## A6. Rounding mode

**The gap.** Not specified anywhere.

**Resolution.** Half away from zero, applied **once**, to the interest total.

**Why not banker's rounding.** Half-even is the better default when many
independent values are rounded and the bias matters — but here only one value
is ever rounded per account per period, so there is no bias to cancel, and
half-up is what a retail fee schedule promises a customer. The apportionment,
not the rounding mode, is what keeps the daily figures honest.

**Where it does not apply.** Fees are exact constants and instalment splits use
integer division with remainder placement. Nothing else rounds.

---

## A7. Tie-breaking in the apportionment

**The gap.** ACC-001's Day 4, Day 5 and Day 6 accruals all have a remainder of
0.0040. One of them gets the spare fils and the brief does not say which.

**Resolution.** Earliest day wins — Day 4. Same rule for instalment splits:
the earliest part takes the remainder.

**Why.** Any rule is defensible; only a *deterministic* one lets a rebuild
reconcile. "Largest, ties to the earliest index" is stable under replay,
trivially explainable to an auditor, and does not depend on dict ordering or
sort stability elsewhere in the program.

---

## A8. Is a zero balance positive, or negative, or neither?

**The gap.** Interest is on *"positive balances only"*; the fee is on a balance
that *"is negative"*. Zero falls between the two.

**Resolution.** Zero is neither. No interest, no fee.

**What turns on it.** ACC-002 sits at exactly 0.000 for Days 1–4. Treating zero
as positive would accrue nothing anyway; treating it as negative would put four
overdraft fees on an account that has done nothing — and see A10 for why those
fees could not even be denominated.

---

## A9. In what currency is the overdraft fee charged on a BHD account?

**The gap.** The fee schedule says "AED 25.00" flat. ACC-002 is a BHD account.
No FX rate, no date convention, no BHD fee is given.

**Resolution.** The ledger **raises `UndefinedFeeCurrency`** rather than guess.
It does not fire on this stream, because ACC-002 never closes negative.

**Why not just pick a rate.** Inventing an AED/BHD rate would silently answer
three questions nobody asked: which rate, as of which date, and who takes the
revaluation. A loud failure on a path the data never exercises is cheaper than
a plausible number in the ledger.

**What a real answer looks like.** A fee schedule per currency, or a fee
account denominated in the account's own currency with the AED figure treated
as the AED-account rate rather than a universal constant.

---

## A10. When is the residual of a partial settlement released?

**The gap.** Auth-A holds 200.00 and settles for 185.00. Nothing says what
becomes of the remaining 15.00.

**Resolution.** Released immediately, on the settlement's value date. The hold
is closed in full; no partial hold survives.

**Why.** A settlement is the closing event for an authorisation. Leaving 15.00
held would suppress the customer's available balance for a transaction that has
completed.

**Where this is too simple.** Real schemes allow multiple partial settlements
against one authorisation — split shipments, in particular — and this model
cannot express that: the second settlement would find Auth-A already `SETTLED`
and be rejected. Flagged in the architecture document as a deliberate cut.

---

## A11. What if a settlement exceeds its authorisation?

**The gap.** Not in the stream, but reachable in the model.

**Resolution.** Booked in full, for the settled amount, with the hold closed.
Not capped at the hold, not rejected.

**Why.** Over-settlement is legitimate and common — restaurant tips, fuel
top-ups, hotel incidentals — and capping the posting to the hold would put the
ledger out of step with the amount actually cleared. Production would apply a
tolerance (a percentage band above the authorisation) above which the record
goes to exception rather than to the account.

---

## A12. Auth-B is never settled. What happens to it at the end of the window?

**The gap.** The brief states the fact and asks nothing.

**Resolution.** Moot here, because Auth-B is *declined* (A13), so no hold ever
exists. Had it been approved, the hold would remain `ACTIVE` past Day 6 and go
on suppressing available balance indefinitely: this model has **no expiry**.

**Why not implement expiry.** It needs a scheme-and-MCC-dependent window (from
about 24 hours for fuel to 30 days for car rental), which is a table of business
data the brief does not supply. Rather than invent one, expiry is named as a
cut and enumerated as an authorisation end-state in the architecture document.

---

## A13. Against which day's balance is an authorisation tested?

**The gap.** The rule says available balance must stay at or above zero, but
not as of which day — the authorisation's value date, or the ledger's total?

**Resolution.** The authorisation's own value date: closing balance at that
value date, minus holds active on or before it.

**Why.** Both events here are value-dated to their booking day, so the choice
is invisible on this data. It becomes real for a backdated authorisation, and
value-date consistency is the rule the rest of the ledger already follows.

**Consequence.** Auth-B is declined — available balance −335.00 falling to
−425.00. This is what makes criterion 5 counterfactual.

---

## A14. Does reversing an entry reverse the fee it caused?

**The gap.** E9 reverses E7. Three fees exist because of E7. Nothing says
whether they follow.

**Resolution.** They stand. The reversal posts one contra entry and nothing
else; no fee is refunded, and no fee is re-assessed against the restored
balance.

**Why.** Fee reversal is a customer-treatment policy, not a ledger mechanic. A
ledger that silently unwound fees on any reversal would also unwind them for a
fraud-driven reversal, where the fee may be exactly what the bank intends to
keep pending investigation.

**What I would build with a policy in hand.** A `FeeAdjustment` event
referencing both the fee and the reversal that triggered it, so the refund is
an explicit, attributable decision rather than a side effect of recomputation.

---

## A15. May the same entry be reversed twice? May a non-existent one be reversed?

**The gap.** Not addressed.

**Resolution.** Both are rejected, with a recorded `REJECTED` decision and no
posting. The check for a double reversal looks for an existing contra entry
against the same original.

**Why.** A reversal is idempotent by intent: a retried instruction must not
credit twice. Reversing an unknown event is an integration bug and should be
visible, not absorbed.

---

## A16. Are the opening balances events?

**The gap.** Both accounts open at zero. The brief lists them as state, not as
events.

**Resolution.** A zero opening balance posts nothing. The code will post an
opening credit if one is non-zero, so the ledger has no privileged
"pre-existing" state that did not arrive as an entry.

---

## A17. "Once per day per account" — which day?

**The gap.** The day it is *assessed* on, or the day it is *dated* into?

**Resolution.** The value date. Uniqueness is enforced by looking for a fee
entry with that account and that value date. Under the retroactive policy Day 5
books three fees at once — for Days 2, 4 and 5 — which is one per day per
account, not three for one day.

---

## A18. Does the capitalised interest credit accrue interest on Day 6?

**The gap.** The credit is value-dated Day 6, and Day 6 is one of the days
interest accrues over.

**Resolution.** No. All six daily accruals are computed from balances taken
before the credit is posted.

**Why.** Otherwise the calculation is self-referential: crediting interest
raises the Day 6 balance, which raises the Day 6 accrual, which raises the
credit. Interest is earned on the balance the customer held, not on the payment
of that interest.

---

## A19. Are the three instalments in E10 three entries or one?

**The gap.** *"BHD 10.000, posted as three equal instalments"* — one credit
described as three parts, or three postings?

**Resolution.** Three separate `CREDIT` entries under event id `E10`, each
noted with its instalment index, all value-dated Day 5.

**Why.** Posting one 10.000 credit would make "three equal instalments"
unobservable in the ledger and would hide the rounding question the criterion
is testing. Three entries make the 3.334 / 3.333 / 3.333 split auditable.

**What is unresolved.** The brief gives no separate value dates for the
instalments, so all three land on Day 5. If instalments were meant to fall on
different days, every ACC-002 balance and both of its accruals change.
