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


def make_card(rule):
    return Card(
        id="BANK_001",
        type=CardType.DEBIT,
        account_id="A001",
        rules=(rule,),
    )


def quote(card, merchant):
    state = State(accounts={"A001": 100000})
    return decide(
        Request("REQ1", merchant.id, 10000),
        merchant,
        [card],
        state,
        DbPolicy(),
    )


def test_category_benefit():
    """카페 업종이면 매장에 관계없이 할인."""
    rule = BenefitRule(
        id="CAFE10",
        categories=("CAFE",),
        rate=Decimal("0.10"),
    )
    card = make_card(rule)

    cafe = Merchant("M_CAFE", "CAFE", False)
    mart = Merchant("M_MART", "MART", False)

    assert quote(card, cafe).benefit_won == 1000
    assert quote(card, mart).benefit_won == 0


def test_merchant_specific_benefit():
    """같은 영화관 업종이어도 지정 매장에만 할인."""
    rule = BenefitRule(
        id="CINEMA20",
        categories=(),
        rate=Decimal("0.20"),
        merchants=("M_CINEMA_A",),
    )
    card = make_card(rule)

    cinema_a = Merchant("M_CINEMA_A", "CINEMA", False)
    cinema_b = Merchant("M_CINEMA_B", "CINEMA", False)

    assert quote(card, cinema_a).benefit_won == 2000
    assert quote(card, cinema_b).benefit_won == 0


def test_excluded_merchant():
    """카페 업종이지만 특정 매장은 할인 제외."""
    rule = BenefitRule(
        id="CAFE10",
        categories=("CAFE",),
        rate=Decimal("0.10"),
        excluded_merchants=("M_EXCLUDED",),
    )
    card = make_card(rule)

    normal = Merchant("M_NORMAL", "CAFE", False)
    excluded = Merchant("M_EXCLUDED", "CAFE", False)

    assert quote(card, normal).benefit_won == 1000

    result = quote(card, excluded)
    assert result.approved
    assert result.benefit_won == 0

    candidate = result.candidates[0]
    assert candidate.eligible is True


def test_exclude_overrides_include():
    """INCLUDE와 EXCLUDE가 겹치면 EXCLUDE 우선."""
    rule = BenefitRule(
        id="RULE1",
        categories=("CAFE",),
        rate=Decimal("0.10"),
        merchants=("M_EXCLUDED",),
        excluded_merchants=("M_EXCLUDED",),
    )
    card = make_card(rule)

    merchant = Merchant("M_EXCLUDED", "CAFE", False)

    result = quote(card, merchant)

    assert result.approved
    assert result.benefit_won == 0


def test_payment_updates_selected_rule_usage():
    """실제 모의 결제 확정 후에만 혜택 사용량 증가."""
    rule = BenefitRule(
        id="CAFE10",
        categories=("CAFE",),
        rate=Decimal("0.10"),
        monthly_cap=1500,
    )
    card = make_card(rule)
    merchant = Merchant("M1", "CAFE", False)
    state = State(accounts={"A001": 30000})

    first = process(
        Request("R1", "M1", 10000),
        merchant,
        [card],
        state,
        DbPolicy(),
    )

    second = process(
        Request("R2", "M1", 10000),
        merchant,
        [card],
        state,
        DbPolicy(),
    )

    assert first.benefit_won == 1000
    assert second.benefit_won == 500
    assert state.benefit_used["CAFE10"] == 1500
    assert state.accounts["A001"] == 10000
