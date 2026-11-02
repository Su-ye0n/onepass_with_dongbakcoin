
# tests/test_month_close_p0.py

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
    decide,
    process,
)
from onepass.month_close_p0 import (
    MonthlySpendTracker,
    close_month,
)


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
                    monthly_cap=5000,
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
            "W001": WalletBalance(
                charge=50000,
                cashback=1000,
                month_applied=10000,
            ),
        },
        credit_used={"CREDIT_OTHER": 20000},
    )

    merchant = Merchant(
        "M001", "CAFE", False, "LE_10B"
    )

    return cards, state, merchant


def test_month_close_updates_previous_performance():
    cards, state, merchant = make_case()
    tracker = MonthlySpendTracker("2026-06")

    for index in range(3):
        rid = f"JUNE_{index}"
        result = process(
            Request(
                rid,
                "M001",
                10000,
                payment_path="DIRECT",
                direct_card_id="BANK",
            ),
            merchant,
            cards,
            state,
            DbPolicy(),
        )

        assert result.approved

        tracker.record(
            request_id=rid,
            user_card_id=result.selected_card_id,
            amount_won=10000,
        )

    transition = close_month(
        month="2026-06",
        cards=cards,
        state=state,
        tracker=tracker,
    )

    assert transition.next_month == "2026-07"

    by_id = {card.id: card for card in transition.cards}

    assert by_id["BANK"].prev_month_perf == 30000
    assert by_id["DB"].prev_month_perf == 0

    bank_close = next(
        c for c in transition.closes
        if c.user_card_id == "BANK"
    )

    assert bank_close.gross_spend_won == 30000
    assert bank_close.eligible_perf_won == 30000


def test_next_month_benefit_uses_new_performance():
    cards, state, merchant = make_case()

    # 6월 실적이 없으면 7월 혜택 조건 미충족
    before = decide(
        Request(
            "BEFORE", "M001", 10000,
            payment_path="DIRECT",
            direct_card_id="BANK",
        ),
        merchant,
        cards,
        state,
        DbPolicy(),
    )

    assert before.benefit_won == 0

    tracker = MonthlySpendTracker("2026-06")
    tracker.record(
        request_id="P1",
        user_card_id="BANK",
        amount_won=30000,
    )

    transition = close_month(
        month="2026-06",
        cards=cards,
        state=state,
        tracker=tracker,
    )

    after = decide(
        Request(
            "JULY_1", "M001", 10000,
            payment_path="DIRECT",
            direct_card_id="BANK",
        ),
        merchant,
        transition.cards,
        transition.state,
        DbPolicy(),
    )

    assert after.approved
    assert after.selected_card_id == "BANK"
    assert after.benefit_won == 1000


def test_monthly_caps_reset_but_balances_remain():
    cards, state, merchant = make_case()

    state.benefit_used["CAFE10"] = 5000
    state.db_month_applied = 30000

    original = deepcopy(state)

    transition = close_month(
        month="2026-06",
        cards=cards,
        state=state,
        tracker=MonthlySpendTracker("2026-06"),
    )

    next_state = transition.state

    assert next_state.benefit_used == {}
    assert next_state.db_month_applied == 0
    assert next_state.wallets["W001"].month_applied == 0

    assert next_state.accounts == {"A001": 100000}
    assert next_state.wallets["W001"].charge == 50000
    assert next_state.wallets["W001"].cashback == 1000

    # Credit used is outstanding; not a monthly reward cap.
    assert next_state.credit_used == {
        "CREDIT_OTHER": 20000
    }

    # Previous state is unchanged.
    assert state == original


def test_excluded_performance_is_not_carried():
    cards, state, _ = make_case()
    tracker = MonthlySpendTracker("2026-06")

    tracker.record(
        request_id="R1",
        user_card_id="BANK",
        amount_won=40000,
        eligible_won=25000,
    )

    transition = close_month(
        month="2026-06",
        cards=cards,
        state=state,
        tracker=tracker,
    )

    bank = next(
        card for card in transition.cards
        if card.id == "BANK"
    )
    bank_close = next(
        c for c in transition.closes
        if c.user_card_id == "BANK"
    )

    assert bank.prev_month_perf == 25000
    assert bank_close.excluded_perf_won == 15000


def test_duplicate_performance_record_rejected():
    tracker = MonthlySpendTracker("2026-06")

    tracker.record(
        request_id="R1",
        user_card_id="BANK",
        amount_won=10000,
    )

    with pytest.raises(
        ValueError,
        match="DUPLICATE_MONTHLY_RECORD",
    ):
        tracker.record(
            request_id="R1",
            user_card_id="BANK",
            amount_won=10000,
        )


def test_month_mismatch_rejected():
    cards, state, _ = make_case()

    with pytest.raises(
        ValueError,
        match="MONTH_MISMATCH",
    ):
        close_month(
            month="2026-07",
            cards=cards,
            state=state,
            tracker=MonthlySpendTracker("2026-06"),
        )


def test_december_to_january_transition():
    cards, state, _ = make_case()

    transition = close_month(
        month="2026-12",
        cards=cards,
        state=state,
        tracker=MonthlySpendTracker("2026-12"),
    )

    assert transition.next_month == "2027-01"


def test_unknown_card_performance_rejected():
    cards, state, _ = make_case()
    tracker = MonthlySpendTracker("2026-06")

    tracker.record(
        request_id="R1",
        user_card_id="UNKNOWN",
        amount_won=10000,
    )

    with pytest.raises(
        ValueError,
        match="UNKNOWN_PERFORMANCE_CARD",
    ):
        close_month(
            month="2026-06",
            cards=cards,
            state=state,
            tracker=tracker,
        )
