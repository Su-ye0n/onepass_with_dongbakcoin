from copy import deepcopy

from onepass.engine import (
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


def test_two_wallets_independent_and_cashback():
    cards = [
        Card(
            "C1",
            CardType.DONGBAEK_CHECK,
            account_id="A",
            wallet_id="W1",
        ),
        Card(
            "C2",
            CardType.DONGBAEK_CHECK,
            account_id="A",
            wallet_id="W2",
        ),
    ]

    state = State(
        accounts={"A": 30000},
        wallets={
            "W1": WalletBalance(charge=20000),
            "W2": WalletBalance(charge=5000),
        },
    )

    merchant = Merchant(
        "M", "CAFE", True, "LE_10B"
    )

    result = process(
        Request(
            "R1",
            "M",
            10000,
            payment_path="DIRECT",
            direct_card_id="C1",
        ),
        merchant,
        cards,
        state,
        DbPolicy(),
    )

    assert result.approved
    assert result.benefit_won == 1000

    assert state.wallets["W1"].charge == 10000
    assert state.wallets["W1"].cashback == 1000

    # 다른 지갑은 변경되지 않아야 함
    assert state.wallets["W2"].charge == 5000

    # 지갑 결제라 연결 계좌도 불변
    assert state.accounts["A"] == 30000


def test_fallback_does_not_spend_wallet():
    card = Card(
        "C1",
        CardType.DONGBAEK_CHECK,
        account_id="A",
        wallet_id="W1",
    )

    state = State(
        accounts={"A": 30000},
        wallets={
            "W1": WalletBalance(charge=500)
        },
    )

    result = process(
        Request("R1", "M", 10000),
        Merchant("M", "CAFE", True),
        [card],
        state,
        DbPolicy(),
    )

    assert result.approved
    assert result.benefit_won == 0

    # 계좌에서 전액 출금
    assert state.accounts["A"] == 20000

    # 지갑 잔액 불변
    assert state.wallets["W1"].charge == 500


def test_shared_account_and_decline_read_only():
    cards = [
        Card(
            "C1",
            CardType.DEBIT,
            account_id="A",
        ),
        Card(
            "C2",
            CardType.DONGBAEK_CHECK,
            account_id="A",
            wallet_id="W",
        ),
    ]

    state = State(
        accounts={"A": 15000},
        wallets={
            "W": WalletBalance(charge=1000)
        },
    )

    merchant = Merchant("M", "CAFE", True)

    process(
        Request(
            "R1",
            "M",
            10000,
            payment_path="DIRECT",
            direct_card_id="C1",
        ),
        merchant,
        cards,
        state,
        DbPolicy(),
    )

    before = deepcopy(state)

    result = process(
        Request(
            "R2",
            "M",
            10000,
            payment_path="DIRECT",
            direct_card_id="C2",
        ),
        merchant,
        cards,
        state,
        DbPolicy(),
    )

    assert not result.approved
    assert state == before


def test_quote_no_mutation():
    card = Card(
        "C",
        CardType.DONGBAEK_CHECK,
        account_id="A",
        wallet_id="W",
    )

    state = State(
        accounts={"A": 10000},
        wallets={
            "W": WalletBalance(charge=20000)
        },
    )

    before = deepcopy(state)

    result = decide(
        Request("R", "M", 10000),
        Merchant("M", "CAFE", True),
        [card],
        state,
        DbPolicy(),
    )

    assert result.approved
    assert state == before
