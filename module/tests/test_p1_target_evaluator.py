
# tests/test_p1_target_evaluator.py

import pytest

from onepass.p1_target_evaluator import (
    MerchantContext,
    TargetCondition,
    TargetStatus,
    evaluate_target,
)


CATEGORY_MAP = {
    "CAFE_BAKERY": "FOOD_CAFE",
    "RESTAURANT": "FOOD_REST",
    "FUEL_AUTO": "FUEL",
}


def condition(
    target_type,
    target_code,
    apply_type="INCLUDE",
    rule_id="BR_TEST",
):
    return TargetCondition(
        rule_id=rule_id,
        target_type=target_type,
        target_code=target_code,
        apply_type=apply_type,
    )


def evaluate(
    conditions,
    merchant_id="M00001",
    industry_code="CAFE_BAKERY",
    category_map=None,
):
    return evaluate_target(
        rule_id="BR_TEST",
        merchant=MerchantContext(
            merchant_id=merchant_id,
            industry_code=industry_code,
        ),
        conditions=conditions,
        category_map=(
            CATEGORY_MAP
            if category_map is None
            else category_map
        ),
    )


def test_category_included():
    result = evaluate([
        condition("CATEGORY", "FOOD_CAFE"),
    ])
    assert result.status == TargetStatus.ELIGIBLE


def test_category_not_matched():
    result = evaluate([
        condition("CATEGORY", "FUEL"),
    ])
    assert result.status == TargetStatus.INELIGIBLE
    assert result.reason == "NO_INCLUDE_MATCH"


def test_merchant_included():
    result = evaluate([
        condition("MERCHANT", "M00001"),
    ])
    assert result.eligible


def test_different_merchant_is_not_included():
    result = evaluate([
        condition("MERCHANT", "M00002"),
    ])
    assert result.status == TargetStatus.INELIGIBLE


def test_exclusion_overrides_inclusion():
    result = evaluate([
        condition("CATEGORY", "FOOD_CAFE"),
        condition(
            "MERCHANT",
            "M00001",
            "EXCLUDE",
        ),
    ])
    assert result.status == TargetStatus.INELIGIBLE
    assert result.reason == "EXPLICITLY_EXCLUDED"


def test_category_exclusion_overrides_merchant():
    result = evaluate([
        condition("MERCHANT", "M00001"),
        condition(
            "CATEGORY",
            "FOOD_CAFE",
            "EXCLUDE",
        ),
    ])
    assert result.status == TargetStatus.INELIGIBLE


def test_unmapped_category_is_unresolved():
    result = evaluate(
        [condition("CATEGORY", "FOOD_CAFE")],
        category_map={},
    )
    assert result.status == TargetStatus.UNRESOLVED
    assert result.reason == "CATEGORY_MAPPING_MISSING"


def test_merchant_only_does_not_need_category_map():
    result = evaluate(
        [condition("MERCHANT", "M00001")],
        category_map={},
    )
    assert result.eligible


def test_missing_target_rules_is_unresolved():
    result = evaluate([])
    assert result.status == TargetStatus.UNRESOLVED


def test_channel_target_is_not_silently_accepted():
    result = evaluate([
        condition("CHANNEL", "NAVERPAY"),
    ])
    assert result.status == TargetStatus.UNRESOLVED
    assert result.reason == "UNSUPPORTED_TARGET_CONDITION"


def test_mixed_rule_ids_rejected():
    result = evaluate([
        condition(
            "CATEGORY",
            "FOOD_CAFE",
            rule_id="BR_OTHER",
        ),
    ])
    assert result.status == TargetStatus.UNRESOLVED
    assert result.reason == "RULE_ID_MISMATCH"


@pytest.mark.parametrize(
    "target_type,apply_type",
    [
        ("UNKNOWN", "INCLUDE"),
        ("CATEGORY", "UNKNOWN"),
        ("", "INCLUDE"),
    ],
)
def test_invalid_condition_is_unresolved(
    target_type, apply_type
):
    result = evaluate([
        condition(
            target_type,
            "FOOD_CAFE",
            apply_type,
        )
    ])
    assert result.status == TargetStatus.UNRESOLVED


def test_missing_merchant_id_is_unresolved():
    result = evaluate(
        [condition("CATEGORY", "FOOD_CAFE")],
        merchant_id="",
    )
    assert result.status == TargetStatus.UNRESOLVED
