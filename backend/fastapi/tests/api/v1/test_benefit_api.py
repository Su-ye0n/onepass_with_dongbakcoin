
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routers.benefit_router import (
    router,
    get_benefit_service,
)


class FakeBenefitService:
    """DB 없이 혜택 API를 테스트하기 위한 가짜 서비스"""

    def get_rule_by_id(self, rule_id: str):
        if rule_id == "BR_001":
            return {
                "rule_id": "BR_001",
                "product_id": "CARD_001",
                "benefit_name": "카페 할인",
                "benefit_type": "DISCOUNT",
                "rate": Decimal("0.10000"),
                "fixed_amount_won": None,
                "min_amount_won": 1000,
                "per_tx_cap_won": 2000,
                "monthly_cap_won": 10000,
                "shared_cap_group": None,
                "day_condition": None,
                "monthly_count_cap": None,
                "perf_threshold_won": 300000,
                "perf_basis_code": None,
                "reward_unit": "WON",
                "stack_rule": None,
                "payment_channel_required": None,
                "rounding_mode": None,
                "valid_from": None,
                "valid_to": None,
                "source_status": "ACTIVE",
            }

        return None

    def get_rules_by_product_id(self, product_id: str):
        if product_id == "CARD_001":
            return [self.get_rule_by_id("BR_001")]

        return []


def create_test_client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    app.dependency_overrides[get_benefit_service] = (
        lambda: FakeBenefitService()
    )

    return TestClient(app)


def test_get_benefit_rule():
    client = create_test_client()

    response = client.get("/api/v1/benefits/BR_001")

    assert response.status_code == 200
    assert response.json()["rule_id"] == "BR_001"
    assert response.json()["product_id"] == "CARD_001"


def test_get_benefit_rule_not_found():
    client = create_test_client()

    response = client.get("/api/v1/benefits/BR_999")

    assert response.status_code == 404


def test_get_benefit_rules_by_product():
    client = create_test_client()

    response = client.get(
        "/api/v1/benefits/products/CARD_001"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["rule_id"] == "BR_001"


def test_get_benefit_rules_by_product_empty():
    client = create_test_client()

    response = client.get(
        "/api/v1/benefits/products/CARD_999"
    )

    assert response.status_code == 200
    assert response.json() == []
