
from collections import Counter
from decimal import Decimal
from pathlib import Path
import csv
import json

from dotenv import load_dotenv
from onepass.db_connection import connect_readonly

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "neondb_stats"
OUT.mkdir(exist_ok=True)
load_dotenv(ROOT / ".env")


def get_tables(cur):
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    return [r["table_name"] for r in cur.fetchall()]


def get_columns(cur, table):
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
    """, (table,))
    return [dict(r) for r in cur.fetchall()]


def save_csv(name, rows):
    path = OUT / name
    if not rows:
        return

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main():
    with connect_readonly() as conn:
        with conn.cursor() as cur:
            tables = get_tables(cur)

            print("=== DATABASE TABLES ===")
            print(", ".join(tables))

            schema = {
                name: get_columns(cur, name)
                for name in tables
            }

            (OUT / "schema.json").write_text(
                json.dumps(schema, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            # 실제 사용자 테이블 이름 자동 탐색
            user_tables = [
                name for name in tables
                if name.lower() in ("user", "users", "customer", "customers")
            ]

            print("\n=== USER TABLE CANDIDATES ===")
            for name in user_tables:
                print(name, [c["column_name"] for c in schema[name]])

            if "user_card" not in tables or "card_month_close" not in tables:
                raise RuntimeError("REQUIRED_CARD_TABLES_NOT_FOUND")

            # 월별 카드 이용금액을 사용자 단위로 합산
            cur.execute("""
                SELECT
                    uc.user_id,
                    COUNT(DISTINCT uc.user_card_id)
                        AS owned_card_count,
                    COUNT(DISTINCT cm.user_card_id)
                        AS cards_with_month_close,
                    COALESCE(SUM(cm.spend_total_won), 0)
                        AS month_spend_won
                FROM public.user_card uc
                LEFT JOIN public.card_month_close cm
                  ON cm.user_card_id = uc.user_card_id
                 AND cm.base_month = %s
                GROUP BY uc.user_id
                ORDER BY uc.user_id
            """, ("2026-05",))

            users = [dict(r) for r in cur.fetchall()]

            for user in users:
                amount = user["month_spend_won"]

                if amount == 0:
                    segment = "00_ZERO"
                elif amount < 100000:
                    segment = "01_UNDER_100K"
                elif amount < 300000:
                    segment = "02_100K_300K"
                elif amount < 500000:
                    segment = "03_300K_500K"
                elif amount < 1000000:
                    segment = "04_500K_1M"
                else:
                    segment = "05_OVER_1M"

                user["spend_segment"] = segment
                user["multi_card_user"] = (
                    user["owned_card_count"] >= 2
                )

            counts = Counter(
                u["spend_segment"] for u in users
            )
            card_counts = Counter(
                u["owned_card_count"] for u in users
            )

            total_spend = sum(
                u["month_spend_won"] for u in users
            )

            summary = {
                "base_month": "2026-05",
                "users_with_card": len(users),
                "total_card_spend_won": int(total_spend),
                "average_spend_per_user_won": (
                    round(total_spend / len(users))
                    if users else 0
                ),
                "spend_segments": dict(sorted(counts.items())),
                "card_count_distribution": dict(
                    sorted(card_counts.items())
                ),
                "multi_card_users": sum(
                    u["multi_card_user"] for u in users
                ),
                "users_without_month_close": sum(
                    u["cards_with_month_close"] == 0
                    for u in users
                ),
            }

            save_csv(
                "user_monthly_segments.csv",
                users
            )

            (OUT / "user_analysis_summary.json").write_text(
                json.dumps(
                    summary,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

            print("\n=== USER STATISTICS ===")
            print(json.dumps(
                summary, ensure_ascii=False, indent=2
            ))
            print("\nSaved:", OUT)


if __name__ == "__main__":
    main()
