
# check_p1_db_targets.py

import os
from collections import Counter

import psycopg
from dotenv import load_dotenv

from onepass.p1_target_repository import (
    P1TargetRepository,
)


def main():
    load_dotenv()
    url = os.getenv("DATABASE_URL")

    if not url:
        raise RuntimeError("DATABASE_URL_NOT_SET")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for table in (
                "merchant",
                "benefit_category_map",
                "benefit_industry",
            ):
                cur.execute(
                    f"SELECT COUNT(*) FROM public.{table}"
                )
                count = cur.fetchone()[0]
                print(f"{table}: {count} rows")

            cur.execute(
                """
                SELECT rule_id, target_code
                FROM public.benefit_industry
                WHERE target_type = 'MERCHANT'
                  AND apply_type = 'INCLUDE'
                ORDER BY rule_id, target_code
                LIMIT 1
                """
            )
            sample_merchant = cur.fetchone()

            cur.execute(
                """
                SELECT
                    bi.rule_id,
                    m.merchant_id
                FROM public.benefit_industry bi
                JOIN public.benefit_category_map bcm
                  ON bcm.std_category = bi.target_code
                JOIN public.merchant m
                  ON m.industry_code = bcm.industry_code
                WHERE bi.target_type = 'CATEGORY'
                  AND bi.apply_type = 'INCLUDE'
                  AND (bcm.valid_from IS NULL
                       OR bcm.valid_from <= DATE '2026-10-27')
                  AND (bcm.valid_to IS NULL
                       OR bcm.valid_to >= DATE '2026-10-27')
                ORDER BY bi.rule_id, m.merchant_id
                LIMIT 1
                """
            )
            sample_category = cur.fetchone()

    samples = []

    if sample_merchant:
        samples.append(
            ("MERCHANT", sample_merchant[0],
             sample_merchant[1])
        )

    if sample_category:
        samples.append(
            ("CATEGORY", sample_category[0],
             sample_category[1])
        )

    repo = P1TargetRepository()
    counts = Counter()

    for kind, rule_id, merchant_id in samples:
        result = repo.evaluate(
            rule_id,
            merchant_id,
            "2026-10-27",
        )

        counts[result.status.value] += 1

        print(
            f"{kind}:",
            f"rule={rule_id}",
            f"merchant={merchant_id}",
            f"status={result.status.value}",
            f"category={result.std_category}",
            f"reason={result.reason}",
        )

    print("RESULT_COUNTS:", dict(counts))


if __name__ == "__main__":
    main()
