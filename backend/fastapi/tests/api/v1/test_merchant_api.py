from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routers.merchant_router import (
    router,
    get_merchant_service,
)


class FakeMerchantService:
    """테스트용 가맹점 서비스"""

    def get_merchants(
        self,
        limit: int = 100,
        offset: int = 0,
    ):
        merchants = [
            {
                "merchant_id": "MERCHANT_001",
                "merchant_name": "테스트 가맹점 1",
                "industry_code": "FOOD",
            },
            {
                "merchant_id": "MERCHANT_002",
                "merchant_name": "테스트 가맹점 2",
                "industry_code": "CAFE",
            },
        ]

        return merchants[offset:offset + limit]

    def get_merchant(self, merchant_id: str):
        for merchant in self.get_merchants():
            if merchant["merchant_id"] == merchant_id:
                return merchant

        return None


def create_test_client():
    """테스트용 FastAPI 앱 생성"""

    app = FastAPI()

    app.include_router(router, prefix="/api/v1")

    app.dependency_overrides[get_merchant_service] = (
        lambda: FakeMerchantService()
    )

    return TestClient(app)


# ========================================
# 1. 가맹점 목록 조회
# ========================================

def test_get_merchants():
    with create_test_client() as client:
        response = client.get("/api/v1/merchants")

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["merchant_id"] == "MERCHANT_001"


# ========================================
# 2. 페이지네이션
# ========================================

def test_get_merchants_pagination():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/merchants?limit=1&offset=1"
        )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["merchant_id"] == "MERCHANT_002"


# ========================================
# 3. 빈 목록
# ========================================

def test_get_merchants_empty():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/merchants?offset=100"
        )

    assert response.status_code == 200
    assert response.json() == []


# ========================================
# 4. 가맹점 단건 조회
# ========================================

def test_get_merchant_by_id():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/merchants/MERCHANT_001"
        )

    assert response.status_code == 200
    assert response.json()["merchant_name"] == "테스트 가맹점 1"


# ========================================
# 5. 존재하지 않는 가맹점
# ========================================

def test_get_merchant_not_found():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/merchants/NOT_FOUND"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "가맹점을 찾을 수 없습니다."


# ========================================
# 6. 잘못된 limit
# ========================================

def test_invalid_limit():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/merchants?limit=501"
        )

    assert response.status_code == 422


# ========================================
# 7. 잘못된 offset
# ========================================

def test_invalid_offset():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/merchants?offset=-1"
        )

    assert response.status_code == 422