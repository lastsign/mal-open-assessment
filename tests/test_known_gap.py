"""The one failing test. It is meant to fail; read the annotation.

Run it on its own to see it red:

    pytest tests/test_known_gap.py --runxfail
"""

from dataclasses import replace

import pytest

from ledger.core import FeePolicy
from ledger.replay import replay, stream


@pytest.mark.gap
@pytest.mark.xfail(
    strict=True,
    reason="overdraft assessment is path-dependent; see the annotation below",
)
def test_the_same_entries_should_produce_the_same_fees() -> None:
    """FAILS BY DESIGN.

    Both replays below end with an identical set of ledger entries: E7 (debit
    620.00, value-dated Day 2) and E9 (its reversal, also value-dated Day 2).
    The only difference is that in the second replay the correction is booked
    on Day 5 alongside the mistake instead of on Day 6.

    Same entries, same value dates, same closing balances by value date --
    and yet:

        E9 booked Day 6 -> fees on Days 2, 4 and 5, Day 6 closes 210.70 AED
        E9 booked Day 5 -> no fees at all,          Day 6 closes 285.80 AED

    WHAT IT REVEALS. My closing balances are a pure function of the log, but
    my *fees* are not: they are a function of the order in which the log was
    written. Seventy-five dirhams of customer money hangs on an operator
    clearing a correction before midnight rather than after. Three concrete
    consequences:

      1. Rebuilding the ledger from its own entries does not reproduce it.
         Any snapshot, replica or disaster-recovery replay that re-derives
         fees will disagree with production unless it also replays arrival
         order -- which means arrival order is load-bearing state I never
         declared as such.
      2. The fee is not explainable to the customer from their statement.
         Everything on the statement says Day 2 closed at +250.00. Nothing
         visible to them justifies the charge.
      3. It is a live incentive to backdate. Whoever controls booking day
         controls fee revenue, and nothing in the model records who decided
         when an event was booked.

    WHAT I WOULD DO INSTEAD. Stop deriving fees on the fly and make each
    assessment an event in its own right, carrying the as-of watermark it was
    computed against. A fee then becomes reproducible input rather than a
    recomputed output, a superseding assessment is a new event that references
    the one it corrects, and the reversal path gets an explicit policy
    decision -- refund, keep, or refer -- instead of inheriting whatever the
    recomputation happens to do. I did not build that; it is a bigger change
    than the two-hour budget allowed, and I would not want it undocumented.
    See REJECTED.md.
    """
    late = replay(stream(), policy=FeePolicy.RETROACTIVE)
    early = replay(
        [replace(e, booked_day=5) if e.event_id == "E9" else e for e in stream()],
        policy=FeePolicy.RETROACTIVE,
    )

    same_entries = {
        (e.account, e.kind, e.amount.minor, e.value_date)
        for e in late.entries
        if e.kind in ("CREDIT", "DEBIT", "SETTLEMENT", "REVERSAL")
    }
    assert same_entries == {
        (e.account, e.kind, e.amount.minor, e.value_date)
        for e in early.entries
        if e.kind in ("CREDIT", "DEBIT", "SETTLEMENT", "REVERSAL")
    }

    late_fees = [e.value_date for e in late.entries if e.kind == "FEE"]
    early_fees = [e.value_date for e in early.entries if e.kind == "FEE"]
    assert late_fees == early_fees, (
        f"identical entries, different fees: {late_fees} vs {early_fees}"
    )
