
# tests/test_m1_generator_p0.py

from copy import deepcopy
from decimal import Decimal

import pytest

from onepass.engine import (
    Card, CardType, DbPolicy, Merchant,
    State, WalletBalance,
)
from onepass.m1_generator_p0 import (
    CategoryParameter,
    SyntheticProfile,
    generate_month_p0,
    generate_months_p0,
)
from onepass.m6_p0 import run_m6_p0
from onepass.multimonth_p0 import run_multimonth_p0


def setup_case():
    profile = SyntheticProfile(
        user_id="U001",
        district_code="26440",
        age_band="20-29",
    )

    merchants = {
        "M_CAFE": Merchant(
            "M_CAFE", "CAFE", True, "LE_10B"
        ),
        "M_MART": Merchant(
            "M_MART", "MART", False, "LE_10B"
        ),
    }

    params = [
        CategoryParameter(
            "CAFE", Decimal("0.6"), 1000, 8000
        ),
        CategoryParameter(
            "MART", Decimal("0.4"), 5000, 20000
        ),
    ]

    cards = [
        Card(
            "BANK", CardType.DEBIT,
            account_id="A001",
        ),
        Card(
            "DB", CardType.DONGBAEK_CHECK,
            account_id="A001",
            wallet_id="W001",
        ),
    ]

    state = State(
        accounts={"A001": 1000000},
        wallets={
            "W001": WalletBalance(charge=100000)
        },
    )

    return profile, merchants, params, cards, state


def test_generation_is_reproducible():
    profile, merchants, params, _, _ = setup_case()

    args = dict(
        profile=profile,
        month="2026-06",
        transaction_count=30,
        category_parameters=params,
        merchants=merchants,
        seed=100,
    )

    first = generate_month_p0(**args)
    second = generate_month_p0(**args)

    assert first == second
    assert len(first.items) == 30


def test_transactions_are_sorted_and_valid():
    profile, merchants, params, _, _ = setup_case()

    result = generate_month_p0(
        profile=profile,
        month="2026-06",
        transaction_count=50,
        category_parameters=params,
        merchants=merchants,
    )

    timestamps = [x.event_at for x in result.items]
    ids = [x.request.id for x in result.items]

    assert timestamps == sorted(timestamps)
    assert len(set(ids)) == 50

    for item in result.items:
        assert item.event_at.startswith("2026-06")
        assert item.event_at.endswith("+09:00")
        assert item.request.amount > 0
        assert item.request.merchant_id in merchants


def test_only_positive_weight_category_generated():
    profile, merchants, _, _, _ = setup_case()

    params = [
        CategoryParameter(
            "CAFE", Decimal("1"), 3000, 3000
        ),
        CategoryParameter(
            "MART", Decimal("0"), 5000, 5000
        ),
    ]

    result = generate_month_p0(
        profile=profile,
        month="2026-06",
        transaction_count=20,
        category_parameters=params,
        merchants=merchants,
    )

    assert all(
        x.request.merchant_id == "M_CAFE"
        and x.request.amount == 3000
        for x in result.items
    )


def test_invalid_parameters_are_rejected():
    profile, merchants, params, _, _ = setup_case()

    with pytest.raises(
        ValueError, match="INVALID_TRANSACTION_COUNT"
    ):
        generate_month_p0(
            profile=profile,
            month="2026-06",
            transaction_count=-1,
            category_parameters=params,
            merchants=merchants,
        )

    with pytest.raises(
        ValueError, match="NO_MERCHANT_FOR_CATEGORY"
    ):
        generate_month_p0(
            profile=profile,
            month="2026-06",
            transaction_count=10,
            category_parameters=[
                CategoryParameter(
                    "CINEMA", Decimal("1"), 1000, 5000
                )
            ],
            merchants=merchants,
        )


def test_generated_transactions_work_with_m6():
    profile, merchants, params, cards, state = setup_case()
    original = deepcopy(state)

    generated = generate_month_p0(
        profile=profile,
        month="2026-06",
        transaction_count=10,
        category_parameters=params,
        merchants=merchants,
        seed=2026,
    )

    results = run_m6_p0(
        items=generated.items,
        merchants=merchants,
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
        default_card_id="BANK",
        a1_weights={"BANK": 0.5, "DB": 0.5},
    )

    assert set(results) == {"A1", "A2", "A3", "B"}
    assert all(
        len(result.decisions) == 10
        for result in results.values()
    )
    assert state == original


def test_generated_months_work_with_multimonth():
    profile, merchants, params, cards, state = setup_case()

    months = generate_months_p0(
        profile=profile,
        counts_by_month={
            "2026-06": 5,
            "2026-07": 0,
            "2026-08": 5,
        },
        category_parameters=params,
        merchants=merchants,
    )

    assert len(months["2026-06"]) == 5
    assert months["2026-07"] == []
    assert len(months["2026-08"]) == 5

    result = run_multimonth_p0(
        monthly_items=months,
        merchants=merchants,
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
        default_card_id="BANK",
        a1_weights={"BANK": 0.5, "DB": 0.5},
    )

    assert len(result.months) == 3
    assert set(result.final_states) == {
        "A1", "A2", "A3", "B"
    }
