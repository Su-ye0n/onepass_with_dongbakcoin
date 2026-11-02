from copy import deepcopy
from decimal import Decimal

import pytest

from onepass.engine import BenefitRule, Card, CardType, DbPolicy, Merchant, Request, State
from onepass.service import quote, commit


def setup_case():
    merchant = Merchant('M1', 'CAFE', True, 'LE_10B')
    cards = [
        Card('DB', CardType.DONGBAEK_CHECK, account_id='A'),
        Card(
            'CC',
            CardType.CREDIT,
            credit_limit=50000,
            rules=(
                BenefitRule('CAFE5', ('CAFE',), Decimal('0.05')),
            ),
        ),
    ]
    state = State(accounts={'A': 30000}, db_charge=20000)
    request = Request('REQ1', 'M1', 10000)

    return request, merchant, cards, state, DbPolicy()


def test_quote_is_read_only():
    request, merchant, cards, state, policy = setup_case()
    before = deepcopy(state)

    result = quote(request, merchant, cards, state, policy)

    assert result.approved and result.selected_card_id == 'DB'
    assert state == before


def test_commit_changes_state_once():
    request, merchant, cards, state, policy = setup_case()

    quote(request, merchant, cards, state, policy)
    result = commit(request, merchant, cards, state, policy)

    assert result.approved and result.benefit_won == 1000
    assert state.db_charge == 10000
    assert len(state.ledger) == 1

    repeated = commit(request, merchant, cards, state, policy)
    assert repeated.reason == 'DUPLICATE_REQUEST'
    assert len(state.ledger) == 1


def test_quote_reflects_state_after_commit():
    request, merchant, cards, state, policy = setup_case()

    commit(request, merchant, cards, state, policy)
    new_request = Request('REQ2', 'M1', 15000)
    result = quote(new_request, merchant, cards, state, policy)

    assert result.approved
    assert state.db_charge == 10000
    assert len(state.ledger) == 1


def test_merchant_mismatch_rejected_without_mutation():
    request, merchant, cards, state, policy = setup_case()
    original = deepcopy(state)

    with pytest.raises(ValueError, match='MERCHANT_MISMATCH'):
        commit(
            Request('OTHER', 'WRONG', 10000),
            merchant,
            cards,
            state,
            policy,
        )

    assert state == original


def test_declined_request_does_not_mutate_state():
    request, merchant, cards, state, policy = setup_case()
    original = deepcopy(state)

    result = commit(
        Request('REQ_BIG', 'M1', 100000),
        merchant,
        cards,
        state,
        policy,
    )

    assert not result.approved
    assert state == original
