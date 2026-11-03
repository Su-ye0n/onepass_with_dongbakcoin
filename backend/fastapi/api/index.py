"""Vercel 진입점: backend/fastapi 의 FastAPI 앱을 그대로 노출한다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # backend/fastapi
sys.path.insert(0, str(ROOT))

from fastapi.responses import RedirectResponse  # noqa: E402

from app.main import app  # noqa: E402


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/api/v1/admin/dashboard")
