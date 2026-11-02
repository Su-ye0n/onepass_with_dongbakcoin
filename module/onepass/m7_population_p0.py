
# onepass/m7_population_p0.py
"""P0-19: Aggregate multi-user OnePass A/B simulation results.

- Does not run the payment engine
- Does not mutate financial states
- Uses summed counts and amounts, not averages of user rates
- Rejects incomplete or incompatible strategy comparisons
- Exports standard CSV files
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .m1_generator_p0 import SyntheticProfile
from .multimonth_p0 import MultiMonthResult


@dataclass(frozen=True)
class PopulationResult:
    profile: SyntheticProfile
    simulation: MultiMonthResult


@dataclass(frozen=True)
class PopulationMetric:
    group_type: str
    group_value: str
    month: str
    strategy_id: str
    user_count: int
    request_count: int
    approved_count: int
    requested_won: int
    approved_won: int
    benefit_won: int
    approval_rate: Decimal
    benefit_rate: Decimal


@dataclass(frozen=True)
class PopulationComparison:
    group_type: str
    group_value: str
    month: str
    baseline_id: str
    onepass_id: str
    user_count: int
    benefit_delta_won: int
    approved_delta_won: int
    same_approval_benefit_delta_won: int
    onepass_only_approved_count: int
    baseline_only_approved_count: int


def _groups(profile: SyntheticProfile):
    return (
        ("ALL", "ALL"),
        ("DISTRICT", profile.district_code),
        ("AGE", profile.age_band),
    )


def aggregate_population_p0(
    population: Sequence[PopulationResult],
) -> tuple[
    list[PopulationMetric],
    list[PopulationComparison],
]:
    """Aggregate full-cohort results for each calendar month.

    All users must have the same ordered months and strategies.
    Only nonempty months are aggregated; an explicitly empty
    month is represented as zero metrics and zero deltas.
    """

    if not population:
        raise ValueError("EMPTY_POPULATION")

    seen_users = set()
    expected_months = None
    expected_strategies = None

    metric_buckets = {}
    comparison_buckets = {}

    for member in population:
        profile = member.profile
        simulation = member.simulation
        uid = profile.user_id

        if not uid or uid in seen_users:
            raise ValueError(f"DUPLICATE_OR_EMPTY_USER: {uid}")

        seen_users.add(uid)

        months = [run.month for run in simulation.months]

        if not months or len(months) != len(set(months)):
            raise ValueError(f"INVALID_USER_MONTHS: {uid}")

        if expected_months is None:
            expected_months = months
        elif months != expected_months:
            raise ValueError(f"MONTH_COHORT_MISMATCH: {uid}")

        for monthly in simulation.months:
            strategies = set(monthly.results)

            if "B" not in strategies:
                raise ValueError(f"MISSING_ONEPASS: {uid}")

            if expected_strategies is None:
                expected_strategies = strategies
            elif strategies != expected_strategies:
                raise ValueError(
                    f"STRATEGY_COHORT_MISMATCH: {uid}"
                )

            baselines = strategies - {"B"}

            if monthly.metrics:
                if set(monthly.metrics) != strategies:
                    raise ValueError(
                        f"INCOMPLETE_METRICS: {uid}/{monthly.month}"
                    )

                if set(monthly.comparisons) != baselines:
                    raise ValueError(
                        f"INCOMPLETE_COMPARISONS: "
                        f"{uid}/{monthly.month}"
                    )

            elif monthly.comparisons:
                raise ValueError(
                    f"COMPARISONS_WITHOUT_METRICS: "
                    f"{uid}/{monthly.month}"
                )

            # Empty months still contribute zero-valued rows.
            for group_type, group_value in _groups(profile):
                for strategy_id in sorted(strategies):
                    key = (
                        group_type,
                        group_value,
                        monthly.month,
                        strategy_id,
                    )

                    bucket = metric_buckets.setdefault(
                        key,
                        {
                            "users": set(),
                            "requests": 0,
                            "approved": 0,
                            "requested_won": 0,
                            "approved_won": 0,
                            "benefit_won": 0,
                        },
                    )

                    bucket["users"].add(uid)
                    metric = monthly.metrics.get(strategy_id)

                    if metric is not None:
                        bucket["requests"] += metric.request_count
                        bucket["approved"] += metric.approved_count
                        bucket["requested_won"] += metric.requested_won
                        bucket["approved_won"] += metric.approved_won
                        bucket["benefit_won"] += metric.benefit_won

                for baseline_id in sorted(baselines):
                    key = (
                        group_type,
                        group_value,
                        monthly.month,
                        baseline_id,
                    )

                    bucket = comparison_buckets.setdefault(
                        key,
                        {
                            "users": set(),
                            "benefit_delta": 0,
                            "approved_delta": 0,
                            "same_approval_delta": 0,
                            "b_only": 0,
                            "baseline_only": 0,
                        },
                    )

                    bucket["users"].add(uid)
                    comparison = monthly.comparisons.get(baseline_id)

                    if comparison is not None:
                        bucket["benefit_delta"] += (
                            comparison.benefit_delta_won
                        )
                        bucket["approved_delta"] += (
                            comparison.approved_delta_won
                        )
                        bucket["same_approval_delta"] += (
                            comparison.same_approval_benefit_delta_won
                        )
                        bucket["b_only"] += (
                            comparison.onepass_only_approved_count
                        )
                        bucket["baseline_only"] += (
                            comparison.baseline_only_approved_count
                        )

    metrics = []

    for key, b in sorted(metric_buckets.items()):
        group_type, group_value, month, strategy = key

        metrics.append(
            PopulationMetric(
                group_type=group_type,
                group_value=group_value,
                month=month,
                strategy_id=strategy,
                user_count=len(b["users"]),
                request_count=b["requests"],
                approved_count=b["approved"],
                requested_won=b["requested_won"],
                approved_won=b["approved_won"],
                benefit_won=b["benefit_won"],
                approval_rate=(
                    Decimal(b["approved"])
                    / Decimal(b["requests"])
                    if b["requests"] else Decimal(0)
                ),
                benefit_rate=(
                    Decimal(b["benefit_won"])
                    / Decimal(b["approved_won"])
                    if b["approved_won"] else Decimal(0)
                ),
            )
        )

    comparisons = []

    for key, b in sorted(comparison_buckets.items()):
        group_type, group_value, month, baseline = key

        comparisons.append(
            PopulationComparison(
                group_type=group_type,
                group_value=group_value,
                month=month,
                baseline_id=baseline,
                onepass_id="B",
                user_count=len(b["users"]),
                benefit_delta_won=b["benefit_delta"],
                approved_delta_won=b["approved_delta"],
                same_approval_benefit_delta_won=(
                    b["same_approval_delta"]
                ),
                onepass_only_approved_count=b["b_only"],
                baseline_only_approved_count=b["baseline_only"],
            )
        )

    return metrics, comparisons


def export_population_csv(
    *,
    metrics: Sequence[PopulationMetric],
    comparisons: Sequence[PopulationComparison],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Export aggregated metrics and comparisons as UTF-8 CSV."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    metrics_path = directory / "population_metrics.csv"
    comparisons_path = directory / "population_comparisons.csv"

    def write(path, records, fields):
        with path.open(
            "w", encoding="utf-8-sig", newline=""
        ) as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()

            for record in records:
                writer.writerow({
                    field: str(getattr(record, field))
                    for field in fields
                })

    metric_fields = list(PopulationMetric.__dataclass_fields__)
    comparison_fields = list(
        PopulationComparison.__dataclass_fields__
    )

    write(metrics_path, metrics, metric_fields)
    write(comparisons_path, comparisons, comparison_fields)

    return metrics_path, comparisons_path
