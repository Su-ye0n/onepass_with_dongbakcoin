
# tests/test_p1_contract_p0.py

import csv
from decimal import Decimal

import pytest

from onepass.p1_payment_p0 import (
    P1PaymentError,
    PaymentContext,
    parse_payment_context,
)
from onepass.p1_catalog_p0 import (
    CatalogValidationError,
    classify_calculation,
    load_benefit_catalog,
    normalize_benefit_row,
)


def sample_rule(**overrides):
    row = {
        "product_id": "P09",
        "benefit_seq": "1",
        "benefit_target_original": "네이버페이, 카카오페이, 삼성페이",
        "benefit_target_kind": "결제채널",
        "benefit_type": "할인",
        "benefit_value": "10%",
        "monthly_count_cap": "월2회",
        "channel_condition": "간편결제",
        "perf_tier_note": "전월 40만원 이상",
    }
    row.update(overrides)
    return row


def test_three_payment_lanes():
    contexts = [
        PaymentContext("OFFLINE", "OFFLINE"),
        PaymentContext("ONLINE", "ONLINE"),
        PaymentContext(
            "SIMPLE_PAY", "ONLINE", "NAVERPAY"
        ),
        PaymentContext(
            "SIMPLE_PAY", "OFFLINE", "SAMSUNGPAY"
        ),
    ]
    assert len(contexts) == 4


def test_qr_is_not_supported():
    with pytest.raises(
        P1PaymentError,
        match="UNSUPPORTED_PAYMENT",
    ):
        PaymentContext("QR", "OFFLINE")


def test_dongbaek_qr_is_not_supported():
    with pytest.raises(
        P1PaymentError,
        match="UNSUPPORTED_PAYMENT_PROVIDER",
    ):
        PaymentContext(
            "SIMPLE_PAY",
            "OFFLINE",
            "DONGBAEK_QR",
        )


def test_simple_pay_requires_provider():
    with pytest.raises(
        P1PaymentError,
        match="SIMPLE_PAY_PROVIDER_REQUIRED",
    ):
        PaymentContext("SIMPLE_PAY", "ONLINE")


def test_invalid_lane_channel_combination():
    with pytest.raises(
        P1PaymentError,
        match="ONLINE_LANE_CHANNEL_MISMATCH",
    ):
        PaymentContext("ONLINE", "OFFLINE")


def test_parse_payment_context():
    result = parse_payment_context({
        "lane": "SIMPLE_PAY",
        "sales_channel": "ONLINE",
        "payment_provider": "KAKAOPAY",
        "is_autopay": False,
    })
    assert result.payment_provider.value == "KAKAOPAY"


def test_percentage_normalization():
    kind, rate, fixed = classify_calculation(
        "할인", "10%"
    )

    assert kind == "RATE"
    assert rate == Decimal("0.10")
    assert fixed is None


def test_per_liter_not_converted_to_percent():
    kind, rate, fixed = classify_calculation(
        "리터당할인", "리터당 50원"
    )

    assert kind == "PER_LITER"
    assert rate is None
    assert fixed is None


def test_pod_pay_rule_needs_p1():
    result = normalize_benefit_row(sample_rule())

    assert result.rule_id == "P09_R01"
    assert result.rate == Decimal("0.10")
    assert result.supported_lanes == ("SIMPLE_PAY",)
    assert result.classification == "P1_CONDITIONAL"


def test_point_reward_separate_from_cash():
    result = normalize_benefit_row(
        sample_rule(
            product_id="P23",
            benefit_seq="3",
            benefit_target_kind="브랜드",
            benefit_type="포인트적립",
            benefit_value="5% 적립",
            channel_condition="",
        )
    )

    assert result.calculation_kind == "POINT_RATE"
    assert result.rate == Decimal("0.05")
    assert result.classification == "P1_COMPLEX"


def test_only_six_products_imported(tmp_path):
    path = tmp_path / "card_rules.csv"
    headers = [
        "product_id",
        "benefit_seq",
        "benefit_target_original",
        "benefit_target_kind",
        "benefit_type",
        "benefit_value",
    ]

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=headers
        )
        writer.writeheader()
        writer.writerow({
            key: sample_rule().get(key, "")
            for key in headers
        })
        writer.writerow({
            "product_id": "P01",
            "benefit_seq": "1",
            "benefit_target_original": "기타",
            "benefit_target_kind": "기타",
            "benefit_type": "할인",
            "benefit_value": "10%",
        })

    result = load_benefit_catalog(
        path, require_complete=False
    )

    assert len(result) == 1
    assert result[0].product_id == "P09"


def test_incomplete_catalog_rejected(tmp_path):
    path = tmp_path / "card_rules.csv"
    headers = [
        "product_id",
        "benefit_seq",
        "benefit_target_original",
        "benefit_target_kind",
        "benefit_type",
        "benefit_value",
    ]

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=headers
        )
        writer.writeheader()
        writer.writerow({
            key: sample_rule().get(key, "")
            for key in headers
        })

    with pytest.raises(
        CatalogValidationError,
        match="INCOMPLETE_PRODUCT",
    ):
        load_benefit_catalog(path)
