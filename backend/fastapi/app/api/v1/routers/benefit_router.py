from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.repositories.benefit_repository import BenefitRepository
from app.schemas.benefit_schema import BenefitRuleResponse
from app.services.benefit_service import BenefitService



# ----------------- 카드 혜택 조회 API ------------
router = APIRouter(prefix="/benefits", tags=["Benefits"])
def get_benefit_service(
    db: Session = Depends(get_db),
) -> BenefitService:
    """혜택 조회 서비스 의존성 생성"""
    repository = BenefitRepository(db)
    return BenefitService(repository)


@router.get(
    "/products/{product_id}",
    response_model=list[BenefitRuleResponse],
)
def get_benefit_rules_by_product(
    product_id: str,
    service: BenefitService = Depends(get_benefit_service),
):
    """카드 상품별 혜택 규칙 목록 조회"""
    return service.get_rules_by_product_id(product_id)


@router.get(
    "/{rule_id}",
    response_model=BenefitRuleResponse,
)
def get_benefit_rule(
    rule_id: str,
    service: BenefitService = Depends(get_benefit_service),
):
    """혜택 규칙 단건 조회"""
    rule = service.get_rule_by_id(rule_id)

    if rule is None:
        raise HTTPException(
            status_code=404,
            detail="혜택 규칙을 찾을 수 없습니다.",
        )

    return rule






