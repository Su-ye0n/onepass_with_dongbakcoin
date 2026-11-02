
# onepass/pipeline_p0.py
"""P0-20: End-to-end synthetic OnePass simulation.

M1 users -> M1 transactions -> A1/A2/A3/B multi-month replay
-> M7 population aggregation -> optional CSV export.

All parameters are synthetic until validated source data
is supplied. No payment network or SQLite writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Mapping, Sequence

from .engine import DbPolicy, Merchant
from .m1_generator_p0 import (
    CategoryParameter,
    generate_months_p0,
)
from .m1_users_p0 import (
    BankCardTemplate,
    PopulationConfig,
    generate_population_p0,
)
from .m7_population_p0 import (
    PopulationComparison,
    PopulationMetric,
    PopulationResult,
    aggregate_population_p0,
    export_population_csv,
)


@dataclass
class PipelineResult:
    population: list[PopulationResult]
    metrics: list[PopulationMetric]
    comparisons: list[PopulationComparison]
    user_count: int
    transaction_count: int
    elapsed_seconds: float
    transactions_per_second: float
    csv_paths: tuple[Path, Path] | None


def run_pipeline_p0(
    *,
    user_count: int,
    population_config: PopulationConfig,
    bank_products: Sequence[BankCardTemplate],
    counts_by_month: Mapping[str, int],
    category_parameters: Sequence[CategoryParameter],
    merchants: Mapping[str, Merchant],
    policy: DbPolicy,
    seed: int = 2026,
    output_dir: str | Path | None = None,
) -> PipelineResult:
    """Run the complete P0 pipeline for synthetic users.

    Each user's A1 weights are provisional equal weights.
    Each strategy replays the same user transactions from
    the same opening state.

    Timing includes generation, replay, and aggregation.
    CSV I/O is excluded from elapsed_seconds.
    """

    if not counts_by_month:
        raise ValueError("NO_MONTHS")

    if not merchants:
        raise ValueError("NO_MERCHANTS")

    start = perf_counter()

    users = generate_population_p0(
        user_count=user_count,
        config=population_config,
        bank_products=bank_products,
        seed=seed,
    )

    population_results = []
    transaction_count = 0

    # Import here to keep the pipeline orchestration explicit.
    from .multimonth_p0 import run_multimonth_p0

    for user in users:
        monthly_items = generate_months_p0(
            profile=user.profile,
            counts_by_month=counts_by_month,
            category_parameters=category_parameters,
            merchants=merchants,
            seed=seed,
        )

        transaction_count += sum(
            len(items) for items in monthly_items.values()
        )

        simulation = run_multimonth_p0(
            monthly_items=monthly_items,
            merchants=merchants,
            cards=user.cards,
            initial_state=user.state,
            policy=policy,
            default_card_id=user.default_card_id,
            a1_weights=user.a1_weights,
            a1_seed=seed,
        )

        population_results.append(
            PopulationResult(
                profile=user.profile,
                simulation=simulation,
            )
        )

    metrics, comparisons = aggregate_population_p0(
        population_results
    )

    elapsed = perf_counter() - start

    paths = None

    if output_dir is not None:
        paths = export_population_csv(
            metrics=metrics,
            comparisons=comparisons,
            output_dir=output_dir,
        )

    return PipelineResult(
        population=population_results,
        metrics=metrics,
        comparisons=comparisons,
        user_count=len(users),
        transaction_count=transaction_count,
        elapsed_seconds=elapsed,
        transactions_per_second=(
            transaction_count / elapsed
            if elapsed > 0 else 0.0
        ),
        csv_paths=paths,
    )
