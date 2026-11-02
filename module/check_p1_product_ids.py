
# check_p1_product_ids.py

import os

import psycopg
from dotenv import load_dotenv

from onepass.p1_product_ids import LEGACY_TO_CANONICAL


def main():
    load_dotenv()

    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL_NOT_SET")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            print("\n=== 1. 카드 상품 ID 현황 ===")

            for old_id, new_id in LEGACY_TO_CANONICAL.items():
                cur.execute(
                    """
                    SELECT product_id
                    FROM public.card_product
                    WHERE product_id IN (%s, %s)
                    ORDER BY product_id
                    """,
                    (old_id, new_id),
                )
                print(
                    f"{old_id} -> {new_id}:",
                    [row[0] for row in cur.fetchall()],
                )

            print("\n=== 2. 상품별 원문 혜택 수 ===")

            cur.execute(
                """
                SELECT product_id, COUNT(*)
                FROM public.card_benefit_source
                GROUP BY product_id
                ORDER BY product_id
                """
            )
            for row in cur.fetchall():
                print(row)

            print("\n=== 3. 상품 ID 참조 FK ===")

            cur.execute(
                """
                SELECT
                    c.conname,
                    n.nspname AS child_schema,
                    t.relname AS child_table,
                    pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_class t
                  ON t.oid = c.conrelid
                JOIN pg_namespace n
                  ON n.oid = t.relnamespace
                WHERE c.contype = 'f'
                  AND c.confrelid =
                    'public.card_product'::regclass
                ORDER BY n.nspname, t.relname
                """
            )
            for row in cur.fetchall():
                print(row)

            print("\n=== 4. 전체 원문 건수 ===")

            cur.execute(
                """
                SELECT COUNT(*)
                FROM public.card_benefit_source
                """
            )
            print(
                "SOURCE_BENEFITS:",
                cur.fetchone()[0],
            )

            print("\n=== 5. DB 직접 연결 성공 ===")


if __name__ == "__main__":
    main()
