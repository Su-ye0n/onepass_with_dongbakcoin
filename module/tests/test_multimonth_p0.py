
# tests/test_multimonth_p0.py

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
from onepass.multimonth_p0 import run_multimonth_p0


def make_case():
    cards = [
        Card(
            id="BANK",
            type=CardType.DEBIT,
            account_id="A001",
            prev_month_perf=0,
            rules=(
                BenefitRule(
                    id="CAFE10",
                    categories=("CAFE",),
                    rate=Decimal("0.10"),
                    prev_month_min=30000,
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
        accounts={"A001": 100000},
        wallets={
            "W001": WalletBalance(charge=50000)
        },
    )

    merchants = {
        "CAFE_DB": Merchant(
            "CAFE_DB", "CAFE", True, "LE_10B"
        ),
        "CAFE_OTHER": Merchant(
            "CAFE_OTHER", "CAFE", False, "LE_10B"
        ),
    }

    return cards, state, merchants


def tx(rid, month, day, merchant_id, amount=10000):
    return ReplayItem(
        event_at=f"{month}-{day:02d}T12:00:00+09:00",
        event_seq=day,
        request=Request(rid, merchant_id, amount),
    )


def run(monthly_items, cards=None, state=None):
    default_cards, default_state, merchants = make_case()

    return run_multimonth_p0(
        monthly_items=monthly_items,
        merchants=merchants,
        cards=cards if cards is not None else default_cards,
        initial_state=(
            state if state is not None else default_state
        ),
        policy=DbPolicy(),
        default_card_id="BANK",
    )


def test_previous_month_performance_is_strategy_specific():
    months = {
        "2026-06": [
            tx("J1", "2026-06", 1, "CAFE_DB"),
            tx("J2", "2026-06", 2, "CAFE_DB"),
            tx("J3", "2026-06", 3, "CAFE_DB"),
        ],
        "2026-07": [
            tx("JUL1", "2026-07", 1, "CAFE_OTHER"),
        ],
    }

    result = run(months)

    june, july = result.months

    assert june.month == "2026-06"
    assert july.month == "2026-07"

    # June: B prefers Dongbaek while A2 uses BANK.
    assert all(
        d.selected_card_id == "BANK"
        for d in june.results["A2"].decisions
    )
    assert all(
        d.selected_card_id == "DB"
        for d in june.results["B"].decisions
    )

    # July: the merchant does not accept Dongbaek.
    # A2 earned enough BANK performance in June.
    # B did not.
    a2_july = july.results["A2"].decisions[0]
    b_july = july.results["B"].decisions[0]

    assert a2_july.approved
    assert b_july.approved

    assert a2_july.selected_card_id == "BANK"
    assert b_july.selected_card_id == "BANK"

    assert a2_july.benefit_won == 1000
    assert b_july.benefit_won == 0

    # Final next-month card objects retain distinct performance.
    a2_bank = next(
        c for c in result.final_cards["A2"]
        if c.id == "BANK"
    )
    b_bank = next(
        c for c in result.final_cards["B"]
        if c.id == "BANK"
    )

    # Both used BANK for 10,000 in July;
    # this is now their performance for August.
    assert a2_bank.prev_month_perf == 10000
    assert b_bank.prev_month_perf == 10000

    # June close shows the original performance difference.
    a2_june_close = next(
        c for c in june.closes["A2"]
        if c.user_card_id == "BANK"
    )
    b_june_close = next(
        c for c in june.closes["B"]
        if c.user_card_id == "BANK"
    )

    assert a2_june_close.eligible_perf_won == 30000
    assert b_june_close.eligible_perf_won == 0


def test_input_state_is_not_modified():
    cards, state, _ = make_case()

    before_cards = deepcopy(cards)
    before_state = deepcopy(state)

    run(
        {
            "2026-06": [
                tx("J1", "2026-06", 1, "CAFE_DB"),
            ]
        },
        cards=cards,
        state=state,
    )

    assert cards == before_cards
    assert state == before_state


def test_empty_month_resets_performance():
    months = {
        "2026-06": [
            tx("J1", "2026-06", 1, "CAFE_OTHER"),
        ],
        "2026-07": [],
        "2026-08": [
            tx("A1", "2026-08", 1, "CAFE_OTHER"),
        ],
    }

    result = run(months)

    assert result.months[1].month == "2026-07"
    assert result.months[1].metrics == {}
    assert result.months[1].comparisons == {}

    july_bank_close = next(
        c for c in result.months[1].closes["A2"]
        if c.user_card_id == "BANK"
    )

    assert july_bank_close.eligible_perf_won == 0

    # Empty July means August BANK does not meet threshold.
    august = result.months[2]
    assert august.results["A2"].decisions[0].benefit_won == 0


def test_missing_intermediate_month_rejected():
    with pytest.raises(
        ValueError,
        match="MONTHS_MUST_BE_CONTIGUOUS",
    ):
        run({
            "2026-06": [],
            "2026-08": [],
        })


def test_duplicate_request_across_months_rejected():
    with pytest.raises(
        ValueError,
        match="DUPLICATE_CROSS_MONTH_REQUEST",
    ):
        run({
            "2026-06": [
                tx("SAME", "2026-06", 1, "CAFE_DB"),
            ],
            "2026-07": [
                tx("SAME", "2026-07", 1, "CAFE_DB"),
            ],
        })


def test_non_kst_timestamp_rejected():
    with pytest.raises(
        ValueError,
        match="EXPECTED_KST_OFFSET",
    ):
        run({
            "2026-06": [
                ReplayItem(
                    event_at="2026-06-01T12:00:00+00:00",
                    event_seq=1,
                    request=Request(
                        "R1", "CAFE_DB", 10000
                    ),
                )
            ],
        })
