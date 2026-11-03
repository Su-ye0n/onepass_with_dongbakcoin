from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth_dependencies import require_path_user
from app.api.dependencies import get_db
from app.schemas.user_schema import (
    UserProfileResponse,
    UserProfileUpdateRequest,
    WalletBalanceResponse,
    WalletTopUpRequest,
    WalletTopUpResponse,
)
from app.services.user_service import (
    DuplicateTopUpError,
    UserNotFoundError,
    UserService,
    WalletNotFoundError,
    WalletSelectionError,
)


router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(require_path_user)],
)


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db)


@router.get(
    "/{user_id}/profile",
    response_model=UserProfileResponse,
)
def get_profile(
    user_id: str,
    service: UserService = Depends(get_user_service),
):
    try:
        return service.get_profile(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put(
    "/{user_id}/profile",
    response_model=UserProfileResponse,
)
def update_profile(
    user_id: str,
    request: UserProfileUpdateRequest,
    service: UserService = Depends(get_user_service),
):
    try:
        return service.update_profile(user_id, request)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{user_id}/wallet",
    response_model=WalletBalanceResponse,
)
def get_wallet_balance(
    user_id: str,
    service: UserService = Depends(get_user_service),
):
    try:
        return service.get_wallet_balance(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WalletNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{user_id}/wallet/top-ups",
    response_model=WalletTopUpResponse,
)
def create_wallet_top_up(
    user_id: str,
    request: WalletTopUpRequest,
    service: UserService = Depends(get_user_service),
):
    try:
        return service.top_up(user_id, request)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WalletNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WalletSelectionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DuplicateTopUpError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
