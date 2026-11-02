
# onepass/m7_p0.py
"""P0 M7: strategy-level benefit and approval comparison.

Consumes M6 ReplayResult objects, never modifies financial state.

Benefits are simulated immediate rewards, not real savings or
tax deductions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from .replay_p0 import ReplayItem, ReplayResult


@dataclass(frozen=True)
class StrategyMetrics:
    strategy_id: str
    request_count: int
    approved_count: int
    declined_count: int
    requested_won: int
    approved_won: int
    benefit_won: int
    approval_rate: Decimal
    benefit_rate: Decimal


@dataclass(frozen=True)
class StrategyComparison:
    baseline_id: str
    onepass_id: str
    benefit_delta_won: int
    approved_delta_won: int
    approved_count_delta: int
    same_approval_benefit_delta_won: int
    onepass_only_approved_count: int
    baseline_only_approved_count: int
    differing_approval_count: int


def summarize_strategies(
    *,
    items: Sequence[ReplayItem],
    results: Mapping[str, ReplayResult],
) -> dict[str, StrategyMetrics]:
    if not items:
        raise ValueError("EMPTY_TRANSACTIONS")

    request_ids = [item.request.id for item in items]
    if len(request_ids) != len(set(request_ids)):
        raise ValueError("DUPLICATE_REQUEST_ID")

    if not results:
        raise ValueError("EMPTY_RESULTS")

    requested_won = sum(
        item.request.amount for item in items
    )
    summaries = {}

    for strategy_id, replay in results.items():
        if replay.strategy_id != strategy_id:
            raise ValueError(
                f"STRATEGY_ID_MISMATCH: {strategy_id}"
            )

        if len(replay.decisions) != len(items):
            raise ValueError(
                f"DECISION_COUNT_MISMATCH: {strategy_id}"
            )

        approved_count = 0
        approved_won = 0
        benefit_won = 0

        for item, decision in zip(
            items, replay.decisions, strict=True
        ):
            if decision.approved:
                if decision.selected_card_id is None:
                    raise ValueError(
                        f"APPROVED_WITHOUT_CARD: {strategy_id}"
                    )
                if decision.benefit_won < 0:
                    raise ValueError(
                        f"NEGATIVE_BENEFIT: {strategy_id}"
                    )

                approved_count += 1
                approved_won += item.request.amount
                benefit_won += decision.benefit_won
            elif decision.benefit_won != 0:
                raise ValueError(
                    f"DECLINED_WITH_BENEFIT: {strategy_id}"
                )

        count = len(items)

        summaries[strategy_id] = StrategyMetrics(
            strategy_id=strategy_id,
            request_count=count,
            approved_count=approved_count,
            declined_count=count - approved_count,
            requested_won=requested_won,
            approved_won=approved_won,
            benefit_won=benefit_won,
            approval_rate=(
                Decimal(approved_count) / Decimal(count)
            ),
            benefit_rate=(
                Decimal(benefit_won) / Decimal(approved_won)
                if approved_won else Decimal(0)
            ),
        )

    return summaries


def compare_to_onepass(
    *,
    items: Sequence[ReplayItem],
    results: Mapping[str, ReplayResult],
    onepass_id: str = "B",
) -> dict[str, StrategyComparison]:
    # Validate result length and basic consistency first.
    summaries = summarize_strategies(
        items=items,
        results=results,
    )

    if onepass_id not in results:
        raise ValueError(
            f"ONEPASS_NOT_FOUND: {onepass_id}"
        )

    onepass = results[onepass_id]
    output = {}

    for baseline_id, baseline in results.items():
        if baseline_id == onepass_id:
            continue

        both_approved_delta = 0
        onepass_only = 0
        baseline_only = 0

        for baseline_decision, b_decision in zip(
            baseline.decisions,
            onepass.decisions,
            strict=True,
        ):
            if (
                baseline_decision.approved
                and b_decision.approved
            ):
                both_approved_delta += (
                    b_decision.benefit_won
                    - baseline_decision.benefit_won
                )
            elif (
                b_decision.approved
                and not baseline_decision.approved
            ):
                onepass_only += 1
            elif (
                baseline_decision.approved
                and not b_decision.approved
            ):
                baseline_only += 1

        base_metric = summaries[baseline_id]
        b_metric = summaries[onepass_id]

        output[baseline_id] = StrategyComparison(
            baseline_id=baseline_id,
            onepass_id=onepass_id,
            benefit_delta_won=(
                b_metric.benefit_won
                - base_metric.benefit_won
            ),
            approved_delta_won=(
                b_metric.approved_won
                - base_metric.approved_won
            ),
            approved_count_delta=(
                b_metric.approved_count
                - base_metric.approved_count
            ),
            same_approval_benefit_delta_won=(
                both_approved_delta
            ),
            onepass_only_approved_count=onepass_only,
            baseline_only_approved_count=baseline_only,
            differing_approval_count=(
                onepass_only + baseline_only
            ),
        )

    return output


def rows_for_export(
    summaries: Mapping[str, StrategyMetrics],
) -> list[dict]:
    """Convert summaries to standard CSV-compatible dictionaries."""
    return [
        {
            **asdict(summary),
            "approval_rate": str(summary.approval_rate),
            "benefit_rate": str(summary.benefit_rate),
        }
        for summary in summaries.values()
    ]
