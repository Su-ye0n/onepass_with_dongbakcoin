
# tests/test_a1_p0.py

from copy import deepcopy
from decimal import Decimal

import pytest

from onepass.a1_p0 import (
    select_a1_card,
    validate_a1_weights,
)
from onepass.engine import (
    Card,
    CardType,
    DbPolicy,
    Merchant,
    Request,
    State,
    WalletBalance,
)
from onepass.m6_p0 import run_m6_p0
from onepass.multimonth_p0 import run_multimonth_p0
from onepass.replay_p0 import ReplayItem


def make_case():
    cards = [
        Card(
            "BANK_A",
            CardType.DEBIT,
            account_id="A001",
        ),
        Card(
            "BANK_B",
            CardType.CREDIT,
            credit_limit=100000,
        ),
        Card(
            "DB",
            CardType.DONGBAEK_CHECK,
            account_id="A001",
            wallet_id="W001",
        ),
    ]

    state = State(
        accounts={"A001": 100000},
        wallets={
            "W001": WalletBalance(charge=30000)
        },
    )

    merchants = {
        "M001": Merchant(
            "M001", "CAFE", True, "LE_10B"
        ),
    }

    return cards, state, merchants


def item(rid, month="2026-06", day=1):
    return ReplayItem(
        event_at=f"{month}-{day:02d}T12:00:00+09:00",
        event_seq=day,
        request=Request(rid, "M001", 10000),
    )


def test_weights_are_normalized():
    cards, _, _ = make_case()

    weights = validate_a1_weights(
        cards,
        {"BANK_A": 5, "BANK_B": 3, "DB": 2},
    )

    assert weights == {
        "BANK_A": Decimal("0.5"),
        "BANK_B": Decimal("0.3"),
        "DB": Decimal("0.2"),
    }


def test_selection_is_reproducible():
    cards, _, _ = make_case()

    weights = {
        "BANK_A": 0.5,
        "BANK_B": 0.3,
        "DB": 0.2,
    }

    first = [
        select_a1_card(
            request_id=f"REQ_{i}",
            cards=cards,
            weights=weights,
            seed=123,
        )
        for i in range(50)
    ]

    second = [
        select_a1_card(
            request_id=f"REQ_{i}",
            cards=list(reversed(cards)),
            weights=weights,
            seed=123,
        )
        for i in range(50)
    ]

    assert first == second
    assert set(first).issubset(set(weights))


def test_single_positive_weight_always_selects_card():
    cards, _, _ = make_case()

    for index in range(20):
        selected = select_a1_card(
            request_id=f"R{index}",
            cards=cards,
            weights={
                "BANK_A": 0,
                "BANK_B": 0,
                "DB": 1,
            },
        )

        assert selected == "DB"


def test_invalid_weights_rejected():
    cards, _, _ = make_case()

    with pytest.raises(
        ValueError, match="A1_INVALID_WEIGHT"
    ):
        validate_a1_weights(
            cards, {"BANK_A": -1, "DB": 2}
        )

    with pytest.raises(
        ValueError, match="A1_UNKNOWN_CARDS"
    ):
        validate_a1_weights(
            cards, {"NOT_OWNED": 1}
        )

    with pytest.raises(
        ValueError, match="A1_ZERO_TOTAL_WEIGHT"
    ):
        validate_a1_weights(
            cards, {"BANK_A": 0, "DB": 0}
        )


def test_m6_a1_enabled_and_state_isolated():
    cards, state, merchants = make_case()
    before = deepcopy(state)

    results = run_m6_p0(
        items=[item("R1")],
        merchants=merchants,
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
        default_card_id="BANK_A",
        a1_weights={
            "BANK_A": 0,
            "BANK_B": 1,
            "DB": 0,
        },
        a1_seed=123,
    )

    assert set(results) == {"A1", "A2", "A3", "B"}

    a1 = results["A1"]

    assert a1.decisions[0].approved
    assert a1.decisions[0].selected_card_id == "BANK_B"

    # A1 used credit; bank account and wallet remain intact.
    assert a1.final_state.accounts["A001"] == 100000
    assert a1.final_state.wallets["W001"].charge == 30000

    assert state == before


def test_multimonth_a1_is_included():
    cards, state, merchants = make_case()

    result = run_multimonth_p0(
        monthly_items={
            "2026-06": [item("JUNE")],
            "2026-07": [item("JULY", "2026-07")],
        },
        merchants=merchants,
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
        default_card_id="BANK_A",
        a1_weights={
            "BANK_A": 1,
            "BANK_B": 0,
            "DB": 0,
        },
    )

    assert set(result.final_states) == {
        "A1", "A2", "A3", "B"
    }

    assert len(result.months) == 2

    for month in result.months:
        assert set(month.results) == {
            "A1", "A2", "A3", "B"
        }
        assert set(month.metrics) == {
            "A1", "A2", "A3", "B"
        }
        assert "A1" in month.comparisons

    assert (
        result.final_states["A1"].accounts["A001"]
        == 80000
    )


def test_omitting_weights_preserves_old_strategies():
    cards, state, merchants = make_case()

    results = run_m6_p0(
        items=[item("R1")],
        merchants=merchants,
        cards=cards,
        initial_state=state,
        policy=DbPolicy(),
        default_card_id="BANK_A",
    )

    assert set(results) == {"A2", "A3", "B"}
