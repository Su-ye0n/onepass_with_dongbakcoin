from copy import deepcopy

import pytest

from onepass.engine import (
    Card,
    CardType,
    DbPolicy,
    Merchant,
    Request,
    State,
    WalletBalance,
)
from onepass.replay_p0 import (
    ReplayItem,
    replay_strategies,
)


def setup_case():
    cards = [
        Card(
            id="BANK",
            type=CardType.DEBIT,
            account_id="A001",
        ),
        Card(
            id="DB",
            type=CardType.DONGBAEK_CHECK,
            account_id="A001",
            wallet_id="W001",
        ),
    ]

    state = State(
        accounts={"A001": 30000},
        wallets={
            "W001": WalletBalance(charge=20000)
        },
    )

    merchants = {
        "M001": Merchant(
            "M001", "CAFE", True, "LE_10B"
        )
    }

    def make_item(
        request_id,
        event_at,
        card_id,
        amount=10000,
        event_seq=1,
    ):
        return ReplayItem(
            event_at=event_at,
            event_seq=event_seq,
            request=Request(
                request_id,
                "M001",
                amount,
                payment_path="DIRECT",
                direct_card_id=card_id,
            ),
        )

    return cards, state, merchants, make_item


def test_strategies_have_independent_states():
    cards, state, merchants, make_item = setup_case()
    original = deepcopy(state)

    results = replay_strategies(
        strategy_items={
            "A2": [
                make_item(
                    "R1",
                    "2026-06-15T12:00:00+09:00",
                    "BANK",
                ),
            ],
            "B": [
                make_item(
                    "R1",
                    "2026-06-15T12:00:00+09:00",
                    "DB",
                ),
            ],
        },
        merchants=merchants,
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
    )

    a2 = results["A2"]
    b = results["B"]

    assert a2.decisions[0].approved
    assert b.decisions[0].approved

    # A2: 은행 체크카드로 결제
    assert a2.final_state.accounts["A001"] == 20000
    assert a2.final_state.wallets["W001"].charge == 20000

    # B: 동백전으로 결제
    assert b.final_state.accounts["A001"] == 30000
    assert b.final_state.wallets["W001"].charge == 10000
    assert b.final_state.wallets["W001"].cashback == 1000

    # 원본 상태는 변경되지 않아야 함
    assert state == original


def test_transactions_share_state_within_strategy():
    cards, state, merchants, make_item = setup_case()

    state.accounts["A001"] = 15000

    items = [
        make_item(
            "R1",
            "2026-06-15T12:00:00+09:00",
            "BANK",
        ),
        make_item(
            "R2",
            "2026-06-15T12:01:00+09:00",
            "BANK",
            event_seq=2,
        ),
    ]

    results = replay_strategies(
        strategy_items={"A2": items},
        merchants=merchants,
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
    )

    result = results["A2"]

    # 첫 결제 후 은행 잔액 5,000원
    assert result.decisions[0].approved

    # 두 번째 결제는 잔액 부족으로 거절
    assert not result.decisions[1].approved

    assert result.final_state.accounts["A001"] == 5000
    assert len(result.final_state.ledger) == 1


def test_different_transactions_cannot_be_compared():
    cards, state, merchants, make_item = setup_case()

    with pytest.raises(
        ValueError,
        match="identical transactions",
    ):
        replay_strategies(
            strategy_items={
                "A2": [
                    make_item(
                        "R1",
                        "2026-06-15T12:00:00+09:00",
                        "BANK",
                        amount=10000,
                    ),
                ],
                "B": [
                    make_item(
                        "R1",
                        "2026-06-15T12:00:00+09:00",
                        "DB",
                        amount=12000,
                    ),
                ],
            },
            merchants=merchants,
            cards=cards,
            initial_state=state,
            policy=DbPolicy(),
        )


def test_duplicate_request_rejected_before_execution():
    cards, state, merchants, make_item = setup_case()
    original = deepcopy(state)

    with pytest.raises(
        ValueError,
        match="Duplicate request_id",
    ):
        replay_strategies(
            strategy_items={
                "A2": [
                    make_item(
                        "R1",
                        "2026-06-15T12:00:00+09:00",
                        "BANK",
                        event_seq=1,
                    ),
                    make_item(
                        "R1",
                        "2026-06-15T12:01:00+09:00",
                        "BANK",
                        event_seq=2,
                    ),
                ],
            },
            merchants=merchants,
            cards=cards,
            initial_state=state,
            policy=DbPolicy(),
        )

    assert state == original


def test_month_boundary_is_rejected():
    cards, state, merchants, make_item = setup_case()

    with pytest.raises(
        ValueError,
        match="Mixed months",
    ):
        replay_strategies(
            strategy_items={
                "B": [
                    make_item(
                        "R1",
                        "2026-06-30T23:59:00+09:00",
                        "DB",
                        event_seq=1,
                    ),
                    make_item(
                        "R2",
                        "2026-07-01T00:01:00+09:00",
                        "DB",
                        event_seq=2,
                    ),
                ],
            },
            merchants=merchants,
            cards=cards,
            initial_state=state,
            policy=DbPolicy(),
        )


def test_quote_and_commit_strategies_can_coexist():
    cards, state, merchants, make_item = setup_case()

    results = replay_strategies(
        strategy_items={
            "A2": [
                make_item(
                    "R1",
                    "2026-06-15T12:00:00+09:00",
                    "BANK",
                ),
            ],
            "B": [
                ReplayItem(
                    event_at="2026-06-15T12:00:00+09:00",
                    event_seq=1,
                    request=Request(
                        "R1",
                        "M001",
                        10000,
                        payment_path="ONECARD",
                    ),
                ),
            ],
        },
        merchants=merchants,
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
    )

    assert results["A2"].decisions[0].approved
    assert results["B"].decisions[0].approved
    assert results["B"].decisions[0].selected_card_id == "DB"
