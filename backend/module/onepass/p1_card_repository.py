
# onepass/p1_card_repository.py

"""Read BNK card products and original benefits from public schema."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from .db_connection import get_database_url


class P1CardRepository:
    def __init__(self, database_url: str | None = None):
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(
            self.database_url or get_database_url(),
            row_factory=dict_row,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        )

    def get_card(self, product_id: str):
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        p.product_id,
                        p.product_name,
                        p.issuer,
                        p.card_type,
                        p.product_status,
                        p.terms_version,
                        p.source_status,
                        d.summary_json,
                        d.source_version
                    FROM public.card_product AS p
                    JOIN public.card_source_detail AS d
                      ON d.product_id = p.product_id
                    WHERE p.product_id = %s
                    """,
                    (product_id,),
                )

                product = cur.fetchone()

                if product is None:
                    return None

                cur.execute(
                    """
                    SELECT
                        source_rule_id,
                        product_id,
                        benefit_seq,
                        source_page,
                        target_original,
                        benefit_type_original,
                        benefit_value_original,
                        condition_json,
                        normalization_status
                    FROM public.card_benefit_source
                    WHERE product_id = %s
                    ORDER BY benefit_seq
                    """,
                    (product_id,),
                )

                return {
                    **product,
                    "benefits": cur.fetchall(),
                }

    def list_cards(self):
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        p.product_id,
                        p.product_name,
                        p.card_type,
                        COUNT(b.source_rule_id) AS benefit_count
                    FROM public.card_product AS p
                    JOIN public.card_source_detail AS d
                      ON d.product_id = p.product_id
                    LEFT JOIN public.card_benefit_source AS b
                      ON b.product_id = p.product_id
                    WHERE p.product_id = ANY(%s)
                    GROUP BY
                        p.product_id,
                        p.product_name,
                        p.card_type
                    ORDER BY p.product_id
                    """,
                    (
                        [
                            "P07", "P09", "P10",
                            "P16", "P19", "P23",
                        ],
                    ),
                )

                return cur.fetchall()
