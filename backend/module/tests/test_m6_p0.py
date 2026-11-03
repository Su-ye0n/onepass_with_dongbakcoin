
# tests/test_m6_p0.py

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


def make_item(
    request_id,
    merchant_id,
    amount,
    minute=0,
):
    return ReplayItem(
        event_at=(
            f"2026-06-15T12:{minute:02d}:00+09:00"
        ),
        event_seq=minute,
        request=Request(
            request_id,
            merchant_id,
            amount,
        ),
    )


def run(items, cards, state, merchants):
    return run_m6_p0(
        items=items,
        merchants=merchants,
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
        default_card_id="BANK",
    )


def test_three_strategies_use_same_transaction():
    cards, state, merchants = setup_case()
    original = deepcopy(state)

    results = run(
        [make_item("R1", "CAFE", 10000)],
        cards,
        state,
        merchants,
    )

    assert set(results) == {"A2", "A3", "B"}

    a2 = results["A2"].decisions[0]
    a3 = results["A3"].decisions[0]
    b = results["B"].decisions[0]

    assert a2.approved
    assert a3.approved
    assert b.approved

    assert a2.selected_card_id == "BANK"
    assert a3.selected_card_id == "DB"
    assert b.selected_card_id == "DB"

    # 동일 거래에 대해 혜택은 카드 선택에 따라 달라짐
    assert a2.benefit_won == 500
    assert a3.benefit_won == 1000
    assert b.benefit_won == 1000

    # 원본 상태 불변
    assert state == original


def test_a3_uses_default_when_not_dongbaek_merchant():
    cards, state, merchants = setup_case()

    results = run(
        [make_item("R1", "MART", 10000)],
        cards,
        state,
        merchants,
    )

    a3 = results["A3"].decisions[0]

    assert a3.approved
    assert a3.selected_card_id == "BANK"
    assert a3.benefit_won == 0

    assert (
        results["A3"].final_state.accounts["A001"]
        == 40000
    )


def test_a3_rechecks_current_wallet_and_account():
    cards, state, merchants = setup_case()

    # 두 번의 1만원 거래
    # 첫 결제 후 지갑 충전금 1만원 + 캐시백 1천원
    # 두 번째 결제도 지갑으로 가능하며
    # 현재 잔액·캐시백을 기준으로 재계산되어야 함
    items = [
        make_item("R1", "CAFE", 10000, minute=0),
        make_item("R2", "CAFE", 10000, minute=1),
    ]

    results = run(items, cards, state, merchants)

    a3 = results["A3"]

    assert len(a3.decisions) == 2
    assert all(d.approved for d in a3.decisions)

    assert [
        d.selected_card_id for d in a3.decisions
    ] == ["DB", "DB"]

    # 첫 결제: 캐시백 1000원
    assert a3.decisions[0].benefit_won == 1000

    # 두 번째 결제: 캐시백 1000원 먼저 소진,
    # 충전금 9000원에 대해서만 10% 적립
    assert a3.decisions[1].benefit_won == 900

    assert a3.final_state.wallets["W001"].charge == 1000
    assert a3.final_state.wallets["W001"].cashback == 900
    assert a3.final_state.accounts["A001"] == 50000


def test_strategy_balances_are_independent():
    cards, state, merchants = setup_case()
    initial = deepcopy(state)

    results = run(
        [make_item("R1", "CAFE", 10000)],
        cards,
        state,
        merchants,
    )

    # A2는 은행 계좌 사용
    assert (
        results["A2"].final_state.accounts["A001"]
        == 40000
    )
    assert (
        results["A2"].final_state.wallets["W001"].charge
        == 20000
    )

    # A3와 B는 동백전 지갑 사용
    for strategy in ("A3", "B"):
        assert (
            results[strategy]
            .final_state.accounts["A001"] == 50000
        )
        assert (
            results[strategy]
            .final_state.wallets["W001"].charge == 10000
        )

    assert state == initial


def test_unknown_default_card_is_rejected():
    cards, state, merchants = setup_case()

    with pytest.raises(
        ValueError,
        match="DEFAULT_CARD_NOT_FOUND",
    ):
        run_m6_p0(
            items=[make_item("R1", "CAFE", 10000)],
            merchants=merchants,
            cards=cards,
            initial_state=state,
            policy=DbPolicy(),
            default_card_id="NON_EXISTENT_CARD",
        )


def test_mixed_months_are_rejected():
    cards, state, merchants = setup_case()

    items = [
        make_item("R1", "CAFE", 10000),
        ReplayItem(
            event_at="2026-07-01T12:00:00+09:00",
            event_seq=1,
            request=Request("R2", "CAFE", 10000),
        ),
    ]

    with pytest.raises(
        ValueError,
        match="Mixed months",
    ):
        run(items, cards, state, merchants)

def test_multiple_dongbaek_cards_are_rejected():
    cards, state, merchants = setup_case()

    cards.append(
        Card(
            id="DB2",
            type=CardType.DONGBAEK_CHECK,
            account_id="A001",
            wallet_id="W001",
        )
    )

    with pytest.raises(
        ValueError,
        match="MULTIPLE_DONGBAEK_CARDS_NOT_ALLOWED",
    ):
        run(
            [make_item("R1", "CAFE", 10000)],
            cards,
            state,
            merchants,
        )

