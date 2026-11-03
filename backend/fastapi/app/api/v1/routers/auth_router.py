from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.auth_dependencies import bearer_scheme, get_current_user
from app.api.dependencies import get_db
from app.db_entities.user_entity import User
from app.schemas.auth_schema import (
    AuthResponse,
    CredentialsRequest,
    LoginRequest,
)
from app.services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    UsernameTakenError,
)
from fastapi.security import HTTPAuthorizationCredentials


router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    request: CredentialsRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    try:
        return service.register(request.username, request.password)
    except UsernameTakenError as exc:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.") from exc


@router.post("/login", response_model=AuthResponse)
def login(
    request: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    try:
        return service.login(request.username, request.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("/logout", status_code=204)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    if credentials is not None:
        service.logout(credentials.credentials)
    return Response(status_code=204)
