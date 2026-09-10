"""One test per stated acceptance criterion.

Criteria the implementation accepts are asserted directly. Criteria it
refuses are asserted *false* -- the test proves the criterion wrong rather
than encoding it. The reasoning lives in REJECTED.md; this file is the
executable half of that argument.
"""

import pytest

from ledger.core import FeePolicy
from ledger.money import AED, Money
from ledger.replay import replay, stream


@pytest.fixture(scope="module")
def book():
    return replay(policy=FeePolicy.RETROACTIVE)


@pytest.fixture(scope="module")
def pit():
    return replay(policy=FeePolicy.POINT_IN_TIME)


# --------------------------------------------------------------- ACCEPTED


def test_c1_day2_restated_at_end_of_day5_is_minus_370(book) -> None:
    """ACCEPTED. 1,200.00 - 950.00 - 620.00 = -370.00."""
    raw = Money.zero(AED)
    for entry in book.entries:
        if (
            entry.account == "ACC-001"
            and entry.value_date <= 2
            and entry.kind in ("CREDIT", "DEBIT")
        ):
            raw = raw + entry.amount
    assert str(raw) == "-370.00 AED"


def test_c3_the_day4_settlement_of_auth_a_is_accepted(book) -> None:
    """ACCEPTED. 185.00 settles under a 200.00 hold; the residual is released."""
    settlement = next(e for e in book.entries if e.event_id == "E5")
    assert settlement.kind == "SETTLEMENT"
    assert str(settlement.amount) == "-185.00 AED"
    assert book.hold_state("Auth-A") == "SETTLED"


def test_c5_a_hold_moves_available_balance_and_not_ledger_balance(book) -> None:
    """ACCEPTED as a statement -- but its premise never occurs.

    Auth-B is declined, so the criterion describes a branch this stream never
    reaches. The property itself is real, so it is tested on Auth-A instead,
    at Day 2 when that hold was live and nothing had settled.
    """
    approved = replay(policy=FeePolicy.RETROACTIVE)
    assert str(approved.snapshots[2]["ACC-001"]) == "250.00 AED"
    decision = next(d for d in book.decisions if d.event_id == "E8")
    assert decision.outcome == "DECLINED"
    assert book.hold_state("Auth-B") == "DECLINED"


# ---------------------------------------------------------------- REFUSED


def test_c2_is_false_e7_does_not_cause_exactly_one_fee_on_day2(book, pit) -> None:
    """REFUSED. False under either resolution of the backdating ambiguity."""
    retro_fees = [e.value_date for e in book.entries if e.kind == "FEE"]
    pit_fees = [e.value_date for e in pit.entries if e.kind == "FEE"]
    assert retro_fees == [2, 4, 5], "three fees, not one"
    assert pit_fees == [5], "one fee, but on Day 5, not Day 2"
    assert retro_fees != [2] and pit_fees != [2]


def test_c4_is_false_an_unmatched_settlement_is_force_posted(book) -> None:
    """REFUSED. Declining E6 would not keep the money, only break clearing."""
    posting = next(e for e in book.entries if e.event_id == "E6")
    assert str(posting.amount) == "-180.00 AED"
    decision = next(d for d in book.decisions if d.event_id == "E6")
    assert decision.outcome == "FORCE_POSTED"


def test_c6_is_false_nothing_returns_to_its_pre_e7_value(book) -> None:
    """REFUSED. The fees stand, so neither fees nor balances rewind."""
    without_e7 = replay(
        [e for e in stream() if e.event_id not in ("E7", "E9")],
        policy=FeePolicy.RETROACTIVE,
    )
    assert str(without_e7.closing_balance("ACC-001", 2)) == "250.00 AED"
    assert str(book.closing_balance("ACC-001", 2)) == "225.00 AED"
    assert [e.kind for e in without_e7.entries if e.kind == "FEE"] == []
    assert len([e for e in book.entries if e.kind == "FEE"]) == 3


def test_c7_is_false_three_instalments_of_3334_overpay_by_two_fils(book) -> None:
    """REFUSED. 3.334 x 3 = 10.002, and the ledger would credit money that
    the event never carried."""
    parts = [e for e in book.entries if e.event_id == "E10"]
    assert [str(p.amount) for p in parts] == ["3.334 BHD", "3.333 BHD", "3.333 BHD"]
    assert sum(p.amount.minor for p in parts) == 10_000


def test_c8_is_false_the_rounding_remainder_is_placed_not_discarded(book) -> None:
    """REFUSED. It contradicts the stated rule, and the remainder is real here:
    independently rounded accruals give 0.69 against a true total of 0.70."""
    accruals = book.daily_accruals("ACC-001")
    credit = next(e for e in book.entries if e.kind == "INTEREST" and e.account == "ACC-001")
    assert sum(accruals) == credit.amount.minor == 70
    naive = [10, 9, 25, 9, 8, 8]  # each day rounded on its own
    assert sum(naive) == 69
    assert sum(accruals) - sum(naive) == 1
