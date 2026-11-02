
# tests/test_p1_target_repository.py

import pytest

from onepass.p1_target_evaluator import TargetStatus
from onepass.p1_target_repository import (
    P1TargetRepository,
    choose_category,
)


class FakeCursor:
    def __init__(
        self,
        merchant_rows,
        condition_rows,
        mapping_rows=None,
    ):
        self.merchant_rows = merchant_rows
        self.condition_rows = condition_rows
        self.mapping_rows = mapping_rows or []
        self.last_query = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.last_query = " ".join(
            str(query).lower().split()
        )

    def fetchall(self):
        if "from public.merchant" in self.last_query:
            return self.merchant_rows

        if "from public.benefit_industry" in self.last_query:
            return self.condition_rows

        if "from public.benefit_category_map" in self.last_query:
            return self.mapping_rows

        raise AssertionError(
            f"UNEXPECTED_QUERY: {self.last_query}"
        )


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.fake_cursor


def evaluate(
    *,
    merchant_rows=None,
    condition_rows=None,
    mapping_rows=None,
):
    cursor = FakeCursor(
        merchant_rows=(
            [("CAFE_BAKERY",)]
            if merchant_rows is None
            else merchant_rows
        ),
        condition_rows=(
            [("CATEGORY", "FOOD_CAFE", "INCLUDE")]
            if condition_rows is None
            else condition_rows
        ),
        mapping_rows=(
            [("CAFE_BAKERY", "FOOD_CAFE")]
            if mapping_rows is None
            else mapping_rows
        ),
    )

    repo = P1TargetRepository(
        connect=lambda: FakeConnection(cursor)
    )

    return repo.evaluate(
        "BR_TEST",
        "M00001",
        "2026-10-27",
    )


def test_category_mapping():
    category, error = choose_category(
        [("CAFE_BAKERY", "FOOD_CAFE")],
        "CAFE_BAKERY",
    )
    assert category == "FOOD_CAFE"
    assert error is None


def test_missing_mapping():
    category, error = choose_category(
        [],
        "CAFE_BAKERY",
    )
    assert category is None
    assert error == "CATEGORY_MAPPING_MISSING"


def test_conflicting_mapping():
    category, error = choose_category(
        [
            ("CAFE_BAKERY", "FOOD_CAFE"),
            ("CAFE_BAKERY", "FOOD_REST"),
        ],
        "CAFE_BAKERY",
    )
    assert category is None
    assert error == "CATEGORY_MAPPING_AMBIGUOUS"


def test_duplicate_identical_mapping_allowed():
    category, error = choose_category(
        [
            ("CAFE_BAKERY", "FOOD_CAFE"),
            ("CAFE_BAKERY", "FOOD_CAFE"),
        ],
        "CAFE_BAKERY",
    )
    assert category == "FOOD_CAFE"
    assert error is None


def test_eligible_category_from_db():
    result = evaluate()
    assert result.status == TargetStatus.ELIGIBLE
    assert result.std_category == "FOOD_CAFE"


def test_unmatched_category_from_db():
    result = evaluate(
        condition_rows=[
            ("CATEGORY", "FUEL", "INCLUDE")
        ]
    )
    assert result.status == TargetStatus.INELIGIBLE


def test_merchant_only_match():
    result = evaluate(
        condition_rows=[
            ("MERCHANT", "M00001", "INCLUDE")
        ],
        mapping_rows=[],
    )
    assert result.status == TargetStatus.ELIGIBLE


def test_merchant_only_no_match():
    result = evaluate(
        condition_rows=[
            ("MERCHANT", "M00002", "INCLUDE")
        ],
        mapping_rows=[],
    )
    assert result.status == TargetStatus.INELIGIBLE


def test_exclusion_from_db():
    result = evaluate(
        condition_rows=[
            ("CATEGORY", "FOOD_CAFE", "INCLUDE"),
            ("MERCHANT", "M00001", "EXCLUDE"),
        ],
    )
    assert result.status == TargetStatus.INELIGIBLE
    assert result.reason == "EXPLICITLY_EXCLUDED"


def test_merchant_not_found():
    result = evaluate(merchant_rows=[])
    assert result.status == TargetStatus.UNRESOLVED
    assert result.reason == "MERCHANT_NOT_FOUND"


def test_missing_industry():
    result = evaluate(merchant_rows=[(None,)])
    assert result.status == TargetStatus.UNRESOLVED
    assert result.reason == "MERCHANT_INDUSTRY_MISSING"


def test_missing_rule_targets():
    result = evaluate(condition_rows=[])
    assert result.status == TargetStatus.UNRESOLVED
    assert result.reason == "TARGET_RULES_MISSING"


def test_missing_category_mapping():
    result = evaluate(mapping_rows=[])
    assert result.status == TargetStatus.UNRESOLVED
    assert result.reason == "CATEGORY_MAPPING_MISSING"


def test_channel_stays_unresolved():
    result = evaluate(
        condition_rows=[
            ("CHANNEL", "NAVERPAY", "INCLUDE")
        ],
    )
    assert result.status == TargetStatus.UNRESOLVED
    assert result.reason == "UNSUPPORTED_TARGET_CONDITION"


def test_rule_id_required():
    repo = P1TargetRepository(
        connect=lambda: None
    )
    with pytest.raises(ValueError):
        repo.evaluate("", "M00001", "2026-10-27")


def test_invalid_date():
    repo = P1TargetRepository(
        connect=lambda: None
    )
    with pytest.raises(ValueError):
        repo.evaluate(
            "BR_TEST",
            "M00001",
            "not-a-date",
        )
