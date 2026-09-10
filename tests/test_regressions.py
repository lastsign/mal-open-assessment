"""One test per finding from the code review, each reproducing the report.

Named after what the defect was, not after the review, so they still read as
specifications once the review is forgotten.
"""

import pytest

from ledger.core import (
    FeePolicy,
    Ledger,
    NoSuchAccount,
    Posting,
    UndefinedFeeCurrency,
)
from ledger.events import Credit, Debit, Reversal
from ledger.money import AED, BHD, CurrencyMismatch, Money
from ledger.replay import CHART, replay, stream


def _without(*event_ids: str):
    return [e for e in stream() if e.event_id not in event_ids]


# 2 -------------------------------------------------------------------------


def test_a_posting_in_the_wrong_currency_is_refused() -> None:
    # It nets to zero against its own contra and would then break every later
    # balance query on an account whose entries can never be removed.
    book = Ledger(CHART)
    with pytest.raises(CurrencyMismatch):
        book.post_event(Credit("X1", 1, 1, "ACC-002", Money(10_000, AED)))
    assert book.entries == ()


def test_a_posting_to_an_account_outside_the_chart_is_refused() -> None:
    book = Ledger(CHART)
    with pytest.raises(NoSuchAccount):
        book._commit(
            "X2", 1, 1,
            [
                Posting("TYPO-ACC", Money(100, AED), "CREDIT"),
                Posting("CLEARING-AED", Money(-100, AED), "CREDIT"),
            ],
        )
    assert book.entries == ()

# 3 -------------------------------------------------------------------------


def test_reversing_a_settlement_does_not_reopen_the_authorisation() -> None:
    # Deliberate: settling consumes an authorisation, and returning the money
    # does not un-consume it. The point of the test is that the ledger says so
    # rather than leaving it to be discovered.
    book = replay(
        [
            *_without("E7", "E8", "E9", "E10"),
            Reversal("R1", 6, 4, "ACC-001", reverses="E5"),
        ],
        policy=FeePolicy.RETROACTIVE,
    )
    assert book.hold_state("Auth-A") == "SETTLED"
    decision = next(d for d in book.decisions if d.event_id == "R1")
    assert "Auth-A stays SETTLED and is not reopened" in decision.reason

# 4 -------------------------------------------------------------------------


def test_a_close_that_cannot_charge_one_customer_charges_none_of_them() -> None:
    # The fee schedule names AED only. Raising partway through would leave
    # ACC-001 charged for a day that never finished closing.
    book = Ledger(CHART, fee_policy=FeePolicy.RETROACTIVE)
    book.post_event(Debit("D1", 1, 1, "ACC-001", Money(10_000, AED)))
    book.post_event(Debit("D2", 1, 1, "ACC-002", Money(10_000, BHD)))
    with pytest.raises(UndefinedFeeCurrency):
        book.close_day(1)
    assert [e for e in book.entries if e.kind == "FEE"] == []
    assert book.snapshots == {}


def test_a_solvent_foreign_currency_account_does_not_block_the_close() -> None:
    # The guard must fire on an account that would be charged, not on every
    # account the fee schedule happens not to name.
    book = replay(policy=FeePolicy.RETROACTIVE)
    assert len([e for e in book.entries if e.kind == "FEE"]) == 6  # 3 fees, both legs
