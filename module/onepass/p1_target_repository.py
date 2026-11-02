
# onepass/p1_target_repository.py

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Callable

import psycopg
from dotenv import load_dotenv

from .p1_target_evaluator import (
    MerchantContext,
    TargetCondition,
    TargetDecision,
    TargetStatus,
    evaluate_target,
)


@dataclass(frozen=True)
class DBTargetResult:
    rule_id: str
    merchant_id: str
    industry_code: str | None
    std_category: str | None
    status: TargetStatus
    reason: str
    matched_targets: tuple[str, ...] = ()


def _default_connect():
    load_dotenv()
    url = os.getenv("DATABASE_URL")

    if not url:
        raise RuntimeError("DATABASE_URL_NOT_SET")

    return psycopg.connect(url, autocommit=False)


def choose_category(
    rows: list[tuple[str, str]],
    industry_code: str,
) -> tuple[str | None, str | None]:
    """
    Select one unambiguous mapping.

    rows:
        [(industry_code, std_category), ...]
        already filtered for the evaluation date.

    Returns:
        (category, error_reason)
    """
    matched = [
        category
        for original, category in rows
        if original == industry_code
    ]

    if not matched:
        return None, "CATEGORY_MAPPING_MISSING"

    if not all(
        isinstance(x, str) and x.strip()
        for x in matched
    ):
        return None, "CATEGORY_MAPPING_INVALID"

    values = set(matched)

    if len(values) != 1:
        return None, "CATEGORY_MAPPING_AMBIGUOUS"

    return matched[0], None


class P1TargetRepository:
    def __init__(
        self,
        connect: Callable | None = None,
    ):
        self._connect = connect or _default_connect

    def evaluate(
        self,
        rule_id: str,
        merchant_id: str,
        as_of: date | str,
    ) -> DBTargetResult:

        day = (
            date.fromisoformat(as_of)
            if isinstance(as_of, str)
            else as_of
        )

        if not isinstance(day, date):
            raise ValueError("INVALID_AS_OF")

        if not rule_id or not merchant_id:
            raise ValueError(
                "RULE_ID_AND_MERCHANT_ID_REQUIRED"
            )

        with self._connect() as conn:
            with conn.cursor() as cur:
                # 조회 전용 트랜잭션
                cur.execute(
                    "SET TRANSACTION READ ONLY"
                )

                cur.execute(
                    """
                    SELECT industry_code
                    FROM public.merchant
                    WHERE merchant_id = %s
                    """,
                    (merchant_id,),
                )
                merchant_rows = cur.fetchall()

                if len(merchant_rows) != 1:
                    reason = (
                        "MERCHANT_NOT_FOUND"
                        if not merchant_rows
                        else "MERCHANT_ID_AMBIGUOUS"
                    )
                    return DBTargetResult(
                        rule_id,
                        merchant_id,
                        None,
                        None,
                        TargetStatus.UNRESOLVED,
                        reason,
                    )

                industry_code = merchant_rows[0][0]

                if not industry_code:
                    return DBTargetResult(
                        rule_id,
                        merchant_id,
                        None,
                        None,
                        TargetStatus.UNRESOLVED,
                        "MERCHANT_INDUSTRY_MISSING",
                    )

                cur.execute(
                    """
                    SELECT
                        target_type,
                        target_code,
                        apply_type
                    FROM public.benefit_industry
                    WHERE rule_id = %s
                    ORDER BY
                        target_type,
                        target_code,
                        apply_type
                    """,
                    (rule_id,),
                )
                condition_rows = cur.fetchall()

                if not condition_rows:
                    return DBTargetResult(
                        rule_id,
                        merchant_id,
                        industry_code,
                        None,
                        TargetStatus.UNRESOLVED,
                        "TARGET_RULES_MISSING",
                    )

                conditions = [
                    TargetCondition(
                        rule_id=rule_id,
                        target_type=target_type,
                        target_code=target_code,
                        apply_type=apply_type,
                    )
                    for (
                        target_type,
                        target_code,
                        apply_type,
                    ) in condition_rows
                ]

                # CATEGORY target이 있는 규칙에만
                # 업종 매핑을 요구함.
                needs_category = any(
                    c.target_type == "CATEGORY"
                    for c in conditions
                )

                category_map = {}
                std_category = None

                if needs_category:
                    cur.execute(
                        """
                        SELECT
                            industry_code,
                            std_category
                        FROM public.benefit_category_map
                        WHERE industry_code = %s
                          AND (
                            valid_from IS NULL
                            OR valid_from <= %s
                          )
                          AND (
                            valid_to IS NULL
                            OR valid_to >= %s
                          )
                        """,
                        (industry_code, day, day),
                    )
                    mapping_rows = cur.fetchall()

                    std_category, error = choose_category(
                        mapping_rows,
                        industry_code,
                    )

                    if error:
                        return DBTargetResult(
                            rule_id,
                            merchant_id,
                            industry_code,
                            None,
                            TargetStatus.UNRESOLVED,
                            error,
                        )

                    category_map[industry_code] = (
                        std_category
                    )

                decision: TargetDecision = evaluate_target(
                    rule_id=rule_id,
                    merchant=MerchantContext(
                        merchant_id=merchant_id,
                        industry_code=industry_code,
                    ),
                    conditions=conditions,
                    category_map=category_map,
                )

                return DBTargetResult(
                    rule_id=rule_id,
                    merchant_id=merchant_id,
                    industry_code=industry_code,
                    std_category=std_category,
                    status=decision.status,
                    reason=decision.reason,
                    matched_targets=(
                        decision.matched_targets
                    ),
                )
