
# onepass/multimonth_p0.py
"""P0-12: independent multi-month A2/A3/B simulation.

- Same transactions for every strategy
- Independent financial state and card performance
- Monthly close after each month
- Explicit empty-month support
- No SQLite writes
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from .engine import ( Card, DbPolicy, Decision, Merchant,State, process,)
from .m6_p0 import (_direct_request,_onecard_request, _select_dongbaek_first,)
from .m7_p0 import (StrategyComparison,StrategyMetrics,compare_to_onepass,summarize_strategies,)
from .month_close_p0 import (CardMonthClose, MonthlySpendTracker,close_month,)
from .replay_p0 import (ReplayItem, ReplayResult, _validate_items,)

from .a1_p0 import select_a1_card, validate_a1_weights

@dataclass
class StrategyRuntime:
    cards: list[Card]
    state: State


@dataclass
class MonthlyRun:
    month: str
    results: dict[str, ReplayResult]
    metrics: dict[str, StrategyMetrics]
    comparisons: dict[str, StrategyComparison]
    closes: dict[str, list[CardMonthClose]]


@dataclass
class MultiMonthResult:
    months: list[MonthlyRun] = field(default_factory=list)
    final_cards: dict[str, list[Card]] = field(default_factory=dict)
    final_states: dict[str, State] = field(default_factory=dict)


def _month_index(month: str) -> int:
    try:
        dt = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError(f"INVALID_MONTH: {month}") from exc

    if dt.strftime("%Y-%m") != month:
        raise ValueError(f"INVALID_MONTH: {month}")

    return dt.year * 12 + dt.month


def _validate_months(
    monthly_items: Mapping[str, Sequence[ReplayItem]],
) -> None:
    if not monthly_items:
        raise ValueError("NO_MONTHS")

    months = list(monthly_items)
    indexes = [_month_index(m) for m in months]

    if any(b != a + 1 for a, b in zip(indexes, indexes[1:])):
        raise ValueError(
            "MONTHS_MUST_BE_CONTIGUOUS_AND_ORDERED"
        )

    seen_requests: set[str] = set()

    for month, items in monthly_items.items():
        if not items:
            # An explicitly provided empty month is allowed.
            continue

        # Reuse the original single-month validation.
        _validate_items({month: items})

        for item in items:
            dt = datetime.fromisoformat(item.event_at)

            # P0 uses Korean local transaction timestamps.
            if dt.utcoffset() != timedelta(hours=9):
                raise ValueError(
                    f"EXPECTED_KST_OFFSET: {item.event_at}"
                )

            if dt.strftime("%Y-%m") != month:
                raise ValueError(
                    f"TRANSACTION_MONTH_MISMATCH: {month}"
                )

            rid = item.request.id

            if rid in seen_requests:
                raise ValueError(
                    f"DUPLICATE_CROSS_MONTH_REQUEST: {rid}"
                )

            seen_requests.add(rid)


def run_multimonth_p0(
    *,
    monthly_items: Mapping[str, Sequence[ReplayItem]],
    merchants: Mapping[str, Merchant],
    cards: Sequence[Card],
    initial_state: State,
    policy: DbPolicy,
    default_card_id: str,
    a1_weights: Mapping[str, object] | None = None,
    a1_seed: int = 2026,
) -> MultiMonthResult:
    """Run A2, A3 and B over consecutive calendar months."""

    _validate_months(monthly_items)

    card_ids = [c.id for c in cards]

    if len(card_ids) != len(set(card_ids)):
        raise ValueError("DUPLICATE_CARD_ID")

    if default_card_id not in card_ids:
        raise ValueError(
            f"DEFAULT_CARD_NOT_FOUND: {default_card_id}"
        )

    dongbaek_cards = [
        c for c in cards
        if c.type.value == "DONGBAEK_CHECK"
        and c.active and not c.lost and not c.expired
    ]

    if len(dongbaek_cards) > 1:
        raise ValueError(
            "MULTIPLE_DONGBAEK_CARDS_NOT_ALLOWED"
        )

    # Validate all merchants before any transaction runs.
    for items in monthly_items.values():
        for item in items:
            if item.request.merchant_id not in merchants:
                raise ValueError(
                    f"UNKNOWN_MERCHANT: {item.request.merchant_id}"
                )

    
    if a1_weights is not None:
        validate_a1_weights(cards, a1_weights)

    strategies = (
        ("A1", "A2", "A3", "B")
        if a1_weights is not None
        else ("A2", "A3", "B")
    )

    runtimes = {
        name: StrategyRuntime(
            cards=deepcopy(list(cards)),
            state=deepcopy(initial_state),
        )
        for name in strategies
    }

    output = MultiMonthResult()

    for month, items in monthly_items.items():
        month_results = {}
        month_closes = {}

        for strategy_id in strategies:
            runtime = runtimes[strategy_id]
            tracker = MonthlySpendTracker(month)
            decisions: list[Decision] = []

            for item in items:
                original = item.request
                merchant = merchants[original.merchant_id]

                
                if strategy_id == "A1":
                    card_id = select_a1_card(
                        request_id=original.id,
                        cards=runtime.cards,
                        weights=a1_weights,
                        seed=a1_seed,
                    )
                    request = _direct_request(
                        original, card_id
                    )

                elif strategy_id == "A2":
                    request = _direct_request(
                        original, default_card_id
                    )

                elif strategy_id == "A3":
                    card_id = _select_dongbaek_first(
                        original=original,
                        merchant=merchant,
                        cards=runtime.cards,
                        state=runtime.state,
                        policy=policy,
                        default_card_id=default_card_id,
                    )
                    request = _direct_request(
                        original, card_id
                    )

                else:
                    request = _onecard_request(original)

                decision = process(
                    request,
                    merchant,
                    runtime.cards,
                    runtime.state,
                    policy,
                )
                decisions.append(decision)

                if decision.approved:
                    if decision.selected_card_id is None:
                        raise ValueError(
                            "APPROVED_WITHOUT_CARD"
                        )

                    # P0 assumption: all approved spend is
                    # performance-eligible unless adjusted later.
                    tracker.record(
                        request_id=original.id,
                        user_card_id=decision.selected_card_id,
                        amount_won=original.amount,
                    )

            # Snapshot the month-end state BEFORE monthly reset.
            month_results[strategy_id] = ReplayResult(
                strategy_id=strategy_id,
                decisions=decisions,
                final_state=deepcopy(runtime.state),
            )

            transition = close_month(
                month=month,
                cards=runtime.cards,
                state=runtime.state,
                tracker=tracker,
            )

            month_closes[strategy_id] = transition.closes

            # Only this strategy receives its own next-month state.
            runtime.cards = transition.cards
            runtime.state = transition.state

        if items:
            metrics = summarize_strategies(
                items=items,
                results=month_results,
            )
            comparisons = compare_to_onepass(
                items=items,
                results=month_results,
            )
        else:
            # M7 currently rejects empty transaction lists.
            metrics = {}
            comparisons = {}

        output.months.append(
            MonthlyRun(
                month=month,
                results=month_results,
                metrics=metrics,
                comparisons=comparisons,
                closes=month_closes,
            )
        )

    output.final_cards = {
        name: deepcopy(runtime.cards)
        for name, runtime in runtimes.items()
    }
    output.final_states = {
        name: deepcopy(runtime.state)
        for name, runtime in runtimes.items()
    }

    return output
