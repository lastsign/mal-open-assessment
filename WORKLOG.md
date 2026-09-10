# Worklog

Kept during the work, not reconstructed afterwards. Times are CEST
(UTC+2). AI assistance (Claude Code) was used throughout for implementation,
for checking my arithmetic against the code, and for drafting prose; the
analysis of which acceptance criteria are wrong, the resolution of every
ambiguity, and the choice of default policy are mine. Where a tool produced
something I did not agree with, that is recorded below.

---

## 2026-09-10

**14:05 — read the brief twice before touching anything.**
Noted immediately that the acceptance criteria contain contradictions with the
non-negotiable rules above them (criterion 8 against the interest rule), which
means at least one is refusable without any computation at all.

**14:10 — replayed the six days on paper.**
Before writing code, by hand, so that the implementation could be checked
against something independent rather than the other way round. Key results:
Day 2 restates to −370.00 raw; E7 drags Days 2, 4 and 5 negative but Day 3
survives at +5.00; interest exact total 0.7020 against 0.69 if each day is
rounded on its own. All three later matched the implementation exactly, which
is the only reason I trust the numbers.

**14:25 — decided the two forks that change every figure.**
(1) Whether a closed day reopens when a backdated entry lands. The brief points
both ways; I chose retroactive as the default because "booked with value_date
equal to the day assessed" is dead text otherwise — but implemented both
behind a flag rather than argue for one in prose. (2) That the capitalised
total is the rounded true sum with the daily figures fitted to it, not the sum
of independently rounded days.

**14:32 — repository initialised.**

**14:35 — core built and committed in four steps:** money primitives, event
types, the append-only core, the replay and report.

First run reproduced every hand-computed figure: fees on Days 2, 4, 5;
capitalised interest 0.70 AED apportioned 0.10 / 0.09 / 0.25 / 0.10 / 0.08 /
0.08; BHD instalments 3.334 / 3.333 / 3.333; Auth-B declined at −335.00
available; E6 force-posted.

**14:36 — changed the report after looking at it.**
The first version printed one balance per day — the restated one — and Day 2
read 225.00 with a 25.00 fee under it and no visible reason. Added the
close-time snapshot alongside, so the report shows both what the day closed at
and what it reads now. This is the change I would defend hardest: the two
numbers together are the entire operational content of a value-dated ledger.

**14:37 — test suite, in three commits.**
Primitives and the replay first; then one test per acceptance criterion, with
the refused ones asserting the criterion *false* rather than encoding it; then
the deliberate failing test.

Choosing what the failing test should reveal took longer than writing it. The
candidates were the arbitrary apportionment tie-break (too small), the
declined-authorisation path not being replay-stable (real but a special case
of the same thing), and the one I chose: overdraft assessment depends on the
order events arrived in, not on the log. Moving E9's booking day from Day 6 to
Day 5 — same entries, same value dates — swings the outcome by 75.00 AED. That
is a genuine flaw in my own design and not a limitation I can dismiss as scope.

**14:40 — REJECTED.md and AMBIGUITIES.md.**
Nineteen ambiguities. Two were found only while writing the document rather
than while coding: the overdraft fee is denominated in AED while ACC-002 is
BHD with no rate given (the code now raises rather than guesses, on a path this
stream never reaches), and the capitalised credit must not itself accrue Day 6
interest, which would otherwise be self-referential.

**14:45 — NUMBERS.md, with the sensitivities measured rather than asserted.**
Ran the replay against halved and doubled constants instead of reasoning about
them. This produced the one finding I had not anticipated: the fee amount is a
threshold, not a slope. At 25.00 Day 3 closes at +5.00 and escapes; at 30.01 it
does not, and a fourth fee appears. Halving the fee changes no outcome at all.
Also found that halving the interest rate flips the *sign* of the rounding gap
— which is a better argument against criterion 8 than the one I had written.

**14:47 — README and Makefile.** Suite green: 70 passed, 1 xfailed.

---

## Still to do

- Architecture & trade-offs document (Part 2).
- Push to GitHub, verify the URL opens in an incognito window.
- Re-read REJECTED.md cold before submitting: every refusal has to be one I can
  argue without notes.
