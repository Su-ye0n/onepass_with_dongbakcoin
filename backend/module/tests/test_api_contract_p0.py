
# tests/test_api_contract_p0.py

from copy import deepcopy

import pytest

from onepass.api_contract_p0 import (
    APIContractError,
    parse_payment_request,
    execute_engine_request,
)
from onepass.engine import (
    Card,
    CardType,
    DbPolicy,
    Merchant,
    State,
    WalletBalance,
)


def make_case():
    merchant = Merchant(
        "M001", "CAFE", True, "LE_10B"
    )

    cards = [
        Card(
            id="UC_DB_001",
            type=CardType.DONGBAEK_CHECK,
            account_id="A001",
            wallet_id="W001",
        ),
        Card(
            id="UC_BANK_001",
            type=CardType.DEBIT,
            account_id="A001",
        ),
    ]

    state = State(
        accounts={"A001": 50000},
        wallets={
            "W001": WalletBalance(charge=30000)
        },
    )

    return merchant, cards, state, DbPolicy()


def payload(request_id="R1", payment_path="ONECARD"):
    result = {
        "request_id": request_id,
        "merchant_id": "M001",
        "amount_won": 10000,
        "payment_path": payment_path,
        "onecard_active": True,
    }

    if payment_path == "DIRECT":
        result["direct_card_id"] = "UC_BANK_001"

    return result


def test_request_parsing():
    result = parse_payment_request(payload())

    assert result.id == "R1"
    assert result.merchant_id == "M001"
    assert result.amount == 10000
    assert result.payment_path == "ONECARD"


def test_invalid_amount_rejected():
    invalid = payload()
    invalid["amount_won"] = -100

    with pytest.raises(
        APIContractError, match="INVALID_AMOUNT_WON"
    ):
        parse_payment_request(invalid)


def test_direct_card_id_required():
    invalid = payload(payment_path="DIRECT")
    del invalid["direct_card_id"]

    with pytest.raises(
        APIContractError,
        match="DIRECT_CARD_ID_REQUIRED",
    ):
        parse_payment_request(invalid)


def test_quote_returns_json_without_mutation():
    merchant, cards, state, policy = make_case()
    original = deepcopy(state)

    response = execute_engine_request(
        payload=payload(),
        merchant=merchant,
        cards=cards,
        state=state,
        policy=policy,
        mode="QUOTE",
    )

    assert response["approved"]
    assert response["selected_user_card_id"] == "UC_DB_001"
    assert response["benefit_won"] == 1000
    assert response["candidates"]
    assert state == original


def test_commit_updates_simulated_state():
    merchant, cards, state, policy = make_case()

    response = execute_engine_request(
        payload=payload(),
        merchant=merchant,
        cards=cards,
        state=state,
        policy=policy,
        mode="COMMIT",
    )

    assert response["approved"]
    assert response["benefit_won"] == 1000
    assert state.wallets["W001"].charge == 20000
    assert state.wallets["W001"].cashback == 1000
    assert state.accounts["A001"] == 50000


def test_duplicate_commit_does_not_double_charge():
    merchant, cards, state, policy = make_case()

    arguments = dict(
        payload=payload(),
        merchant=merchant,
        cards=cards,
        state=state,
        policy=policy,
        mode="COMMIT",
    )

    first = execute_engine_request(**arguments)
    second = execute_engine_request(**arguments)

    assert first["approved"]
    assert not second["approved"]
    assert second["reason"] == "DUPLICATE_REQUEST"
    assert state.wallets["W001"].charge == 20000


def test_direct_card_payment():
    merchant, cards, state, policy = make_case()

    response = execute_engine_request(
        payload=payload(
            request_id="DIRECT_001",
            payment_path="DIRECT",
        ),
        merchant=merchant,
        cards=cards,
        state=state,
        policy=policy,
        mode="COMMIT",
    )

    assert response["approved"]
    assert response["selected_user_card_id"] == "UC_BANK_001"
    assert response["benefit_won"] == 0
    assert state.accounts["A001"] == 40000
    assert state.wallets["W001"].charge == 30000


def test_invalid_execution_mode_rejected():
    merchant, cards, state, policy = make_case()

    with pytest.raises(
        APIContractError,
        match="INVALID_EXECUTION_MODE",
    ):
        execute_engine_request(
            payload=payload(),
            merchant=merchant,
            cards=cards,
            state=state,
            policy=policy,
            mode="REAL_PAYMENT",
        )
