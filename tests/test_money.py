"""Money primitives: the properties everything else leans on."""

from fractions import Fraction

import pytest

from ledger.money import (
    AED,
    BHD,
    CurrencyMismatch,
    Money,
    allocate,
    apportion,
    round_half_up,
)


def test_parses_at_the_currency_scale() -> None:
    assert Money.parse("1,200.00", AED) == Money(120_000, AED)
    assert Money.parse("10.000", BHD) == Money(10_000, BHD)
    assert Money.parse("-620.00", AED) == Money(-62_000, AED)


def test_rejects_over_precision_rather_than_rounding_it_away() -> None:
    with pytest.raises(ValueError):
        Money.parse("1.005", AED)


def test_arithmetic_across_currencies_is_refused() -> None:
    with pytest.raises(CurrencyMismatch):
        Money(1, AED) + Money(1, BHD)


@pytest.mark.parametrize("parts", range(1, 8))
@pytest.mark.parametrize("minor", [10_000, 1, 7, -10_000, 0, 999_999])
def test_allocation_always_sums_to_the_original(minor: int, parts: int) -> None:
    total = Money(minor, BHD)
    pieces = allocate(total, parts)
    assert len(pieces) == parts
    assert sum(p.minor for p in pieces) == minor


def test_ten_bhd_in_three_is_not_three_equal_thirds() -> None:
    # BHD 10.000 / 3 has no exact representation at three decimal places.
    # The remainder is placed, not spread: 3.334 + 3.333 + 3.333 == 10.000.
    assert [str(p) for p in allocate(Money.parse("10.000", BHD), 3)] == [
        "3.334 BHD",
        "3.333 BHD",
        "3.333 BHD",
    ]


def test_round_half_up_moves_away_from_zero() -> None:
    assert round_half_up(Fraction(1, 2)) == 1
    assert round_half_up(Fraction(-1, 2)) == -1
    assert round_half_up(Fraction(47, 5)) == 9  # 9.4


def test_apportionment_reconciles_to_the_total() -> None:
    exact = [Fraction(47, 5), Fraction(42, 5), Fraction(42, 5)]  # 9.4, 8.4, 8.4
    total = round_half_up(sum(exact, Fraction(0)))  # 26.2 -> 26
    shares = apportion(exact, total)
    assert sum(shares) == total
    # The extra unit goes to the earliest of the tied remainders, so that the
    # same input always produces the same daily figures.
    assert shares == [10, 8, 8]
