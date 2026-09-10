# Worklog

Kept during the work, not reconstructed afterwards. Times are CEST
(UTC+2). AI assistance (Claude Code) was used throughout for implementation,
for checking my arithmetic against the code, and for drafting prose; the
analysis of which acceptance criteria are wrong, the resolution of every
ambiguity, and the choice of default policy are mine. Where a tool produced
something I did not agree with, that is recorded below.

---

## 2026-09-10

### 14:05 — read the brief twice before touching anything.
Noted immediately that the acceptance criteria contain contradictions with the
non-negotiable rules above them (criterion 8 against the interest rule), which
means at least one is refusable without any computation at all.

### 14:10 — replayed the six days on paper.
Before writing code, by hand, so that the implementation could be checked
against something independent rather than the other way round. Key results:
Day 2 restates to −370.00 raw; E7 drags Days 2, 4 and 5 negative but Day 3
survives at +5.00; interest exact total 0.7020 against 0.69 if each day is
rounded on its own. All three later matched the implementation exactly, which
is the only reason I trust the numbers.

### 14:25 — decided the two forks that change every figure.
(1) Whether a closed day reopens when a backdated entry lands. The brief points
both ways; I chose retroactive as the default because "booked with value_date
equal to the day assessed" is dead text otherwise — but implemented both
behind a flag rather than argue for one in prose. (2) That the capitalised
total is the rounded true sum with the daily figures fitted to it, not the sum
of independently rounded days.

### 14:32 — repository initialised.

### 14:35 — core built and committed in four steps

Money primitives, event types, the append-only core, the replay and report.

First run reproduced every hand-computed figure: fees on Days 2, 4, 5;
capitalised interest 0.70 AED apportioned 0.10 / 0.09 / 0.25 / 0.10 / 0.08 /
0.08; BHD instalments 3.334 / 3.333 / 3.333; Auth-B declined at −335.00
available; E6 force-posted.

### 14:36 — changed the report after looking at it.
The first version printed one balance per day — the restated one — and Day 2
read 225.00 with a 25.00 fee under it and no visible reason. Added the
close-time snapshot alongside, so the report shows both what the day closed at
and what it reads now. This is the change I would defend hardest: the two
numbers together are the entire operational content of a value-dated ledger.

### 14:37 — test suite, in three commits.
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

### 14:40 — REJECTED.md and AMBIGUITIES.md.
Nineteen ambiguities. Two were found only while writing the document rather
than while coding: the overdraft fee is denominated in AED while ACC-002 is
BHD with no rate given (the code now raises rather than guesses, on a path this
stream never reaches), and the capitalised credit must not itself accrue Day 6
interest, which would otherwise be self-referential.

### 14:45 — NUMBERS.md, with the sensitivities measured rather than asserted.
Ran the replay against halved and doubled constants instead of reasoning about
them. This produced the one finding I had not anticipated: the fee amount is a
threshold, not a slope. At 25.00 Day 3 closes at +5.00 and escapes; at 30.01 it
does not, and a fourth fee appears. Halving the fee changes no outcome at all.
Also found that halving the interest rate flips the *sign* of the rounding gap
— which is a better argument against criterion 8 than the one I had written.

**14:47 — README and Makefile.** Suite green: 70 passed, 1 xfailed.

### 14:48 — architecture document (Part 2), written in LaTeX.
Source in `doc/architecture.tex`, built to three pages. LaTeX rather than a
word processor so the source is diffable in the same history as the code.

### 15:22 — jurisdiction pass, and the one thing I nearly shipped wrong.
Went back over the money rules against the market the brief actually names.
Two outcomes.

First, a correction. AMBIGUITIES A9 originally argued that the overdraft fee
could not be charged on the BHD account because "no FX rate is given". That is
the weak version and it would not have survived questioning: both the dirham
and the Bahraini dinar are pegged to the US dollar, so a cross rate is
administratively determined and I could compute one. Rewrote it around the
argument that actually holds — a published fee is a product decision, not an
FX problem, and converting it produces a price nobody disclosed to the
customer. Same conclusion, defensible reasoning instead of a convenient one.

Second, a genuine finding. The brief places the ledger in a UAE-licensed bank,
and that is not one regulatory perimeter: onshore under the Higher Shari'ah
Authority, and inside ADGM under the FSRA's own rulebook, answer differently.
Two of the brief's own non-negotiable rules do not survive an Islamic licence
— a rate known in advance cannot be a mudarabah profit share, and a flat fee
charged daily while a balance is negative is proportional to the duration of a
debt regardless of being flat. Added as AMBIGUITIES A20 and a subsection of
§2, and implemented nothing: the rules were given as non-negotiable and
nothing in the brief invokes Islamic finance, so refusing them would be
inventing a requirement. Added A21 on the calendar for the same reason.

Deliberately kept short. A long unrequested Shari'ah appendix in an exercise
that never mentions it reads as scope invention; half a page reads as knowing
the market. Also created SOURCES.md, which separates what I actually consulted
from what I asserted from memory — the peg rates and the working-week change
are in the second list and are quoted nowhere that matters.

### 16:00 — complexity gate, and it earned its place immediately.
Added complexipy (cognitive) and radon (McCabe) behind `make complexity`, kept
out of `make test` so the suite stays dependency-free. It failed on the first
run: `render()` scored 48 cognitive against a threshold of 15, and 26
cyclomatic — grade D. Everything else was clean, average A.

Committed the gate red, deliberately, then fixed it in the next commit, so the
history shows the tool finding the problem rather than me claiming it did.
Split `render()` into six per-section helpers; cognitive went 48 to 2. Verified
the report output is byte-identical under both policies by diffing before and
after, and added `tests/test_report.py` so the split stays safe to repeat.

### 16:11 — double-entry, and a bug it turned up on the way.
The gap I had been circling: the ledger was single-entry. A credit came from
nowhere, a fee debited the customer and credited nothing, and §2 of the
architecture document was discussing reconciliation against a general ledger
that the design had no structure to reconcile with. Every customer-facing
number was already right — which is what made it worth fixing, because right
and *provably* right are different claims.

Built the commit path as buffer, validate, append rather than posting each leg
as it is produced. Two reasons, and the second is the one I would give first:
an event that raises between its legs must not leave a one-sided entry in a
log that cannot delete; and grouping plus validating the set is most of what a
`Transaction` record needs, so the later change becomes an addition rather
than a migration. Deciding that now cost nothing; deciding it later would have
cost every handler.

The force post's other side goes to suspense rather than clearing. Both
defensible — the scheme has been paid — but suspense makes the unreconciled
180.00 a balance someone can see and age, which is what REJECTED.md already
said should happen. The chart now implements the argument instead of asserting
it.

Bug found while doing this, predating it: Day 6 was reported as "restated by
backdated entries". Nothing was backdated — interest capitalises after
`close_day(6)`, so the snapshot was taken before the credit existed and the
report misdescribed how the money got there. Fixed in its own commit, before
the double-entry work, so the history shows it as the separate thing it is.

Eight existing tests failed on the first run, all of them implicitly
single-entry: they counted entries and now saw both legs. Updated to filter to
the customer leg, and added `tests/test_double_entry.py` — every transaction
sums to zero per currency, the whole book cancels on every day under both
policies, an unbalanced commit is refused before anything is appended, and a
chart with nowhere to post the other side fails loudly rather than posting
one-sided.

### 16:37 — code review, and it was worth running.
Eight findings, every one reproduced against the code rather than asserted,
and I disagreed with none of them. Two mattered.

`_commit` — the path whose entire justification is catching bad transactions —
validated the arithmetic and not the accounts. An AED posting into the BHD
customer account balances against its own contra, commits, and then breaks
every later balance query on that account permanently, because the log cannot
delete. I had written the zero-sum check and stopped there, satisfied, without
asking what else a posting can be wrong about.

The other one is worse because I had already written it down myself: the
architecture document names "a close that dies halfway leaves fees
half-assessed" as a deferred risk, and `close_day` did exactly that — raising
`UndefinedFeeCurrency` partway through a loop that had already committed
another customer's fee. I described the failure mode in prose and then shipped
it in code, in the same repository, the same afternoon. Fixed by deciding the
whole close before committing any of it.

The rest: the report still read a module-level customer list after I had added
a chart parameter; a chart currency with no postings crashed the trial balance
on a missing dict key; the chart had a suspense account in AED but not BHD, so
the force-post path — the one the assessment exercises — died on the other
supported currency; and the interest block reported "no positive closing
balance" for an account that held one and simply earned less than a fils,
which is a false statement about a customer's money.

Wrote one test per finding first and checked they failed against the unfixed
code: eight of nine did, the ninth being a guard that the fix does not
over-fire. Split the fixes across two commits, core and report.

The thing I want to remember from this: every finding was in a path the tests
did not cover, and I had been reading the coverage as though green meant
checked. It meant the six days in the brief work.

### 17:08 — split the posting from the transaction.
The question that started it: does a ledger store anything other than debits
and credits? It does not, and mine was storing more. `Entry` carried a `kind`
field, which meant the contra leg of a credit was a negative amount labelled
`CREDIT`. The label described the event; it lived on the posting; it
contradicted half the log.

Built the `Transaction` layer. An entry is now an account, a signed amount and
a reference; everything true of all the legs -- dates, operation type, the
originating event -- moved up. It took about an hour, and the reason it took
an hour rather than a rewrite is the decision made earlier today to buffer,
validate and append postings as a set: the transaction already existed in all
but name.

The real argument for doing it is not tidiness. A ledger core that grows a new
enum member for every product is not a core. A loan, a term deposit, a standing
order should each be a new chart entry and a new posting rule; the ledger does
not know what a loan is, only that some event resolved into postings that
balanced. That property is now testable, and tested: `Entry` has exactly four
fields and none of them is a product word.

Report output is byte-identical under both policies -- verified by diff, which
is the only reason I trust a change that touched every handler. Twenty-five
tests failed on the first run, all of them reading `entry.kind` or a date that
had moved; they now join the entry to its transaction, which is the shape a
reporting query would take anyway.

---

## Still to do

- Push to GitHub, verify the URL opens in an incognito window.
- Re-read REJECTED.md cold before submitting: every refusal has to be one I can
  argue without notes.
- Read AAOIFI Standards 3, 8 and 19 directly rather than through summaries
  before defending the §2 argument out loud.
