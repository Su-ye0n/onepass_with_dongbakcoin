
# tests/test_p1_lane_evaluator.py

import pytest

from onepass.p1_lane_evaluator import (
    evaluate_lane,
    evaluate_card_lanes,
)
from onepass.p1_payment_p0 import PaymentContext


def pod_pay_rule():
    return {
        "source_rule_id": "P09_R01",
        "product_id": "P09",
        "target_original": (
            "P(Pay) 간편결제 : "
            "네이버페이, 카카오페이, 삼성페이"
        ),
        "condition_json": {},
    }


@pytest.mark.parametrize(
    "provider",
    ["NAVERPAY", "KAKAOPAY", "SAMSUNGPAY"],
)
def test_supported_simple_pay_providers(provider):
    payment = PaymentContext(
        "SIMPLE_PAY", "ONLINE", provider
    )

    result = evaluate_lane(
        pod_pay_rule(), payment
    )

    assert result.decision == "CHANNEL_MATCHED"
    assert result.can_calculate_benefit is False


@pytest.mark.parametrize(
    "lane,channel",
    [
        ("OFFLINE", "OFFLINE"),
        ("ONLINE", "ONLINE"),
    ],
)
def test_direct_card_not_eligible_for_pay_rule(
    lane, channel
):
    result = evaluate_lane(
        pod_pay_rule(),
        PaymentContext(lane, channel),
    )

    assert result.decision == "NOT_APPLICABLE"


def test_unknown_rule_fails_closed_for_calculation():
    rule = {
        "source_rule_id": "P16_R01",
        "product_id": "P16",
        "target_original": "아파트관리비 자동납부",
    }

    result = evaluate_lane(
        rule,
        PaymentContext("ONLINE", "ONLINE"),
    )

    assert result.decision == "NEEDS_RULE_REVIEW"
    assert result.can_calculate_benefit is False


def test_source_changed_requires_review():
    rule = pod_pay_rule()
    rule["target_original"] = "다른 혜택"

    result = evaluate_lane(
        rule,
        PaymentContext(
            "SIMPLE_PAY", "ONLINE", "NAVERPAY"
        ),
    )

    assert result.decision == "NEEDS_RULE_REVIEW"


def test_all_benefits_preserved():
    card = {
        "benefits": [
            pod_pay_rule(),
            {
                "source_rule_id": "P09_R02",
                "product_id": "P09",
                "target_original": "편의점",
            },
        ]
    }

    result = evaluate_card_lanes(
        card,
        PaymentContext(
            "SIMPLE_PAY", "ONLINE", "NAVERPAY"
        ),
    )

    assert len(result) == 2
    assert result[0].decision == "CHANNEL_MATCHED"
    assert result[1].decision == "NEEDS_RULE_REVIEW"


def test_invalid_benefit_record_rejected():
    with pytest.raises(
        ValueError,
        match="INVALID_BENEFIT_RECORD",
    ):
        evaluate_lane(
            {"source_rule_id": ""},
            PaymentContext("OFFLINE", "OFFLINE"),
        )


def test_missing_benefit_list_rejected():
    with pytest.raises(
        ValueError,
        match="CARD_BENEFITS_NOT_LIST",
    ):
        evaluate_card_lanes(
            {"benefits": None},
            PaymentContext("OFFLINE", "OFFLINE"),
        )
