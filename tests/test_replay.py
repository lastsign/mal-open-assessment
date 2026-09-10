"""The six-day replay, number by number, under both fee policies."""

import pytest

from ledger.core import FeePolicy
from ledger.money import AED, BHD, Money
from ledger.replay import CUSTOMERS, replay


@pytest.fixture(scope="module")
def retro():
    return replay(policy=FeePolicy.RETROACTIVE)


@pytest.fixture(scope="module")
def pit():
    return replay(policy=FeePolicy.POINT_IN_TIME)


def _fees(book) -> list[tuple[int, int]]:
    """(value_date, booked_day) of every overdraft fee, customer side only.

    Each fee is two postings now; the customer leg is the one being counted.
    """
    return [
        (e.value_date, e.booked_day)
        for e in book.entries
        if e.kind == "FEE" and e.account in CUSTOMERS
    ]


def _closings(book, account) -> list[str]:
    return [str(book.closing_balance(account, day)) for day in range(1, 7)]


# ---------------------------------------------------------------- balances


def test_day2_restated_before_any_fee_is_minus_370(retro) -> None:
    # 1,200.00 - 950.00 - 620.00. E3 is a hold and moves no ledger money.
    fee_entries = {e.seq for e in retro.entries if e.kind == "FEE"}
    total = Money.zero(AED)
    for entry in retro.entries:
        if entry.account == "ACC-001" and entry.value_date <= 2 and entry.seq not in fee_entries:
            if entry.kind == "REVERSAL":
                continue
            total = total + entry.amount
    assert str(total) == "-370.00 AED"


def test_retroactive_closing_balances(retro) -> None:
    assert _closings(retro, "ACC-001") == [
        "250.00 AED", "225.00 AED", "625.00 AED",
        "235.00 AED", "210.00 AED", "210.70 AED",
    ]
    assert _closings(retro, "ACC-002") == [
        "0.000 BHD", "0.000 BHD", "0.000 BHD",
        "0.000 BHD", "10.000 BHD", "10.008 BHD",
    ]


def test_point_in_time_closing_balances(pit) -> None:
    assert _closings(pit, "ACC-001") == [
        "250.00 AED", "250.00 AED", "650.00 AED",
        "285.00 AED", "260.00 AED", "260.78 AED",
    ]


def test_days_closed_on_their_own_knowledge(retro) -> None:
    # Day 2 genuinely closed at +250.00; only the arrival of E7 on Day 5 made
    # it negative in hindsight. The report must not conflate the two views.
    assert str(retro.snapshots[2]["ACC-001"]) == "250.00 AED"
    assert str(retro.closing_balance("ACC-001", 2)) == "225.00 AED"


# -------------------------------------------------------------------- fees


def test_retroactive_policy_assesses_three_fees(retro) -> None:
    # E7 drags Days 2, 4 and 5 below zero. Day 3 survives at +5.00 because
    # the Day 2 fee is itself value-dated into Day 2.
    assert _fees(retro) == [(2, 5), (4, 5), (5, 5)]


def test_point_in_time_policy_assesses_one_fee_on_day_five(pit) -> None:
    assert _fees(pit) == [(5, 5)]


def test_a_fee_is_never_assessed_twice_for_the_same_day(retro) -> None:
    dates = [value_date for value_date, _ in _fees(retro)]
    assert len(dates) == len(set(dates))


def test_the_fee_itself_feeds_the_next_days_balance(retro) -> None:
    # Day 3 would close at +30.00 on the raw entries; the Day 2 fee brings it
    # to +5.00, which is still positive and so escapes a fee of its own.
    assert str(retro.closing_balance("ACC-001", 3)) == "625.00 AED"
    assert any(e.kind == "FEE" and e.value_date == 2 for e in retro.entries)


# ----------------------------------------------------------------- interest


def test_daily_accruals_sum_exactly_to_the_capitalised_credit(retro) -> None:
    accruals = retro.daily_accruals("ACC-001")
    credit = next(
        e for e in retro.entries
        if e.kind == "INTEREST" and e.account == "ACC-001"
    )
    assert sum(accruals) == credit.amount.minor
    assert str(credit.amount) == "0.70 AED"
    assert accruals == [10, 9, 25, 10, 8, 8]


def test_bhd_interest_needs_no_apportionment(retro) -> None:
    credit = next(
        e for e in retro.entries
        if e.kind == "INTEREST" and e.account == "ACC-002"
    )
    assert str(credit.amount) == "0.008 BHD"
    assert retro.daily_accruals("ACC-002") == [0, 0, 0, 0, 4, 4]


def test_interest_ignores_days_that_closed_at_or_below_zero(retro) -> None:
    # ACC-002 sits at 0.000 for four days. Zero is not a positive balance.
    assert retro.daily_accruals("ACC-002")[:4] == [0, 0, 0, 0]


def test_interest_is_credited_once_on_day_six(retro) -> None:
    credits = [
        e for e in retro.entries
        if e.kind == "INTEREST" and e.account in CUSTOMERS
    ]
    assert len(credits) == 2  # one per customer account
    assert {e.value_date for e in credits} == {6}


# ----------------------------------------------------------- append-only


def test_sequence_numbers_are_dense_and_ordered(retro) -> None:
    seqs = [e.seq for e in retro.entries]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))


def test_the_reversal_adds_a_record_rather_than_removing_one(retro) -> None:
    e7 = [e for e in retro.entries if e.event_id == "E7" and e.account == "ACC-001"]
    e9 = [e for e in retro.entries if e.event_id == "E9" and e.account == "ACC-001"]
    assert len(e7) == 1 and len(e9) == 1
    assert e7[0].amount == -e9[0].amount
    assert e9[0].value_date == e7[0].value_date == 2
    assert e9[0].booked_day == 6
