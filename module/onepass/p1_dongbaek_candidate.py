
"""Dongbaek candidate evaluation for P1 simulation.

No automatic top-up, no DB writes.
Cashback inputs are explicit simulation assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN


@dataclass(frozen=True)
class DongbaekInputs:
    balance_won: int | None
    cashback_rate: Decimal | None
    cashback_remaining_won: int | None


def evaluate_dongbaek_candidate(
    merchant: dict,
    amount_won: int,
    lane: str,
    inputs: DongbaekInputs,
) -> dict:
    """Evaluate Dongbaek payment eligibility and cashback."""

    result = {
        "product_id": "PRD_DB_SYN",
        "status": "UNRESOLVED",
        "payment_possible": None,
        "cash_benefit_won": None,
        "reason": None,
        "simulation_inputs": {
            "balance_won": inputs.balance_won,
            "cashback_rate": (
                str(inputs.cashback_rate)
                if inputs.cashback_rate is not None
                else None
            ),
            "cashback_remaining_won": (
                inputs.cashback_remaining_won
            ),
        },
    }

    # 1. 결제금액 유효성
    if amount_won <= 0:
        result["reason"] = "INVALID_AMOUNT"
        return result

    # 2. 가맹점 등록 상태 구분
    merchant_status = merchant.get("dongbaek_status")

    if merchant_status == "NOT_REGISTERED":
        result.update(
            status="INELIGIBLE",
            payment_possible=False,
            cash_benefit_won=0,
            reason="MERCHANT_NOT_REGISTERED",
        )
        return result

    if merchant_status != "REGISTERED":
        result.update(
            status="UNRESOLVED",
            payment_possible=None,
            cash_benefit_won=None,
            reason="MERCHANT_REGISTRATION_UNKNOWN",
        )
        return result

    # 3. 결제 채널 검증
    # 온라인/간편결제는 실제 승인 경로가 확인되지 않았으므로
    # 동백전 사용 가능 여부를 확정하지 않는다.
    if lane != "OFFLINE":
        result["reason"] = "DONGBAEK_LANE_NOT_VERIFIED"
        return result

    # 4. 지갑 잔액 확인
    if inputs.balance_won is None:
        result["reason"] = "DONGBAEK_BALANCE_UNKNOWN"
        return result

    if inputs.balance_won < 0:
        result["reason"] = "INVALID_BALANCE"
        return result

    if inputs.balance_won < amount_won:
        result.update(
            status="INELIGIBLE",
            payment_possible=False,
            cash_benefit_won=0,
            reason="INSUFFICIENT_BALANCE_NO_AUTO_TOPUP",
        )
        return result

    # 잔액과 결제채널 조건 충족
    result["payment_possible"] = True

    # 5. 캐시백 정책 정보 확인
    # 매출구간 불명은 0% 캐시백과 구분한다.
    if (
        inputs.cashback_rate is None
        or inputs.cashback_remaining_won is None
    ):
        result["reason"] = "DONGBAEK_POLICY_UNKNOWN"
        return result

    rate = inputs.cashback_rate
    remaining = inputs.cashback_remaining_won

    if (
        not rate.is_finite()
        or rate < 0
        or rate > 1
    ):
        result["reason"] = "INVALID_CASHBACK_RATE"
        return result

    if remaining < 0:
        result["reason"] = "INVALID_CASHBACK_REMAINING"
        return result

    # 6. 예상 캐시백 계산
    estimated = int(
        (
            Decimal(amount_won) * rate
        ).to_integral_value(
            rounding=ROUND_DOWN
        )
    )

    cashback = min(estimated, remaining)

    result.update(
        status="COMPARABLE",
        cash_benefit_won=cashback,
        reason=(
            "DONGBAEK_CASHBACK_AVAILABLE"
            if cashback > 0
            else "DONGBAEK_CASHBACK_ZERO"
        ),
    )

    return result


def select_onepass_card(
    dongbaek: dict,
    bnk_comparison: dict,
) -> dict:
    """Select a candidate under Dongbaek-first policy.

    A positive Dongbaek cashback takes priority.
    BNK selection requires full comparison.

    Unresolved Dongbaek information must not be
    represented as a confirmed global optimum.
    """

    db_status = dongbaek["status"]
    db_benefit = dongbaek["cash_benefit_won"]

    # 1. 동백전 캐시백이 있으면 우선 선택
    if (
        db_status == "COMPARABLE"
        and dongbaek["payment_possible"] is True
        and db_benefit is not None
        and db_benefit > 0
    ):
        return {
            "selected_card": "PRD_DB_SYN",
            "selection_status": "SELECTED",
            "reason": "DONGBAEK_FIRST_WITH_CASHBACK",
            "estimated_cash_benefit_won": db_benefit,
            "decision_policy": "DONGBAEK_FIRST",
            "note": (
                "Selected by priority policy, "
                "not necessarily maximum benefit."
            ),
        }

    # 2. 동백전 평가가 미확정인 경우
    if db_status == "UNRESOLVED":
        # 동백전 결제 채널 지원이 불확실할 때는
        # BNK 현금 혜택 후보를 잠정 추천할 수 있다.
        if (
            dongbaek["reason"]
            == "DONGBAEK_LANE_NOT_VERIFIED"
        ):
            cash_leader = bnk_comparison.get(
                "cash_leader"
            )

            if cash_leader is not None:
                return {
                    "selected_card": (
                        cash_leader["product_id"]
                    ),
                    "selection_status": "PROVISIONAL",
                    "reason": (
                        "BNK_PROVISIONAL_"
                        "DONGBAEK_LANE_UNKNOWN"
                    ),
                    "estimated_cash_benefit_won": (
                        cash_leader["cash_benefit_won"]
                    ),
                    "decision_policy": "DONGBAEK_FIRST",
                    "warning": (
                        "동백전 결제 채널 지원 여부와 "
                        "BNK 결제 승인 가능 여부는 "
                        "검증되지 않았습니다."
                    ),
                }

        # 등록 상태 또는 캐시백 정책 미확인
        return {
            "selected_card": None,
            "selection_status": "UNRESOLVED",
            "reason": dongbaek["reason"],
            "estimated_cash_benefit_won": None,
            "decision_policy": "DONGBAEK_FIRST",
        }

    # 3. 동백전이 불가능하거나 캐시백이 0원인 경우
    bnk_card = bnk_comparison.get("final_bnk_card")

    if (
        bnk_comparison.get("comparison_complete")
        and bnk_card is not None
    ):
        cash_leader = bnk_comparison.get(
            "cash_leader"
        )

        return {
            "selected_card": bnk_card,
            "selection_status": "SELECTED",
            "reason": "BNK_FALLBACK",
            "estimated_cash_benefit_won": (
                cash_leader["cash_benefit_won"]
                if cash_leader is not None
                else None
            ),
            "decision_policy": "DONGBAEK_FIRST",
        }

    # 4. BNK 현금 혜택만 비교 가능한 경우
    cash_leader = bnk_comparison.get("cash_leader")

    if cash_leader is not None:
        return {
            "selected_card": cash_leader["product_id"],
            "selection_status": "PROVISIONAL",
            "reason": (
                "BNK_CASH_LEADER_WITH_UNRESOLVED_POINT"
            ),
            "estimated_cash_benefit_won": (
                cash_leader["cash_benefit_won"]
            ),
            "decision_policy": "DONGBAEK_FIRST",
            "warning": (
                "현금 혜택 기준 임시 선택입니다. "
                "포인트 혜택이 미확정이므로 "
                "전체 최적 카드로 확정할 수 없습니다."
            ),
        }

    # 5. 비교 가능한 후보 없음
    return {
        "selected_card": None,
        "selection_status": "UNRESOLVED",
        "reason": "NO_COMPARABLE_BNK_CANDIDATE",
        "estimated_cash_benefit_won": None,
        "decision_policy": "DONGBAEK_FIRST",
    }
