"""One test per finding from the code review, each reproducing the report.

Named after what the defect was, not after the review, so they still read as
specifications once the review is forgotten.
"""

import pytest

from ledger.core import (
    AccountKind,
    FeePolicy,
    Ledger,
    NoSuchAccount,
    Posting,
    UndefinedFeeCurrency,
)
from ledger.events import Credit, Debit, Reversal, Settlement
from ledger.money import AED, BHD, CurrencyMismatch, Money
from ledger.replay import CHART, WINDOW, render, replay, stream
from tests.helpers import customer_legs


def _without(*event_ids: str):
    return [e for e in stream() if e.event_id not in event_ids]


# 1 -------------------------------------------------------------------------


def test_a_chart_currency_with_no_postings_reports_zero_not_a_crash() -> None:
    # E10 is the only BHD event; without it the BHD block has no entries at
    # all, and the trial balance carries no BHD key to look up.
    book = replay(_without("E10"), policy=FeePolicy.RETROACTIVE)
    report = render(book, FeePolicy.RETROACTIVE)
    assert "  BHD" in report
    assert "0.000" in report.split("  BHD")[1]


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
            "X2", "CREDIT", 1, 1,
            [
                Posting("TYPO-ACC", Money(100, AED)),
                Posting("CLEARING-AED", Money(-100, AED)),
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
    # The two debits stand; no fee was committed and no day was closed.
    assert [t for t in book.transactions if t.kind == "FEE"] == []
    assert book.snapshots == {}


def test_a_solvent_foreign_currency_account_does_not_block_the_close() -> None:
    # The guard must fire on an account that would be charged, not on every
    # account the fee schedule happens not to name.
    book = replay(policy=FeePolicy.RETROACTIVE)
    assert len(customer_legs(book, kind="FEE")) == 3


# 5 -------------------------------------------------------------------------


def test_an_unmatched_settlement_in_the_other_currency_force_posts() -> None:
    # Suspense existed in AED only, so the force-post path -- the one the
    # assessment actually exercises -- died on a BHD settlement.
    book = replay(
        [*stream(), Settlement("S1", 5, 5, "ACC-002", "Auth-X", Money(5_000, BHD))],
        policy=FeePolicy.RETROACTIVE,
    )
    assert str(book.closing_balance("SUSPENSE-BHD", WINDOW)) == "5.000 BHD"
    decision = next(d for d in book.decisions if d.event_id == "S1")
    assert decision.outcome == "FORCE_POSTED"


# 6 -------------------------------------------------------------------------


def test_the_report_follows_the_books_chart_not_a_module_constant() -> None:
    single = {k: v for k, v in CHART.items() if k != "ACC-002"}
    book = replay(_without("E10"), policy=FeePolicy.RETROACTIVE, chart=single)
    report = render(book, FeePolicy.RETROACTIVE)
    assert "ACC-001" in report
    assert "ACC-002" not in report


# 7 -------------------------------------------------------------------------


def test_an_accrual_rounded_away_is_not_reported_as_an_absent_balance() -> None:
    # 1.00 AED for six days accrues 0.0024, which rounds to nothing. Saying
    # "no positive closing balance" would be a false statement about the
    # customer's account.
    book = replay(
        [Credit("C1", 1, 1, "ACC-001", Money(100, AED))],
        policy=FeePolicy.RETROACTIVE,
    )
    report = render(book, FeePolicy.RETROACTIVE)
    assert "ACC-001  accrued less than one minor unit over the window" in report
    assert "ACC-002  no positive closing balance in the window" in report
