"""Money: integer minor units, inseparable from a currency.

No float appears anywhere in this package. Exact arithmetic is `int` for
booked amounts and `Fraction` for intermediate interest, never `Decimal`
contexts and never binary floating point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Final, NewType

Currency = NewType("Currency", str)

AED: Final = Currency("AED")
BHD: Final = Currency("BHD")

# The scale of a currency is a property of the currency, not of an entry.
# Storing it per entry would let two AED entries disagree about what a minor
# unit is -- a bug class we decline to own for the life of the ledger.
EXPONENT: Final[dict[Currency, int]] = {AED: 2, BHD: 3}


class CurrencyMismatch(Exception):
    """Arithmetic was attempted across two currencies."""


class UnknownCurrency(Exception):
    """A currency was used before it was registered with a scale."""


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in minor units of `currency`. Immutable and hashable."""

    minor: int
    currency: Currency

    def __post_init__(self) -> None:
        if self.currency not in EXPONENT:
            raise UnknownCurrency(self.currency)

    @classmethod
    def zero(cls, currency: Currency) -> Money:
        return cls(0, currency)

    @classmethod
    def parse(cls, text: str, currency: Currency) -> Money:
        """Parse a human decimal string at exactly the currency's scale.

        Rejects over-precision instead of rounding it away: `1.005` in AED is
        an input error somewhere upstream, not something to silently absorb.
        """
        if currency not in EXPONENT:
            raise UnknownCurrency(currency)
        exponent = EXPONENT[currency]
        cleaned = text.replace(",", "").strip()
        sign = -1 if cleaned.startswith("-") else 1
        cleaned = cleaned.lstrip("+-")
        whole, _, frac = cleaned.partition(".")
        if len(frac) > exponent:
            raise ValueError(f"{text!r} has more precision than {currency}")
        frac = frac.ljust(exponent, "0")
        return cls(sign * int(whole + frac if frac else whole), currency)

    def _same(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(f"{self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.minor - other.minor, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.minor, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._same(other)
        return self.minor < other.minor

    @property
    def is_negative(self) -> bool:
        return self.minor < 0

    @property
    def is_positive(self) -> bool:
        return self.minor > 0

    def __str__(self) -> str:
        exponent = EXPONENT[self.currency]
        sign = "-" if self.minor < 0 else ""
        digits = str(abs(self.minor)).rjust(exponent + 1, "0")
        if exponent == 0:
            return f"{sign}{digits} {self.currency}"
        return f"{sign}{digits[:-exponent]}.{digits[-exponent:]} {self.currency}"


def allocate(total: Money, parts: int) -> list[Money]:
    """Split `total` into `parts` that sum to exactly `total`.

    The remainder goes to the earliest parts. A deterministic rule is worth
    more than a fair-looking one: the same input must always produce the same
    instalments, or a replay of the log stops reconciling.
    """
    if parts < 1:
        raise ValueError("parts must be >= 1")
    base, remainder = divmod(total.minor, parts)
    return [
        Money(base + (1 if i < remainder else 0), total.currency)
        for i in range(parts)
    ]


def round_half_up(value: Fraction) -> int:
    """Round to the nearest integer, halves away from zero.

    Banker's rounding is the better default for repeated independent
    roundings, but it is not what a retail fee schedule promises a customer,
    and the apportionment below removes the bias that half-up would otherwise
    introduce. See NUMBERS.md.
    """
    if value < 0:
        return -math.floor(-value + Fraction(1, 2))
    return math.floor(value + Fraction(1, 2))


def apportion(exact: list[Fraction], total: int) -> list[int]:
    """Integers closest to `exact` that sum to exactly `total`.

    Largest remainder, ties broken by earliest index. Used so that the daily
    interest accruals we print reconcile to the single capitalised credit
    rather than merely being near it.
    """
    floors = [math.floor(value) for value in exact]
    deficit = total - sum(floors)
    if not 0 <= deficit <= len(exact):
        raise ValueError(f"cannot apportion {total} over {len(exact)} accruals")
    order = sorted(
        range(len(exact)),
        key=lambda i: (-(exact[i] - floors[i]), i),
    )
    for i in order[:deficit]:
        floors[i] += 1
    return floors
