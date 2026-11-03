from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routers.admin_router import (
    get_admin_service,
    router,
)
from app.services.admin_service import classify_cohort


class FakeAdminService:
    """테스트용 직원 대시보드 서비스"""

    def get_overview(self):
        return {"counts": {"users": 1}, "scenarios": {"S00": 10, "S01": 20}}

    def get_users(self):
        return [{"id": "U0001", "g": "G1", "a": 10, "c": 20}]

    def get_user_transactions(self, user_id: str):
        if user_id != "U0001":
            return None
        return [{"transaction_id": "T1", "amount_won": 1000}]


def create_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_admin_service] = lambda: FakeAdminService()
    return TestClient(app)


def test_overview():
    response = create_client().get("/admin/overview")
    assert response.status_code == 200
    assert response.json()["counts"]["users"] == 1


def test_users():
    response = create_client().get("/admin/users")
    assert response.status_code == 200
    assert response.json()[0]["g"] == "G1"


def test_user_transactions_not_found():
    response = create_client().get("/admin/users/NOPE/transactions")
    assert response.status_code == 404


def test_classify_cohort():
    assert classify_cohort("ACTIVE", "300K_500K") == ("G4", "활성", False)
    assert classify_cohort("ACTIVE", "NON_MEMBER") == ("G6", "미보유", True)
    assert classify_cohort(None, "NON_MEMBER") == ("G6", "미보유", False)
    assert classify_cohort(None, None) == ("G7", "정보 없음", False)
