
# tests/test_m7_p0.py

from copy import deepcopy
from decimal import Decimal

import pytest

from onepass.engine import (
    BenefitRule,
    Card,
    CardType,
    DbPolicy,
    Merchant,
    Request,
    State,
    WalletBalance,
)
from onepass.replay_p0 import ReplayItem
from onepass.m6_p0 import run_m6_p0
from onepass.m7_p0 import (
    summarize_strategies,
    compare_to_onepass,
    rows_for_export,
)


def setup_case():
    cards = [
        Card(
            id="BANK",
            type=CardType.DEBIT,
            account_id="A001",
            rules=(
                BenefitRule(
                    id="CAFE5",
                    categories=("CAFE",),
                    rate=Decimal("0.05"),
                ),
            ),
        ),
        Card(
            id="DB",
            type=CardType.DONGBAEK_CHECK,
            account_id="A001",
            wallet_id="W001",
        ),
    ]

    state = State(
        accounts={"A001": 50000},
        wallets={
            "W001": WalletBalance(charge=20000)
        },
    )

    merchants = {
        "CAFE": Merchant(
            "CAFE", "CAFE", True, "LE_10B"
        ),
        "MART": Merchant(
            "MART", "MART", False, "LE_10B"
        ),
    }

    return cards, state, merchants


def make_item(rid, merchant_id, amount, minute=0):
    return ReplayItem(
        event_at=f"2026-06-15T12:{minute:02d}:00+09:00",
        event_seq=minute,
        request=Request(rid, merchant_id, amount),
    )


def execute(items):
    cards, state, merchants = setup_case()
    original = deepcopy(state)

    results = run_m6_p0(
        items=items,
        merchants=merchants,
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
        default_card_id="BANK",
    )

    assert state == original
    return results


def test_m7_single_transaction_metrics():
    items = [make_item("R1", "CAFE", 10000)]
    results = execute(items)

    summary = summarize_strategies(
        items=items,
        results=results,
    )

    assert set(summary) == {"A2", "A3", "B"}

    assert summary["A2"].benefit_won == 500
    assert summary["A3"].benefit_won == 1000
    assert summary["B"].benefit_won == 1000

    assert summary["B"].approved_count == 1
    assert summary["B"].declined_count == 0
    assert summary["B"].requested_won == 10000
    assert summary["B"].approved_won == 10000
    assert summary["B"].approval_rate == Decimal("1")
    assert summary["B"].benefit_rate == Decimal("0.1")


def test_m7_onepass_vs_baselines():
    items = [make_item("R1", "CAFE", 10000)]
    results = execute(items)

    comparisons = compare_to_onepass(
        items=items,
        results=results,
    )

    assert set(comparisons) == {"A2", "A3"}

    a2 = comparisons["A2"]
    assert a2.benefit_delta_won == 500
    assert a2.approved_delta_won == 0
    assert a2.approved_count_delta == 0
    assert a2.same_approval_benefit_delta_won == 500

    a3 = comparisons["A3"]
    assert a3.benefit_delta_won == 0
    assert a3.same_approval_benefit_delta_won == 0


def test_m7_multiple_transactions():
    items = [
        make_item("R1", "CAFE", 10000, 0),
        make_item("R2", "MART", 10000, 1),
    ]

    results = execute(items)

    summaries = summarize_strategies(
        items=items,
        results=results,
    )

    for name in ("A2", "A3", "B"):
        assert summaries[name].request_count == 2
        assert summaries[name].approved_count == 2
        assert summaries[name].approved_won == 20000

    assert summaries["A2"].benefit_won == 500
    assert summaries["A3"].benefit_won == 1000
    assert summaries["B"].benefit_won == 1000


def test_m7_declined_transaction_not_counted():
    items = [
        make_item("R1", "CAFE", 60000),
    ]

    results = execute(items)
    summaries = summarize_strategies(
        items=items,
        results=results,
    )

    for summary in summaries.values():
        assert summary.request_count == 1
        assert summary.approved_count == 0
        assert summary.declined_count == 1
        assert summary.approved_won == 0
        assert summary.benefit_won == 0
        assert summary.approval_rate == Decimal("0")
        assert summary.benefit_rate == Decimal("0")


def test_m7_export_rows():
    items = [make_item("R1", "CAFE", 10000)]
    results = execute(items)

    summaries = summarize_strategies(
        items=items,
        results=results,
    )

    rows = rows_for_export(summaries)

    assert len(rows) == 3
    assert {row["strategy_id"] for row in rows} == {
        "A2", "A3", "B"
    }

    b_row = next(
        row for row in rows
        if row["strategy_id"] == "B"
    )

    assert b_row["benefit_won"] == 1000
    assert b_row["approval_rate"] == "1"
    assert b_row["benefit_rate"] == "0.1"


def test_m7_rejects_result_length_mismatch():
    items = [make_item("R1", "CAFE", 10000)]
    results = execute(items)

    results["B"].decisions.clear()

    with pytest.raises(
        ValueError,
        match="DECISION_COUNT_MISMATCH",
    ):
        summarize_strategies(
            items=items,
            results=results,
        )
