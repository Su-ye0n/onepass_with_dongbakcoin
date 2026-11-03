from pathlib import Path
import sys

from sqlalchemy import text

# 프로젝트 루트
BASE_DIR = Path(__file__).resolve().parents[1]

# backend 모듈 경로 등록
sys.path.insert(0, str(BASE_DIR / "backend"))

from app.core.database import engine


def init_db():
    sql_path = BASE_DIR / "db" / "schema.sql"

    if not sql_path.exists():
        raise FileNotFoundError(
            f"SQL 파일을 찾을 수 없습니다: {sql_path}"
        )

    sql_script = sql_path.read_text(encoding="utf-8-sig")

    # SQL 파일 전체를 하나의 트랜잭션으로 실행
    with engine.begin() as connection:
        connection.exec_driver_sql(sql_script)

    print("NeonDB 테이블 생성 완료!")


if __name__ == "__main__":
    init_db()