from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db_entities.benefit_entity
import app.db_entities.card_entity
import app.db_entities.category_entity
import app.db_entities.ledger_entity
import app.db_entities.merchant_entity
import app.db_entities.policy_entity
import app.db_entities.registration_entity
import app.db_entities.user_entity
from app.api.auth_dependencies import require_path_user
from app.api.v1.routers.user_router import get_user_service, router
from app.core.database import Base
from app.db_entities.ledger_entity import Ledger
from app.db_entities.user_entity import DbWallet, User, UserProfile
from app.schemas.user_schema import (
    UserProfileUpdateRequest,
    WalletTopUpRequest,
)
from app.services.user_service import (
    DuplicateTopUpError,
    UserService,
)
from scripts.load_demo_users import load_demo_users


def create_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False)


def seed_user(db: Session) -> None:
    db.add(
        User(
            user_id="USER_001",
            user_type="SYNTHETIC",
            origin_type="SYNTHETIC",
            user_status="ACTIVE",
        )
    )
    db.add(
        UserProfile(
            user_id="USER_001",
            display_name="김개미",
            student_card_id="DEMO-STUDENT-0001",
            phone_number="010-0000-0000",
            address="부산광역시 (데모 주소)",
            source_mode="SYNTHETIC",
        )
    )
    db.add(
        DbWallet(
            wallet_id="WALLET_USER_001",
            user_id="USER_001",
            charge_won=30_000,
            cashback_won=1_000,
            policy_support_won=2_000,
            wallet_status="ACTIVE",
            origin_type="SYNTHETIC",
        )
    )
    db.commit()


def test_profile_get_and_update():
    engine, session_factory = create_database()
    try:
        with session_factory() as db:
            seed_user(db)
            service = UserService(db)
            profile = service.get_profile("USER_001")
            assert profile.display_name == "김개미"
            assert profile.student_card_id == "DEMO-STUDENT-0001"

            updated = service.update_profile(
                "USER_001",
                UserProfileUpdateRequest(
                    display_name="김개미",
                    student_card_id="DEMO-STUDENT-0002",
                    phone_number="010-0000-0000",
                    address="부산광역시 (수정된 데모 주소)",
                ),
            )
            assert updated.student_card_id == "DEMO-STUDENT-0002"
            assert updated.address == "부산광역시 (수정된 데모 주소)"
    finally:
        engine.dispose()


def test_wallet_balance_and_top_up_are_idempotent():
    engine, session_factory = create_database()
    try:
        with session_factory() as db:
            seed_user(db)
            service = UserService(db)
            before = service.get_wallet_balance("USER_001")
            assert before.balance_won == 33_000

            request = WalletTopUpRequest(
                request_id="topup-request-001",
                amount_won=10_000,
                wallet_id="WALLET_USER_001",
            )
            first = service.top_up("USER_001", request)
            second = service.top_up("USER_001", request)

            assert first.tx_id == second.tx_id
            assert first.balance_won == second.balance_won == 43_000
            assert service.get_wallet_balance("USER_001").balance_won == 43_000
            topups = db.scalars(
                select(Ledger).where(Ledger.event_type == "TOPUP")
            ).all()
            assert len(topups) == 1
            assert topups[0].approval_status == "APPROVED"
            assert topups[0].bucket_type == "DB_CHARGE"
            assert topups[0].source_mode == "MOCK"
    finally:
        engine.dispose()


def test_reused_top_up_request_id_with_different_amount_conflicts():
    engine, session_factory = create_database()
    try:
        with session_factory() as db:
            seed_user(db)
            service = UserService(db)
            service.top_up(
                "USER_001",
                WalletTopUpRequest(
                    request_id="topup-request-002",
                    amount_won=5_000,
                    wallet_id="WALLET_USER_001",
                ),
            )
            try:
                service.top_up(
                    "USER_001",
                    WalletTopUpRequest(
                        request_id="topup-request-002",
                        amount_won=6_000,
                        wallet_id="WALLET_USER_001",
                    ),
                )
            except DuplicateTopUpError:
                pass
            else:
                raise AssertionError("Expected conflicting request ID to fail")

            assert service.get_wallet_balance("USER_001").balance_won == 38_000
    finally:
        engine.dispose()


def test_user_profile_and_wallet_routes():
    engine, session_factory = create_database()
    try:
        with session_factory() as db:
            seed_user(db)
            service = UserService(db)
            app = FastAPI()
            app.include_router(router, prefix="/api/v1")
            app.dependency_overrides[get_user_service] = lambda: service
            app.dependency_overrides[require_path_user] = lambda: db.get(
                User, "USER_001"
            )

            with TestClient(app) as client:
                profile = client.get("/api/v1/users/USER_001/profile")
                wallet = client.get("/api/v1/users/USER_001/wallet")
                top_up = client.post(
                    "/api/v1/users/USER_001/wallet/top-ups",
                    json={
                        "request_id": "topup-route-001",
                        "amount_won": 1_000,
                        "wallet_id": "WALLET_USER_001",
                    },
                )
                invalid_top_up = client.post(
                    "/api/v1/users/USER_001/wallet/top-ups",
                    json={
                        "request_id": "topup-route-002",
                        "amount_won": 500_001,
                    },
                )

            assert profile.status_code == 200
            assert profile.json()["display_name"] == "김개미"
            assert wallet.status_code == 200
            assert wallet.json()["balance_won"] == 33_000
            assert top_up.status_code == 200
            assert top_up.json()["approval_status"] == "APPROVED"
            assert top_up.json()["source_mode"] == "MOCK"
            assert invalid_top_up.status_code == 422
    finally:
        engine.dispose()


def test_synthetic_csv_loader_is_idempotent_for_local_databases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database_url = URL.create(
        "sqlite",
        database=str(tmp_path / "demo-seed.db"),
    ).render_as_string(hide_password=False)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE "user" (
                        user_id TEXT PRIMARY KEY,
                        user_type TEXT,
                        origin_type TEXT,
                        user_status TEXT
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE db_wallet (
                        wallet_id TEXT PRIMARY KEY,
                        user_id TEXT REFERENCES "user"(user_id),
                        charge_won INTEGER,
                        cashback_won INTEGER,
                        policy_support_won INTEGER,
                        wallet_status TEXT,
                        origin_type TEXT
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE ledger (
                        tx_id TEXT,
                        request_id TEXT,
                        user_id TEXT,
                        user_card_id TEXT,
                        merchant_id TEXT,
                        event_at TIMESTAMP,
                        event_seq INTEGER,
                        event_type TEXT,
                        bucket_type TEXT,
                        delta_won INTEGER,
                        gross_purchase_won INTEGER,
                        awarded_benefit_won INTEGER,
                        approval_status TEXT,
                        source_mode TEXT,
                        event_note TEXT
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE card_product (
                        product_id TEXT PRIMARY KEY
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE merchant (
                        merchant_id TEXT PRIMARY KEY
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE user_card (
                        user_card_id TEXT PRIMARY KEY,
                        user_id TEXT,
                        product_id TEXT,
                        card_status TEXT,
                        credit_limit_won INTEGER,
                        default_preference_rank INTEGER,
                        expires_at DATE,
                        active_from DATE,
                        registered_ref TEXT
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO "user" (user_id, user_type, origin_type)
                    VALUES ('U0004', 'SYNTHETIC', 'SYNTHETIC')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO card_product (product_id)
                    VALUES ('BNK_CR_P07'), ('BNK_CK_P23')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO user_card (
                        user_card_id, user_id, product_id, card_status,
                        credit_limit_won, default_preference_rank,
                        expires_at, active_from
                    ) VALUES
                    ('UC_U0004_CR', 'U0004', 'BNK_CR_P07', 'ACTIVE',
                     1500000, 1, '2028-12-31', '2025-01-01'),
                    ('UC_U0004_CK', 'U0004', 'BNK_CK_P23', 'ACTIVE',
                     NULL, 2, '2028-12-31', '2025-01-01')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO merchant (merchant_id)
                    VALUES ('M00001'), ('M00002'), ('M00003')
                    """
                )
            )
            migration_path = (
                Path(__file__).resolve().parents[5]
                / "db"
                / "migrations"
                / "20261103_profile_wallet_demo.sql"
            )
            for statement in migration_path.read_text(encoding="utf-8").split(";"):
                statement = statement.strip()
                if statement and statement.upper() not in {"BEGIN", "COMMIT"}:
                    connection.execute(text(statement))
            connection.execute(
                text("ALTER TABLE user_profile ADD COLUMN university TEXT")
            )
            connection.execute(
                text("ALTER TABLE user_profile ADD COLUMN department TEXT")
            )
    finally:
        engine.dispose()

    monkeypatch.setenv("DATABASE_URL", database_url)
    assert load_demo_users(apply=True) == 1
    assert load_demo_users(apply=True) == 1

    with create_engine(database_url).connect() as connection:
        profile = connection.execute(
            text(
                """
                SELECT display_name, student_card_id, university, department,
                       source_mode
                FROM user_profile
                WHERE user_id = 'USER_001'
                """
            )
        ).one()
        wallet = connection.execute(
            text("SELECT charge_won FROM db_wallet WHERE wallet_id = 'WALLET_USER_001'")
        ).scalar_one()
        card = connection.execute(
            text(
                """
                SELECT user_id, product_id, credit_limit_won
                FROM user_card
                WHERE user_card_id = 'DEMO_USER_CARD_001'
                """
            )
        ).one()
        demo_cards = connection.execute(
            text(
                """
                SELECT user_card_id, product_id, credit_limit_won,
                       default_preference_rank, registered_ref
                FROM user_card
                WHERE user_id = 'USER_001'
                ORDER BY default_preference_rank
                """
            )
        ).all()
        source_cards = connection.execute(
            text(
                """
                SELECT user_card_id, product_id, credit_limit_won
                FROM user_card
                WHERE user_id = 'U0004'
                ORDER BY default_preference_rank
                """
            )
        ).all()
        payment_summary = connection.execute(
            text(
                """
                SELECT COUNT(*), SUM(gross_purchase_won)
                FROM ledger
                WHERE user_id = 'USER_001' AND event_type = 'PAYMENT'
                """
            )
        ).one()
    assert profile == ("김개미", "s_123", "갈매기 대학교", "철학과", "SYNTHETIC")
    assert wallet == 30_000
    assert tuple(card) == ("USER_001", "BNK_CR_P07", 1_500_000)
    assert [tuple(item[:4]) for item in demo_cards] == [
        ("DEMO_USER_CARD_001", "BNK_CR_P07", 1_500_000, 1),
        ("DEMO_USER_CARD_U0004_CK", "BNK_CK_P23", None, 2),
    ]
    assert [tuple(item) for item in source_cards] == [
        ("UC_U0004_CR", "BNK_CR_P07", 1_500_000),
        ("UC_U0004_CK", "BNK_CK_P23", None),
    ]
    assert tuple(payment_summary) == (3, 35_500)


def test_synthetic_csv_loader_blocks_remote_database_by_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://demo:password@example.invalid/demo",
    )
    with pytest.raises(RuntimeError, match="restricted to a local database"):
        load_demo_users(apply=True)
