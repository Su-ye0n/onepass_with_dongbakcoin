from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.repositories.merchant_repository import MerchantRepository
from app.schemas.merchant_schema import MerchantResponse
from app.services.merchant_service import MerchantService


# --------- 가맹점 API -----    -------
router = APIRouter(
    prefix="/merchants",
    tags=["Merchants"],
)


def get_merchant_service(
    db: Session = Depends(get_db),
) -> MerchantService:
    repository = MerchantRepository(db)
    return MerchantService(repository)


# --------- 가맹점 목록 조회 ------------
@router.get(
    "",
    response_model=list[MerchantResponse],
)
def get_merchants(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: MerchantService = Depends(get_merchant_service),
):
    """가맹점 목록 페이지 단위 조회"""

    return service.get_merchants(
        limit=limit,
        offset=offset,
    )


# --------- 가맹점 단건 조회 ------------
@router.get(
    "/{merchant_id}",
    response_model=MerchantResponse,
)
def get_merchant(
    merchant_id: str,
    service: MerchantService = Depends(get_merchant_service),
):
    """가맹점 ID로 단건 조회"""

    merchant = service.get_merchant(merchant_id)

    if merchant is None:
        raise HTTPException(
            status_code=404,
            detail="가맹점을 찾을 수 없습니다.",
        )

    return merchant