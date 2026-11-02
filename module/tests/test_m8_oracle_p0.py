
# tests/test_m8_oracle_p0.py
"""P0 M8 independent answer-key validation.

Expected values are fixed manually and are not derived
from engine calculations.

All rates and policies below are synthetic test assumptions.
"""

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
    decide,
    process,
)


def bank_card(
    rate="0.05",
    *,
    cap=None,
    minimum=0,
    performance=0,
    threshold=0,
    excluded=(),
):
    return Card(
        id="BANK",
        type=CardType.DEBIT,
        account_id="A001",
        prev_month_perf=performance,
        rules=(
            BenefitRule(
                id="RULE1",
                categories=("CAFE",),
                rate=Decimal(rate),
                prev_month_min=threshold,
                min_payment=minimum,
                per_tx_cap=cap,
                excluded_merchants=excluded,
            ),
        ),
    )


def merchant(
    merchant_id="CAFE_NORMAL",
    *,
    db_registered=False,
):
    return Merchant(
        merchant_id,
        "CAFE",
        db_registered,
        "LE_10B",
    )


# Independent oracle:
# (test_id, rate, amount, per_tx_cap, min_payment, expected)
RATE_CASES = [
    ("five_percent", "0.05", 10000, None, 0, 500),
    ("ten_percent", "0.10", 10000, None, 0, 1000),
    ("per_transaction_cap", "0.10", 10000, 700, 0, 700),
    ("minimum_met", "0.05", 10000, None, 10000, 500),
    ("minimum_not_met", "0.05", 9999, None, 10000, 0),
]


@pytest.mark.parametrize(
    "case_id,rate,amount,cap,minimum,expected",
    RATE_CASES,
    ids=[case[0] for case in RATE_CASES],
)
def test_independent_rate_oracle(
    case_id, rate, amount, cap, minimum, expected
):
    card = bank_card(
        rate, cap=cap, minimum=minimum
    )
    state = State(accounts={"A001": 100000})

    result = decide(
        Request(case_id, "CAFE_NORMAL", amount),
        merchant(),
        [card],
        state,
        DbPolicy(),
    )

    assert result.approved
    assert result.selected_card_id == "BANK"
    assert result.benefit_won == expected


def test_independent_merchant_exclusion_oracle():
    card = bank_card(
        "0.10",
        excluded=("CAFE_EXCLUDED",),
    )
    state = State(accounts={"A001": 20000})

    result = decide(
        Request("R1", "CAFE_EXCLUDED", 10000),
        merchant("CAFE_EXCLUDED"),
        [card],
        state,
        DbPolicy(),
    )

    # A card benefit exclusion does not imply payment rejection.
    assert result.approved is True
    assert result.selected_card_id == "BANK"
    assert result.benefit_won == 0


def test_independent_performance_oracle():
    card = bank_card(
        "0.10",
        performance=29999,
        threshold=30000,
    )

    result = decide(
        Request("R1", "CAFE_NORMAL", 10000),
        merchant(),
        [card],
        State(accounts={"A001": 20000}),
        DbPolicy(),
    )

    assert result.approved
    assert result.benefit_won == 0


def test_independent_dongbaek_funding_oracle():
    db_card = Card(
        id="DB",
        type=CardType.DONGBAEK_CHECK,
        account_id="A001",
        wallet_id="W001",
    )

    state = State(
        accounts={"A001": 50000},
        wallets={
            "W001": WalletBalance(
                charge=30000,
                cashback=2000,
            )
        },
    )

    result = process(
        Request("DB1", "CAFE_NORMAL", 10000),
        merchant(db_registered=True),
        [db_card],
        state,
        DbPolicy(),
    )

    # Manually calculated P0 assumption:
    # 2,000 cashback spent + 8,000 charge spent.
    # New cashback: 8,000 * 10% = 800.
    assert result.approved
    assert result.selected_card_id == "DB"
    assert result.benefit_won == 800

    assert state.wallets["W001"].charge == 22000
    assert state.wallets["W001"].cashback == 800
    assert state.wallets["W001"].month_applied == 8000
    assert state.accounts["A001"] == 50000


def test_independent_account_fallback_oracle():
    db_card = Card(
        id="DB",
        type=CardType.DONGBAEK_CHECK,
        account_id="A001",
        wallet_id="W001",
    )

    state = State(
        accounts={"A001": 20000},
        wallets={
            "W001": WalletBalance(charge=500)
        },
    )

    result = process(
        Request("DB2", "CAFE_NORMAL", 10000),
        merchant(db_registered=True),
        [db_card],
        state,
        DbPolicy(),
    )

    assert result.approved
    assert result.benefit_won == 0
    assert state.accounts["A001"] == 10000
    assert state.wallets["W001"].charge == 500
    assert state.wallets["W001"].cashback == 0


def test_independent_priority_oracle():
    cards = [
        Card(
            id="BANK_A",
            type=CardType.DEBIT,
            account_id="A001",
            rules=(
                BenefitRule(
                    "A_RULE", ("CAFE",),
                    Decimal("0.05"),
                ),
            ),
        ),
        Card(
            id="BANK_B",
            type=CardType.DEBIT,
            account_id="A001",
            rules=(
                BenefitRule(
                    "B_RULE", ("CAFE",),
                    Decimal("0.05"),
                ),
            ),
        ),
    ]

    state = State(
        accounts={"A001": 20000},
        category_priorities={
            "CAFE": {"BANK_B": 1, "BANK_A": 2}
        },
    )

    result = decide(
        Request("R1", "CAFE_NORMAL", 10000),
        merchant(),
        cards,
        state,
        DbPolicy(),
    )

    assert result.approved
    assert result.benefit_won == 500
    assert result.selected_card_id == "BANK_B"


def test_quote_and_commit_state_oracle():
    card = bank_card("0.05")
    state = State(accounts={"A001": 20000})
    original = deepcopy(state)

    preview = decide(
        Request("R1", "CAFE_NORMAL", 10000),
        merchant(),
        [card],
        state,
        DbPolicy(),
    )

    assert preview.approved
    assert preview.benefit_won == 500
    assert state == original

    committed = process(
        Request("R1", "CAFE_NORMAL", 10000),
        merchant(),
        [card],
        state,
        DbPolicy(),
    )

    assert committed.approved
    assert committed.benefit_won == 500
    assert state.accounts["A001"] == 10000
    assert state.benefit_used["RULE1"] == 500

    repeated = process(
        Request("R1", "CAFE_NORMAL", 10000),
        merchant(),
        [card],
        state,
        DbPolicy(),
    )

    assert not repeated.approved
    assert repeated.reason == "DUPLICATE_REQUEST"
    assert state.accounts["A001"] == 10000
    assert len(state.ledger) == 1
