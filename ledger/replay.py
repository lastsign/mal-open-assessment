"""Replays the six-day window and prints the report.

Events are processed in booking-day order, and in stream order within a day.
The stream lists E10 (booked Day 5) after E9 (booked Day 6); honouring the
listing literally would let Day 6 knowledge close Day 5. See AMBIGUITIES.md.
"""

from __future__ import annotations

import argparse
from typing import Mapping

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
from ledger.money import AED, BHD, Currency, EXPONENT, Money

WINDOW: Day = 6

ACCOUNTS: Mapping[str, Currency] = {"ACC-001": AED, "ACC-002": BHD}

OPENING: Mapping[str, Money] = {
    "ACC-001": Money.parse("0.00", AED),
    "ACC-002": Money.parse("0.000", BHD),
}


def stream() -> list[Event]:
    aed = lambda text: Money.parse(text, AED)  # noqa: E731
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


def render(book: Ledger, policy: FeePolicy, events: list[Event]) -> str:
    out: list[str] = []
    out.append(f"In-memory account ledger -- Day 1..{WINDOW}")
    out.append(f"overdraft-fee policy: {policy.value}")
    out.append("")

    by_day: dict[Day, list[Decision]] = {}
    for decision in book.decisions:
        by_day.setdefault(decision.day, []).append(decision)

    out.append("Restated at end of Day 6 (all entries, by value date)")
    out.append("-" * 66)
    header = "  day  " + "  ".join(_pad(a, 16) for a in ACCOUNTS)
    out.append(header)
    for day in range(1, WINDOW + 1):
        row = [_pad(str(book.closing_balance(a, day)), 16) for a in ACCOUNTS]
        out.append(f"  {day:>3}  " + "  ".join(row))
    out.append("")

    for day in range(1, WINDOW + 1):
        out.append(f"Day {day}")
        for account in ACCOUNTS:
            closed = book.snapshots[day][account]
            restated = book.closing_balance(account, day)
            out.append(f"  closed at         {account}  {closed}")
            if restated != closed:
                out.append(
                    f"  restated          {account}  {restated}"
                    "  (backdated entries arrived after this close)"
                )
        fees = [
            e for e in book.entries
            if e.kind == "FEE" and e.value_date == day
        ]
        if fees:
            for fee in fees:
                out.append(
                    f"  fee               {fee.account}  {fee.amount}  "
                    f"(assessed on Day {fee.booked_day}, value-dated Day {day})"
                )
        else:
            out.append("  fee               none")

        auths = sorted({e.auth_id for e in book._holds if e.day <= day})
        if auths:
            for auth_id in auths:
                opened = next(e for e in book._holds if e.auth_id == auth_id)
                out.append(
                    f"  authorisation     {auth_id}  {book.hold_state(auth_id, day)}  "
                    f"({opened.amount})"
                )
        else:
            out.append("  authorisation     none")

        problems = [
            d for d in by_day.get(day, [])
            if d.outcome in ("DECLINED", "FORCE_POSTED", "REJECTED")
        ]
        if problems:
            for problem in problems:
                out.append(f"  error             {problem.event_id}  {problem.outcome}: {problem.reason}")
        else:
            out.append("  error             none")
        out.append("")

    out.append("Interest")
    out.append("-" * 66)
    for account, currency in ACCOUNTS.items():
        accruals = book.daily_accruals(account)
        if not any(accruals):
            out.append(f"  {account}  no positive closing balance in the window")
            continue
        shown = "  ".join(str(Money(a, currency)).split()[0] for a in accruals)
        total = sum(accruals)
        out.append(f"  {account}  daily: {shown}")
        out.append(f"  {account}  capitalised on Day {WINDOW}: {Money(total, currency)}")
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
    print(render(replay(policy=policy), policy, stream()))


if __name__ == "__main__":
    main()
