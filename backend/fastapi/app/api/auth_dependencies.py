from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db_entities.user_entity import User
from app.services.auth_service import get_current_user_id


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = get_current_user_id(db, credentials.credentials)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="로그인 정보가 만료되었습니다. 다시 로그인해 주세요.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_path_user(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    requested_user_id = request.path_params.get("user_id")
    if requested_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="본인 계정만 조회할 수 있습니다.")
    return current_user
