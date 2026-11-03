from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth_dependencies import require_path_user
from app.api.dependencies import get_db
from app.schemas.identity_card_schema import UserIdentityCardResponse
from app.services.identity_card_service import IdentityCardService


router = APIRouter(
    prefix="/users",
    tags=["Demo Identity Cards"],
    dependencies=[Depends(require_path_user)],
)


def get_identity_card_service(
    db: Session = Depends(get_db),
) -> IdentityCardService:
    return IdentityCardService(db)


@router.get(
    "/{user_id}/identity-cards",
    response_model=list[UserIdentityCardResponse],
)
def get_user_identity_cards(
    user_id: str,
    service: IdentityCardService = Depends(get_identity_card_service),
) -> list[UserIdentityCardResponse]:
    return service.get_user_identity_cards(user_id)
