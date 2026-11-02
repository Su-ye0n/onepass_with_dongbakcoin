
# tests/test_p1_rule_repository.py

from decimal import Decimal

from onepass.p1_rule_repository import (
    map_db_rule,
    RuleTarget,
)


def example_row(**changes):
    row = {
        "rule_id": "TEST_ONLINE",
        "product_id": "P09",
        "benefit_type": "RATE",
        "rate": Decimal("0.10"),
        "fixed_amount_won": None,
        "min_amount_won": 10000,
        "per_tx_cap_won": 3000,
        "monthly_cap_won": 20000,
        "shared_cap_group": None,
        "day_condition": "ALL",
        "monthly_count_cap": None,
        "perf_threshold_won": 400000,
        "perf_basis_code": None,
        "reward_unit": "CASH",
        "stack_rule": "MAX_ONLY",
        "payment_channel_required": "ONLINE",
        "rounding_mode": "FLOOR",
        "source_status": "VERIFIED",
    }
    row.update(changes)
    return row


def online_target():
    return [{
        "target_type": "CHANNEL",
        "target_code": "ONLINE",
        "apply_type": "INCLUDE",
    }]


def test_basic_online_rule_mapping():
    result = map_db_rule(
        example_row(), online_target(), []
    )
    assert result.status == "READY"
    assert result.rule.verified is True
    assert result.rule.value == Decimal("0.10")
    assert result.rule.prev_month_min_won == 400000
    assert result.rule.allowed_lanes == frozenset({
        "ONLINE"
    })


def test_unverified_source_blocked():
    result = map_db_rule(
        example_row(source_status="PENDING"),
        online_target(),
        [],
    )
    assert result.status == "PENDING_REVIEW"
    assert result.rule.verified is False
    assert "SOURCE_NOT_VERIFIED" in result.reasons


def test_category_target_requires_evaluator():
    result = map_db_rule(
        example_row(),
        [{
            "target_type": "CATEGORY",
            "target_code": "FOOD",
            "apply_type": "INCLUDE",
        }],
        [],
    )
    assert result.status == "PENDING_REVIEW"
    assert "TARGET_EVALUATOR_REQUIRED" in result.reasons


def test_missing_target_not_global():
    result = map_db_rule(
        example_row(), [], []
    )
    assert result.status == "PENDING_REVIEW"
    assert "TARGET_NOT_DEFINED" in result.reasons


def test_shared_cap_requires_resolution():
    result = map_db_rule(
        example_row(
            shared_cap_group="GROUP_A"
        ),
        online_target(),
        [{
            "tier_id": "T1",
            "cap_group": "GROUP_A",
            "perf_min_won": 400000,
            "monthly_cap_won": 20000,
        }],
    )
    assert result.status == "PENDING_REVIEW"
    assert len(result.cap_tiers) == 1
    assert "SHARED_CAP_RESOLUTION_REQUIRED" in (
        result.reasons
    )


def test_monthly_count_requires_state():
    result = map_db_rule(
        example_row(monthly_count_cap=2),
        online_target(),
        [],
    )
    assert result.status == "PENDING_REVIEW"
    assert "MONTHLY_USAGE_STATE_REQUIRED" in result.reasons


def test_point_reward_blocked():
    result = map_db_rule(
        example_row(reward_unit="POINT"),
        online_target(),
        [],
    )
    assert result.status == "PENDING_REVIEW"
    assert "UNSUPPORTED_REWARD_UNIT" in result.reasons


def test_unknown_channel_blocked():
    result = map_db_rule(
        example_row(
            payment_channel_required="CARD"
        ),
        online_target(),
        [],
    )
    assert result.status == "PENDING_REVIEW"
    assert "PAYMENT_CHANNEL_NOT_NORMALIZED" in (
        result.reasons
    )


def test_invalid_rate_blocked():
    result = map_db_rule(
        example_row(rate=Decimal("2.0")),
        online_target(),
        [],
    )
    assert result.status == "PENDING_REVIEW"
    assert "INVALID_BENEFIT_VALUE" in result.reasons


def test_target_dataclass():
    target = RuleTarget(
        "CHANNEL", "ONLINE", "INCLUDE"
    )
    assert target.target_code == "ONLINE"
