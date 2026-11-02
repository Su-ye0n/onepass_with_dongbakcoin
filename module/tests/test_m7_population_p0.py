
# tests/test_m7_population_p0.py

import csv
from copy import deepcopy
from dataclasses import replace

import pytest

from onepass.engine import (
    Card, CardType, DbPolicy, Merchant,
    Request, State, WalletBalance,
)
from onepass.m1_generator_p0 import SyntheticProfile
from onepass.replay_p0 import ReplayItem
from onepass.multimonth_p0 import run_multimonth_p0
from onepass.m7_population_p0 import (
    PopulationResult,
    aggregate_population_p0,
    export_population_csv,
)


def make_user(uid, district, age):
    profile = SyntheticProfile(
        user_id=uid,
        district_code=district,
        age_band=age,
    )

    cards = [
        Card(
            "BANK", CardType.DEBIT,
            account_id="ACCOUNT",
        ),
        Card(
            "DB", CardType.DONGBAEK_CHECK,
            account_id="ACCOUNT",
            wallet_id="WALLET",
        ),
    ]

    state = State(
        accounts={"ACCOUNT": 50000},
        wallets={
            "WALLET": WalletBalance(charge=30000)
        },
    )

    merchant = Merchant(
        "M001", "CAFE", True, "LE_10B"
    )

    item = ReplayItem(
        event_at="2026-06-15T12:00:00+09:00",
        event_seq=1,
        request=Request(
            f"{uid}_R1", "M001", 10000
        ),
    )

    simulation = run_multimonth_p0(
        monthly_items={
            "2026-06": [item],
            "2026-07": [],
        },
        merchants={"M001": merchant},
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
        default_card_id="BANK",
    )

    return PopulationResult(profile, simulation)


@pytest.fixture
def population():
    return [
        make_user("U001", "DIST_A", "20-29"),
        make_user("U002", "DIST_B", "30-39"),
    ]


def find_metric(metrics, month, strategy, group="ALL", value="ALL"):
    return next(
        row for row in metrics
        if row.month == month
        and row.strategy_id == strategy
        and row.group_type == group
        and row.group_value == value
    )


def find_comparison(comparisons, month, baseline):
    return next(
        row for row in comparisons
        if row.month == month
        and row.group_type == "ALL"
        and row.baseline_id == baseline
    )


def test_population_total_benefits(population):
    metrics, comparisons = aggregate_population_p0(
        population
    )

    a2 = find_metric(metrics, "2026-06", "A2")
    b = find_metric(metrics, "2026-06", "B")

    assert a2.user_count == 2
    assert a2.request_count == 2
    assert a2.approved_count == 2
    assert a2.benefit_won == 0

    assert b.user_count == 2
    assert b.request_count == 2
    assert b.approved_count == 2
    assert b.approved_won == 20000
    assert b.benefit_won == 2000

    comparison = find_comparison(
        comparisons, "2026-06", "A2"
    )

    assert comparison.benefit_delta_won == 2000
    assert comparison.same_approval_benefit_delta_won == 2000
    assert comparison.approved_delta_won == 0


def test_region_and_age_groups(population):
    metrics, _ = aggregate_population_p0(population)

    district = find_metric(
        metrics, "2026-06", "B",
        group="DISTRICT", value="DIST_A"
    )

    age = find_metric(
        metrics, "2026-06", "B",
        group="AGE", value="30-39"
    )

    assert district.user_count == 1
    assert district.benefit_won == 1000

    assert age.user_count == 1
    assert age.benefit_won == 1000


def test_empty_month_keeps_zero_rows(population):
    metrics, comparisons = aggregate_population_p0(
        population
    )

    july = find_metric(metrics, "2026-07", "B")

    assert july.user_count == 2
    assert july.request_count == 0
    assert july.approved_count == 0
    assert july.benefit_won == 0

    comparison = find_comparison(
        comparisons, "2026-07", "A2"
    )

    assert comparison.benefit_delta_won == 0


def test_duplicate_user_rejected(population):
    duplicate = [population[0], population[0]]

    with pytest.raises(
        ValueError,
        match="DUPLICATE_OR_EMPTY_USER",
    ):
        aggregate_population_p0(duplicate)


def test_cohort_month_mismatch_rejected(population):
    changed = deepcopy(population[1])
    changed.simulation.months.pop()

    with pytest.raises(
        ValueError,
        match="MONTH_COHORT_MISMATCH",
    ):
        aggregate_population_p0(
            [population[0], changed]
        )


def test_csv_export(population, tmp_path):
    metrics, comparisons = aggregate_population_p0(
        population
    )

    metric_path, comparison_path = export_population_csv(
        metrics=metrics,
        comparisons=comparisons,
        output_dir=tmp_path,
    )

    assert metric_path.exists()
    assert comparison_path.exists()

    with metric_path.open(
        encoding="utf-8-sig", newline=""
    ) as file:
        metric_rows = list(csv.DictReader(file))

    with comparison_path.open(
        encoding="utf-8-sig", newline=""
    ) as file:
        comparison_rows = list(csv.DictReader(file))

    assert metric_rows
    assert comparison_rows

    b_june = next(
        row for row in metric_rows
        if row["group_type"] == "ALL"
        and row["month"] == "2026-06"
        and row["strategy_id"] == "B"
    )

    assert b_june["benefit_won"] == "2000"
    assert b_june["approved_won"] == "20000"
