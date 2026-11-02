
"""OnePass P1: read-only, single-transaction simulation (no top-up/payment)."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import json

from dotenv import load_dotenv
from psycopg.rows import dict_row

from onepass.db_connection import connect_readonly
from onepass.p1_product_ids import SELECTED_PRODUCT_IDS
from onepass.p1_payment_p0 import (
    PaymentContext,
    PaymentLane,
    SalesChannel,
    PaymentProvider,
)
from onepass.p1_rule_repository import P1RuleRepository
from onepass.p1_eligibility_repository import P1EligibilityRepository
from onepass.p1_monthly_db_repository import P1MonthlyDBRepository
from onepass.p1_rule_engine import RuleUsage
from onepass.p1_simulation_policy import (
    evaluate_p1_benefit,
    ExecutionMode,
)
from dataclasses import replace
from decimal import Decimal

from onepass.p1_dongbaek_candidate import (
    DongbaekInputs,
    evaluate_dongbaek_candidate,
    select_onepass_card,
)

def payment_context(lane: str, provider: str | None):
    lane_enum = PaymentLane(lane)
    channel = (
        SalesChannel.ONLINE
        if lane_enum != PaymentLane.OFFLINE
        else SalesChannel.OFFLINE
    )
    p = PaymentProvider(provider) if provider else None
    return PaymentContext(
        lane=lane_enum,
        sales_channel=channel,
        payment_provider=p,
    )


def fetch_customer_and_merchant(user_id, merchant_id):
    with connect_readonly() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT merchant_id, merchant_name, industry_code,
                   sub_group, brand, address, sales_band,
                   dongbaek_status
            FROM public.merchant
            WHERE merchant_id = %s
            """,
            (merchant_id,),
        )
        merchant = cur.fetchone()

        if not merchant:
            raise ValueError(f"MERCHANT_NOT_FOUND: {merchant_id}")

        if user_id:
            cur.execute(
                """
                SELECT user_id
                FROM public.user_card
                WHERE user_id = %s
                LIMIT 1
                """,
                (user_id,),
            )
            found = cur.fetchone()
            if not found:
                raise ValueError(f"USER_NOT_FOUND: {user_id}")
        else:
            cur.execute(
                """
                SELECT user_id
                FROM public.user_card
                WHERE product_id = ANY(%s)
                ORDER BY user_id
                LIMIT 1
                """,
                (list(SELECTED_PRODUCT_IDS),),
            )
            found = cur.fetchone()
            if not found:
                raise ValueError("NO_SYNTHETIC_USER")
            user_id = found["user_id"]

        cur.execute(
            """
            SELECT user_card_id, product_id, card_status,
                   default_preference_rank
            FROM public.user_card
            WHERE user_id = %s
            ORDER BY default_preference_rank NULLS LAST, product_id
            """,
            (user_id,),
        )
        cards = cur.fetchall()

        cur.execute(
            """
            SELECT DISTINCT base_month
            FROM public.card_month_close
            ORDER BY base_month DESC
            LIMIT 12
            """
        )
        months = [r["base_month"] for r in cur.fetchall()]

    return user_id, dict(merchant), [dict(r) for r in cards], months



def quote_bnk_card(
    card,
    merchant_id,
    amount,
    payment,
    as_of,
    base_month,
    rules_repo,
    eligibility_repo,
    monthly_repo,
    usage_state=None,
):
    """
    6월 신규 가상 시뮬레이션의 첫 거래를 계산한다.

    - 전월 실적: 5월 DB
    - 당월 혜택 사용액: 가상 상태 0원
    - 당월 이용 횟수: 가상 상태 0회
    - DB 변경 없음
    - PENDING 규칙은 계산하지 않음
    """

    product = card["product_id"]

    result = {
        "product_id": product,
        "user_card_id": card["user_card_id"],
        "status": "UNRESOLVED",
        "cash_benefit_won": None,
        "reason": [],
        "rules": [],
        "simulation_assumptions": [
            "CURRENT_MONTH_USAGE_STARTS_AT_ZERO",
            "PREVIOUS_PERFORMANCE_FROM_DB",
            "ASSUMED_RULES_ALLOWED_IN_SIMULATION",
        ],
    }

    if product not in SELECTED_PRODUCT_IDS:
        result["reason"].append("PRODUCT_OUTSIDE_BNK_SIX")
        return result

    if card.get("card_status") != "ACTIVE":
        result["reason"].append("CARD_NOT_CONFIRMED_ACTIVE")
        return result

    loaded_rules = rules_repo.load(product, as_of)

    if not loaded_rules:
        result["reason"].append("NO_ACTIVE_RULE")
        return result

    monthly = monthly_repo.load(
        user_card_id=card["user_card_id"],
        base_month=base_month,
    )

    monthly_rules = {
        r.rule_id: r
        for r in monthly.rules
    }

    # 실제 DB의 혜택 단위를 사용한다.
    # 포인트를 임의로 원화로 환산하지 않음.
    with connect_readonly() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT rule_id, reward_unit,
                       payment_channel_required,
                       stack_rule
                FROM public.benefit_rule
                WHERE product_id = %s
                """,
                (product,),
            )
            rule_details = {
                row["rule_id"]: dict(row)
                for row in cur.fetchall()
            }

    known = []
    unresolved = []

    for loaded in loaded_rules:
        rule = loaded.rule
        rule_id = rule.rule_id

        record = {
            "rule_id": rule_id,
            "source_status": loaded.source_status,
            "target_channel_status": None,
            "status": "UNRESOLVED",
            "benefit_won": None,
            "point_message": None,
            "reason": "",
        }

        eligibility = eligibility_repo.evaluate(
            rule_id=rule_id,
            merchant_id=merchant_id,
            payment=payment,
            as_of=as_of,
        )

        record["target_channel_status"] = eligibility.status

        if eligibility.status == "INELIGIBLE":
            record.update(
                status="INELIGIBLE",
                benefit_won=0,
                reason=eligibility.reason,
            )

        elif eligibility.status != "ELIGIBLE":
            record["reason"] = (
                "ELIGIBILITY:" + eligibility.reason
            )

        elif loaded.source_status == "PENDING":
            record.update(
                status="PENDING_REVIEW",
                reason="SOURCE_PENDING",
            )

        else:
            m = monthly_rules.get(rule_id)
            detail = rule_details.get(rule_id)

            if m is None:
                record["reason"] = "MONTHLY_RULE_NOT_FOUND"

            elif m.eligible_perf_won is None:
                record["reason"] = (
                    "PREVIOUS_PERFORMANCE_UNKNOWN"
                )

            elif detail is None:
                record["reason"] = "RULE_DETAILS_NOT_FOUND"

            else:
                prev_spend = int(m.eligible_perf_won)

                # 이전 달 DB의 benefit_used_won은
                # 이번 달 사용액으로 해석하지 않는다.
                # 새 가상 시뮬레이션의 첫 거래이므로 0.
                usage_state = usage_state or {}

                rule_state = usage_state.get(
                    ("RULE", card["user_card_id"], rule_id),
                    {"count": 0, "benefit_won": 0},
                )

                group_state = usage_state.get(
                    (
                        "GROUP",
                        card["user_card_id"],
                        rule.shared_cap_group,
                    ),
                    {"benefit_won": 0},
                )

                usage = RuleUsage(
                    monthly_count=rule_state["count"],
                    rule_benefit_used_won=rule_state["benefit_won"],
                    shared_benefit_used_won=group_state["benefit_won"],
                )

                # DB의 공유 한도 구간 중
                # 전월 실적에 해당하는 구간 선택.
                effective_cap = None

                if rule.shared_cap_group is not None:
                    matched_tiers = [
                        tier
                        for tier in loaded.cap_tiers
                        if (
                            tier.cap_group
                            == rule.shared_cap_group
                            and prev_spend
                            >= tier.perf_min_won
                        )
                    ]

                    if matched_tiers:
                        selected_tier = max(
                            matched_tiers,
                            key=lambda x: x.perf_min_won,
                        )
                        effective_cap = (
                            selected_tier.monthly_cap_won
                        )

                # 기존 정규화 로직에서 ANY 채널은
                # 구체적 적용 대상을 확인할 수 없어서
                # 별도 확인 상태로 유지된다.
                #
                # 이번 합성 실험에서는 eligibility가
                # 실제 업종/가맹점/레인을 판정했을 때만
                # 채널 판정 완료로 취급한다.
                model_reasons = list(loaded.reasons)

                if (
                    detail["payment_channel_required"]
                    == "ANY"
                    and eligibility.status == "ELIGIBLE"
                ):
                    model_reasons = [
                        r for r in model_reasons
                        if r not in {
                            "PAYMENT_CHANNEL_NOT_NORMALIZED",
                        }
                    ]

                # 이 실행에서는 전월 적격 실적값을
                # 성과 기준으로 사용하는 합성 가정.
                performance_assumed = (
                    "PERFORMANCE_BASIS_NOT_RESOLVED"
                    in model_reasons
                )

                if performance_assumed:
                    model_reasons.remove(
                        "PERFORMANCE_BASIS_NOT_RESOLVED"
                    )

                simulated_loaded = replace(
                    loaded,
                    reasons=tuple(model_reasons),
                )

                q = evaluate_p1_benefit(
                    simulated_loaded,
                    reward_unit=detail["reward_unit"],
                    amount_won=amount,
                    prev_month_spend_won=prev_spend,
                    payment=payment,
                    usage=usage,
                    mode=ExecutionMode.SIMULATION,
                    effective_monthly_cap_won=effective_cap,
                    target_eligibility_confirmed=True,
                    usage_state_confirmed=True,
                    performance_basis_confirmed=(
                        performance_assumed
                        or (
                            "PERFORMANCE_BASIS_NOT_RESOLVED"
                            not in model_reasons
                        )
                    ),
                )

                record.update(
                    status=q.status,
                    benefit_won=(
                        q.cash_benefit_won
                        if q.status == "ELIGIBLE"
                        else (
                            0 if q.status == "INELIGIBLE"
                            else None
                        )
                    ),
                    point_message=q.point_message,
                    reason=q.reason,
                )

                record["prev_month_spend_won"] = prev_spend

                if performance_assumed:
                    record["performance_basis"] = (
                        "SIMULATION_ASSUMPTION"
                    )

                if effective_cap is not None:
                    record["effective_monthly_cap_won"] = (
                        effective_cap
                    )

        result["rules"].append(record)

        if (
            record["status"] == "ELIGIBLE"
            and record["benefit_won"] is not None
        ):
            known.append(record["benefit_won"])

        elif record["status"] not in {
            "INELIGIBLE",
        }:
            unresolved.append(
                rule_id + ":" + record["reason"]
            )

    # MAX_ONLY 규칙의 단일 최대 혜택 비교.
    # 중복 적용 가능한 혜택을 합산하지 않는다.
    result["cash_benefit_won"] = (
        max(known) if known else (
            0 if not unresolved else None
        )
    )

    if unresolved:
        result["status"] = "PARTIAL_QUOTE"
        result["reason"] = unresolved

    else:
        # 모든 해당 규칙을 판정한 경우에만
        # 카드 비교가 가능한 것으로 표시한다.
        result["status"] = "COMPARABLE"
        result["reason"] = [
            "SIMULATED_MAX_SINGLE_BENEFIT"
        ]

    return result


def compare_bnk_candidates(candidates):
    """
    카드별 결과 비교.

    현금 혜택과 포인트를 임의 환산하지 않는다.
    미확정 후보가 있으면 전체 최적 카드를 확정하지 않는다.
    """

    cash_candidates = []
    review_candidates = []
    excluded_candidates = []

    for candidate in candidates:
        product_id = candidate["product_id"]
        status = candidate["status"]
        benefit = candidate["cash_benefit_won"]

        if status == "COMPARABLE" and benefit is not None:
            cash_candidates.append({
                "product_id": product_id,
                "cash_benefit_won": benefit,
                "basis": "SIMULATED_CASH_BENEFIT",
            })

        else:
            point_rules = [
                {
                    "rule_id": rule["rule_id"],
                    "message": rule.get("point_message"),
                }
                for rule in candidate.get("rules", [])
                if rule["status"] == "POINT_INFORMATION"
            ]

            review_candidates.append({
                "product_id": product_id,
                "status": status,
                "point_rules": point_rules,
                "reasons": candidate.get("reason", []),
            })

    cash_candidates.sort(
        key=lambda item: (
            -item["cash_benefit_won"],
            item["product_id"],
        )
    )

    cash_leader = (
        cash_candidates[0]
        if cash_candidates
        else None
    )

    # 금액 비교를 완료하지 않은 카드가 있다면
    # 전체 최적 카드라고 단정하지 않는다.
    comparison_complete = (
        len(review_candidates) == 0
        and len(cash_candidates) > 0
    )

    final_bnk_card = None
    selection_reason = None

    if comparison_complete:
        final_bnk_card = cash_leader["product_id"]
        selection_reason = "ALL_BNK_CANDIDATES_COMPARED"

    elif cash_leader is not None:
        selection_reason = (
            "CASH_LEADER_FOUND_BUT_OTHER_CANDIDATES_UNRESOLVED"
        )

    else:
        selection_reason = "NO_FULLY_CALCULATED_CASH_CANDIDATE"

    return {
        "comparison_complete": comparison_complete,
        "cash_leader": cash_leader,
        "cash_candidates": cash_candidates,
        "review_candidates": review_candidates,
        "final_bnk_card": final_bnk_card,
        "selection_reason": selection_reason,
        "comparison_policy": (
            "NO_ASSUMED_POINT_TO_KRW_CONVERSION"
        ),
    }

def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--user-id", default=None)
    ap.add_argument("--merchant-id", default="M00336")
    ap.add_argument("--amount", type=int, default=32000)
    ap.add_argument(
        "--lane",
        choices=["OFFLINE", "ONLINE", "SIMPLE_PAY"],
        default="OFFLINE",
    )
    ap.add_argument(
        "--provider",
        choices=["NAVERPAY", "KAKAOPAY", "SAMSUNGPAY"],
    )
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument(
        "--base-month",
        help="Month used for DB snapshot, e.g. 2026-09",
    )

    ap.add_argument(
    "--db-balance",
    type=int,
    default=None,
    help="Simulation-only Dongbaek balance in KRW",
)

    ap.add_argument(
        "--db-cashback-rate",
        type=Decimal,
        default=None,
        help="Simulation-only cashback fraction, e.g. 0.10",
    )

    ap.add_argument(
        "--db-cashback-remaining",
        type=int,
        default=None,
        help="Simulation-only remaining cashback amount in KRW",
    )

    args = ap.parse_args()

    if args.amount <= 0:
        ap.error("--amount must be positive")

    if (args.lane == "SIMPLE_PAY") != bool(args.provider):
        ap.error(
            "--provider is required only when --lane SIMPLE_PAY"
        )

    load_dotenv(Path(__file__).resolve().parent / ".env")

    pay = payment_context(args.lane, args.provider)

    user, merchant, cards, months = fetch_customer_and_merchant(
        args.user_id,
        args.merchant_id,
    )

    month = args.base_month or (
        months[0] if months else None
    )

    if not month:
        raise RuntimeError("NO_MONTHLY_CLOSE_DATA")

    rr = P1RuleRepository()
    er = P1EligibilityRepository()
    mr = P1MonthlyDBRepository()

    candidates = []

    for card in cards:
        try:
            candidates.append(
                quote_bnk_card(
                    card,
                    args.merchant_id,
                    args.amount,
                    pay,
                    args.as_of,
                    month,
                    rr,
                    er,
                    mr,
                )
            )
        except Exception as exc:
            candidates.append({
                "product_id": card["product_id"],
                "status": "UNRESOLVED",
                "cash_benefit_won": None,
                "reason": [
                    f"{type(exc).__name__}:{exc}"
                ],
                "rules": [],
            })

    comparison = compare_bnk_candidates(candidates)
    dongbaek_candidate = evaluate_dongbaek_candidate(
        merchant=merchant,
        amount_won=args.amount,
        lane=args.lane,
        inputs=DongbaekInputs(
            balance_won=args.db_balance,
            cashback_rate=args.db_cashback_rate,
            cashback_remaining_won=args.db_cashback_remaining,
        ),
    )

    onepass_decision = select_onepass_card(
        dongbaek=dongbaek_candidate,
        bnk_comparison=comparison,
    )

    out = {
        "bnk_candidates": candidates,
        "bnk_comparison": comparison,

        "dongbaek_candidate": dongbaek_candidate,
        "onepass_decision": onepass_decision,

        "best_fully_comparable_bnk_card": (
            comparison["final_bnk_card"]
        ),

        "onepass_final_selection": (
            onepass_decision["selected_card"]
        ),

        "final_selection_reason": (
            onepass_decision["reason"]
        ),
    }

    print(
        json.dumps(
            out,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
