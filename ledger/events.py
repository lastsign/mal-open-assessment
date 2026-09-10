"""The input stream: what the bank was told, and when it was told it.

Every event carries two dates and they are not interchangeable.
`booked_day` is when the ledger learned of the event; `value_date` is the day
the money is deemed to have moved. A backdated entry is one where the two
disagree, and every hard question in this ledger comes from that gap.
"""

from __future__ import annotations

from dataclasses import dataclass

from ledger.money import Money

Day = int


@dataclass(frozen=True, slots=True)
class Credit:
    event_id: str
    booked_day: Day
    value_date: Day
    account: str
    amount: Money
    instalments: int = 1


@dataclass(frozen=True, slots=True)
class Debit:
    event_id: str
    booked_day: Day
    value_date: Day
    account: str
    amount: Money


@dataclass(frozen=True, slots=True)
class Authorization:
    event_id: str
    booked_day: Day
    value_date: Day
    account: str
    auth_id: str
    amount: Money


@dataclass(frozen=True, slots=True)
class Settlement:
    event_id: str
    booked_day: Day
    value_date: Day
    account: str
    auth_id: str
    amount: Money


@dataclass(frozen=True, slots=True)
class Reversal:
    event_id: str
    booked_day: Day
    value_date: Day
    account: str
    reverses: str


Event = Credit | Debit | Authorization | Settlement | Reversal
