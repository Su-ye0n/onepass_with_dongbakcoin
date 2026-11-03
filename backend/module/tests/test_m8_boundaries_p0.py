
# tests/test_m8_boundaries_p0.py
"""P0-18: independent boundary-condition tests.

All expected amounts are manually fixed using P0 assumptions.
These tests do not assert official card-product policies.
"""

from copy import deepcopy
from decimal import Decimal

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


def make_merchant(
    merchant_id="M001",
    registered=True,
):
    return Merchant(
        merchant_id,
        "CAFE",
        registered,
        "LE_10B",
    )


def test_exact_debit_account_balance():
    """계좌 잔액 10,000원으로 정확히 10,000원 결제."""
    card = Card(
        id="BANK",
        type=CardType.DEBIT,
        account_id="A001",
    )

    state = State(accounts={"A001": 10000})

    result = process(
        Request("R1", "M001", 10000),
        make_merchant(),
        [card],
        state,
        DbPolicy(),
    )

    assert result.approved
    assert result.selected_card_id == "BANK"
    assert state.accounts["A001"] == 0
    assert len(state.ledger) == 1


def test_insufficient_debit_balance_does_not_mutate():
    """잔액이 1원 부족하면 결제 거절, 원본 상태 불변."""
    card = Card(
        id="BANK",
        type=CardType.DEBIT,
        account_id="A001",
    )

    state = State(accounts={"A001": 9999})
    original = deepcopy(state)

    result = process(
        Request("R1", "M001", 10000),
        make_merchant(),
        [card],
        state,
        DbPolicy(),
    )

    assert not result.approved
    assert result.benefit_won == 0
    assert state == original


def test_credit_limit_exact_boundary():
    """신용카드 한도 10,000원으로 정확히 10,000원 승인."""
    card = Card(
        id="CREDIT",
        type=CardType.CREDIT,
        credit_limit=10000,
    )

    state = State(accounts={})

    result = process(
        Request("R1", "M001", 10000),
        make_merchant(),
        [card],
        state,
        DbPolicy(),
    )

    assert result.approved
    assert result.selected_card_id == "CREDIT"
    assert state.credit_used["CREDIT"] == 10000


def test_monthly_benefit_cap_remaining_100_won():
    """월 혜택한도 1,000원 중 900원을 사용한 경우."""
    rule = BenefitRule(
        id="CAFE10",
        categories=("CAFE",),
        rate=Decimal("0.10"),
        monthly_cap=1000,
    )

    card = Card(
        id="BANK",
        type=CardType.DEBIT,
        account_id="A001",
        rules=(rule,),
    )

    state = State(
        accounts={"A001": 20000},
        benefit_used={"CAFE10": 900},
    )

    result = process(
        Request("R1", "M001", 10000),
        make_merchant(),
        [card],
        state,
        DbPolicy(),
    )

    # 원래 혜택 1,000원이지만 남은 한도는 100원.
    assert result.approved
    assert result.benefit_won == 100
    assert state.benefit_used["CAFE10"] == 1000
    assert state.accounts["A001"] == 10000


def test_previous_performance_exact_threshold():
    """전월 실적이 기준금액과 정확히 같으면 혜택 적용."""
    rule = BenefitRule(
        id="CAFE5",
        categories=("CAFE",),
        rate=Decimal("0.05"),
        prev_month_min=30000,
    )

    card = Card(
        id="BANK",
        type=CardType.DEBIT,
        account_id="A001",
        prev_month_perf=30000,
        rules=(rule,),
    )

    result = decide(
        Request("R1", "M001", 10000),
        make_merchant(),
        [card],
        State(accounts={"A001": 20000}),
        DbPolicy(),
    )

    assert result.approved
    assert result.benefit_won == 500


def test_lost_card_is_not_approved():
    """분실 카드만 보유하면 승인 불가."""
    card = Card(
        id="BANK",
        type=CardType.DEBIT,
        account_id="A001",
        lost=True,
    )

    state = State(accounts={"A001": 20000})
    original = deepcopy(state)

    result = process(
        Request("R1", "M001", 10000),
        make_merchant(),
        [card],
        state,
        DbPolicy(),
    )

    assert not result.approved
    assert state == original


def test_dongbaek_unregistered_merchant_uses_bank():
    """동백전 비가맹점에서는 일반 체크카드 선택."""
    cards = [
        Card(
            id="DB",
            type=CardType.DONGBAEK_CHECK,
            account_id="A001",
            wallet_id="W001",
        ),
        Card(
            id="BANK",
            type=CardType.DEBIT,
            account_id="A001",
        ),
    ]

    state = State(
        accounts={"A001": 20000},
        wallets={
            "W001": WalletBalance(charge=30000)
        },
    )

    result = process(
        Request("R1", "M001", 10000),
        make_merchant(registered=False),
        cards,
        state,
        DbPolicy(),
    )

    assert result.approved
    assert result.selected_card_id == "BANK"
    assert result.benefit_won == 0

    assert state.accounts["A001"] == 10000
    assert state.wallets["W001"].charge == 30000


def test_repeated_quote_does_not_change_state():
    """반복된 혜택 조회로 잔액·한도·원장이 변경되면 안 됨."""
    card = Card(
        id="DB",
        type=CardType.DONGBAEK_CHECK,
        account_id="A001",
        wallet_id="W001",
    )

    state = State(
        accounts={"A001": 10000},
        wallets={
            "W001": WalletBalance(charge=20000)
        },
    )

    original = deepcopy(state)

    for _ in range(5):
        result = decide(
            Request("R1", "M001", 10000),
            make_merchant(),
            [card],
            state,
            DbPolicy(),
        )

        assert result.approved
        assert result.benefit_won == 1000

    assert state == original
