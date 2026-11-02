
# tests/test_p1_rule_engine.py

from dataclasses import replace
from decimal import Decimal

import pytest

from onepass.p1_payment_p0 import PaymentContext
from onepass.p1_rule_engine import (
    NormalizedRule,
    RuleUsage,
    quote_rule,
)


def payment(
    lane="SIMPLE_PAY",
    provider="NAVERPAY",
):
    if lane == "SIMPLE_PAY":
        return PaymentContext(
            lane, "ONLINE", provider
        )

    return PaymentContext(lane, lane)


def sample_rule(**overrides):
    rule = NormalizedRule(
        rule_id="TEST_R01",
        product_id="TEST_PRODUCT",
        calculation_type="RATE",
        value=Decimal("0.10"),
        verified=True,
        min_payment_won=10000,
        prev_month_min_won=400000,
        per_tx_cap_won=5000,
        monthly_cap_won=20000,
        monthly_count_cap=2,
        allowed_lanes=frozenset({"SIMPLE_PAY"}),
        allowed_providers=frozenset({
            "NAVERPAY", "KAKAOPAY", "SAMSUNGPAY"
        }),
    )
    return replace(rule, **overrides)


def quote(rule=None, **kwargs):
    data = {
        "amount_won": 30000,
        "prev_month_spend_won": 500000,
        "payment": payment(),
    }
    data.update(kwargs)
    return quote_rule(rule or sample_rule(), **data)


def test_verified_rate_calculation():
    result = quote()
    assert result.decision == "ELIGIBLE"
    assert result.benefit_won == 3000


def test_unverified_rule_not_calculated():
    result = quote(sample_rule(verified=False))
    assert result.decision == "PENDING_REVIEW"
    assert result.benefit_won == 0


def test_minimum_payment_failure():
    result = quote(amount_won=9000)
    assert result.reason == "MIN_PAYMENT_NOT_MET"


def test_previous_month_performance_failure():
    result = quote(prev_month_spend_won=399999)
    assert result.reason == "PREV_MONTH_PERFORMANCE_NOT_MET"


def test_monthly_count_exhausted():
    result = quote(
        usage=RuleUsage(monthly_count=2)
    )
    assert result.reason == "MONTHLY_COUNT_EXHAUSTED"


def test_per_transaction_cap():
    result = quote(amount_won=100000)
    assert result.benefit_won == 5000


def test_monthly_cap_remaining():
    result = quote(
        usage=RuleUsage(
            rule_benefit_used_won=19000
        )
    )
    assert result.benefit_won == 1000


def test_shared_cap_requires_resolved_limit():
    rule = sample_rule(
        shared_cap_group="GROUP_A"
    )
    result = quote(rule)

    assert result.decision == "PENDING_REVIEW"
    assert result.reason == "SHARED_CAP_NOT_RESOLVED"


def test_shared_cap_remaining():
    rule = sample_rule(
        shared_cap_group="GROUP_A"
    )
    result = quote(
        rule,
        usage=RuleUsage(
            shared_benefit_used_won=19500
        ),
        effective_monthly_cap_won=20000,
    )
    assert result.benefit_won == 500


def test_shared_cap_exhausted():
    rule = sample_rule(
        shared_cap_group="GROUP_A"
    )
    result = quote(
        rule,
        usage=RuleUsage(
            shared_benefit_used_won=20000
        ),
        effective_monthly_cap_won=20000,
    )
    assert result.decision == "INELIGIBLE"
    assert result.benefit_won == 0


def test_provider_mismatch():
    rule = sample_rule(
        allowed_providers=frozenset({"NAVERPAY"})
    )
    result = quote(
        rule,
        payment=payment(
            "SIMPLE_PAY", "KAKAOPAY"
        ),
    )
    assert result.reason == "PAYMENT_PROVIDER_MISMATCH"


def test_lane_mismatch():
    result = quote(
        payment=payment("OFFLINE")
    )
    assert result.reason == "PAYMENT_LANE_MISMATCH"


def test_fixed_amount_calculation():
    rule = sample_rule(
        calculation_type="FIXED",
        value=Decimal("1500"),
        per_tx_cap_won=None,
    )
    result = quote(rule)

    assert result.benefit_won == 1500


def test_floor_rounding():
    rule = sample_rule(
        value=Decimal("0.003"),
        min_payment_won=0,
        per_tx_cap_won=None,
    )
    result = quote(
        rule,
        amount_won=1099,
    )
    assert result.benefit_won == 3


def test_quote_does_not_mutate_usage():
    usage = RuleUsage(
        monthly_count=1,
        rule_benefit_used_won=1000,
        shared_benefit_used_won=500,
    )
    original = usage

    result = quote(usage=usage)

    assert result.decision == "ELIGIBLE"
    assert usage == original


def test_invalid_rate_rejected():
    with pytest.raises(
        ValueError, match="INVALID_RATE"
    ):
        sample_rule(value=Decimal("1.2"))


def test_invalid_monthly_count_rejected():
    with pytest.raises(
        ValueError,
        match="INVALID_MONTHLY_COUNT_CAP",
    ):
        sample_rule(monthly_count_cap=0)


def test_invalid_amount_rejected():
    with pytest.raises(
        ValueError,
        match="INVALID_TRANSACTION_AMOUNT",
    ):
        quote(amount_won=-1)
