
# tests/test_p1_monthly_db_repository.py

import pytest

from onepass.p1_monthly_db_repository import (
    DBRuleMonth,
    MonthlyDBError,
    P1MonthlyDBRepository,
    assess_state,
    valid_month,
)


PRODUCT = "BNK_CR_P07"


def make_rule(
    rule_id="BR_P07_CAFE",
    *,
    count_cap=None,
    eligible=350000,
    used=1000,
):
    return DBRuleMonth(
        rule_id=rule_id,
        product_id=PRODUCT,
        eligible_perf_won=eligible,
        excluded_perf_won=0,
        threshold_met=1,
        benefit_used_won=used,
        shared_cap_group="GROUP_A",
        monthly_count_cap=count_cap,
        perf_basis_code="PREV_MONTH",
    )


class FakeCursor:
    def __init__(
        self,
        card_rows=None,
        close_rows=None,
        rule_rows=None,
    ):
        self.card_rows = (
            [("U001", PRODUCT)]
            if card_rows is None else card_rows
        )
        self.close_rows = (
            [(400000, 2500)]
            if close_rows is None else close_rows
        )
        self.rule_rows = (
            [tuple(vars(make_rule()).values())]
            if rule_rows is None else rule_rows
        )
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.query = " ".join(
            str(query).lower().split()
        )

    def fetchall(self):
        if "from public.user_card" in self.query:
            return self.card_rows
        if "from public.card_month_close" in self.query:
            return self.close_rows
        if "from public.card_perf_month_close" in self.query:
            return self.rule_rows
        raise AssertionError(self.query)


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.fake_cursor


def load(**changes):
    cursor = FakeCursor(**changes)
    repo = P1MonthlyDBRepository(
        connect=lambda: FakeConnection(cursor)
    )
    return repo.load(
        user_card_id="UC001",
        base_month="2026-09",
    )


def test_month_validation():
    valid_month("2026-09")


@pytest.mark.parametrize(
    "month",
    ["2026-13", "2026-9", "", "abc"],
)
def test_invalid_month(month):
    with pytest.raises(MonthlyDBError):
        valid_month(month)


def test_realistic_month_load():
    result = load()
    assert result.user_id == "U001"
    assert result.product_id == PRODUCT
    assert result.spend_total_won == 400000
    assert len(result.rules) == 1
    assert result.rules[0].benefit_used_won == 1000


def test_performance_stays_unconfirmed():
    result = load()
    assert result.status == "UNRESOLVED"
    assert (
        "PERFORMANCE_BASIS_NOT_CONFIRMED"
        in result.reasons
    )


def test_used_count_not_inferred():
    status, reasons = assess_state(
        spend_total_won=400000,
        benefit_total_won=2500,
        rule_rows=(make_rule(count_cap=3),),
    )
    assert status == "UNRESOLVED"
    assert "MONTHLY_USED_COUNT_NOT_AVAILABLE" in reasons


def test_missing_month_close():
    result = load(close_rows=[])
    assert "CARD_SPEND_MISSING" in result.reasons


def test_missing_rule_month():
    result = load(rule_rows=[])
    assert "RULE_MONTH_DATA_MISSING" in result.reasons


def test_missing_usage_is_not_zero():
    rule = make_rule(used=None)
    status, reasons = assess_state(
        spend_total_won=400000,
        benefit_total_won=2500,
        rule_rows=(rule,),
    )
    assert status == "UNRESOLVED"
    assert "RULE_BENEFIT_USAGE_MISSING" in reasons


def test_duplicate_rules_detected():
    rule = make_rule()
    _, reasons = assess_state(
        spend_total_won=400000,
        benefit_total_won=2500,
        rule_rows=(rule, rule),
    )
    assert "DUPLICATE_RULE_MONTH" in reasons


def test_user_card_missing():
    with pytest.raises(
        MonthlyDBError,
        match="USER_CARD_NOT_FOUND",
    ):
        load(card_rows=[])


def test_product_mismatch_blocked():
    row = list(vars(make_rule()).values())
    row[1] = "BNK_CR_P09"
    with pytest.raises(
        MonthlyDBError,
        match="RULE_PRODUCT_MISMATCH",
    ):
        load(rule_rows=[tuple(row)])
