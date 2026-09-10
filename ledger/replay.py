"""Replays the six-day window and prints the report.

Events are processed in booking-day order, and in stream order within a day.
The stream lists E10 (booked Day 5) after E9 (booked Day 6); honouring the
listing literally would let Day 6 knowledge close Day 5. See AMBIGUITIES.md.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping

from ledger.core import Account, AccountKind, Decision, FeePolicy, Ledger
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



def _account(account_id: str, currency: Currency, kind: AccountKind) -> Account:
    return Account(account_id, currency, kind)


# The chart is deliberately the smallest one that lets every event balance.
# Customer accounts are the only ones that attract fees and interest; the
# rest exist so that money has somewhere to come from and go to.
CHART: Mapping[str, Account] = {
    a.id: a
    for a in (
        _account("ACC-001", AED, AccountKind.CUSTOMER),
        _account("ACC-002", BHD, AccountKind.CUSTOMER),
        _account("CLEARING-AED", AED, AccountKind.CLEARING),
        _account("CLEARING-BHD", BHD, AccountKind.CLEARING),
        _account("SUSPENSE-AED", AED, AccountKind.SUSPENSE),
        _account("SUSPENSE-BHD", BHD, AccountKind.SUSPENSE),
        _account("INCOME-FEES-AED", AED, AccountKind.INCOME),
        _account("EXPENSE-INTEREST-AED", AED, AccountKind.EXPENSE),
        _account("EXPENSE-INTEREST-BHD", BHD, AccountKind.EXPENSE),
    )
}

CUSTOMERS: tuple[str, ...] = ("ACC-001", "ACC-002")

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
    chart: Mapping[str, Account] | None = None,
) -> Ledger:
    events = stream() if events is None else events
    book = Ledger(CHART if chart is None else chart, fee_policy=policy)
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
    customers = book.customers
    rows = [
        f"Restated at end of Day {WINDOW} (all entries, by value date)",
        "-" * 66,
        "  day  " + "  ".join(_pad(a, 16) for a in customers),
    ]
    for day in range(1, WINDOW + 1):
        cells = [_pad(str(book.closing_balance(a, day)), 16) for a in customers]
        rows.append(f"  {day:>3}  " + "  ".join(cells))
    return rows


def _balances(book: Ledger, day: Day) -> list[str]:
    """Both views of the day: how it closed, and how it reads now."""
    rows: list[str] = []
    for account in book.customers:
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
    for account in book.customers:
        currency = book.currency_of(account)
        accruals = book.daily_accruals(account)
        earned = any(
            book.closing_balance(account, day).is_positive
            for day in range(1, WINDOW + 1)
        )
        if not earned:
            rows.append(f"  {account}  no positive closing balance in the window")
            continue
        if not any(accruals):
            # A real balance that accrued less than one minor unit is not the
            # same fact as never having been in credit, and saying so would be
            # a false statement about the customer's account.
            rows.append(
                f"  {account}  accrued less than one minor unit over the window"
            )
            continue
        shown = "  ".join(str(Money(a, currency)).split()[0] for a in accruals)
        rows.append(f"  {account}  daily: {shown}")
        rows.append(
            f"  {account}  capitalised on Day {WINDOW}: "
            f"{Money(sum(accruals), currency)}"
        )
    return rows


def _amount(value: Money) -> str:
    """The number alone: in a grouped report the block header carries the code."""
    return str(value).rsplit(" ", 1)[0]


def _accounts_by_currency(book: Ledger) -> dict[Currency, list[str]]:
    """The chart split into currency blocks, chart order kept within each."""
    grouped: dict[Currency, list[str]] = {}
    for account_id, account in book.chart.items():
        grouped.setdefault(account.currency, []).append(account_id)
    return grouped


def _block(book: Ledger, currency: Currency, account_ids: list[str]) -> list[tuple[str, str]]:
    """(label, figure) for one currency's accounts, with its total last.

    An internal account that never moved is omitted; a customer account is
    always shown, even at zero, because its absence would read as an error
    rather than as an empty account.
    """
    lines = [
        (account_id, _amount(book.closing_balance(account_id, WINDOW)))
        for account_id in account_ids
        if book.closing_balance(account_id, WINDOW).minor != 0
        or account_id in book.customers
    ]
    # A chart currency that saw no postings is zero, not missing: the
    # trial balance only carries currencies that actually have entries.
    total = Money(book.trial_balance(WINDOW).get(currency, 0), currency)
    return [*lines, ("sum", _amount(total))]


def _align(lines: list[tuple[str, str]]) -> list[str]:
    """Two columns, figures right-justified, a rule above the last row.

    Widths come from the content, so a longer account name or a larger figure
    widens the column rather than breaking the alignment.
    """
    label_width = max(len(label) for label, _ in lines)
    figure_width = max(len(figure) for _, figure in lines)
    body = [
        f"    {label:<{label_width}}  {figure:>{figure_width}}"
        for label, figure in lines[:-1]
    ]
    total_label, total_figure = lines[-1]
    return [
        *body,
        f"    {'':<{label_width}}  {'-' * figure_width}",
        f"    {total_label:<{label_width}}  {total_figure:>{figure_width}}",
    ]


def _trial_balance(book: Ledger) -> list[str]:
    """Every account grouped by currency, and the proof that each block cancels.

    Grouped rather than listed flat for two reasons. A trial balance that mixes
    currencies cannot be added up, so a single column of them is not a trial
    balance at all. And within one currency every amount carries the same
    number of decimal places, so right-justifying the figures lines the decimal
    points up without any special handling.
    """
    rows = [f"Trial balance at end of Day {WINDOW}", "-" * 66]
    grouped = _accounts_by_currency(book)
    for currency in sorted(grouped):
        rows.append(f"  {currency}")
        rows += _align(_block(book, currency, grouped[currency]))
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
    out += _trial_balance(book)
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
