"""The ledger core: an append-only log and the views derived from it.

Nothing in this module mutates or removes a record. Corrections are new
records. Balances, holds and authorisation states are all derived by reading
the log, never stored as a field that could drift from it.
"""

from __future__ import annotations

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


class UndefinedFeeCurrency(Exception):
    """An overdraft fee was owed in a currency the fee schedule does not name."""


EntryKind = Literal["CREDIT", "DEBIT", "SETTLEMENT", "FEE", "INTEREST", "REVERSAL"]
Outcome = Literal["APPROVED", "DECLINED", "FORCE_POSTED", "REJECTED", "REVERSED"]
HoldState = Literal["ACTIVE", "SETTLED", "RELEASED", "DECLINED"]


@dataclass(frozen=True, slots=True)
class Entry:
    """One posting. Signed: positive increases the account's balance."""

    seq: int
    event_id: str
    account: str
    amount: Money
    value_date: Day
    booked_day: Day
    kind: EntryKind
    note: str = ""


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
        accounts: Mapping[str, Currency],
        fee_policy: FeePolicy = FeePolicy.RETROACTIVE,
    ) -> None:
        self._accounts = dict(accounts)
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

    # ---------------------------------------------------------------- log

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _post(
        self,
        event_id: str,
        account: str,
        amount: Money,
        value_date: Day,
        booked_day: Day,
        kind: EntryKind,
        note: str = "",
    ) -> Entry:
        entry = Entry(
            self._next_seq(),
            event_id,
            account,
            amount,
            value_date,
            booked_day,
            kind,
            note,
        )
        self._entries.append(entry)
        return entry

    def _decide(self, event_id: str, day: Day, outcome: Outcome, reason: str) -> None:
        self._decisions.append(
            Decision(self._next_seq(), event_id, day, outcome, reason)
        )

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
        return [e for e in self._entries if e.kind == "FEE" and e.value_date == day]

    # ------------------------------------------------------------- views

    def closing_balance(self, account: str, day: Day) -> Money:
        """Every entry with value_date <= day, whenever it was booked."""
        total = Money.zero(self._accounts[account])
        for entry in self._entries:
            if entry.account == account and entry.value_date <= day:
                total = total + entry.amount
        return total

    def hold_state(self, auth_id: str, day: Day | None = None) -> HoldState | None:
        state: HoldState | None = None
        for event in self._holds:
            if event.auth_id == auth_id and (day is None or event.day <= day):
                state = event.state
        return state

    def active_holds(self, account: str, day: Day | None = None) -> Money:
        total = Money.zero(self._accounts[account])
        seen: set[str] = {
            e.auth_id
            for e in self._holds
            if e.account == account and (day is None or e.day <= day)
        }
        for auth_id in seen:
            if self.hold_state(auth_id, day) == "ACTIVE":
                opened = next(e for e in self._holds if e.auth_id == auth_id)
                total = total + opened.amount
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
                self._post(
                    event.event_id,
                    event.account,
                    -event.amount,
                    event.value_date,
                    event.booked_day,
                    "DEBIT",
                )
            case Authorization():
                self._on_authorization(event)
            case Settlement():
                self._on_settlement(event)
            case Reversal():
                self._on_reversal(event)

    def _on_credit(self, event: Credit) -> None:
        for i, part in enumerate(allocate(event.amount, event.instalments), start=1):
            note = (
                f"instalment {i}/{event.instalments}" if event.instalments > 1 else ""
            )
            self._post(
                event.event_id,
                event.account,
                part,
                event.value_date,
                event.booked_day,
                "CREDIT",
                note,
            )

    def _on_authorization(self, event: Authorization) -> None:
        projected = (
            self.available_balance(event.account, event.value_date) - event.amount
        )
        if projected.is_negative:
            self._holds.append(
                HoldEvent(
                    self._next_seq(),
                    event.auth_id,
                    event.account,
                    event.value_date,
                    "DECLINED",
                    event.amount,
                )
            )
            self._decide(
                event.event_id,
                event.booked_day,
                "DECLINED",
                f"available {self.available_balance(event.account, event.value_date)} "
                f"would fall to {projected}",
            )
            return
        self._holds.append(
            HoldEvent(
                self._next_seq(),
                event.auth_id,
                event.account,
                event.value_date,
                "ACTIVE",
                event.amount,
            )
        )
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
            self._post(
                event.event_id,
                event.account,
                -event.amount,
                event.value_date,
                event.booked_day,
                "SETTLEMENT",
                "unmatched: force post",
            )
            self._decide(
                event.event_id,
                event.booked_day,
                "FORCE_POSTED",
                f"no authorisation {event.auth_id} in the ledger",
            )
            return
        if state != "ACTIVE":
            self._decide(
                event.event_id,
                event.booked_day,
                "REJECTED",
                f"authorisation {event.auth_id} is already {state}",
            )
            return
        opened = next(e for e in self._holds if e.auth_id == event.auth_id)
        self._post(
            event.event_id,
            event.account,
            -event.amount,
            event.value_date,
            event.booked_day,
            "SETTLEMENT",
            f"settles {event.auth_id}",
        )
        self._holds.append(
            HoldEvent(
                self._next_seq(),
                event.auth_id,
                event.account,
                event.value_date,
                "SETTLED",
                event.amount,
            )
        )
        residual = opened.amount - event.amount
        reason = f"settled {event.amount} against hold {opened.amount}"
        if residual.is_positive:
            reason += f", residual {residual} released"
        self._decide(event.event_id, event.booked_day, "APPROVED", reason)

    def _on_reversal(self, event: Reversal) -> None:
        originals = [e for e in self._entries if e.event_id == event.reverses]
        if not originals:
            self._decide(
                event.event_id,
                event.booked_day,
                "REJECTED",
                f"nothing booked under {event.reverses}",
            )
            return
        if any(e.note == f"reverses {event.reverses}" for e in self._entries):
            self._decide(
                event.event_id,
                event.booked_day,
                "REJECTED",
                f"{event.reverses} is already reversed",
            )
            return
        for original in originals:
            self._post(
                event.event_id,
                original.account,
                -original.amount,
                event.value_date,
                event.booked_day,
                "REVERSAL",
                f"reverses {event.reverses}",
            )
        self._decide(
            event.event_id, event.booked_day, "REVERSED", f"contra of {event.reverses}"
        )

    # ------------------------------------------------------------- close

    def close_day(self, day: Day) -> list[Entry]:
        """Assess overdraft fees for this close. Returns the fees booked."""
        days: Iterable[Day] = (
            range(1, day + 1) if self._fee_policy is FeePolicy.RETROACTIVE else (day,)
        )
        booked: list[Entry] = []
        for account in self._accounts:
            # Ascending: a fee dated day D is itself an entry that drags
            # every later closing balance down, and may trigger the next fee.
            for candidate in days:
                fee = self._maybe_assess_fee(account, candidate, day)
                if fee is not None:
                    booked.append(fee)
        self.snapshots[day] = {
            account: self.closing_balance(account, day) for account in self._accounts
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
        if self._accounts[account] != OVERDRAFT_FEE.currency:
            raise UndefinedFeeCurrency(
                f"{account} is {self._accounts[account]} but the fee schedule "
                f"is written in {OVERDRAFT_FEE.currency}; no rate was given. "
                f"See AMBIGUITIES.md."
            )
        return self._post(
            account=account,
            event_id=f"FEE-{account}-D{value_date}",
            amount=-OVERDRAFT_FEE,
            value_date=value_date,
            booked_day=booked_day,
            kind="FEE",
            note="overdraft",
        )

    def capitalize_interest(self, last_day: Day) -> None:
        """Accrue daily on positive closing balances, credit once at the end.

        The accruals are apportioned to the capitalised total rather than
        rounded independently, so the daily figures we publish add up to the
        single credit the customer actually receives.
        """
        for account, currency in self._accounts.items():
            exact = [
                Fraction(max(self.closing_balance(account, day).minor, 0))
                * DAILY_INTEREST_RATE
                for day in range(1, last_day + 1)
            ]
            total = round_half_up(sum(exact, Fraction(0)))
            self._daily_accruals[account] = apportion(exact, total)
            if total:
                self._post(
                    event_id=f"INT-{account}",
                    account=account,
                    amount=Money(total, currency),
                    value_date=last_day,
                    booked_day=last_day,
                    kind="INTEREST",
                    note="capitalised accrual",
                )
        # Capitalisation is part of the last day's close, not something that
        # arrived after it. Without this the report calls the credit a
        # backdated restatement, which is a lie about how the money got there.
        if last_day in self.snapshots:
            self.snapshots[last_day] = {
                account: self.closing_balance(account, last_day)
                for account in self._accounts
            }
