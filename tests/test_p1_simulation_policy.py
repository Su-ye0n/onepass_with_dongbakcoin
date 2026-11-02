
# tests/test_p1_simulation_policy.py

from dataclasses import replace
from decimal import Decimal

from onepass.p1_payment_p0 import PaymentContext
from onepass.p1_rule_engine import NormalizedRule
from onepass.p1_rule_repository import LoadedRule
from onepass.p1_simulation_policy import (
    ExecutionMode,
    evaluate_p1_benefit,
    summarize_cash_benefits,
)


def payment():
    return PaymentContext("OFFLINE", "OFFLINE")


def loaded_rule(
    *,
    rate="0.10",
    source="ASSUMED",
    reasons=("SOURCE_NOT_VERIFIED",),
):
    rule = NormalizedRule(
        rule_id="BR_P07_FUEL",
        product_id="P07",
        calculation_type="RATE",
        value=Decimal(rate),
        verified=False,
        allowed_lanes=frozenset({"OFFLINE"}),
    )
    return LoadedRule(
        rule=rule,
        targets=(),
        cap_tiers=(),
        status="PENDING_REVIEW",
        reasons=reasons,
        source_status=source,
    )


def evaluate(loaded, **changes):
    arguments = dict(
        reward_unit="CASH",
        amount_won=100000,
        prev_month_spend_won=500000,
        payment=payment(),
        mode=ExecutionMode.SIMULATION,
    )
    arguments.update(changes)
    return evaluate_p1_benefit(loaded, **arguments)


def test_assumed_rule_runs_in_simulation():
    result = evaluate(loaded_rule())
    assert result.status == "ELIGIBLE"
    assert result.cash_benefit_won == 10000
    assert result.assumptions_applied


def test_assumed_rule_blocked_in_verified_mode():
    result = evaluate(
        loaded_rule(),
        mode=ExecutionMode.VERIFIED,
    )
    assert result.status == "PENDING_REVIEW"
    assert result.cash_benefit_won == 0


def test_verified_rule_runs():
    result = evaluate(
        loaded_rule(
            source="VERIFIED",
            reasons=(),
        ),
        mode=ExecutionMode.VERIFIED,
    )
    assert result.status == "ELIGIBLE"
    assert not result.assumptions_applied


def test_pending_rule_never_runs():
    result = evaluate(
        loaded_rule(source="PENDING"),
    )
    assert result.status == "PENDING_REVIEW"


def test_fuel_percentage_discount():
    # Synthetic fuel rule rate, not a per-liter calculation.
    result = evaluate(
        loaded_rule(rate="0.03636")
    )
    assert result.status == "ELIGIBLE"
    assert result.cash_benefit_won == 3636


def test_green_point_not_converted_to_cash():
    result = evaluate(
        loaded_rule(),
        reward_unit="POINT",
    )
    assert result.status == "POINT_INFORMATION"
    assert result.cash_benefit_won == 0
    assert "포인트" in result.point_message


def test_point_excluded_from_cash_summary():
    cash = evaluate(
        loaded_rule(rate="0.01")
    )
    point = evaluate(
        loaded_rule(),
        reward_unit="POINT",
    )
    summary = summarize_cash_benefits([cash, point])

    assert summary["max_single_cash_benefit_won"] == 1000
    assert summary["has_point_candidate"]
    assert summary["comparison_is_complete"] is False


def test_unresolved_merchant_target_remains_blocked():
    result = evaluate(
        loaded_rule(
            reasons=(
                "SOURCE_NOT_VERIFIED",
                "TARGET_EVALUATOR_REQUIRED",
            )
        )
    )
    assert result.status == "PENDING_REVIEW"


def test_unresolved_shared_cap_remains_blocked():
    result = evaluate(
        loaded_rule(
            reasons=(
                "SOURCE_NOT_VERIFIED",
                "SHARED_CAP_RESOLUTION_REQUIRED",
            )
        )
    )
    assert result.status == "PENDING_REVIEW"


def test_unknown_reward_unit_blocked():
    result = evaluate(
        loaded_rule(),
        reward_unit="MILES",
    )
    assert result.status == "PENDING_REVIEW"
