
# onepass/p1_simulation_policy.py

"""P1 simulation execution policy.

Separate source assurance from actual calculation eligibility.
Points are never converted to KRW.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Any

from .p1_payment_p0 import PaymentContext
from .p1_rule_engine import RuleUsage, quote_rule
from .p1_rule_repository import LoadedRule


class ExecutionMode(str, Enum):
    SIMULATION = "SIMULATION"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True)
class P1BenefitResult:
    rule_id: str
    status: str
    cash_benefit_won: int
    point_message: str | None
    reason: str
    source_status: str
    assumptions_applied: bool


def evaluate_p1_benefit(
    loaded: LoadedRule,
    *,
    reward_unit: str,
    amount_won: int,
    prev_month_spend_won: int,
    payment: PaymentContext,
    usage: RuleUsage = RuleUsage(),
    mode: ExecutionMode = ExecutionMode.SIMULATION,
    effective_monthly_cap_won: int | None = None,
    target_eligibility_confirmed: bool = False,
    usage_state_confirmed: bool = False,
    performance_basis_confirmed: bool = False,
) -> P1BenefitResult:
    """Quote an explicitly supported rule without side effects.

    Callers must independently resolve category/merchant,
    performance exclusions and monthly usage state.
    Flags are trusted only when backed by actual checks.
    """

    mode = ExecutionMode(mode)
    source = loaded.source_status
    rule = loaded.rule

    assumptions_applied = (
        mode == ExecutionMode.SIMULATION
        and source == "ASSUMED"
    )

    def result(status: str, reason: str,
               cash: int = 0,
               point_message: str | None = None):
        return P1BenefitResult(
            rule_id=rule.rule_id,
            status=status,
            cash_benefit_won=cash,
            point_message=point_message,
            reason=reason,
            source_status=source,
            assumptions_applied=assumptions_applied,
        )

    if source == "PENDING":
        return result("PENDING_REVIEW", "SOURCE_PENDING")

    if source not in {"VERIFIED", "ASSUMED"}:
        return result(
            "PENDING_REVIEW",
            "SOURCE_STATUS_UNSUPPORTED",
        )

    if mode == ExecutionMode.VERIFIED and source != "VERIFIED":
        return result(
            "PENDING_REVIEW",
            "VERIFIED_MODE_REQUIRES_VERIFIED_SOURCE",
        )

    # Points do not enter won-denominated cash comparisons.
    # This is an informational candidate, not confirmed earnings.
    if reward_unit == "POINT":
        return result(
            "POINT_INFORMATION",
            "POINT_CALCULATION_DEFERRED",
            point_message="추가 포인트 적립 가능 (조건 확인 필요)",
        )

    if reward_unit != "CASH":
        return result(
            "PENDING_REVIEW",
            "UNKNOWN_REWARD_UNIT",
        )

    # The existing repository can flag unresolved conditions.
    # An ASSUMED source is allowed for simulation, but no
    # unsupported condition is silently waived.
    unresolved = set(loaded.reasons) - {
        "SOURCE_NOT_VERIFIED",
    }

    if (
        "TARGET_NOT_DEFINED" in unresolved
        or "TARGET_EVALUATOR_REQUIRED" in unresolved
        or "CHANNEL_TARGET_INCONSISTENT" in unresolved
    ):
        if target_eligibility_confirmed:
            unresolved -= {
                "TARGET_NOT_DEFINED",
                "TARGET_EVALUATOR_REQUIRED",
                "CHANNEL_TARGET_INCONSISTENT",
            }

    if (
        "MONTHLY_USAGE_STATE_REQUIRED" in unresolved
        and usage_state_confirmed
    ):
        unresolved.remove("MONTHLY_USAGE_STATE_REQUIRED")

    if (
        "PERFORMANCE_BASIS_NOT_RESOLVED" in unresolved
        and performance_basis_confirmed
    ):
        unresolved.remove("PERFORMANCE_BASIS_NOT_RESOLVED")

    if "SHARED_CAP_RESOLUTION_REQUIRED" in unresolved:
        if (
            effective_monthly_cap_won is not None
            and usage_state_confirmed
        ):
            unresolved.remove("SHARED_CAP_RESOLUTION_REQUIRED")

    if unresolved:
        return result(
            "PENDING_REVIEW",
            "UNRESOLVED:" + ",".join(sorted(unresolved)),
        )

    # If an imported rule was originally blocked by its
    # assurance status only, allow a temporary verified
    # DTO for pure calculation; never modify DB assurance.
    executable = replace(rule, verified=True)

    quoted = quote_rule(
        executable,
        amount_won=amount_won,
        prev_month_spend_won=prev_month_spend_won,
        payment=payment,
        usage=usage,
        effective_monthly_cap_won=effective_monthly_cap_won,
    )

    return result(
        quoted.decision,
        quoted.reason,
        cash=quoted.benefit_won,
    )


def summarize_cash_benefits(
    results: list[P1BenefitResult],
) -> dict[str, Any]:
    """Do NOT add overlapping benefits blindly.

    Returns the largest independently quoted cash benefit
    only, not a complete card-level stacking calculation.
    """
    cash = [
        item.cash_benefit_won
        for item in results
        if item.status == "ELIGIBLE"
    ]

    return {
        "max_single_cash_benefit_won": max(
            cash, default=0
        ),
        "has_point_candidate": any(
            item.status == "POINT_INFORMATION"
            for item in results
        ),
        "has_unresolved_rules": any(
            item.status == "PENDING_REVIEW"
            for item in results
        ),
        "comparison_is_complete": False,
    }
