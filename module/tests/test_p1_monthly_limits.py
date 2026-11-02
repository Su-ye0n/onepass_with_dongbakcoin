
# tests/test_p1_monthly_limits.py

import pytest

from onepass.p1_monthly_limits import (
    CapTier,
    LimitError,
    LimitRule,
    MonthlyUsage,
    apply_monthly_benefit,
    evaluate_monthly_limits,
    resolve_cap_tier,
)


def rule(**changes):
    defaults = {
        "rule_id": "BR_TEST",
        "product_id": "BNK_CR_P07",
        "perf_threshold_won": 300000,
        "monthly_cap_won": 10000,
        "monthly_count_cap": 3,
    }
    defaults.update(changes)
    return LimitRule(**defaults)


def check(
    *,
    selected_rule=None,
    quote=5000,
    previous=400000,
    usage=None,
    tiers=(),
    perf_confirmed=True,
    usage_confirmed=True,
):
    return evaluate_monthly_limits(
        rule=selected_rule or rule(),
        quoted_benefit_won=quote,
        previous_spend_won=previous,
        usage=usage if usage is not None else MonthlyUsage(),
        tiers=tiers,
        performance_basis_confirmed=perf_confirmed,
        usage_state_confirmed=usage_confirmed,
    )


def test_full_discount_available():
    result = check()
    assert result.eligible
    assert result.allowed_won == 5000


def test_performance_threshold_not_met():
    result = check(previous=200000)
    assert result.status == "INELIGIBLE"
    assert result.reason == "PERFORMANCE_THRESHOLD_NOT_MET"


def test_performance_basis_unconfirmed():
    result = check(perf_confirmed=False)
    assert result.status == "UNRESOLVED"


def test_previous_spend_missing():
    result = check(previous=None)
    assert result.reason == "PREVIOUS_SPEND_MISSING"


def test_usage_state_unconfirmed():
    result = check(usage_confirmed=False)
    assert result.reason == "MONTHLY_USAGE_STATE_REQUIRED"


def test_rule_monthly_cap_reduces_discount():
    usage = MonthlyUsage(
        benefit_used_won={"BR_TEST": 8000}
    )
    result = check(usage=usage)
    assert result.allowed_won == 2000


def test_rule_cap_exhausted():
    usage = MonthlyUsage(
        benefit_used_won={"BR_TEST": 10000}
    )
    result = check(usage=usage)
    assert result.reason == "MONTHLY_CAP_EXHAUSTED"


def test_monthly_count_exhausted():
    usage = MonthlyUsage(
        benefit_count={"BR_TEST": 3}
    )
    result = check(usage=usage)
    assert result.reason == "MONTHLY_COUNT_EXHAUSTED"


def test_tier_selection():
    tiers = (
        CapTier(0, 3000),
        CapTier(300000, 7000),
        CapTier(500000, 12000),
    )
    assert resolve_cap_tier(
        prev_month_spend_won=400000,
        tiers=tiers,
    ) == 7000


def test_shared_cap_limits_discount():
    usage = MonthlyUsage(
        shared_used_won={"GROUP_A": 6000}
    )
    result = check(
        selected_rule=rule(
            shared_cap_group="GROUP_A"
        ),
        usage=usage,
        tiers=(CapTier(300000, 8000),),
    )
    assert result.allowed_won == 2000


def test_shared_cap_without_tier_is_unresolved():
    result = check(
        selected_rule=rule(
            shared_cap_group="GROUP_A"
        )
    )
    assert result.reason == "SHARED_CAP_TIER_MISSING"


def test_tier_without_shared_group():
    result = check(
        quote=5000,
        tiers=(CapTier(300000, 3000),),
    )
    assert result.allowed_won == 3000


def test_apply_updates_usage():
    usage = MonthlyUsage()
    selected_rule = rule()

    result = check(
        selected_rule=selected_rule,
        usage=usage,
    )

    apply_monthly_benefit(
        rule=selected_rule,
        decision=result,
        usage=usage,
    )

    assert usage.benefit_used_won["BR_TEST"] == 5000
    assert usage.benefit_count["BR_TEST"] == 1


def test_shared_group_updates():
    usage = MonthlyUsage()
    selected_rule = rule(
        shared_cap_group="GROUP_A"
    )

    result = check(
        selected_rule=selected_rule,
        usage=usage,
        tiers=(CapTier(0, 10000),),
    )

    apply_monthly_benefit(
        rule=selected_rule,
        decision=result,
        usage=usage,
    )

    assert usage.shared_used_won["GROUP_A"] == 5000


def test_negative_money_rejected():
    with pytest.raises(LimitError):
        check(quote=-100)


def test_ambiguous_tier():
    tiers = (
        CapTier(300000, 5000),
        CapTier(300000, 7000),
    )
    result = check(tiers=tiers)
    assert result.reason == "AMBIGUOUS_CAP_TIER"


def test_count_not_incremented_for_zero_benefit():
    usage = MonthlyUsage()
    selected_rule = rule()

    result = check(
        selected_rule=selected_rule,
        quote=0,
        usage=usage,
    )

    apply_monthly_benefit(
        rule=selected_rule,
        decision=result,
        usage=usage,
    )

    assert usage.benefit_count == {}
