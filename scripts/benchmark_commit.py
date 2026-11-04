"""'실제 거래가 반영되는 부분' 처리시간 측정 (모의 결제 1건 = 검증 + 원장 INSERT + COMMIT).

실행: DATABASE_URL=sqlite:// python scripts/benchmark_commit.py
- 임시 SQLite(메모리 / 파일)에서 PaymentService.create_mock_payment 를 2,000번 호출한다.
- 운영 DB(PostgreSQL)는 네트워크 왕복이 더해지므로 숫자가 다르다. 운영 환경 측정값은 아니다.
- 중복 요청 거절과 오류 시 ROLLBACK 도 함께 확인한다.
"""
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "fastapi"))

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base  # noqa: E402
import app.db_entities.user_entity as ue  # noqa: E402
import app.db_entities.card_entity as ce  # noqa: E402
import app.db_entities.merchant_entity as me  # noqa: E402
import app.db_entities.ledger_entity  # noqa: E402,F401
import app.db_entities.policy_entity  # noqa: E402,F401
import app.db_entities.benefit_entity  # noqa: E402,F401
import app.db_entities.category_entity  # noqa: E402,F401
import app.db_entities.registration_entity  # noqa: E402,F401
import app.db_entities.auth_entity  # noqa: E402,F401
import app.db_entities.identity_card_entity  # noqa: E402,F401
from app.db_entities.ledger_entity import Ledger  # noqa: E402
from app.repositories.ledger_repository import LedgerRepository  # noqa: E402
from app.schemas.payment_schema import MockPaymentRequest  # noqa: E402
from app.services.payment_service import PaymentService  # noqa: E402


def make_session(url: str):
    memory = url == "sqlite://"
    engine = create_engine(
        url, connect_args={"check_same_thread": False},
        **({"poolclass": StaticPool} if memory else {}),
    )

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def pay(session, k: int, request_id: str | None = None):
    req = MockPaymentRequest(
        request_id=request_id or f"R{k}", user_id="U1",
        user_card_id="UC1", merchant_id="M1", amount_won=20000,
    )
    with session() as db:
        PaymentService(db=db).create_mock_payment(req)


for label, url in (
    ("SQLite 메모리", "sqlite://"),
    ("SQLite 파일  ", "sqlite:///" + tempfile.mkdtemp() + "/bench.db"),
):
    S = make_session(url)
    with S() as db:  # 외래키 순서대로 시드 데이터 입력
        db.add(ue.User(user_id="U1")); db.commit()
        db.add(me.Merchant(merchant_id="M1", industry_code="RESTAURANT")); db.commit()
        db.add(ce.UserCard(user_card_id="UC1", user_id="U1")); db.commit()
    ms = []
    for k in range(2000):
        t0 = time.perf_counter(); pay(S, k); ms.append((time.perf_counter() - t0) * 1e3)
    ms.sort()
    print(f"[{label}] 결제 1건: 중앙값 {statistics.median(ms):.2f} ms / 95% {ms[int(len(ms) * .95)]:.2f} ms")
    try:
        pay(S, 0, "R0"); print("  중복 요청이 거절되지 않음 (오류)")
    except Exception as exc:
        print(f"  같은 request_id 재요청 -> {type(exc).__name__} (거절)")
    with S() as db:
        try:
            LedgerRepository(db).create_ledger(Ledger(
                tx_id="x", request_id="bad", user_id="NO_SUCH_USER",
                event_type="PAYMENT", approval_status="APPROVED", source_mode="MOCK"))
            db.commit()
        except Exception as exc:
            db.rollback(); print(f"  없는 사용자로 INSERT -> {type(exc).__name__}, ROLLBACK")
    with S() as db:
        left = len(LedgerRepository(db).get_ledgers_by_request_id("bad"))
        print(f"  ROLLBACK 후 남은 행: {left}건")
