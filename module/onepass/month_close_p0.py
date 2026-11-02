
# onepass/month_close_p0.py
"""P0 M2: Monthly performance closing and period transition.

This module does not modify engine.py or write to SQLite.

P0 assumption:
- Approved purchase amount counts toward card performance
  unless the caller provides an explicitly adjusted eligible amount.
- Credit outstanding balance is NOT automatically repaid.
- Wallet balances carry forward.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Sequence

from .engine import Card, State


def _parse_month(month: str) -> date:
    try:
        parsed = date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise ValueError(
            f"INVALID_MONTH: {month}"
        ) from exc

    if parsed.strftime("%Y-%m") != month:
        raise ValueError(f"INVALID_MONTH: {month}")

    return parsed


def _next_month(month: str) -> str:
    current = _parse_month(month)
    year = current.year + (current.month == 12)
    month_number = current.month % 12 + 1
    return f"{year:04d}-{month_number:02d}"


@dataclass
class MonthlySpendTracker:
    """Approved performance-eligible spending by user_card_id."""

    month: str
    approved_won: dict[str, int] = field(
        default_factory=dict
    )
    eligible_perf_won: dict[str, int] = field(
        default_factory=dict
    )
    excluded_perf_won: dict[str, int] = field(
        default_factory=dict
    )
    recorded_requests: set[str] = field(
        default_factory=set
    )

    def __post_init__(self) -> None:
        _parse_month(self.month)

    def record(
        self,
        *,
        request_id: str,
        user_card_id: str,
        amount_won: int,
        eligible_won: int | None = None,
    ) -> None:
        """Record one APPROVED purchase, exactly once.

        Call this only after process() returned approved=True.
        """

        if request_id in self.recorded_requests:
            raise ValueError(
                f"DUPLICATE_MONTHLY_RECORD: {request_id}"
            )

        if not user_card_id:
            raise ValueError("MISSING_USER_CARD_ID")

        if amount_won <= 0:
            raise ValueError("INVALID_APPROVED_AMOUNT")

        if eligible_won is None:
            eligible_won = amount_won

        if not 0 <= eligible_won <= amount_won:
            raise ValueError("INVALID_ELIGIBLE_PERFORMANCE")

        self.approved_won[user_card_id] = (
            self.approved_won.get(user_card_id, 0)
            + amount_won
        )
        self.eligible_perf_won[user_card_id] = (
            self.eligible_perf_won.get(user_card_id, 0)
            + eligible_won
        )
        self.excluded_perf_won[user_card_id] = (
            self.excluded_perf_won.get(user_card_id, 0)
            + amount_won - eligible_won
        )
        self.recorded_requests.add(request_id)


@dataclass(frozen=True)
class CardMonthClose:
    user_card_id: str
    close_month: str
    gross_spend_won: int
    eligible_perf_won: int
    excluded_perf_won: int


@dataclass
class MonthTransition:
    next_month: str
    cards: list[Card]
    state: State
    closes: list[CardMonthClose]


def close_month(
    *,
    month: str,
    cards: Sequence[Card],
    state: State,
    tracker: MonthlySpendTracker,
) -> MonthTransition:
    """Return independent next-month cards and state.

    Does not mutate input cards, state, or tracker.
    """

    _parse_month(month)

    if tracker.month != month:
        raise ValueError(
            f"MONTH_MISMATCH: {month} != {tracker.month}"
        )

    card_ids = [card.id for card in cards]

    if len(card_ids) != len(set(card_ids)):
        raise ValueError("DUPLICATE_CARD_ID")

    unknown = (
        set(tracker.approved_won)
        | set(tracker.eligible_perf_won)
        | set(tracker.excluded_perf_won)
    ) - set(card_ids)

    if unknown:
        raise ValueError(
            f"UNKNOWN_PERFORMANCE_CARD: {sorted(unknown)}"
        )

    next_cards = []
    closes = []

    for card in cards:
        gross = tracker.approved_won.get(card.id, 0)
        eligible = tracker.eligible_perf_won.get(card.id, 0)
        excluded = tracker.excluded_perf_won.get(card.id, 0)

        if gross != eligible + excluded:
            raise ValueError(
                f"PERFORMANCE_SUM_MISMATCH: {card.id}"
            )

        # Card is frozen; create a new next-month instance.
        next_cards.append(
            replace(card, prev_month_perf=eligible)
        )

        closes.append(
            CardMonthClose(
                user_card_id=card.id,
                close_month=month,
                gross_spend_won=gross,
                eligible_perf_won=eligible,
                excluded_perf_won=excluded,
            )
        )

    next_state = deepcopy(state)

    # Benefit caps restart in the next month.
    next_state.benefit_used.clear()

    # Legacy single-wallet monthly cap.
    next_state.db_month_applied = 0

    # Current ERD multi-wallet structure.
    for wallet in next_state.wallets.values():
        wallet.month_applied = 0

    # Keep accounts, wallet balances, credit outstanding,
    # ledger, and processed request IDs unchanged.
    return MonthTransition(
        next_month=_next_month(month),
        cards=next_cards,
        state=next_state,
        closes=closes,
    )
