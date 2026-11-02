# check_p1_monthly_schema.py

import os
import psycopg
from dotenv import load_dotenv


TABLES = (
    "card_month_close",
    "card_perf_month_close",
    "user_card",
    "benefit_cap_tier",
    "benefit_rule",
)


def main():
    load_dotenv()

    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL_NOT_SET")

    with psycopg.connect(
        url, autocommit=False
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SET TRANSACTION READ ONLY"
            )

            for table in TABLES:
                print(f"\n=== {table} ===")

                cur.execute(
                    """
                    SELECT
                        column_name,
                        data_type,
                        is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (table,),
                )

                columns = cur.fetchall()

                for name, dtype, nullable in columns:
                    print(
                        f"{name}: {dtype} "
                        f"(nullable={nullable})"
                    )

                if not columns:
                    print("TABLE_NOT_FOUND")
                    continue

                # Fixed whitelist: no user-supplied SQL identifiers.
                from psycopg import sql

                cur.execute(
                    sql.SQL(
                        "SELECT COUNT(*) FROM public.{}"
                    ).format(sql.Identifier(table))
                )

                print(
                    "ROWS:", cur.fetchone()[0]
                )

        conn.rollback()


if __name__ == "__main__":
    main()
