from copy import deepcopy
from decimal import Decimal

from onepass.engine import (
    BenefitRule,
    Card,
    CardType,
    DbPolicy,
    Merchant,
    Request,
    State,
    decide,
    process,
)


def make_case(rate_a="0.05", rate_b="0.05"):
    cards = [
        Card(
            id="BANK_A",
            type=CardType.DEBIT,
            account_id="A001",
            rules=(
                BenefitRule(
                    "RULE_A",
                    ("CAFE",),
                    Decimal(rate_a),
                ),
            ),
        ),
        Card(
            id="BANK_B",
            type=CardType.DEBIT,
            account_id="A001",
            rules=(
                BenefitRule(
                    "RULE_B",
                    ("CAFE",),
                    Decimal(rate_b),
                ),
            ),
        ),
    ]

    state = State(
        accounts={"A001": 100000},
        category_priorities={
            "CAFE": {
                "BANK_B": 1,
                "BANK_A": 2,
            }
        },
    )

    merchant = Merchant("M001", "CAFE", False)
    request = Request("R001", "M001", 10000)
    return cards, state, merchant, request


def test_equal_benefit_uses_user_priority():
    cards, state, merchant, request = make_case()

    result = decide(
        request, merchant, cards, state, DbPolicy()
    )

    assert result.approved
    assert result.benefit_won == 500
    assert result.selected_card_id == "BANK_B"


def test_higher_benefit_overrides_user_priority():
    cards, state, merchant, request = make_case(
        rate_a="0.10",
        rate_b="0.05",
    )

    result = decide(
        request, merchant, cards, state, DbPolicy()
    )

    assert result.approved
    assert result.benefit_won == 1000
    assert result.selected_card_id == "BANK_A"


def test_other_category_priority_does_not_apply():
    cards, state, merchant, request = make_case()

    state.category_priorities = {
        "MART": {
            "BANK_B": 1,
            "BANK_A": 2,
        }
    }

    result = decide(
        request, merchant, cards, state, DbPolicy()
    )

    # 카페에 설정된 우선순위가 없으므로
    # 기존 동률 처리 기준인 카드 ID 순서 적용
    assert result.selected_card_id == "BANK_A"


def test_quote_does_not_change_priorities():
    cards, state, merchant, request = make_case()
    original = deepcopy(state)

    decide(request, merchant, cards, state, DbPolicy())

    assert state == original


def test_commit_preserves_priority_configuration():
    cards, state, merchant, request = make_case()

    result = process(
        request, merchant, cards, state, DbPolicy()
    )

    assert result.approved
    assert result.selected_card_id == "BANK_B"
    assert state.accounts["A001"] == 90000
    assert state.category_priorities["CAFE"]["BANK_B"] == 1


def test_ineligible_priority_card_is_not_selected():
    cards, state, merchant, request = make_case()

    # BANK_B가 잔액을 사용할 수 없는 계좌를 참조
    cards[1] = Card(
        id="BANK_B",
        type=CardType.DEBIT,
        account_id="EMPTY",
        rules=cards[1].rules,
    )

    result = decide(
        request, merchant, cards, state, DbPolicy()
    )

    assert result.approved
    assert result.selected_card_id == "BANK_A"
