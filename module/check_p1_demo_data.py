
"""P1 시연용 사용자와 월별 데이터 진단. DB 읽기 전용."""

import os
import psycopg
from dotenv import load_dotenv

load_dotenv(".env")

BNK_PRODUCTS = (
    "BNK_CR_P07",
    "BNK_CR_P09",
    "BNK_CR_P10",
    "BNK_CR_P16",
    "BNK_CK_P19",
    "BNK_CK_P23",
)

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")

        print("\n=== 1. 월 마감 데이터 분포 ===")
        cur.execute("""
            SELECT base_month, COUNT(*)
            FROM public.card_month_close
            GROUP BY base_month
            ORDER BY base_month DESC
        """)
        for month, count in cur.fetchall():
            print(month, count)

        print("\n=== 2. 규칙별 월 마감 데이터 분포 ===")
        cur.execute("""
            SELECT base_month, COUNT(*)
            FROM public.card_perf_month_close
            GROUP BY base_month
            ORDER BY base_month DESC
        """)
        for month, count in cur.fetchall():
            print(month, count)

        print("\n=== 3. BNK 카드 복수 보유 사용자 TOP 10 ===")
        cur.execute("""
            SELECT
                user_id,
                COUNT(DISTINCT product_id) AS card_count,
                STRING_AGG(
                    DISTINCT product_id, ', '
                ) AS products
            FROM public.user_card
            WHERE product_id = ANY(%s)
              AND (card_status = 'ACTIVE'
                   OR card_status IS NULL)
            GROUP BY user_id
            ORDER BY card_count DESC, user_id
            LIMIT 10
        """, (list(BNK_PRODUCTS),))

        users = cur.fetchall()

        for user_id, count, products in users:
            print(user_id, count, products)

        print("\n=== 4. U0001 월별 데이터 ===")
        cur.execute("""
            SELECT
                uc.user_card_id,
                uc.product_id,
                cm.base_month,
                cm.spend_total_won,
                cm.benefit_total_won
            FROM public.user_card uc
            LEFT JOIN public.card_month_close cm
                ON cm.user_card_id = uc.user_card_id
            WHERE uc.user_id = %s
            ORDER BY uc.product_id, cm.base_month DESC
        """, ("U0001",))

        for row in cur.fetchall():
            print(row)

        print("\n=== 5. U0001 규칙별 월 마감 ===")
        cur.execute("""
            SELECT
                uc.product_id,
                pm.base_month,
                pm.rule_id,
                pm.eligible_perf_won,
                pm.benefit_used_won
            FROM public.user_card uc
            JOIN public.card_perf_month_close pm
                ON pm.user_card_id = uc.user_card_id
            WHERE uc.user_id = %s
            ORDER BY pm.base_month DESC, pm.rule_id
            LIMIT 30
        """, ("U0001",))

        for row in cur.fetchall():
            print(row)

print("\n진단 완료: DB 변경 없음")
