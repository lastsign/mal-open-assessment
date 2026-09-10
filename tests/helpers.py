"""Shared query helpers for the tests.

An entry no longer knows when it happened or why -- that moved to the
transaction -- so tests join the two and filter on the join. This is the same
shape a reporting query would take.
"""

from __future__ import annotations

from ledger.core import Entry, Ledger, Transaction


def postings(
    book: Ledger,
    *,
    kind: str | None = None,
    account: str | None = None,
    event_id: str | None = None,
) -> list[tuple[Transaction, Entry]]:
    rows = book.postings()
    if kind is not None:
        rows = [(t, e) for t, e in rows if t.kind == kind]
    if account is not None:
        rows = [(t, e) for t, e in rows if e.account == account]
    if event_id is not None:
        rows = [(t, e) for t, e in rows if t.event_id == event_id]
    return rows


def customer_legs(book: Ledger, **filters: str) -> list[tuple[Transaction, Entry]]:
    """Only the customer side of each transaction, never the contra."""
    customers = set(book.customers)
    return [
        (t, e) for t, e in postings(book, **filters) if e.account in customers
    ]
