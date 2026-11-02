
# tests/test_p1_eligibility_repository.py

from datetime import date
from types import SimpleNamespace

import pytest

from onepass.p1_eligibility_repository import (
    P1EligibilityRepository,
)


class FakeCursor:
    def __init__(
        self,
        *,
        rule=("ANY", "ASSUMED", None, None),
        merchant=("CAFE_BAKERY",),
        targets=None,
        mappings=None,
    ):
        self.rule = rule
        self.merchant = merchant
        self.targets = (
            [("CATEGORY", "FOOD_CAFE", "INCLUDE")]
            if targets is None else targets
        )
        self.mappings = (
            [("CAFE_BAKERY", "FOOD_CAFE")]
            if mappings is None else mappings
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
        if "from public.benefit_rule" in self.query:
            return [] if self.rule is None else [self.rule]
        if "from public.merchant" in self.query:
            return [] if self.merchant is None else [self.merchant]
        if "from public.benefit_industry" in self.query:
            return self.targets
        if "from public.benefit_category_map" in self.query:
            return self.mappings
        raise AssertionError(self.query)


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor


def payment(lane="OFFLINE", provider=None):
    return SimpleNamespace(
        lane=lane,
        payment_provider=provider,
        sales_channel=(
            "OFFLINE" if lane == "OFFLINE"
            else "ONLINE"
        ),
    )


def evaluate(
    *,
    rule=("ANY", "ASSUMED", None, None),
    merchant=("CAFE_BAKERY",),
    targets=None,
    mappings=None,
    pay=None,
):
    cursor = FakeCursor(
        rule=rule,
        merchant=merchant,
        targets=targets,
        mappings=mappings,
    )
    repo = P1EligibilityRepository(
        connect=lambda: FakeConnection(cursor)
    )
    return repo.evaluate(
        rule_id="BR_TEST",
        merchant_id="M00001",
        payment=pay or payment(),
        as_of="2026-10-27",
    )


def test_category_and_offline_match():
    r = evaluate()
    assert r.status == "ELIGIBLE"
    assert r.target_status == "ELIGIBLE"
    assert r.channel_status == "ELIGIBLE"


def test_category_and_online_match():
    r = evaluate(pay=payment("ONLINE"))
    assert r.eligible


def test_category_mismatch():
    r = evaluate(
        targets=[("CATEGORY", "FUEL", "INCLUDE")]
    )
    assert r.status == "INELIGIBLE"


def test_merchant_match():
    r = evaluate(
        targets=[("MERCHANT", "M00001", "INCLUDE")]
    )
    assert r.eligible


def test_merchant_excluded():
    r = evaluate(
        targets=[
            ("CATEGORY", "FOOD_CAFE", "INCLUDE"),
            ("MERCHANT", "M00001", "EXCLUDE"),
        ]
    )
    assert r.status == "INELIGIBLE"
    assert r.reason == "EXPLICITLY_EXCLUDED"


def test_naverpay_channel_match():
    r = evaluate(
        targets=[
            ("CATEGORY", "FOOD_CAFE", "INCLUDE"),
            ("CHANNEL", "NAVERPAY", "INCLUDE"),
        ],
        pay=payment("SIMPLE_PAY", "NAVERPAY"),
    )
    assert r.eligible


def test_naverpay_channel_rejects_kakaopay():
    r = evaluate(
        targets=[
            ("CATEGORY", "FOOD_CAFE", "INCLUDE"),
            ("CHANNEL", "NAVERPAY", "INCLUDE"),
        ],
        pay=payment("SIMPLE_PAY", "KAKAOPAY"),
    )
    assert r.status == "INELIGIBLE"


def test_channel_only_rule_not_assumed_universal():
    r = evaluate(
        targets=[("CHANNEL", "NAVERPAY", "INCLUDE")],
        pay=payment("SIMPLE_PAY", "NAVERPAY"),
    )
    assert r.status == "UNRESOLVED"


def test_missing_category_mapping():
    r = evaluate(mappings=[])
    assert r.status == "UNRESOLVED"
    assert r.reason == "CATEGORY_MAPPING_MISSING"


def test_invalid_target_type():
    r = evaluate(
        targets=[("UNKNOWN", "X", "INCLUDE")]
    )
    assert r.status == "UNRESOLVED"


def test_pending_source_not_automatically_verified():
    r = evaluate(
        rule=("ANY", "PENDING", None, None)
    )
    assert r.status == "ELIGIBLE"
    assert r.source_status == "PENDING"


def test_rule_not_found():
    r = evaluate(rule=None)
    assert r.status == "UNRESOLVED"
    assert r.reason == "RULE_NOT_FOUND_OR_DUPLICATED"


def test_merchant_not_found():
    r = evaluate(merchant=None)
    assert r.status == "UNRESOLVED"


def test_expired_rule():
    r = evaluate(
        rule=(
            "ANY", "ASSUMED",
            date(2026, 1, 1),
            date(2026, 9, 30),
        )
    )
    assert r.status == "INELIGIBLE"
    assert r.reason == "RULE_OUT_OF_VALIDITY"


def test_ambiguous_card_requirement():
    r = evaluate(
        rule=("CARD", "ASSUMED", None, None)
    )
    assert r.status == "UNRESOLVED"
    assert r.channel_status == "UNRESOLVED"


@pytest.mark.parametrize(
    "invalid_date",
    ["invalid", "2026-99-99"],
)
def test_invalid_date_rejected(invalid_date):
    with pytest.raises(ValueError):
        repo = P1EligibilityRepository(
            connect=lambda: None
        )
        repo.evaluate(
            rule_id="BR_TEST",
            merchant_id="M00001",
            payment=payment(),
            as_of=invalid_date,
        )
