
# load_p1_benefit_rules.py

import argparse
import csv
import io
import os
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import ZipFile

import psycopg
from psycopg import sql
from dotenv import load_dotenv


SEED = "seed_20261023"

TABLES = {
    "BENEFIT_RULE": ("benefit_rule", 20),
    "BENEFIT_INDUSTRY": ("benefit_industry", 91),
    "BENEFIT_CAP_TIER": ("benefit_cap_tier", 15),
    "CARD_PERF_EXCLUDE": ("card_perf_exclude", 2),
}

PRODUCT_IDS = {
    "BNK_CR_P07",
    "BNK_CR_P09",
    "BNK_CR_P10",
    "BNK_CR_P16",
    "BNK_CK_P19",
    "BNK_CK_P23",
}

KEYS = {
    "benefit_rule": ("rule_id",),
    "benefit_industry": (
        "rule_id", "target_type",
        "target_code", "apply_type"
    ),
    "benefit_cap_tier": ("tier_id",),
    "card_perf_exclude": ("exclude_id",),
}


def read_zip(zip_path):
    result = {}

    with ZipFile(zip_path) as archive:
        names = archive.namelist()

        for csv_name, (_, expected) in TABLES.items():
            suffix = (
                f"/csv/{SEED}/{csv_name}.csv"
            )

            matches = [
                name for name in names
                if name.endswith(suffix)
            ]

            if len(matches) != 1:
                raise ValueError(
                    f"CSV_NOT_FOUND_OR_DUPLICATED: {csv_name}"
                )

            content = archive.read(
                matches[0]
            ).decode("utf-8-sig")

            reader = csv.DictReader(
                io.StringIO(content)
            )

            if not reader.fieldnames:
                raise ValueError(
                    f"EMPTY_HEADER: {csv_name}"
                )

            if len(reader.fieldnames) != len(
                set(reader.fieldnames)
            ):
                raise ValueError(
                    f"DUPLICATE_COLUMNS: {csv_name}"
                )

            rows = list(reader)

            if len(rows) != expected:
                raise ValueError(
                    f"ROW_COUNT_MISMATCH: {csv_name} "
                    f"{len(rows)} != {expected}"
                )

            if any(
                None in row
                or any(v is None for v in row.values())
                for row in rows
            ):
                raise ValueError(
                    f"MALFORMED_CSV: {csv_name}"
                )

            result[csv_name] = rows

    return result


def validate_csv(data):
    rules = data["BENEFIT_RULE"]

    rule_ids = [
        row["rule_id"] for row in rules
    ]

    if len(set(rule_ids)) != 20:
        raise ValueError("DUPLICATE_RULE_ID")

    statuses = Counter(
        row["source_status"] for row in rules
    )

    if statuses != Counter({
        "ASSUMED": 13,
        "PENDING": 7,
    }):
        raise ValueError(
            f"UNEXPECTED_SOURCE_STATUS: {statuses}"
        )

    for row in rules:
        if row["product_id"] not in PRODUCT_IDS:
            raise ValueError(
                f"UNKNOWN_PRODUCT: {row['product_id']}"
            )

        if row["payment_channel_required"] != "ANY":
            raise ValueError(
                "UNEXPECTED_PAYMENT_CHANNEL_RULE"
            )

    for row in data["BENEFIT_INDUSTRY"]:
        if row["rule_id"] not in rule_ids:
            raise ValueError(
                f"UNKNOWN_RULE: {row['rule_id']}"
            )

    for name in (
        "BENEFIT_CAP_TIER",
        "CARD_PERF_EXCLUDE",
    ):
        for row in data[name]:
            if row["product_id"] not in PRODUCT_IDS:
                raise ValueError(
                    f"UNKNOWN_PRODUCT_IN_{name}"
                )

    for csv_name, rows in data.items():
        table = TABLES[csv_name][0]
        keys = KEYS[table]

        identifiers = [
            tuple(row[k] for k in keys)
            for row in rows
        ]

        if len(set(identifiers)) != len(identifiers):
            raise ValueError(
                f"DUPLICATE_KEYS: {csv_name}"
            )

    print(
        "CSV_VALIDATED: "
        "rules=20, industry=91, tier=15, exclude=2"
    )
    print("SOURCE_STATUS:", dict(statuses))
    print(
        "WARNING: 20 rules use "
        "payment_channel_required=ANY"
    )


def get_db_columns(cur, table):
    cur.execute(
        """
        SELECT
            column_name,
            is_generated,
            is_identity
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )

    return {
        row[0]: (row[1], row[2])
        for row in cur.fetchall()
    }


def equal_values(actual, expected):
    if actual is None or expected is None:
        return actual is None and expected is None

    if isinstance(actual, (date, datetime)):
        return actual.isoformat() == expected

    if isinstance(actual, (Decimal, int, float)):
        try:
            return (
                Decimal(str(actual))
                == Decimal(str(expected))
            )
        except InvalidOperation:
            return False

    return str(actual) == str(expected)


def find_existing(cur, table, row, columns):
    keys = KEYS[table]

    where = sql.SQL(" AND ").join(
        sql.SQL("{} = %s").format(
            sql.Identifier(key)
        )
        for key in keys
    )

    query = sql.SQL(
        "SELECT {} FROM public.{} WHERE {}"
    ).format(
        sql.SQL(", ").join(
            sql.Identifier(c) for c in columns
        ),
        sql.Identifier(table),
        where,
    )

    cur.execute(
        query,
        [row[key] for key in keys],
    )

    return cur.fetchall()


def insert_table(cur, csv_name, rows):
    table = TABLES[csv_name][0]
    db_columns = get_db_columns(cur, table)

    if not db_columns:
        raise ValueError(
            f"DB_TABLE_NOT_FOUND: {table}"
        )

    csv_columns = list(rows[0].keys())

    missing = set(csv_columns) - set(db_columns)
    if missing:
        raise ValueError(
            f"DB_COLUMN_MISMATCH: {table}, {missing}"
        )

    # DB에서 자동 생성하는 컬럼은 INSERT에서 제외
    generated_columns = {
        col
        for col in csv_columns
        if db_columns[col][0] != "NEVER"
        or db_columns[col][1] == "YES"
    }

    # 현재 확인된 자동 생성 컬럼만 허용
    if generated_columns - {"exclude_id"}:
        raise ValueError(
            f"UNEXPECTED_GENERATED_COLUMNS: "
            f"{table}, {generated_columns}"
        )

    insert_columns = [
        col for col in csv_columns
        if col not in generated_columns
    ]

    insert_sql = sql.SQL(
        "INSERT INTO public.{} ({}) VALUES ({})"
    ).format(
        sql.Identifier(table),
        sql.SQL(", ").join(
            sql.Identifier(c) for c in insert_columns
        ),
        sql.SQL(", ").join(
            sql.Placeholder() for _ in insert_columns
        ),
    )

    inserted = 0
    skipped = 0

    for row in rows:
        values = [
            None if row[col] == "" else row[col]
            for col in insert_columns
        ]

        # 자동 생성 ID를 가진 테이블은
        # 나머지 데이터 컬럼으로 기존 행 검색
        if generated_columns:
            where = sql.SQL(" AND ").join(
                sql.SQL("{} IS NOT DISTINCT FROM %s").format(
                    sql.Identifier(col)
                )
                for col in insert_columns
            )

            query = sql.SQL(
                "SELECT COUNT(*) FROM public.{} WHERE {}"
            ).format(
                sql.Identifier(table),
                where,
            )

            cur.execute(query, values)
            count = cur.fetchone()[0]

            if count > 1:
                raise ValueError(
                    f"DUPLICATE_DB_ROWS: {table}"
                )

            if count == 1:
                skipped += 1
                continue

        else:
            existing = find_existing(
                cur, table, row, csv_columns
            )

            if existing:
                if len(existing) != 1:
                    raise ValueError(
                        f"DUPLICATE_DB_ROWS: {table}"
                    )

                identical = all(
                    equal_values(actual, expected)
                    for actual, expected in zip(
                        existing[0],
                        [
                            None if row[col] == ""
                            else row[col]
                            for col in csv_columns
                        ],
                    )
                )

                if not identical:
                    raise ValueError(
                        f"EXISTING_ROW_DIFFERENT: "
                        f"{table}, "
                        f"{tuple(row[k] for k in KEYS[table])}"
                    )

                skipped += 1
                continue

        cur.execute(insert_sql, values)

        if cur.rowcount != 1:
            raise RuntimeError(
                f"INSERT_FAILED: {table}"
            )

        inserted += 1

    print(
        f"{table}: inserted={inserted}, "
        f"already_present={skipped}"
    )


def execute(cur, data):
    cur.execute(
        "SET LOCAL lock_timeout = '5s'"
    )

    cur.execute(
        "SELECT pg_advisory_xact_lock(20261027, 72)"
    )

    # 적재 중 관련 테이블의 동시 변경 제한
    for table, _ in TABLES.values():
        cur.execute(
            sql.SQL(
                "LOCK TABLE public.{} "
                "IN SHARE ROW EXCLUSIVE MODE"
            ).format(sql.Identifier(table))
        )

    cur.execute(
        """
        SELECT product_id
        FROM public.card_product
        WHERE product_id = ANY(%s)
        """,
        (sorted(PRODUCT_IDS),),
    )

    found = {
        row[0] for row in cur.fetchall()
    }

    if found != PRODUCT_IDS:
        raise ValueError(
            "CANONICAL_PRODUCTS_NOT_READY: "
            f"{sorted(PRODUCT_IDS - found)}"
        )

    print("PRODUCT_IDS_VALIDATED: 6")

    for csv_name, rows in data.items():
        insert_table(cur, csv_name, rows)

    rule_ids = [
        row["rule_id"]
        for row in data["BENEFIT_RULE"]
    ]

    cur.execute(
        """
        SELECT rule_id
        FROM public.benefit_rule
        WHERE rule_id = ANY(%s)
        """,
        (rule_ids,),
    )

    loaded_ids = {
        row[0] for row in cur.fetchall()
    }

    if loaded_ids != set(rule_ids):
        raise RuntimeError(
            "RULE_ID_VALIDATION_FAILED"
        )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM public.benefit_industry
        WHERE rule_id = ANY(%s)
        """,
        (rule_ids,),
    )

    if cur.fetchone()[0] != 91:
        raise RuntimeError(
            "BENEFIT_INDUSTRY_COUNT_MISMATCH"
        )

    print("DB_INSERT_VALIDATED")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--zip",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    args = parser.parse_args()

    if not args.zip.exists():
        raise FileNotFoundError(args.zip)

    data = read_zip(args.zip)
    validate_csv(data)

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
                execute(cur, data)

            if args.apply:
                conn.commit()
                print("COMMITTED")
            else:
                conn.rollback()
                print("DRY_RUN_OK - ROLLED_BACK")

        except Exception:
            conn.rollback()
            raise


if __name__ == "__main__":
    main()
