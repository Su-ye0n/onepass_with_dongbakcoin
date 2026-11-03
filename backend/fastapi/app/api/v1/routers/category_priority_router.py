from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.repositories.card_repository import CardRepository
from app.repositories.category_repository import CategoryRepository
from app.schemas.category_priority_schema import (
    CategoryPriorityResponse,
    CategoryPriorityUpdateRequest,
)
from app.services.category_service import CategoryService


router = APIRouter(
    prefix="/users/{user_id}/category-priorities",
    tags=["Category Priorities"],
)


def get_category_service(
    db: Session = Depends(get_db),
) -> CategoryService:
    return CategoryService(
        category_repository=CategoryRepository(db),
        card_repository=CardRepository(db),
    )


@router.get(
    "",
    response_model=list[CategoryPriorityResponse],
)
def get_category_priorities(
    user_id: str,
    service: CategoryService = Depends(get_category_service),
):
    """사용자 업종별 카드 우선순위 조회"""

    return service.get_category_priorities(user_id)


@router.put(
    "",
    response_model=list[CategoryPriorityResponse],
)
def update_category_priorities(
    user_id: str,
    request: CategoryPriorityUpdateRequest,
    service: CategoryService = Depends(get_category_service),
):
    """사용자 업종별 카드 우선순위 일괄 저장"""

    try:
        return service.update_category_priorities(
            user_id=user_id,
            items=request.priorities,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc