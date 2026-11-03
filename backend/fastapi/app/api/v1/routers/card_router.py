from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.repositories.card_repository import CardRepository
from app.schemas.card_schema import CardProductResponse
from app.services.card_service import CardService
from app.schemas.card_schema import UserCardResponse
from app.repositories.user_repository import UserRepository
from app.schemas.card_schema import UserCardCreateRequest


from app.schemas.card_schema import (
    CardPriorityUpdateRequest,
    UserCardResponse,
)





# --------- 카드 상품 조회 API ------------
router = APIRouter(
    prefix="/cards",
    tags=["Cards"],
)


def get_card_service(
    db: Session = Depends(get_db),
) -> CardService:
    card_repository = CardRepository(db)
    user_repository = UserRepository(db)
    
    return CardService(
        repository=card_repository,
        user_repository=user_repository,
    )


@router.get(
    "/products",
    response_model=list[CardProductResponse],
)
def get_card_products(
    service: CardService = Depends(get_card_service),
):
    """전체 카드 상품 조회"""
    return service.get_all_products()


@router.get(
    "/products/{product_id}",
    response_model=CardProductResponse,
)
def get_card_product(
    product_id: str,
    service: CardService = Depends(get_card_service),
):
    """카드 상품 상세 조회"""

    product = service.get_product_by_id(product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="카드 상품을 찾을 수 없습니다.",
        )

    return product









# --------- 사용자 보유 카드 조회 API ------------
user_card_router = APIRouter(
    prefix="/users",
    tags=["User Cards"],
)












@user_card_router.get(
    "/{user_id}/cards",
    response_model=list[UserCardResponse],
)
def get_user_cards(
    user_id: str,
    service: CardService = Depends(get_card_service),
):
    """사용자 보유 카드 목록 조회"""

    return service.get_user_cards(user_id)









# --------- 사용자 카드 우선순위 조회 ------------
@user_card_router.get(
    "/{user_id}/cards/priorities",
    response_model=list[UserCardResponse],
)
def get_card_priorities(
    user_id: str,
    service: CardService = Depends(get_card_service),
):
    """사용자 카드 우선순위 조회"""
    return service.get_card_priorities(user_id)






# --------- 사용자 카드 우선순위 설정 ------------
@user_card_router.put(
    "/{user_id}/cards/priorities",
    response_model=list[UserCardResponse],
)
def update_card_priorities(
    user_id: str,
    request: CardPriorityUpdateRequest,
    service: CardService = Depends(get_card_service),
):
    """사용자 카드 우선순위 일괄 변경"""

    priorities = {
        card.user_card_id: card.priority
        for card in request.cards
    }

    try:
        return service.update_card_priorities(
            user_id=user_id,
            priorities=priorities,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc





# ----- ---- 사용자 보유 카드 단건 조회 ------------
@user_card_router.get(
    "/{user_id}/cards/{user_card_id}",
    response_model=UserCardResponse,
)
def get_user_card(
    user_id: str,
    user_card_id: str,
    service: CardService = Depends(get_card_service),
):
    """사용자 보유 카드 단건 조회"""

    card = service.get_user_card(user_id, user_card_id)

    if card is None:
        raise HTTPException(
            status_code=404,
            detail="보유 카드를 찾을 수 없습니다.",
        )

    return card





# --------- 사용자 보유 카드 등록 API ------------
@user_card_router.post(
    "/{user_id}/cards",
    response_model=UserCardResponse,
    status_code=201,
)
def create_user_card(
    user_id: str,
    request: UserCardCreateRequest,
    service: CardService = Depends(get_card_service),
):
    """사용자 보유 카드 등록"""

    try:
        return service.create_user_card(
            user_id=user_id,
            product_id=request.product_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc





# --------- 사용자 등록 카드 삭제 ------------
@user_card_router.delete(
    "/{user_id}/cards/{user_card_id}",
    status_code=204,
)
def delete_user_card(
    user_id: str,
    user_card_id: str,
    service: CardService = Depends(get_card_service),
):
    """사용자 등록 카드 삭제"""

    success = service.deactivate_user_card(
        user_id=user_id,
        user_card_id=user_card_id,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="등록된 카드를 찾을 수 없거나 이미 해제된 카드입니다.",
        )







