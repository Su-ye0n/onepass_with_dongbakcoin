
"""NeonDB user / merchant / transaction statistics.

Read-only. No DB writes.
Outputs aggregated statistics only.
"""

import csv
import json
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from onepass.db_connection import connect_readonly


BASE = Path(__file__).resolve().parent
OUT = BASE / "neondb_stats"
OUT.mkdir(exist_ok=True)

load_dotenv(BASE / ".env")


QUERIES = {
    "table_counts": """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """,

    "users_by_profile": """
        SELECT
            COALESCE(age_band, 'UNKNOWN') AS age_band,
            COALESCE(district_code, 'UNKNOWN') AS district_code,
            COALESCE(spend_band, 'UNKNOWN') AS spend_band,
            COUNT(*) AS users,
            ROUND(AVG(estimated_monthly_spend_won), 0)
                AS avg_estimated_monthly_spend_won
        FROM public."USER"
        GROUP BY 1, 2, 3
        ORDER BY users DESC
    """,

    "users_by_dongbaek_level": """
        SELECT
            COALESCE(dongbaek_usage_level, 'UNKNOWN')
                AS dongbaek_usage_level,
            COUNT(*) AS users
        FROM public."USER"
        GROUP BY 1
        ORDER BY users DESC
    """,

    "card_ownership": """
        SELECT
            COALESCE(cp.card_type, 'UNKNOWN') AS card_type,
            COUNT(*) AS card_records,
            COUNT(DISTINCT uc.user_id) AS unique_users,
            COUNT(DISTINCT uc.product_id) AS products
        FROM public.user_card uc
        LEFT JOIN public.card_product cp
            ON uc.product_id = cp.product_id
        GROUP BY 1
        ORDER BY card_records DESC
    """,

    "cards_per_user": """
        SELECT
            card_count,
            COUNT(*) AS users
        FROM (
            SELECT
                u.user_id,
                COUNT(uc.user_card_id) AS card_count
            FROM public."USER" u
            LEFT JOIN public.user_card uc
                ON u.user_id = uc.user_id
            GROUP BY u.user_id
        ) x
        GROUP BY card_count
        ORDER BY card_count
    """,

    "merchant_industries": """
        SELECT
            industry_code,
            COALESCE(dongbaek_status, 'UNKNOWN')
                AS dongbaek_status,
            COUNT(*) AS merchants
        FROM public.merchant
        GROUP BY 1, 2
        ORDER BY merchants DESC
    """,

    "merchant_sales_bands": """
        SELECT
            COALESCE(sales_band, 'UNKNOWN') AS sales_band,
            COUNT(*) AS merchants
        FROM public.merchant
        GROUP BY 1
        ORDER BY merchants DESC
    """,

    "month_close_coverage": """
        SELECT
            cm.base_month,
            COUNT(*) AS card_records,
            COUNT(DISTINCT uc.user_id) AS users,
            SUM(cm.spend_total_won) AS total_card_spend_won,
            ROUND(AVG(cm.spend_total_won), 0)
                AS avg_card_spend_won
        FROM public.card_month_close cm
        JOIN public.user_card uc
            ON cm.user_card_id = uc.user_card_id
        GROUP BY cm.base_month
        ORDER BY cm.base_month
    """,

    "user_spend_segments": """
        WITH user_month AS (
            SELECT
                cm.base_month,
                uc.user_id,
                SUM(cm.spend_total_won) AS spend_won
            FROM public.card_month_close cm
            JOIN public.user_card uc
                ON cm.user_card_id = uc.user_card_id
            GROUP BY cm.base_month, uc.user_id
        )
        SELECT
            base_month,
            CASE
                WHEN spend_won = 0 THEN '00_ZERO'
                WHEN spend_won < 100000 THEN '01_UNDER_100K'
                WHEN spend_won < 300000 THEN '02_100K_300K'
                WHEN spend_won < 500000 THEN '03_300K_500K'
                WHEN spend_won < 1000000 THEN '04_500K_1M'
                ELSE '05_OVER_1M'
            END AS spend_segment,
            COUNT(*) AS users,
            SUM(spend_won) AS total_spend_won,
            ROUND(AVG(spend_won), 0) AS avg_spend_won
        FROM user_month
        GROUP BY 1, 2
        ORDER BY 1, 2
    """,

    "ledger_events": """
        SELECT
            COALESCE(event_type, 'UNKNOWN') AS event_type,
            COALESCE(bucket_type, 'UNKNOWN') AS bucket_type,
            COALESCE(approval_status, 'UNKNOWN')
                AS approval_status,
            COALESCE(source_mode, 'UNKNOWN') AS source_mode,
            COUNT(*) AS ledger_rows,
            COUNT(DISTINCT user_id) AS users,
            COUNT(DISTINCT tx_id) AS distinct_tx_ids,
            COUNT(*) FILTER (WHERE tx_id IS NULL)
                AS rows_without_tx_id,
            SUM(COALESCE(gross_purchase_won, 0))
                AS gross_purchase_field_sum,
            SUM(COALESCE(delta_won, 0))
                AS delta_field_sum,
            SUM(COALESCE(awarded_benefit_won, 0))
                AS awarded_benefit_field_sum
        FROM public.ledger
        GROUP BY 1, 2, 3, 4
        ORDER BY ledger_rows DESC
    """,

    "ledger_time_distribution": """
        SELECT
            LEFT(event_at::text, 7) AS event_month,
            event_type,
            COUNT(*) AS ledger_rows,
            COUNT(DISTINCT tx_id) AS distinct_tx_ids
        FROM public.ledger
        GROUP BY 1, 2
        ORDER BY 1, 2
    """,

    "ledger_data_quality": """
        SELECT
            COUNT(*) AS ledger_rows,
            COUNT(*) FILTER (WHERE tx_id IS NULL)
                AS missing_tx_id,
            COUNT(*) FILTER (WHERE merchant_id IS NULL)
                AS missing_merchant_id,
            COUNT(*) FILTER (WHERE user_card_id IS NULL)
                AS missing_user_card_id,
            COUNT(*) FILTER (
                WHERE gross_purchase_won IS NOT NULL
            ) AS rows_with_purchase_amount,
            COUNT(DISTINCT user_id) AS users_with_ledger
        FROM public.ledger
    """,
}


def save_csv(name, rows):
    if not rows:
        return

    path = OUT / f"{name}.csv"

    with path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=list(rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    report = {
        "source": "NeonDB public schema",
        "note": (
            "Card month close figures are snapshots. "
            "Ledger event rows are not automatically "
            "payment transactions."
        ),
        "statistics": {},
        "errors": {},
    }

    with connect_readonly() as conn:
        with conn.cursor() as cur:

            for name, query in QUERIES.items():
                print(f"\n=== {name} ===")

                try:
                    cur.execute(query)
                    rows = [
                        dict(row)
                        for row in cur.fetchall()
                    ]

                    report["statistics"][name] = rows
                    save_csv(name, rows)

                    for row in rows[:15]:
                        print(row)

                    if len(rows) > 15:
                        print(
                            f"... total {len(rows)} rows"
                        )

                except Exception as exc:
                    conn.rollback()
                    report["errors"][name] = str(exc)
                    print("ERROR:", exc)

    output = OUT / "summary.json"
    output.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print("\n=== COMPLETE ===")
    print("Output folder:", OUT)
    print("Failed queries:", len(report["errors"]))
    print("Summary:", output)


if __name__ == "__main__":
    main()
