
# import_bnk_cards.py
# 부산은행 6종 상품 및 혜택 원문을 NeonDB에 적재.
# 기존 P0 엔진/테스트 테이블의 데이터를 삭제하지 않음.

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import psycopg
from openpyxl import load_workbook
from psycopg.types.json import Jsonb

from onepass.db_connection import get_database_url


SOURCE = Path(
    "data/부산은행_카드상품_목록표_v0.1.xlsx"
)

PRODUCT_IDS = {
    "P07", "P09", "P10",
    "P16", "P19", "P23",
}

EXPECTED_COUNTS = {
    "P07": 10,
    "P09": 10,
    "P10": 7,
    "P16": 8,
    "P19": 6,
    "P23": 7,
}

SOURCE_VERSION = "BNK_CATALOG_V0.1_20261023"


def read_sheet(wb, sheet_name):
    """Actual headers are in row 4, not row 1."""
    ws = wb[sheet_name]

    rows = ws.iter_rows(values_only=True)
    all_rows = list(rows)

    headers = [
        str(value).strip() if value is not None else ""
        for value in all_rows[3]
    ]

    if not all(headers):
        raise ValueError(
            f"EMPTY_HEADER: {sheet_name}"
        )

    if len(headers) != len(set(headers)):
        raise ValueError(
            f"DUPLICATE_HEADER: {sheet_name}"
        )

    result = []

    for values in all_rows[4:]:
        if not values or all(
            value is None for value in values
        ):
            continue

        row = {}

        for key, value in zip(headers, values):
            if not key:
                continue

            row[key] = (
                "" if value is None else str(value).strip()
            )

        if row.get("product_id") in PRODUCT_IDS or (
            row.get("상품ID") in PRODUCT_IDS
        ):
            result.append(row)

    return result


def load_source():
    if not SOURCE.is_file():
        raise FileNotFoundError(
            f"XLSX_NOT_FOUND: {SOURCE}"
        )

    wb = load_workbook(
        SOURCE,
        read_only=True,
        data_only=True,
    )

    try:
        products = read_sheet(
            wb, "01_상품요약"
        )
        benefits = read_sheet(
            wb, "02_혜택상세"
        )
    finally:
        wb.close()

    product_ids = [
        p["상품ID"] for p in products
    ]

    if (
        len(products) != 6
        or set(product_ids) != PRODUCT_IDS
        or len(set(product_ids)) != 6
    ):
        raise ValueError(
            f"UNEXPECTED_PRODUCTS: {product_ids}"
        )

    counts = Counter(
        b["product_id"] for b in benefits
    )

    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError(
            f"UNEXPECTED_BENEFIT_COUNTS: {dict(counts)}"
        )

    for benefit in benefits:
        if not benefit.get("benefit_target_original"):
            raise ValueError(
                "MISSING_BENEFIT_TARGET"
            )

        if not benefit.get("benefit_seq"):
            raise ValueError(
                "MISSING_BENEFIT_SEQ"
            )

    unique_keys = {
        (
            b["product_id"],
            int(b["benefit_seq"]),
        )
        for b in benefits
    }

    if len(unique_keys) != len(benefits):
        raise ValueError(
            "DUPLICATE_BENEFIT_SEQUENCE"
        )

    return products, benefits


CREATE_SOURCE_TABLES = """
CREATE TABLE IF NOT EXISTS public.card_source_detail (
    product_id TEXT PRIMARY KEY
        REFERENCES public.card_product(product_id),

    source_version TEXT NOT NULL,
    source_file TEXT NOT NULL,

    summary_json JSONB NOT NULL,

    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.card_benefit_source (
    source_rule_id TEXT PRIMARY KEY,

    product_id TEXT NOT NULL
        REFERENCES public.card_product(product_id),

    benefit_seq INTEGER NOT NULL,

    source_version TEXT NOT NULL,
    source_page TEXT,

    target_original TEXT NOT NULL,
    benefit_type_original TEXT NOT NULL,
    benefit_value_original TEXT,

    condition_json JSONB NOT NULL,

    normalization_status TEXT NOT NULL
        DEFAULT 'PENDING'
        CHECK (
            normalization_status IN (
                'PENDING',
                'REVIEWED',
                'VERIFIED'
            )
        ),

    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (product_id, benefit_seq)
);

CREATE INDEX IF NOT EXISTS
    idx_card_benefit_source_product
ON public.card_benefit_source (
    product_id, benefit_seq
);
"""


def import_catalog(*, dry_run=False):
    products, benefits = load_source()

    print("Products:", len(products))
    print("Benefits:", len(benefits))

    if dry_run:
        for p in products:
            pid = p["상품ID"]
            print(
                pid,
                p["상품명"],
                EXPECTED_COUNTS[pid],
            )
        return

    confirm = input(
        "Insert/update the 6-card source catalog "
        "in NeonDB? Type IMPORT: "
    )

    if confirm != "IMPORT":
        print("Cancelled.")
        return

    with psycopg.connect(
        get_database_url(),
        connect_timeout=10,
    ) as conn:
        
        with conn.cursor() as cur:
            # Verify that the backend's public schema is installed.
            cur.execute(
                """
                SELECT to_regclass(
                    'public.card_product'
                )
                """
            )

            table_name = cur.fetchone()[0]

            if table_name is None:
                raise RuntimeError(
                    "CARD_PRODUCT_TABLE_NOT_CREATED"
                )

            # Create catalog source tables after verification.
            cur.execute(CREATE_SOURCE_TABLES)

            # Continue with the existing:
            # for p in products:
            #     ...

            for p in products:
                pid = p["상품ID"]

                card_type = (
                    "BANK_CREDIT"
                    if p["구분"] == "신용"
                    else "BANK_CHECK"
                )

                # Never overwrite an already verified
                # product master automatically.
                cur.execute(
                    """
                    INSERT INTO public.card_product (
                        product_id,
                        product_name,
                        issuer,
                        card_type,
                        product_status,
                        terms_version,
                        source_status,
                        source_ref
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        'TEST_ONLY', %s,
                        'PENDING', %s
                    )
                    ON CONFLICT (product_id)
                    DO UPDATE SET
                        product_name = EXCLUDED.product_name,
                        issuer = EXCLUDED.issuer,
                        card_type = EXCLUDED.card_type,
                        terms_version = EXCLUDED.terms_version,
                        source_ref = EXCLUDED.source_ref
                    WHERE card_product.source_status
                          <> 'VERIFIED'
                    """,
                    (
                        pid,
                        p["상품명"],
                        "BNK_BUSAN",
                        card_type,
                        SOURCE_VERSION,
                        p.get("원본파일", ""),
                    ),
                )


                cur.execute(
                    """
                    INSERT INTO public.card_source_detail (
                        product_id,
                        source_version,
                        source_file,
                        summary_json
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (product_id)
                    DO UPDATE SET
                        source_version =
                            EXCLUDED.source_version,
                        source_file =
                            EXCLUDED.source_file,
                        summary_json =
                            EXCLUDED.summary_json,
                        updated_at =
                            CURRENT_TIMESTAMP
                    """,
                    (
                        pid,
                        SOURCE_VERSION,
                        p.get("원본파일", ""),
                        Jsonb(p),
                    ),
                )


            for b in benefits:
                pid = b["product_id"]
                seq = int(b["benefit_seq"])

                # Preserve all original conditions,
                # including ambiguous wording.
                raw_conditions = {
                    key: value
                    for key, value in b.items()
                    if key not in {
                        "product_id",
                        "benefit_seq",
                    }
                }

                cur.execute(
                    """
                    INSERT INTO
                        public.card_benefit_source (
                            source_rule_id,
                            product_id,
                            benefit_seq,
                            source_version,
                            source_page,
                            target_original,
                            benefit_type_original,
                            benefit_value_original,
                            condition_json
                        )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (source_rule_id)
                    DO UPDATE SET
                        source_version =
                            EXCLUDED.source_version,
                        source_page =
                            EXCLUDED.source_page,
                        target_original =
                            EXCLUDED.target_original,
                        benefit_type_original =
                            EXCLUDED.benefit_type_original,
                        benefit_value_original =
                            EXCLUDED.benefit_value_original,
                        condition_json =
                            EXCLUDED.condition_json,
                        normalization_status = 'PENDING',
                        updated_at =
                            CURRENT_TIMESTAMP
                    WHERE card_benefit_source
                          .normalization_status
                          <> 'VERIFIED'
                    """,
                    (
                        f"{pid}_R{seq:02d}",
                        pid,
                        seq,
                        SOURCE_VERSION,
                        b.get("source_page", ""),
                        b["benefit_target_original"],
                        b.get("benefit_type", ""),
                        b.get("benefit_value", ""),
                        Jsonb(raw_conditions),
                    ),
                )

            # Verify imported source data inside
            # the same transaction.
            cur.execute(
                """
                SELECT product_id, COUNT(*)
                FROM public.card_benefit_source
                WHERE product_id = ANY(%s)
                GROUP BY product_id
                """,
                (sorted(PRODUCT_IDS),),
            )

            result = dict(cur.fetchall())

            if result != EXPECTED_COUNTS:
                raise RuntimeError(
                    f"DB_IMPORT_MISMATCH: {result}"
                )

        # Automatic commit on successful exit;
        # rollback on any exception.

    print("IMPORT_OK")
    print("Products: 6")
    print("Benefits: 48")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    args = parser.parse_args()

    import_catalog(dry_run=args.dry_run)
