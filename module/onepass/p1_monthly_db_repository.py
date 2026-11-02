
# onepass/p1_monthly_db_repository.py

from dataclasses import dataclass
from datetime import date
from typing import Callable
import os

import psycopg
from dotenv import load_dotenv


class MonthlyDBError(ValueError):
    pass


@dataclass(frozen=True)
class DBRuleMonth:
    rule_id: str
    product_id: str
    eligible_perf_won: int | None
    excluded_perf_won: int | None
    threshold_met: bool | None
    benefit_used_won: int | None
    shared_cap_group: str | None
    monthly_count_cap: int | None
    perf_basis_code: str | None


@dataclass(frozen=True)
class DBMonthlyState:
    user_card_id: str
    user_id: str
    product_id: str
    base_month: str
    spend_total_won: int | None
    benefit_total_won: int | None
    rules: tuple[DBRuleMonth, ...]
    status: str
    reasons: tuple[str, ...]


def connect_db():
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL_NOT_SET")
    return psycopg.connect(url, autocommit=False)


def valid_month(value: str):
    if not isinstance(value, str):
        raise MonthlyDBError("INVALID_BASE_MONTH")
    try:
        parsed = date.fromisoformat(value + "-01")
    except ValueError:
        raise MonthlyDBError("INVALID_BASE_MONTH") from None
    if parsed.strftime("%Y-%m") != value:
        raise MonthlyDBError("INVALID_BASE_MONTH")


def assess_state(
    *,
    spend_total_won,
    benefit_total_won,
    rule_rows,
):
    """
    Record data limitations explicitly.

    Count-limited rules cannot be fully initialized
    because card_perf_month_close has no used_count.

    This does not prove the performance basis.
    """
    reasons = []

    if spend_total_won is None:
        reasons.append("CARD_SPEND_MISSING")
    if benefit_total_won is None:
        reasons.append("CARD_BENEFIT_TOTAL_MISSING")
    if not rule_rows:
        reasons.append("RULE_MONTH_DATA_MISSING")

    seen = set()
    for row in rule_rows:
        if row.rule_id in seen:
            reasons.append("DUPLICATE_RULE_MONTH")
        seen.add(row.rule_id)

        if row.eligible_perf_won is None:
            reasons.append("ELIGIBLE_PERFORMANCE_MISSING")
        if row.benefit_used_won is None:
            reasons.append("RULE_BENEFIT_USAGE_MISSING")
        if row.monthly_count_cap is not None:
            reasons.append("MONTHLY_USED_COUNT_NOT_AVAILABLE")

    # Reading a row does not confirm its month semantics.
    reasons.append("PERFORMANCE_BASIS_NOT_CONFIRMED")

    return (
        "READY_FOR_REVIEW" if not reasons else "UNRESOLVED",
        tuple(sorted(set(reasons))),
    )


class P1MonthlyDBRepository:
    def __init__(self, connect: Callable | None = None):
        self._connect = connect or connect_db

    def load(
        self,
        *,
        user_card_id: str,
        base_month: str,
    ) -> DBMonthlyState:
        if not user_card_id:
            raise MonthlyDBError("USER_CARD_ID_REQUIRED")
        valid_month(base_month)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SET TRANSACTION READ ONLY"
                )

                # Verify ownership and product mapping.
                cur.execute(
                    """
                    SELECT user_id, product_id
                    FROM public.user_card
                    WHERE user_card_id = %s
                    """,
                    (user_card_id,),
                )
                cards = cur.fetchall()

                if len(cards) != 1:
                    raise MonthlyDBError(
                        "USER_CARD_NOT_FOUND_OR_DUPLICATED"
                    )

                user_id, product_id = cards[0]
                if not user_id or not product_id:
                    raise MonthlyDBError(
                        "USER_CARD_REFERENCE_INCOMPLETE"
                    )

                cur.execute(
                    """
                    SELECT
                        spend_total_won,
                        benefit_total_won
                    FROM public.card_month_close
                    WHERE user_card_id = %s
                      AND base_month = %s
                    """,
                    (user_card_id, base_month),
                )
                closes = cur.fetchall()

                if len(closes) > 1:
                    raise MonthlyDBError(
                        "DUPLICATE_CARD_MONTH_CLOSE"
                    )

                if closes:
                    spend_total, benefit_total = closes[0]
                else:
                    spend_total, benefit_total = None, None

                # LEFT JOIN: retain unknown rule references
                # instead of silently dropping them.
                cur.execute(
                    """
                    SELECT
                        pcm.rule_id,
                        br.product_id,
                        pcm.eligible_perf_won,
                        pcm.excluded_perf_won,
                        pcm.threshold_met,
                        pcm.benefit_used_won,
                        br.shared_cap_group,
                        br.monthly_count_cap,
                        br.perf_basis_code
                    FROM public.card_perf_month_close pcm
                    LEFT JOIN public.benefit_rule br
                      ON br.rule_id = pcm.rule_id
                    WHERE pcm.user_card_id = %s
                      AND pcm.base_month = %s
                    ORDER BY pcm.rule_id
                    """,
                    (user_card_id, base_month),
                )
                raw_rules = cur.fetchall()

        rules = tuple(
            DBRuleMonth(*row) for row in raw_rules
        )

        # Fail on mismatched card-product relationships.
        for row in rules:
            if row.product_id != product_id:
                raise MonthlyDBError(
                    f"RULE_PRODUCT_MISMATCH: {row.rule_id}"
                )

        status, reasons = assess_state(
            spend_total_won=spend_total,
            benefit_total_won=benefit_total,
            rule_rows=rules,
        )

        return DBMonthlyState(
            user_card_id=user_card_id,
            user_id=user_id,
            product_id=product_id,
            base_month=base_month,
            spend_total_won=spend_total,
            benefit_total_won=benefit_total,
            rules=rules,
            status=status,
            reasons=reasons,
        )
