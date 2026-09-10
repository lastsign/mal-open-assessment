"""The ledger core: an append-only log and the views derived from it.

Nothing in this module mutates or removes a record. Corrections are new
records. Balances, holds and authorisation states are all derived by reading
the log, never stored as a field that could drift from it.

Postings are double-entry. Every event resolves to a set of postings that sums
to zero in each currency it touches, and they are validated before any of them
is appended -- so an event that does not balance leaves no trace at all rather
than half of one.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Final, Literal

from ledger.events import (
    Authorization,
    Credit,
    Day,
    Debit,
    Event,
    Reversal,
    Settlement,
)
from ledger.money import (
    AED,
    Currency,
    Money,
    allocate,
    apportion,
    round_half_up,
)

OVERDRAFT_FEE: Final = Money(2500, AED) # amount in minor units
DAILY_INTEREST_RATE: Final = Fraction(4, 10_000)  # 0.04% per day


class FeePolicy(StrEnum):
    """How the ledger reacts when a backdated entry lands on a closed day."""

    RETROACTIVE = "retroactive"
    POINT_IN_TIME = "point-in-time"


class AccountKind(StrEnum):
    """What an account is for. Only CUSTOMER accounts attract fees and interest."""

    CUSTOMER = "customer"
    CLEARING = "clearing"
    SUSPENSE = "suspense"
    INCOME = "income"
    EXPENSE = "expense"


class UndefinedFeeCurrency(Exception):
    """An overdraft fee was owed in a currency the fee schedule does not name."""


class Unbalanced(Exception):
    """A set of postings did not sum to zero in every currency it touched."""


class NoSuchAccount(Exception):
    """The chart of accounts has no account to post the other side against."""


EntryKind = Literal["CREDIT", "DEBIT", "SETTLEMENT", "FEE", "INTEREST", "REVERSAL"]
Outcome = Literal["APPROVED", "DECLINED", "FORCE_POSTED", "REJECTED", "REVERSED"]
HoldState = Literal["ACTIVE", "SETTLED", "RELEASED", "DECLINED"]


@dataclass(frozen=True, slots=True)
class Account:
    id: str
    currency: Currency
    kind: AccountKind


@dataclass(frozen=True, slots=True)
class Posting:
    """One side of a transaction, before it is committed to the log."""

    account: str
    amount: Money
    kind: EntryKind
    note: str = ""
    reverses: str = ""


@dataclass(frozen=True, slots=True)
class Entry:
    """One committed posting. Signed: positive increases the account's balance."""

    seq: int
    event_id: str
    account: str
    amount: Money
    value_date: Day
    booked_day: Day
    kind: EntryKind
    note: str = ""
    reverses: str = ""


@dataclass(frozen=True, slots=True)
class Decision:
    """A judgement the engine made. Recorded even when nothing was posted."""

    seq: int
    event_id: str
    day: Day
    outcome: Outcome
    reason: str


@dataclass(frozen=True, slots=True)
class HoldEvent:
    """A transition in an authorisation's life. The state is the last one."""

    seq: int
    auth_id: str
    account: str
    day: Day
    state: HoldState
    amount: Money


class Ledger:
    def __init__(
        self,
        chart: Mapping[str, Account],
        fee_policy: FeePolicy = FeePolicy.RETROACTIVE,
    ) -> None:
        self._chart = dict(chart)
        self._fee_policy = fee_policy
        self._entries: list[Entry] = []
        self._decisions: list[Decision] = []
        self._holds: list[HoldEvent] = []
        self._seq = 0
        self._daily_accruals: dict[str, list[int]] = {}
        # What each day looked like at the moment it closed. Kept for the
        # report only: the log remains the sole source of truth, and a
        # backdated entry will make these disagree with the restated view.
        self.snapshots: dict[Day, dict[str, Money]] = {}

    # ------------------------------------------------------------- chart

    @property
    def customers(self) -> list[str]:
        return [a.id for a in self._chart.values() if a.kind is AccountKind.CUSTOMER]

    @property
    def chart(self) -> Mapping[str, Account]:
        return dict(self._chart)

    def currency_of(self, account: str) -> Currency:
        return self._chart[account].currency

    def _contra(self, kind: AccountKind, currency: Currency) -> str:
        """The internal account that takes the other side, or a loud failure.

        A missing contra account is a gap in the chart, not something to
        improvise around: posting one-sided would silently break the
        zero-sum invariant that everything else here relies on.
        """
        matches = [
            a.id for a in self._chart.values()
            if a.kind is kind and a.currency == currency
        ]
        if len(matches) != 1:
            raise NoSuchAccount(
                f"expected exactly one {kind} account in {currency}, found {len(matches)}"
            )
        return matches[0]

    # ---------------------------------------------------------------- log

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _commit(
        self,
        event_id: str,
        value_date: Day,
        booked_day: Day,
        postings: list[Posting],
    ) -> list[Entry]:
        """Append a balanced set of postings, or none of them.

        Validation runs before the first append, so an unbalanced transaction
        cannot leave a partial trace. This is also the seam a `Transaction`
        record would slot into later: by the time control reaches here the
        postings are already grouped, validated and committed as one unit, so
        giving that unit an identity is an addition rather than a rewrite.
        """
        totals: dict[Currency, int] = defaultdict(int)
        for posting in postings:
            totals[posting.amount.currency] += posting.amount.minor
        unbalanced = {c: v for c, v in totals.items() if v != 0}
        if unbalanced:
            raise Unbalanced(f"{event_id}: {unbalanced}")

        committed = [
            Entry(
                seq=self._next_seq(),
                event_id=event_id,
                account=posting.account,
                amount=posting.amount,
                value_date=value_date,
                booked_day=booked_day,
                kind=posting.kind,
                note=posting.note,
                reverses=posting.reverses,
            )
            for posting in postings
        ]
        self._entries.extend(committed)
        return committed

    def _decide(self, event_id: str, day: Day, outcome: Outcome, reason: str) -> None:
        self._decisions.append(Decision(self._next_seq(), event_id, day, outcome, reason))

    @property
    def entries(self) -> tuple[Entry, ...]:
        return tuple(self._entries)

    @property
    def decisions(self) -> tuple[Decision, ...]:
        return tuple(self._decisions)

    @property
    def holds(self) -> tuple[HoldEvent, ...]:
        return tuple(self._holds)

    def authorisation_ids(self, day: Day) -> list[str]:
        """Every authorisation the ledger knows of as of `day`, in order."""
        return sorted({e.auth_id for e in self._holds if e.day <= day})

    def hold_amount(self, auth_id: str) -> Money:
        """The amount the authorisation was opened for."""
        return next(e for e in self._holds if e.auth_id == auth_id).amount

    def fees_on(self, day: Day) -> list[Entry]:
        return [
            e for e in self._entries
            if e.kind == "FEE" and e.value_date == day and e.account in self.customers
        ]

    # ------------------------------------------------------------- views

    def closing_balance(self, account: str, day: Day) -> Money:
        """Every entry with value_date <= day, whenever it was booked."""
        total = Money.zero(self.currency_of(account))
        for entry in self._entries:
            if entry.account == account and entry.value_date <= day:
                total = total + entry.amount
        return total

    def trial_balance(self, day: Day) -> dict[Currency, int]:
        """Every account summed per currency. Must be zero in each of them."""
        totals: dict[Currency, int] = defaultdict(int)
        for entry in self._entries:
            if entry.value_date <= day:
                totals[entry.amount.currency] += entry.amount.minor
        return dict(totals)

    def hold_state(self, auth_id: str, day: Day | None = None) -> HoldState | None:
        state: HoldState | None = None
        for event in self._holds:
            if event.auth_id == auth_id and (day is None or event.day <= day):
                state = event.state
        return state

    def active_holds(self, account: str, day: Day | None = None) -> Money:
        total = Money.zero(self.currency_of(account))
        seen = {
            e.auth_id for e in self._holds
            if e.account == account and (day is None or e.day <= day)
        }
        for auth_id in seen:
            if self.hold_state(auth_id, day) == "ACTIVE":
                total = total + self.hold_amount(auth_id)
        return total

    def available_balance(self, account: str, day: Day) -> Money:
        return self.closing_balance(account, day) - self.active_holds(account, day)

    def daily_accruals(self, account: str) -> list[int]:
        return list(self._daily_accruals.get(account, []))

    # ------------------------------------------------------------ intake

    def post_event(self, event: Event) -> None:
        match event:
            case Credit():
                self._on_credit(event)
            case Debit():
                self._on_debit(event)
            case Authorization():
                self._on_authorization(event)
            case Settlement():
                self._on_settlement(event)
            case Reversal():
                self._on_reversal(event)

    def _on_credit(self, event: Credit) -> None:
        contra = self._contra(AccountKind.CLEARING, event.amount.currency)
        postings: list[Posting] = []
        parts = allocate(event.amount, event.instalments)
        for i, part in enumerate(parts, start=1):
            note = f"instalment {i}/{event.instalments}" if event.instalments > 1 else ""
            postings.append(Posting(event.account, part, "CREDIT", note))
            postings.append(Posting(contra, -part, "CREDIT", note))
        self._commit(event.event_id, event.value_date, event.booked_day, postings)

    def _on_debit(self, event: Debit) -> None:
        contra = self._contra(AccountKind.CLEARING, event.amount.currency)
        self._commit(
            event.event_id, event.value_date, event.booked_day,
            [
                Posting(event.account, -event.amount, "DEBIT"),
                Posting(contra, event.amount, "DEBIT"),
            ],
        )

    def _on_authorization(self, event: Authorization) -> None:
        """A hold posts nothing: it is a memo against available balance."""
        available = self.available_balance(event.account, event.value_date)
        projected = available - event.amount
        state: HoldState = "DECLINED" if projected.is_negative else "ACTIVE"
        self._holds.append(
            HoldEvent(self._next_seq(), event.auth_id, event.account,
                      event.value_date, state, event.amount)
        )
        if state == "DECLINED":
            self._decide(
                event.event_id, event.booked_day, "DECLINED",
                f"available {available} would fall to {projected}",
            )
        else:
            self._decide(
                event.event_id, event.booked_day, "APPROVED", f"hold {event.amount}"
            )

    def _on_settlement(self, event: Settlement) -> None:
        """Settlements are booked, never balance-checked.

        The obligation was created when the authorisation was approved, or --
        for an unmatched settlement -- by the scheme upstream of us. Declining
        here would not keep the money; it would only put our ledger out of
        step with the clearing file. See REJECTED.md.
        """
        state = self.hold_state(event.auth_id)
        if state is None:
            self._force_post(event)
            return
        if state != "ACTIVE":
            self._decide(
                event.event_id, event.booked_day, "REJECTED",
                f"authorisation {event.auth_id} is already {state}",
            )
            return
        held = self.hold_amount(event.auth_id)
        contra = self._contra(AccountKind.CLEARING, event.amount.currency)
        self._commit(
            event.event_id, event.value_date, event.booked_day,
            [
                Posting(event.account, -event.amount, "SETTLEMENT",
                        f"settles {event.auth_id}"),
                Posting(contra, event.amount, "SETTLEMENT", f"settles {event.auth_id}"),
            ],
        )
        self._holds.append(
            HoldEvent(self._next_seq(), event.auth_id, event.account,
                      event.value_date, "SETTLED", event.amount)
        )
        residual = held - event.amount
        reason = f"settled {event.amount} against hold {held}"
        if residual.is_positive:
            reason += f", residual {residual} released"
        self._decide(event.event_id, event.booked_day, "APPROVED", reason)

    def _force_post(self, event: Settlement) -> None:
        """The other side goes to suspense, not clearing.

        We owe someone; we cannot yet say who. Parking it in suspense makes
        the unreconciled position a balance an operator can see and age,
        rather than something buried inside the clearing account.
        """
        contra = self._contra(AccountKind.SUSPENSE, event.amount.currency)
        note = "unmatched: force post"
        self._commit(
            event.event_id, event.value_date, event.booked_day,
            [
                Posting(event.account, -event.amount, "SETTLEMENT", note),
                Posting(contra, event.amount, "SETTLEMENT", note),
            ],
        )
        self._decide(
            event.event_id, event.booked_day, "FORCE_POSTED",
            f"no authorisation {event.auth_id} in the ledger",
        )

    def _on_reversal(self, event: Reversal) -> None:
        originals = [e for e in self._entries if e.event_id == event.reverses]
        if not originals:
            self._decide(
                event.event_id, event.booked_day, "REJECTED",
                f"nothing booked under {event.reverses}",
            )
            return
        if any(e.reverses == event.reverses for e in self._entries):
            self._decide(
                event.event_id, event.booked_day, "REJECTED",
                f"{event.reverses} is already reversed",
            )
            return
        # Reversing every leg of the original keeps the contra balanced for
        # free: a balanced transaction negated is still balanced.
        self._commit(
            event.event_id, event.value_date, event.booked_day,
            [
                Posting(o.account, -o.amount, "REVERSAL",
                        f"reverses {event.reverses}", event.reverses)
                for o in originals
            ],
        )
        self._decide(event.event_id, event.booked_day, "REVERSED", f"contra of {event.reverses}")

    # ------------------------------------------------------------- close

    def close_day(self, day: Day) -> list[Entry]:
        """Assess overdraft fees for this close. Returns the fees booked."""
        days: Iterable[Day] = (
            range(1, day + 1) if self._fee_policy is FeePolicy.RETROACTIVE else (day,)
        )
        booked: list[Entry] = []
        for account in self.customers:
            # Ascending: a fee dated day D is itself an entry that drags
            # every later closing balance down, and may trigger the next fee.
            for candidate in days:
                fee = self._maybe_assess_fee(account, candidate, day)
                if fee is not None:
                    booked.append(fee)
        self.snapshots[day] = {
            account: self.closing_balance(account, day) for account in self.customers
        }
        return booked

    def _maybe_assess_fee(
        self, account: str, value_date: Day, booked_day: Day
    ) -> Entry | None:
        already = any(
            e.account == account and e.kind == "FEE" and e.value_date == value_date
            for e in self._entries
        )
        if already:
            return None
        if not self.closing_balance(account, value_date).is_negative:
            return None
        if self.currency_of(account) != OVERDRAFT_FEE.currency:
            raise UndefinedFeeCurrency(
                f"{account} is {self.currency_of(account)} but the fee schedule "
                f"is written in {OVERDRAFT_FEE.currency}; no rate was given. "
                f"See AMBIGUITIES.md."
            )
        income = self._contra(AccountKind.INCOME, OVERDRAFT_FEE.currency)
        entries = self._commit(
            f"FEE-{account}-D{value_date}", value_date, booked_day,
            [
                Posting(account, -OVERDRAFT_FEE, "FEE", "overdraft"),
                Posting(income, OVERDRAFT_FEE, "FEE", "overdraft"),
            ],
        )
        return entries[0]

    def capitalize_interest(self, last_day: Day) -> None:
        """Accrue daily on positive closing balances, credit once at the end.

        The accruals are apportioned to the capitalised total rather than
        rounded independently, so the daily figures we publish add up to the
        single credit the customer actually receives.
        """
        for account in self.customers:
            currency = self.currency_of(account)
            exact = [
                Fraction(max(self.closing_balance(account, day).minor, 0))
                * DAILY_INTEREST_RATE
                for day in range(1, last_day + 1)
            ]
            total = round_half_up(sum(exact, Fraction(0)))
            self._daily_accruals[account] = apportion(exact, total)
            if not total:
                continue
            credit = Money(total, currency)
            expense = self._contra(AccountKind.EXPENSE, currency)
            self._commit(
                f"INT-{account}", last_day, last_day,
                [
                    Posting(account, credit, "INTEREST", "capitalised accrual"),
                    Posting(expense, -credit, "INTEREST", "capitalised accrual"),
                ],
            )
        # Capitalisation is part of the last day's close, not something that
        # arrived after it. Without this the report calls the credit a
        # backdated restatement, which is a lie about how the money got there.
        if last_day in self.snapshots:
            self.snapshots[last_day] = {
                account: self.closing_balance(account, last_day)
                for account in self.customers
            }
