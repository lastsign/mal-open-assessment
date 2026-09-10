"""Double-entry invariants.

These are the properties that make the word "ledger" honest: money always
comes from somewhere, and the whole book cancels to zero in every currency.
"""

from collections import defaultdict

import pytest

from ledger.core import (
    Account,
    AccountKind,
    FeePolicy,
    Ledger,
    NoSuchAccount,
    Posting,
    Unbalanced,
)
from ledger.money import AED, Money
from ledger.replay import CHART, CUSTOMERS, WINDOW, replay, stream
from tests.helpers import customer_legs, postings


@pytest.fixture(scope="module")
def retro():
    return replay(policy=FeePolicy.RETROACTIVE)


@pytest.fixture(scope="module")
def pit():
    return replay(policy=FeePolicy.POINT_IN_TIME)


# ------------------------------------------------------------- invariants


@pytest.mark.parametrize("policy", list(FeePolicy))
def test_every_transaction_sums_to_zero_in_every_currency(policy) -> None:
    book = replay(policy=policy)
    by_transaction: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for transaction, entry in book.postings():
        by_transaction[transaction.id][entry.amount.currency] += entry.amount.minor
    for transaction_id, totals in by_transaction.items():
        for currency, total in totals.items():
            assert total == 0, f"{transaction_id} is out by {total} {currency}"


@pytest.mark.parametrize("policy", list(FeePolicy))
def test_the_book_cancels_on_every_day_not_just_the_last(policy) -> None:
    book = replay(policy=policy)
    for day in range(1, WINDOW + 1):
        for currency, total in book.trial_balance(day).items():
            assert total == 0, f"day {day} is out by {total} {currency}"


def test_customer_balances_are_unchanged_by_the_contra_accounts(retro) -> None:
    # The numbers the assessment cares about must not move because the other
    # side of each posting now exists.
    assert [str(retro.closing_balance("ACC-001", d)) for d in range(1, 7)] == [
        "250.00 AED", "225.00 AED", "625.00 AED",
        "235.00 AED", "210.00 AED", "210.70 AED",
    ]
    assert str(retro.closing_balance("ACC-002", WINDOW)) == "10.008 BHD"


# ------------------------------------------------------ where money lands


def test_the_unmatched_settlement_parks_in_suspense_not_clearing(retro) -> None:
    # An operator has to be able to see the unreconciled position and age it.
    assert str(retro.closing_balance("SUSPENSE-AED", WINDOW)) == "180.00 AED"
    e6 = postings(retro, event_id="E6")
    assert {e.account for _, e in e6} == {"ACC-001", "SUSPENSE-AED"}


def test_fee_income_equals_what_the_customer_was_charged(retro) -> None:
    charged = sum(-e.amount.minor for _, e in customer_legs(retro, kind="FEE"))
    assert str(retro.closing_balance("INCOME-FEES-AED", WINDOW)) == "75.00 AED"
    assert charged == 7500


def test_interest_is_an_expense_to_the_bank(retro) -> None:
    assert str(retro.closing_balance("EXPENSE-INTEREST-AED", WINDOW)) == "-0.70 AED"
    assert str(retro.closing_balance("EXPENSE-INTEREST-BHD", WINDOW)) == "-0.008 BHD"


def test_reversing_an_event_reverses_both_of_its_legs(retro) -> None:
    e7 = {e.account: e.amount.minor for _, e in postings(retro, event_id="E7")}
    e9 = {e.account: e.amount.minor for _, e in postings(retro, event_id="E9")}
    assert e7.keys() == e9.keys()
    assert all(e9[account] == -amount for account, amount in e7.items())


# --------------------------------------------------------- loud failures


def test_an_unbalanced_transaction_is_refused_before_anything_is_appended() -> None:
    # Reaching for a private method deliberately: this invariant is the whole
    # point of the commit path, and there is no public way to violate it.
    book = Ledger(CHART)
    with pytest.raises(Unbalanced):
        book._commit("BAD", "CREDIT", 1, 1, [Posting("ACC-001", Money(100, AED))])
    assert book.entries == ()


def test_a_chart_with_nowhere_to_post_the_other_side_fails_loudly() -> None:
    # Force-posting needs a suspense account. Without one the ledger must
    # refuse rather than quietly post one-sided.
    crippled = {k: v for k, v in CHART.items() if v.kind is not AccountKind.SUSPENSE}
    with pytest.raises(NoSuchAccount):
        replay(stream(), policy=FeePolicy.RETROACTIVE, chart=crippled)


def test_an_ambiguous_chart_is_refused_too() -> None:
    doubled = dict(CHART)
    doubled["CLEARING-AED-2"] = Account("CLEARING-AED-2", AED, AccountKind.CLEARING)
    with pytest.raises(NoSuchAccount):
        replay(stream(), policy=FeePolicy.RETROACTIVE, chart=doubled)


# ------------------------------------------------------------- the layering


def test_an_entry_carries_no_product_vocabulary() -> None:
    """The whole point of the split.

    A posting is an account and a signed amount, and nothing else. When the
    product word lived here, a contra leg carried a negative amount labelled
    CREDIT -- a field describing the event while sitting on the posting, and
    contradicting half the log it annotated.
    """
    from dataclasses import fields

    from ledger.core import Entry

    assert {f.name for f in fields(Entry)} == {
        "seq",
        "transaction",
        "account",
        "amount",
    }


def test_every_entry_belongs_to_a_transaction(retro) -> None:
    known = {t.id for t in retro.transactions}
    assert {e.transaction for e in retro.entries} <= known
    assert len(retro.entries) > len(retro.transactions)  # every one has legs


def test_dates_and_reasons_live_on_the_transaction(retro) -> None:
    # A new product should be a new posting rule and a new chart entry, not a
    # new member of an enum inside the ledger core. That only holds while the
    # core's own records stay free of product-specific fields.
    transaction = next(t for t in retro.transactions if t.kind == "FEE")
    assert (transaction.value_date, transaction.booked_day) == (2, 5)
    assert transaction.note == "overdraft"
