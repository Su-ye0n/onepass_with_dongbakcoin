
# tests/test_p1_monthly_state.py

import pytest

from onepass.p1_monthly_state import (
    MonthlyKey,
    MonthlySnapshot,
    MonthlyStateError,
    MonthlyStateRegistry,
    RuleUsageRecord,
    build_monthly_snapshot,
)


def make_snapshot(
    records=None,
    expected=None,
    **kwargs,
):
    params = dict(
        key=MonthlyKey(
            "U001", "CARD001", "2026-10"
        ),
        previous_spend_won=400000,
        records=records if records is not None else [
            RuleUsageRecord(
                "BR_A", 3000, 2, "GROUP1"
            ),
            RuleUsageRecord(
                "BR_B", 2000, 1, "GROUP1"
            ),
        ],
        expected_rule_ids=expected or {
            "BR_A", "BR_B"
        },
        performance_basis_confirmed=True,
        usage_state_confirmed=True,
    )
    params.update(kwargs)
    return build_monthly_snapshot(**params)


def test_snapshot_build():
    s = make_snapshot()
    assert s.previous_spend_won == 400000
    assert s.usage.benefit_used_won["BR_A"] == 3000
    assert s.usage.benefit_count["BR_A"] == 2


def test_shared_group_aggregate():
    s = make_snapshot()
    assert s.usage.shared_used_won["GROUP1"] == 5000


def test_missing_previous_spend():
    with pytest.raises(
        MonthlyStateError,
        match="PREVIOUS_SPEND_MISSING",
    ):
        make_snapshot(previous_spend_won=None)


def test_unconfirmed_performance():
    with pytest.raises(
        MonthlyStateError,
        match="PERFORMANCE_BASIS_NOT_CONFIRMED",
    ):
        make_snapshot(
            performance_basis_confirmed=False
        )


def test_unconfirmed_usage():
    with pytest.raises(
        MonthlyStateError,
        match="USAGE_STATE_NOT_CONFIRMED",
    ):
        make_snapshot(
            usage_state_confirmed=False
        )


def test_missing_rule_blocked():
    with pytest.raises(
        MonthlyStateError,
        match="INCOMPLETE_RULE_USAGE",
    ):
        make_snapshot(
            records=[
                RuleUsageRecord("BR_A", 1000, 1)
            ]
        )


def test_confirmed_zero_usage():
    s = make_snapshot(
        records=[
            RuleUsageRecord("BR_A", 1000, 1)
        ],
        zero_usage_confirmed=True,
    )
    assert s.usage.benefit_used_won["BR_B"] == 0
    assert s.usage.benefit_count["BR_B"] == 0


def test_duplicate_rule_rejected():
    with pytest.raises(
        MonthlyStateError,
        match="DUPLICATE_RULE_USAGE",
    ):
        make_snapshot(
            records=[
                RuleUsageRecord("BR_A", 100, 1),
                RuleUsageRecord("BR_A", 200, 1),
            ]
        )


def test_unknown_rule_rejected():
    with pytest.raises(
        MonthlyStateError,
        match="UNKNOWN_RULE_USAGE",
    ):
        make_snapshot(
            records=[
                RuleUsageRecord("BR_X", 100, 1)
            ]
        )


def test_negative_usage_rejected():
    with pytest.raises(MonthlyStateError):
        RuleUsageRecord("BR_A", -100, 1)


def test_invalid_month():
    with pytest.raises(
        MonthlyStateError,
        match="INVALID_MONTH",
    ):
        MonthlyKey(
            "U001", "CARD001", "2026-13"
        )


def test_independent_users():
    registry = MonthlyStateRegistry()
    first = make_snapshot()

    second = make_snapshot(
        key=MonthlyKey(
            "U002", "CARD001", "2026-10"
        )
    )

    registry.add(first)
    registry.add(second)

    first.usage.benefit_used_won["BR_A"] += 1000

    assert (
        second.usage.benefit_used_won["BR_A"]
        == 3000
    )


def test_duplicate_snapshot_rejected():
    registry = MonthlyStateRegistry()
    snapshot = make_snapshot()
    registry.add(snapshot)

    with pytest.raises(
        MonthlyStateError,
        match="DUPLICATE_MONTHLY_SNAPSHOT",
    ):
        registry.add(snapshot)


def test_missing_snapshot_rejected():
    registry = MonthlyStateRegistry()

    with pytest.raises(
        MonthlyStateError,
        match="MONTHLY_SNAPSHOT_NOT_LOADED",
    ):
        registry.get(
            MonthlyKey(
                "U001", "CARD001", "2026-10"
            )
        )
