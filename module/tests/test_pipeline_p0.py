
# tests/test_pipeline_p0.py

from decimal import Decimal

import pytest

from onepass.engine import CardType, DbPolicy, Merchant
from onepass.m1_generator_p0 import CategoryParameter
from onepass.m1_users_p0 import (
    BankCardTemplate,
    PopulationConfig,
)
from onepass.pipeline_p0 import run_pipeline_p0


def make_arguments():
    return dict(
        user_count=3,
        population_config=PopulationConfig(
            district_weights={"26440": 1},
            age_weights={"20-29": 1},
            bank_card_count_weights={1: 1},
            opening_account_won=300000,
            opening_db_charge_won=100000,
        ),
        bank_products=[
            BankCardTemplate(
                "BANK_A",
                CardType.DEBIT,
            ),
            BankCardTemplate(
                "BANK_B",
                CardType.CREDIT,
                credit_limit_won=300000,
            ),
        ],
        counts_by_month={
            "2026-06": 4,
            "2026-07": 3,
        },
        category_parameters=[
            CategoryParameter(
                "CAFE",
                Decimal("1"),
                1000,
                3000,
            ),
        ],
        merchants={
            "M001": Merchant(
                "M001", "CAFE", True, "LE_10B"
            ),
        },
        policy=DbPolicy(),
        seed=2026,
    )


def test_full_pipeline_runs_four_strategies():
    result = run_pipeline_p0(**make_arguments())

    assert result.user_count == 3
    assert result.transaction_count == 21
    assert len(result.population) == 3

    for user in result.population:
        assert len(user.simulation.months) == 2
        assert set(user.simulation.final_states) == {
            "A1", "A2", "A3", "B"
        }

    assert result.metrics
    assert result.comparisons


def test_population_aggregate_is_consistent():
    result = run_pipeline_p0(**make_arguments())

    june_b = next(
        row for row in result.metrics
        if row.group_type == "ALL"
        and row.month == "2026-06"
        and row.strategy_id == "B"
    )

    assert june_b.user_count == 3
    assert june_b.request_count == 12
    assert june_b.approved_count <= 12
    assert june_b.benefit_won >= 0


def test_pipeline_is_reproducible():
    first = run_pipeline_p0(**make_arguments())
    second = run_pipeline_p0(**make_arguments())

    # Do not compare wall-clock execution time.
    assert first.metrics == second.metrics
    assert first.comparisons == second.comparisons


def test_pipeline_exports_csv(tmp_path):
    args = make_arguments()
    args["output_dir"] = tmp_path

    result = run_pipeline_p0(**args)

    assert result.csv_paths is not None
    assert all(path.exists() for path in result.csv_paths)


def test_invalid_user_count_rejected():
    args = make_arguments()
    args["user_count"] = 0

    with pytest.raises(
        ValueError,
        match="INVALID_USER_COUNT",
    ):
        run_pipeline_p0(**args)
