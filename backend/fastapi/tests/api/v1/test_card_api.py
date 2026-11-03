from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routers.card_router import (
    router,
    user_card_router,
    get_card_service,
)


class FakeCardService:
    """테스트용 카드 서비스"""

    # 카드 상품 조회
    def get_all_products(self):
        return [
            {
                "product_id": "CARD_001",
                "product_name": "테스트 카드",
                "issuer": "테스트 카드사",
                "card_type": "CREDIT",
                "product_status": "ACTIVE",
            }
        ]

    def get_product_by_id(self, product_id: str):
        for product in self.get_all_products():
            if product["product_id"] == product_id:
                return product

        return None

    # 사용자 보유 카드 조회
    def get_user_cards(self, user_id: str):
        if user_id != "USER_001":
            return []

        return [
            {
                "user_card_id": "UC_001",
                "user_id": "USER_001",
                "product_id": "CARD_001",
                "card_status": "ACTIVE",
            }
        ]

    def get_user_card(
        self,
        user_id: str,
        user_card_id: str,
    ):
        for card in self.get_user_cards(user_id):
            if card["user_card_id"] == user_card_id:
                return card

        return None


    # 사용자 보유 카드 등록
    def create_user_card(
        self,
        user_id: str,
        product_id: str,
    ):
        if user_id != "USER_001":
            raise ValueError("사용자를 찾을 수 없습니다.")

        if self.get_product_by_id(product_id) is None:
            raise ValueError("카드 상품을 찾을 수 없습니다.")

        return {
            "user_card_id": "UC_NEW_001",
            "user_id": user_id,
            "product_id": product_id,
            "card_status": "ACTIVE",
        }


    # 사용자 등록 카드 삭제
    # (이미 삭제된 카드를 다시 삭제하면 404)
    def deactivate_user_card(
        self,
        user_id: str,
        user_card_id: str,
    ) -> bool:
        if user_id != "USER_001":
            return False

        if user_card_id != "UC_001":
            return False

        if getattr(self, "card_deleted", False):
            return False

        self.card_deleted = True
        return True





    # 사용자 카드 우선순위 조회
    def get_card_priorities(self, user_id: str):
        if user_id != "USER_001":
            return []

        return [
            {
                "user_card_id": "UC_001",
                "user_id": user_id,
                "product_id": "CARD_001",
                "card_status": "ACTIVE",
                "default_preference_rank": 1,
            }
        ]



    # 사용자 카드 우선순위 설정
    def update_card_priorities(
        self,
        user_id: str,
        priorities: dict[str, int],
    ):
        if user_id != "USER_001":
            raise ValueError("우선순위를 설정할 활성 카드가 없습니다.")

        if priorities != {"UC_001": 1}:
            raise ValueError(
                "사용자의 모든 활성 카드를 포함해야 합니다."
            )

        return self.get_card_priorities(user_id)

    























    





def create_test_client():
    """테스트용 FastAPI 앱 생성"""

    app = FastAPI()

    # 카드 상품 조회 Router
    app.include_router(router, prefix="/api/v1")

    # 사용자 보유 카드 조회 Router
    app.include_router(user_card_router, prefix="/api/v1")

    # 실제 Service 대신 Fake Service 사용
    app.dependency_overrides[get_card_service] = (
        lambda: FakeCardService()
    )

    return TestClient(app)



# ========================================
# 7-1. 카드 상품 조회 API 테스트
# ========================================

def test_get_card_products():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/cards/products"
        )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["product_id"] == "CARD_001"


def test_get_card_product_by_id():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/cards/products/CARD_001"
        )

    assert response.status_code == 200
    assert response.json()["product_name"] == "테스트 카드"


def test_get_card_product_not_found():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/cards/products/NOT_FOUND"
        )

    assert response.status_code == 404


# ========================================
# 7-2. 사용자 보유 카드 조회 API 테스트
# ========================================

def test_get_user_cards():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/users/USER_001/cards"
        )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["user_card_id"] == "UC_001"


def test_get_user_card():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/users/USER_001/cards/UC_001"
        )

    assert response.status_code == 200
    assert response.json()["product_id"] == "CARD_001"


def test_get_user_card_not_found():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/users/USER_001/cards/NOT_FOUND"
        )

    assert response.status_code == 404


def test_cannot_get_other_users_card():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/users/USER_002/cards/UC_001"
        )

    assert response.status_code == 404




# ========================================
# 7-3. 사용자 보유 카드 등록 API 테스트
# ========================================

def test_create_user_card_success():
    with create_test_client() as client:
        response = client.post(
            "/api/v1/users/USER_001/cards",
            json={"product_id": "CARD_001"},
        )

    assert response.status_code == 201

    data = response.json()

    assert data["user_card_id"] == "UC_NEW_001"
    assert data["user_id"] == "USER_001"
    assert data["product_id"] == "CARD_001"
    assert data["card_status"] == "ACTIVE"


def test_create_user_card_user_not_found():
    with create_test_client() as client:
        response = client.post(
            "/api/v1/users/NOT_FOUND/cards",
            json={"product_id": "CARD_001"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "사용자를 찾을 수 없습니다."
    )


def test_create_user_card_product_not_found():
    with create_test_client() as client:
        response = client.post(
            "/api/v1/users/USER_001/cards",
            json={"product_id": "NOT_FOUND"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "카드 상품을 찾을 수 없습니다."
    )


def test_create_user_card_missing_product_id():
    with create_test_client() as client:
        response = client.post(
            "/api/v1/users/USER_001/cards",
            json={},
        )

    assert response.status_code == 422








# ========================================
# 사용자 등록 카드 삭제 API 테스트
# ========================================

def test_delete_user_card_success():
    with create_test_client() as client:
        response = client.delete(
            "/api/v1/users/USER_001/cards/UC_001"
        )

    assert response.status_code == 204
    assert response.content == b""


def test_delete_user_card_not_found():
    with create_test_client() as client:
        response = client.delete(
            "/api/v1/users/USER_001/cards/NOT_FOUND"
        )

    assert response.status_code == 404


def test_cannot_delete_other_users_card():
    with create_test_client() as client:
        response = client.delete(
            "/api/v1/users/USER_002/cards/UC_001"
        )

    assert response.status_code == 404





# 재삭제 테스트
def test_delete_user_card_twice():
    fake_service = FakeCardService()

    app = FastAPI()
    app.include_router(user_card_router, prefix="/api/v1")
    app.dependency_overrides[get_card_service] = lambda: fake_service

    with TestClient(app) as client:
        first = client.delete(
            "/api/v1/users/USER_001/cards/UC_001"
        )
        second = client.delete(
            "/api/v1/users/USER_001/cards/UC_001"
        )

    assert first.status_code == 204
    assert second.status_code == 404














# ========================================
# 7-5. 사용자 카드 우선순위 API 테스트
# ========================================

def test_get_card_priorities():
    with create_test_client() as client:
        response = client.get(
            "/api/v1/users/USER_001/cards/priorities"
        )

    assert response.status_code == 200
    assert response.json()[0]["default_preference_rank"] == 1


def test_update_card_priorities_success():
    with create_test_client() as client:
        response = client.put(
            "/api/v1/users/USER_001/cards/priorities",
            json={
                "cards": [
                    {"user_card_id": "UC_001", "priority": 1}
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()[0]["default_preference_rank"] == 1


def test_update_card_priorities_invalid_rank():
    with create_test_client() as client:
        response = client.put(
            "/api/v1/users/USER_001/cards/priorities",
            json={
                "cards": [
                    {"user_card_id": "UC_001", "priority": 0}
                ]
            },
        )

    assert response.status_code == 422


def test_update_card_priorities_wrong_card():
    with create_test_client() as client:
        response = client.put(
            "/api/v1/users/USER_001/cards/priorities",
            json={
                "cards": [
                    {"user_card_id": "OTHER_CARD", "priority": 1}
                ]
            },
        )

    assert response.status_code == 400