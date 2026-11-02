
# tests/test_m1_users_p0.py

from copy import deepcopy
from decimal import Decimal

import pytest

from onepass.engine import CardType, DbPolicy, Merchant
from onepass.m1_users_p0 import (
    BankCardTemplate,
    PopulationConfig,
    generate_user_p0,
    generate_population_p0,
)
from onepass.m1_generator_p0 import (
    CategoryParameter,
    generate_month_p0,
)
from onepass.m6_p0 import run_m6_p0


def sample_config():
    return PopulationConfig(
        district_weights={
            "26440": 2,
            "26350": 1,
        },
        age_weights={
            "20-29": 2,
            "30-39": 1,
        },
        bank_card_count_weights={
            1: 1,
            2: 2,
        },
        opening_account_won=100000,
        opening_db_charge_won=30000,
        opening_db_cashback_won=2000,
    )


def sample_products():
    return [
        BankCardTemplate(
            "BANK_CHECK_A",
            CardType.DEBIT,
        ),
        BankCardTemplate(
            "BANK_CREDIT_B",
            CardType.CREDIT,
            credit_limit_won=200000,
        ),
        BankCardTemplate(
            "BANK_CHECK_C",
            CardType.DEBIT,
        ),
    ]


def test_user_has_one_dongbaek_and_multiple_bank_cards():
    user = generate_user_p0(
        user_id="U001",
        config=PopulationConfig(
            district_weights={"26440": 1},
            age_weights={"20-29": 1},
            bank_card_count_weights={2: 1},
        ),
        bank_products=sample_products(),
    )

    assert len(user.cards) == 3

    db_cards = [
        c for c in user.cards
        if c.type == CardType.DONGBAEK_CHECK
    ]

    assert len(db_cards) == 1
    assert len(user.state.wallets) == 1

    assert user.default_card_id in {
        c.id for c in user.cards[1:]
    }


def test_generation_is_reproducible():
    args = dict(
        user_id="U001",
        config=sample_config(),
        bank_products=sample_products(),
        seed=123,
    )

    first = generate_user_p0(**args)
    second = generate_user_p0(**args)

    assert first == second


def test_population_ids_and_states_are_independent():
    users = generate_population_p0(
        user_count=20,
        config=sample_config(),
        bank_products=sample_products(),
    )

    assert len(users) == 20
    assert len({
        u.profile.user_id for u in users
    }) == 20

    assert len({
        c.id for u in users for c in u.cards
    }) == sum(len(u.cards) for u in users)

    original_second = deepcopy(users[1].state)

    account_id = next(iter(users[0].state.accounts))
    users[0].state.accounts[account_id] -= 1000

    assert users[1].state == original_second


def test_invalid_card_count_rejected():
    with pytest.raises(
        ValueError, match="INVALID_BANK_CARD_COUNT"
    ):
        generate_user_p0(
            user_id="U001",
            config=PopulationConfig(
                district_weights={"26440": 1},
                age_weights={"20-29": 1},
                bank_card_count_weights={5: 1},
            ),
            bank_products=sample_products(),
        )


def test_invalid_balance_rejected():
    config = PopulationConfig(
        district_weights={"26440": 1},
        age_weights={"20-29": 1},
        bank_card_count_weights={1: 1},
        opening_account_won=-100,
    )

    with pytest.raises(
        ValueError, match="INVALID_OPENING_BALANCE"
    ):
        generate_user_p0(
            user_id="U001",
            config=config,
            bank_products=sample_products(),
        )


def test_generated_user_connects_to_m1_and_m6():
    user = generate_user_p0(
        user_id="U001",
        config=sample_config(),
        bank_products=sample_products(),
    )

    merchants = {
        "M001": Merchant(
            "M001", "CAFE", True, "LE_10B"
        )
    }

    generated = generate_month_p0(
        profile=user.profile,
        month="2026-06",
        transaction_count=5,
        category_parameters=[
            CategoryParameter(
                "CAFE", Decimal("1"), 3000, 5000
            )
        ],
        merchants=merchants,
    )

    results = run_m6_p0(
        items=generated.items,
        merchants=merchants,
        cards=user.cards,
        initial_state=user.state,
        policy=DbPolicy(),
        default_card_id=user.default_card_id,
        a1_weights=user.a1_weights,
    )

    assert set(results) == {"A1", "A2", "A3", "B"}
    assert all(
        len(r.decisions) == 5
        for r in results.values()
    )
