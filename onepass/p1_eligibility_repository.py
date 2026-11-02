
# onepass/p1_eligibility_repository.py

from dataclasses import dataclass
from datetime import date
from typing import Callable

import os
import psycopg
from dotenv import load_dotenv

from .p1_target_evaluator import (
    MerchantContext,
    TargetCondition,
    TargetStatus,
    evaluate_target,
)
from .p1_target_repository import choose_category
from .p1_channel_evaluator import (
    ChannelStatus,
    evaluate_channel,
)


@dataclass(frozen=True)
class EligibilityResult:
    rule_id: str
    merchant_id: str
    status: str
    reason: str
    target_status: str
    channel_status: str
    source_status: str | None
    std_category: str | None = None

    @property
    def eligible(self) -> bool:
        return self.status == "ELIGIBLE"


def _connect():
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL_NOT_SET")
    return psycopg.connect(url)


def _value(value):
    return getattr(value, "value", value)


class P1EligibilityRepository:
    def __init__(self, connect: Callable | None = None):
        self._connect = connect or _connect

    def evaluate(
        self,
        *,
        rule_id: str,
        merchant_id: str,
        payment,
        as_of: str | date,
    ) -> EligibilityResult:

        if not rule_id or not merchant_id:
            raise ValueError("RULE_AND_MERCHANT_REQUIRED")

        day = (
            date.fromisoformat(as_of)
            if isinstance(as_of, str)
            else as_of
        )
        if not isinstance(day, date):
            raise ValueError("INVALID_DATE")

        def result(
            status,
            reason,
            target_status="NOT_EVALUATED",
            channel_status="NOT_EVALUATED",
            source_status=None,
            std_category=None,
        ):
            return EligibilityResult(
                rule_id=rule_id,
                merchant_id=merchant_id,
                status=status,
                reason=reason,
                target_status=target_status,
                channel_status=channel_status,
                source_status=source_status,
                std_category=std_category,
            )

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")

                # 1. 혜택 규칙 및 유효기간
                cur.execute(
                    """
                    SELECT
                        payment_channel_required,
                        source_status,
                        valid_from,
                        valid_to
                    FROM public.benefit_rule
                    WHERE rule_id = %s
                    """,
                    (rule_id,),
                )
                rules = cur.fetchall()

                if len(rules) != 1:
                    return result(
                        "UNRESOLVED",
                        "RULE_NOT_FOUND_OR_DUPLICATED",
                    )

                required, source_status, start, end = rules[0]

                if (
                    (start is not None and day < start)
                    or (end is not None and day > end)
                ):
                    return result(
                        "INELIGIBLE",
                        "RULE_OUT_OF_VALIDITY",
                        source_status=source_status,
                    )

                # 2. 가맹점
                cur.execute(
                    """
                    SELECT industry_code
                    FROM public.merchant
                    WHERE merchant_id = %s
                    """,
                    (merchant_id,),
                )
                merchants = cur.fetchall()

                if len(merchants) != 1:
                    return result(
                        "UNRESOLVED",
                        "MERCHANT_NOT_FOUND_OR_DUPLICATED",
                        source_status=source_status,
                    )

                industry_code = merchants[0][0]
                if not industry_code:
                    return result(
                        "UNRESOLVED",
                        "MERCHANT_INDUSTRY_MISSING",
                        source_status=source_status,
                    )

                # 3. 혜택 대상 조건
                cur.execute(
                    """
                    SELECT target_type, target_code, apply_type
                    FROM public.benefit_industry
                    WHERE rule_id = %s
                    """,
                    (rule_id,),
                )
                rows = cur.fetchall()

                target_conditions = []
                channel_includes = []
                channel_excludes = []
                invalid_condition = False

                for target_type, target_code, apply_type in rows:
                    if target_type == "CHANNEL":
                        if apply_type == "INCLUDE":
                            channel_includes.append(target_code)
                        elif apply_type == "EXCLUDE":
                            channel_excludes.append(target_code)
                        else:
                            invalid_condition = True
                    elif target_type in ("CATEGORY", "MERCHANT"):
                        target_conditions.append(
                            TargetCondition(
                                rule_id=rule_id,
                                target_type=target_type,
                                target_code=target_code,
                                apply_type=apply_type,
                            )
                        )
                    else:
                        invalid_condition = True

                if invalid_condition:
                    return result(
                        "UNRESOLVED",
                        "UNKNOWN_TARGET_CONDITION",
                        source_status=source_status,
                    )

                # CHANNEL만 있는 규칙을 모든 가맹점에
                # 적용 가능한 것으로 간주하지 않음.
                if not target_conditions:
                    return result(
                        "UNRESOLVED",
                        "TARGET_RULES_MISSING",
                        source_status=source_status,
                    )

                # 4. 필요한 경우 표준 업종 조회
                category_map = {}
                std_category = None

                if any(
                    c.target_type == "CATEGORY"
                    for c in target_conditions
                ):
                    cur.execute(
                        """
                        SELECT industry_code, std_category
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

                    std_category, error = choose_category(
                        cur.fetchall(),
                        industry_code,
                    )

                    if error:
                        return result(
                            "UNRESOLVED",
                            error,
                            source_status=source_status,
                        )

                    category_map[industry_code] = std_category

                # 5. 업종·가맹점 평가
                target = evaluate_target(
                    rule_id=rule_id,
                    merchant=MerchantContext(
                        merchant_id=merchant_id,
                        industry_code=industry_code,
                    ),
                    conditions=target_conditions,
                    category_map=category_map,
                )

                # 6. 결제 레인 평가
                channel = evaluate_channel(
                    payment=payment,
                    payment_channel_required=required,
                    channel_includes=channel_includes,
                    channel_excludes=channel_excludes,
                )

                ts = _value(target.status)
                cs = _value(channel.status)

                # 명시적 제외가 확인되면 적용 불가.
                # 그 외 미확정 조건이 있다면 보류.
                if (
                    ts == TargetStatus.INELIGIBLE.value
                    or cs == ChannelStatus.INELIGIBLE.value
                ):
                    status = "INELIGIBLE"
                    reason = (
                        target.reason
                        if ts == "INELIGIBLE"
                        else channel.reason
                    )
                elif (
                    ts == TargetStatus.UNRESOLVED.value
                    or cs == ChannelStatus.UNRESOLVED.value
                ):
                    status = "UNRESOLVED"
                    reason = (
                        target.reason
                        if ts == "UNRESOLVED"
                        else channel.reason
                    )
                else:
                    status = "ELIGIBLE"
                    reason = "TARGET_AND_CHANNEL_MATCHED"

                return result(
                    status,
                    reason,
                    target_status=ts,
                    channel_status=cs,
                    source_status=source_status,
                    std_category=std_category,
                )
