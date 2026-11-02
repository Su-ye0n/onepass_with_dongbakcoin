
# run_p0.py
"""Run a synthetic P0 benchmark.

Example:
    python run_p0.py --users 100 --transactions 20
"""

import argparse
from decimal import Decimal

from onepass.engine import CardType, DbPolicy, Merchant
from onepass.m1_generator_p0 import CategoryParameter
from onepass.m1_users_p0 import (
    BankCardTemplate,
    PopulationConfig,
)
from onepass.pipeline_p0 import run_pipeline_p0
import tracemalloc

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument(
        "--transactions", type=int, default=10
    )
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    tracemalloc.start()

    result = run_pipeline_p0(
        user_count=args.users,
        population_config=PopulationConfig(
            # Synthetic test weights, not official population data
            district_weights={
                "26440": 1,
                "26350": 1,
            },
            age_weights={
                "20-29": 1,
                "30-39": 1,
            },
            bank_card_count_weights={
                1: 1,
                2: 1,
            },
            opening_account_won=500000,
            opening_db_charge_won=200000,
        ),
        bank_products=[
            BankCardTemplate("CHECK_A", CardType.DEBIT),
            BankCardTemplate(
                "CREDIT_B",
                CardType.CREDIT,
                credit_limit_won=500000,
            ),
            BankCardTemplate("CHECK_C", CardType.DEBIT),
        ],
        counts_by_month={
            "2026-06": args.transactions,
            "2026-07": args.transactions,
        },
        category_parameters=[
            CategoryParameter(
                "CAFE", Decimal("0.6"),
                3000, 8000
            ),
            CategoryParameter(
                "MART", Decimal("0.4"),
                5000, 20000
            ),
        ],
        merchants={
            "CAFE_1": Merchant(
                "CAFE_1", "CAFE", True, "LE_10B"
            ),
            "MART_1": Merchant(
                "MART_1", "MART", False, "LE_10B"
            ),
        },
        policy=DbPolicy(),
        seed=args.seed,
        output_dir="outputs/p0",
    )
    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(
        f"Python current memory: "
        f"{current_bytes / 1024**2:.2f} MiB"
    )
    print(
        f"Python peak memory: "
        f"{peak_bytes / 1024**2:.2f} MiB"
    )

    print(f"Users: {result.user_count:,}")
    print(
        f"Original transactions: "
        f"{result.transaction_count:,}"
    )
    print(
        f"Elapsed (excluding CSV): "
        f"{result.elapsed_seconds:.4f} seconds"
    )
    print(
        f"Original transactions/second: "
        f"{result.transactions_per_second:,.1f}"
    )

    print("\nJune summary:")
    for row in result.metrics:
        if (
            row.group_type == "ALL"
            and row.month == "2026-06"
        ):
            print(
                f"{row.strategy_id}: "
                f"benefit={row.benefit_won:,} KRW, "
                f"approved={row.approved_count:,}/"
                f"{row.request_count:,}"
            )

    if result.csv_paths:
        print("\nCSV files:")
        for path in result.csv_paths:
            print(path)


if __name__ == "__main__":
    main()
