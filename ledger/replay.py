"""Replays the six-day window and prints the report.

Events are processed in booking-day order, and in stream order within a day.
The stream lists E10 (booked Day 5) after E9 (booked Day 6); honouring the
listing literally would let Day 6 knowledge close Day 5. See AMBIGUITIES.md.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping

from ledger.core import Decision, FeePolicy, Ledger
from ledger.events import (
    Authorization,
    Credit,
    Day,
    Debit,
    Event,
    Reversal,
    Settlement,
)
from ledger.money import AED, BHD, Currency, Money

WINDOW: Day = 6

ACCOUNTS: Mapping[str, Currency] = {"ACC-001": AED, "ACC-002": BHD}

OPENING: Mapping[str, Money] = {
    "ACC-001": Money.parse("0.00", AED),
    "ACC-002": Money.parse("0.000", BHD),
}


def stream() -> list[Event]:
    aed = lambda text: Money.parse(text, AED)
    return [
        Credit("E1", 1, 1, "ACC-001", aed("1200.00")),
        Debit("E2", 1, 1, "ACC-001", aed("950.00")),
        Authorization("E3", 2, 2, "ACC-001", "Auth-A", aed("200.00")),
        Credit("E4", 3, 3, "ACC-001", aed("400.00")),
        Settlement("E5", 4, 4, "ACC-001", "Auth-A", aed("185.00")),
        Settlement("E6", 4, 4, "ACC-001", "Auth-Z", aed("180.00")),
        Debit("E7", 5, 2, "ACC-001", aed("620.00")),
        Authorization("E8", 5, 5, "ACC-001", "Auth-B", aed("90.00")),
        Reversal("E9", 6, 2, "ACC-001", reverses="E7"),
        Credit("E10", 5, 5, "ACC-002", Money.parse("10.000", BHD), instalments=3),
    ]


def replay(
    events: list[Event] | None = None,
    policy: FeePolicy = FeePolicy.RETROACTIVE,
) -> Ledger:
    events = stream() if events is None else events
    book = Ledger(ACCOUNTS, fee_policy=policy)
    for account, opening in OPENING.items():
        if opening.minor:
            book.post_event(Credit(f"OPEN-{account}", 1, 1, account, opening))
    for day in range(1, WINDOW + 1):
        for event in [e for e in events if e.booked_day == day]:
            book.post_event(event)
        book.close_day(day)
    book.capitalize_interest(WINDOW)
    return book


# ------------------------------------------------------------------ report


def _pad(text: str, width: int) -> str:
    return text.rjust(width)


def _line(label: str, rest: str) -> str:
    """One report row: a fixed-width label column, then its content."""
    return "  " + label.ljust(18) + rest


def _restated_table(book: Ledger) -> list[str]:
    rows = [
        f"Restated at end of Day {WINDOW} (all entries, by value date)",
        "-" * 66,
        "  day  " + "  ".join(_pad(a, 16) for a in ACCOUNTS),
    ]
    for day in range(1, WINDOW + 1):
        cells = [_pad(str(book.closing_balance(a, day)), 16) for a in ACCOUNTS]
        rows.append(f"  {day:>3}  " + "  ".join(cells))
    return rows


def _balances(book: Ledger, day: Day) -> list[str]:
    """Both views of the day: how it closed, and how it reads now."""
    rows: list[str] = []
    for account in ACCOUNTS:
        closed = book.snapshots[day][account]
        restated = book.closing_balance(account, day)
        rows.append(_line("closed at", f"{account}  {closed}"))
        if restated != closed:
            rows.append(
                _line(
                    "restated",
                    f"{account}  {restated}"
                    "  (backdated entries arrived after this close)",
                )
            )
    return rows


def _fees(book: Ledger, day: Day) -> list[str]:
    fees = book.fees_on(day)
    if not fees:
        return [_line("fee", "none")]
    return [
        _line(
            "fee",
            f"{fee.account}  {fee.amount}  "
            f"(assessed on Day {fee.booked_day}, value-dated Day {day})",
        )
        for fee in fees
    ]


def _authorisations(book: Ledger, day: Day) -> list[str]:
    auth_ids = book.authorisation_ids(day)
    if not auth_ids:
        return [_line("authorisation", "none")]
    return [
        _line(
            "authorisation",
            f"{auth_id}  {book.hold_state(auth_id, day)}  "
            f"({book.hold_amount(auth_id)})",
        )
        for auth_id in auth_ids
    ]


def _errors(decisions: list[Decision]) -> list[str]:
    problems = [
        d for d in decisions
        if d.outcome in ("DECLINED", "FORCE_POSTED", "REJECTED")
    ]
    if not problems:
        return [_line("error", "none")]
    return [
        _line("error", f"{d.event_id}  {d.outcome}: {d.reason}")
        for d in problems
    ]


def _interest(book: Ledger) -> list[str]:
    rows = ["Interest", "-" * 66]
    for account, currency in ACCOUNTS.items():
        accruals = book.daily_accruals(account)
        if not any(accruals):
            rows.append(f"  {account}  no positive closing balance in the window")
            continue
        shown = "  ".join(str(Money(a, currency)).split()[0] for a in accruals)
        rows.append(f"  {account}  daily: {shown}")
        rows.append(
            f"  {account}  capitalised on Day {WINDOW}: "
            f"{Money(sum(accruals), currency)}"
        )
    return rows


def render(book: Ledger, policy: FeePolicy) -> str:
    by_day: dict[Day, list[Decision]] = {}
    for decision in book.decisions:
        by_day.setdefault(decision.day, []).append(decision)

    out = [
        f"In-memory account ledger -- Day 1..{WINDOW}",
        f"overdraft-fee policy: {policy.value}",
        "",
        *_restated_table(book),
        "",
    ]
    for day in range(1, WINDOW + 1):
        out.append(f"Day {day}")
        out += _balances(book, day)
        out += _fees(book, day)
        out += _authorisations(book, day)
        out += _errors(by_day.get(day, []))
        out.append("")
    out += _interest(book)
    out.append("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        choices=[p.value for p in FeePolicy],
        default=FeePolicy.RETROACTIVE.value,
        help="how overdraft fees react to a backdated entry landing on a closed day",
    )
    args = parser.parse_args()
    policy = FeePolicy(args.policy)
    print(render(replay(policy=policy), policy))


if __name__ == "__main__":
    main()
