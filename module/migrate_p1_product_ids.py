
# migrate_p1_product_ids.py

import argparse
import os

import psycopg
from psycopg import sql
from dotenv import load_dotenv

from onepass.p1_product_ids import LEGACY_TO_CANONICAL


# 실제 DB 사전 점검에서 확인된 FK 테이블
FK_TABLES = (
    "benefit_cap_tier",
    "benefit_rule",
    "card_benefit_source",
    "card_perf_exclude",
    "card_source_detail",
    "user_card",
)


def count_rows(cur, table, product_id):
    query = sql.SQL(
        "SELECT COUNT(*) FROM public.{} "
        "WHERE product_id = %s"
    ).format(sql.Identifier(table))

    cur.execute(query, (product_id,))
    return cur.fetchone()[0]


def product_exists(cur, product_id):
    cur.execute(
        """
        SELECT EXISTS(
            SELECT 1 FROM public.card_product
            WHERE product_id = %s
        )
        """,
        (product_id,),
    )
    return cur.fetchone()[0]


def get_columns(cur):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'card_product'
          AND is_generated = 'NEVER'
          AND is_identity = 'NO'
        ORDER BY ordinal_position
        """
    )
    columns = [r[0] for r in cur.fetchall()]

    if "product_id" not in columns:
        raise RuntimeError("PRODUCT_ID_NOT_FOUND")

    return columns


def verify_fk_schema(cur):
    cur.execute(
        """
        SELECT c.relname
        FROM pg_constraint fk
        JOIN pg_class c ON c.oid = fk.conrelid
        JOIN pg_namespace n
          ON n.oid = c.relnamespace
        WHERE fk.contype = 'f'
          AND fk.confrelid =
              'public.card_product'::regclass
          AND n.nspname = 'public'
        """
    )

    actual = {r[0] for r in cur.fetchall()}
    expected = set(FK_TABLES)

    if actual != expected:
        raise RuntimeError(
            f"FK_SCHEMA_CHANGED: "
            f"actual={sorted(actual)}, "
            f"expected={sorted(expected)}"
        )


def migrate(cur):
    mapping = LEGACY_TO_CANONICAL

    old_ids = list(mapping.keys())
    new_ids = list(mapping.values())

    existing_old = [
        x for x in old_ids if product_exists(cur, x)
    ]
    existing_new = [
        x for x in new_ids if product_exists(cur, x)
    ]

    if not existing_old and len(existing_new) == 6:
        print("ALREADY_MIGRATED")
        return

    if len(existing_old) != 6 or existing_new:
        raise RuntimeError(
            "PARTIAL_MIGRATION_OR_ID_CONFLICT: "
            f"old={existing_old}, new={existing_new}"
        )

    verify_fk_schema(cur)

    before = {
        (table, old): count_rows(cur, table, old)
        for table in FK_TABLES
        for old in old_ids
    }

    source_total_before = sum(
        before[("card_benefit_source", old)]
        for old in old_ids
    )

    if source_total_before != 48:
        raise RuntimeError(
            f"SOURCE_COUNT_NOT_48: {source_total_before}"
        )

    columns = get_columns(cur)

    insert_columns = sql.SQL(", ").join(
        sql.Identifier(c) for c in columns
    )

    select_columns = sql.SQL(", ").join(
        sql.Placeholder()
        if c == "product_id"
        else sql.Identifier(c)
        for c in columns
    )

    insert_sql = sql.SQL(
        "INSERT INTO public.card_product ({}) "
        "SELECT {} FROM public.card_product "
        "WHERE product_id = %s"
    ).format(insert_columns, select_columns)

    print("=== 상품 신규 ID 생성 ===")

    for old_id, new_id in mapping.items():
        cur.execute(insert_sql, (new_id, old_id))

        if cur.rowcount != 1:
            raise RuntimeError(
                f"COPY_FAILED: {old_id}"
            )

        print(f"{old_id} -> {new_id}")

    print("\n=== FK 참조 이관 ===")

    for table in FK_TABLES:
        query = sql.SQL(
            "UPDATE public.{} "
            "SET product_id = %s "
            "WHERE product_id = %s"
        ).format(sql.Identifier(table))

        moved = 0

        for old_id, new_id in mapping.items():
            cur.execute(query, (new_id, old_id))
            moved += cur.rowcount

            after_count = count_rows(
                cur, table, new_id
            )

            if after_count != before[(table, old_id)]:
                raise RuntimeError(
                    f"REFERENCE_COUNT_MISMATCH: "
                    f"{table}, {old_id}"
                )

        print(f"{table}: {moved} rows")

    print("\n=== 기존 상품 ID 정리 ===")

    for old_id in old_ids:
        cur.execute(
            """
            DELETE FROM public.card_product
            WHERE product_id = %s
            """,
            (old_id,),
        )

        if cur.rowcount != 1:
            raise RuntimeError(
                f"DELETE_FAILED: {old_id}"
            )

    print("\n=== 최종 검증 ===")

    for old_id, new_id in mapping.items():
        if product_exists(cur, old_id):
            raise RuntimeError(
                f"OLD_PRODUCT_REMAINS: {old_id}"
            )

        if not product_exists(cur, new_id):
            raise RuntimeError(
                f"NEW_PRODUCT_MISSING: {new_id}"
            )

    for table in FK_TABLES:
        for old_id in old_ids:
            if count_rows(cur, table, old_id):
                raise RuntimeError(
                    f"OLD_REFERENCE_REMAINS: "
                    f"{table}, {old_id}"
                )

    source_total_after = sum(
        count_rows(cur, "card_benefit_source", new)
        for new in new_ids
    )

    if source_total_after != source_total_before:
        raise RuntimeError(
            "SOURCE_BENEFITS_NOT_PRESERVED"
        )

    print(
        "SOURCE_BENEFITS:",
        source_total_after
    )
    print("MIGRATION_VALIDATED")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes to database",
    )

    args = parser.parse_args()

    load_dotenv()
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL_NOT_SET")

    with psycopg.connect(
        database_url,
        autocommit=False,
    ) as conn:

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SET LOCAL lock_timeout = '5s'"
                )

                cur.execute(
                    "SELECT pg_advisory_xact_lock("
                    "20261027, 71)"
                )

                # 이관 중 다른 쓰기가 끼어들지 않도록
                # 대상 테이블에 트랜잭션 잠금 적용
                for table in (
                    "card_product",
                    *FK_TABLES,
                ):
                    cur.execute(
                        sql.SQL(
                            "LOCK TABLE public.{} "
                            "IN SHARE ROW EXCLUSIVE MODE"
                        ).format(sql.Identifier(table))
                    )

                migrate(cur)

            if args.apply:
                conn.commit()
                print("\nCOMMITTED")
            else:
                conn.rollback()
                print("\nDRY_RUN_OK - ROLLED_BACK")

        except Exception:
            conn.rollback()
            raise


if __name__ == "__main__":
    main()
