
from types import SimpleNamespace

import pytest

from onepass.p1_channel_evaluator import (
    ChannelStatus,
    evaluate_channel,
)


def payment(
    lane="OFFLINE",
    provider=None,
    sales_channel="OFFLINE",
):
    return SimpleNamespace(
    lane=lane,
    payment_provider=provider,
    sales_channel=sales_channel,
    )


def test_offline_any():
    result = evaluate_channel(
        payment=payment(),
        payment_channel_required="ANY",
    )
    assert result.status == ChannelStatus.ELIGIBLE


def test_online_any():
    result = evaluate_channel(
        payment=payment("ONLINE", None, "ONLINE"),
        payment_channel_required="ANY",
    )
    assert result.eligible


def test_simple_pay_any():
    result = evaluate_channel(
        payment=payment(
            "SIMPLE_PAY", "NAVERPAY", "ONLINE"
        ),
        payment_channel_required="ANY",
    )
    assert result.eligible


def test_online_card_required_matches():
    result = evaluate_channel(
        payment=payment("ONLINE", None, "ONLINE"),
        payment_channel_required="ONLINE",
    )
    assert result.eligible


def test_online_card_required_rejects_offline():
    result = evaluate_channel(
        payment=payment(),
        payment_channel_required="ONLINE",
    )
    assert result.status == ChannelStatus.INELIGIBLE


def test_online_card_required_rejects_simple_pay():
    result = evaluate_channel(
        payment=payment(
            "SIMPLE_PAY", "NAVERPAY", "ONLINE"
        ),
        payment_channel_required="ONLINE",
    )
    assert result.status == ChannelStatus.INELIGIBLE


def test_naverpay_included():
    result = evaluate_channel(
        payment=payment(
            "SIMPLE_PAY", "NAVERPAY", "ONLINE"
        ),
        payment_channel_required="ANY",
        channel_includes=["NAVERPAY"],
    )
    assert result.eligible


def test_other_provider_not_included():
    result = evaluate_channel(
        payment=payment(
            "SIMPLE_PAY", "KAKAOPAY", "ONLINE"
        ),
        payment_channel_required="ANY",
        channel_includes=["NAVERPAY"],
    )
    assert result.status == ChannelStatus.INELIGIBLE


def test_provider_exclusion_overrides_include():
    result = evaluate_channel(
        payment=payment(
            "SIMPLE_PAY", "NAVERPAY", "ONLINE"
        ),
        payment_channel_required="ANY",
        channel_includes=["NAVERPAY"],
        channel_excludes=["NAVERPAY"],
    )
    assert result.reason == "PROVIDER_EXCLUDED"


def test_provider_target_rejects_regular_card():
    result = evaluate_channel(
        payment=payment(),
        payment_channel_required="ANY",
        channel_includes=["NAVERPAY"],
    )
    assert result.status == ChannelStatus.INELIGIBLE


def test_unknown_provider_target_unresolved():
    result = evaluate_channel(
        payment=payment(
            "SIMPLE_PAY", "NAVERPAY", "ONLINE"
        ),
        payment_channel_required="ANY",
        channel_includes=["UNKNOWN_PAY"],
    )
    assert result.status == ChannelStatus.UNRESOLVED


def test_card_semantics_unresolved():
    result = evaluate_channel(
        payment=payment(),
        payment_channel_required="CARD",
    )
    assert result.status == ChannelStatus.UNRESOLVED


def test_qr_excluded():
    result = evaluate_channel(
        payment=payment(),
        payment_channel_required="QR",
    )
    assert result.status == ChannelStatus.INELIGIBLE


def test_missing_simple_pay_provider():
    result = evaluate_channel(
        payment=payment(
            "SIMPLE_PAY", None, "ONLINE"
        ),
        payment_channel_required="ANY",
    )
    assert result.status == ChannelStatus.UNRESOLVED


def test_provider_not_allowed_for_normal_card():
    result = evaluate_channel(
        payment=payment(
            "OFFLINE", "NAVERPAY", "OFFLINE"
        ),
        payment_channel_required="ANY",
    )
    assert result.status == ChannelStatus.UNRESOLVED


@pytest.mark.parametrize(
    "invalid_rule",
    ["", "SIMPLE_PAY", "UNKNOWN"],
)
def test_unknown_requirement_unresolved(invalid_rule):
    result = evaluate_channel(
        payment=payment(),
        payment_channel_required=invalid_rule,
    )
    assert result.status == ChannelStatus.UNRESOLVED
