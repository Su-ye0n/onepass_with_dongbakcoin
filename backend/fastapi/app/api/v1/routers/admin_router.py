from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.repositories.admin_repository import AdminRepository
from app.services.admin_service import AdminService


# --------- 직원 대시보드 API (읽기 전용) ------------
router = APIRouter(
    prefix="/admin",
    tags=["Admin Dashboard"],
)

DASHBOARD_FILE = (
    Path(__file__).resolve().parents[3] / "static" / "admin_dashboard.html"
)


def get_admin_service(
    db: Session = Depends(get_db),
) -> AdminService:
    return AdminService(AdminRepository(db))


def _results_or_503(call):
    try:
        return call()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"시뮬레이션 결과 파일이 없습니다: {exc}",
        ) from exc


@router.get("/overview")
def get_overview(
    service: AdminService = Depends(get_admin_service),
):
    """KPI · 시나리오 합계 · 결제수단 배정 · 가맹점 업종 · 정책 · S02"""

    return _results_or_503(service.get_overview)


@router.get("/users")
def get_users(
    service: AdminService = Depends(get_admin_service),
):
    """사용자별 프로필 · 그룹(G1~G7) · 시나리오 혜택(a=S00, b=S10, c=S01, d=S11)"""

    return _results_or_503(service.get_users)


@router.get("/users/{user_id}/transactions")
def get_user_transactions(
    user_id: str,
    service: AdminService = Depends(get_admin_service),
):
    """한 사용자의 거래별 시나리오 비교 (선택 카드 · 혜택)"""

    items = _results_or_503(lambda: service.get_user_transactions(user_id))

    if items is None:
        raise HTTPException(
            status_code=404,
            detail="시뮬레이션 결과에 없는 사용자입니다.",
        )

    return items


@router.get("/dashboard", include_in_schema=False)
def get_dashboard():
    """직원 대시보드 화면 (같은 서버에서 API를 부르므로 CORS 설정 불필요)"""

    if not DASHBOARD_FILE.exists():
        raise HTTPException(status_code=404, detail="대시보드 파일이 없습니다.")

    return FileResponse(DASHBOARD_FILE, media_type="text/html")
