import app.db_entities.auth_entity
import app.db_entities.benefit_entity
import app.db_entities.card_entity
import app.db_entities.category_entity
import app.db_entities.ledger_entity
import app.db_entities.identity_card_entity
import app.db_entities.merchant_entity
import app.db_entities.policy_entity
import app.db_entities.registration_entity
import app.db_entities.user_entity
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.api.v1.routers.auth_router import router as auth_router
from app.api.v1.routers.identity_card_router import router as identity_card_router
from app.api.v1.routers.user_router import router as user_router
from app.core.database import Base
from app.db_entities.auth_entity import UserCredential, UserSession
from app.db_entities.identity_card_entity import UserIdentityCard
from app.services.auth_service import AuthService


def create_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    db = session_factory()
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(identity_card_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), db, engine


def test_register_login_and_logout_create_a_persistent_account():
    client, db, engine = create_client()
    try:
        unauthenticated = client.get("/api/v1/users/USER_001/profile")
        assert unauthenticated.status_code == 401

        registered = client.post(
            "/api/v1/auth/register",
            json={"username": "NewUser", "password": "secure-pass-123"},
        )
        assert registered.status_code == 201
        account = registered.json()
        user_id = account["user"]["user_id"]
        token = account["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        credential = db.get(UserCredential, "newuser")
        assert credential is not None
        assert credential.user_id == user_id
        assert credential.password_hash != "secure-pass-123"
        assert db.get(UserSession, token) is None

        profile = client.get(
            f"/api/v1/users/{user_id}/profile",
            headers=auth_headers,
        )
        identity_cards = client.get(
            f"/api/v1/users/{user_id}/identity-cards",
            headers=auth_headers,
        )
        wallet = client.get(
            f"/api/v1/users/{user_id}/wallet",
            headers=auth_headers,
        )
        assert profile.status_code == 200
        assert profile.json()["display_name"] == "NewUser"
        assert identity_cards.status_code == 200
        assert identity_cards.json() == []
        assert wallet.status_code == 200
        assert wallet.json()["balance_won"] == 0

        duplicate = client.post(
            "/api/v1/auth/register",
            json={"username": "newuser", "password": "secure-pass-456"},
        )
        assert duplicate.status_code == 409

        other_account = client.post(
            "/api/v1/auth/register",
            json={"username": "another", "password": "secure-pass-456"},
        ).json()
        cross_account = client.get(
            f"/api/v1/users/{user_id}/profile",
            headers={"Authorization": f"Bearer {other_account['access_token']}"},
        )
        assert cross_account.status_code == 403

        wrong_password = client.post(
            "/api/v1/auth/login",
            json={"username": "newuser", "password": "incorrect-pass"},
        )
        assert wrong_password.status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "NEWUSER", "password": "secure-pass-123"},
        )
        assert login.status_code == 200
        assert login.json()["user"]["user_id"] == user_id

        logout = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert logout.status_code == 204
        after_logout = client.get(
            f"/api/v1/users/{user_id}/profile",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert after_logout.status_code == 401
    finally:
        db.close()
        engine.dispose()


def test_register_rejects_short_password_and_invalid_username():
    client, db, engine = create_client()
    try:
        short_password = client.post(
            "/api/v1/auth/register",
            json={"username": "user-1", "password": "short"},
        )
        invalid_username = client.post(
            "/api/v1/auth/register",
            json={"username": "id with spaces", "password": "secure-pass-123"},
        )
        assert short_password.status_code == 422
        assert invalid_username.status_code == 422
    finally:
        db.close()
        engine.dispose()


def test_seeded_demo_password_hash_matches_authentication_format():
    seeded_hash = (
        "pbkdf2_sha256$310000$lbe3ACu_z8Uo90xO02YypQ=="
        "$TiLE1SZstmunCoq0OY900o4Mdoz1wvnByc0zPYWb_MQ="
    )
    assert AuthService._verify_password("1234", seeded_hash)
    assert not AuthService._verify_password("1235", seeded_hash)


def test_identity_cards_are_returned_only_to_their_authenticated_owner():
    client, db, engine = create_client()
    try:
        registered = client.post(
            "/api/v1/auth/register",
            json={"username": "identity-user", "password": "secure-pass-123"},
        ).json()
        user_id = registered["user"]["user_id"]
        db.add(
            UserIdentityCard(
                identity_card_id="DEMO-CIVIC-001",
                user_id=user_id,
                card_type="CIVIC",
                issuer_name="부산광역시 (데모)",
                title="부산광역시 시민증",
                holder_name="테스트 사용자",
                subtitle="부산 금정구 · 데모 인증",
                status="ACTIVE",
                service_summary="시민 인증 · 지역 혜택",
                credential_label="데모 시민증",
                source_mode="SYNTHETIC",
                created_at=AuthService._now(),
            )
        )
        db.commit()
        token = registered["access_token"]
        identity_cards = client.get(
            f"/api/v1/users/{user_id}/identity-cards",
            headers={"Authorization": f"Bearer {token}"},
        )
        denied = client.get(
            f"/api/v1/users/{user_id}/identity-cards",
            headers={"Authorization": "Bearer " + ("x" * 40)},
        )
        other_account = client.post(
            "/api/v1/auth/register",
            json={"username": "identity-other", "password": "secure-pass-456"},
        ).json()
        cross_owner = client.get(
            f"/api/v1/users/{user_id}/identity-cards",
            headers={"Authorization": f"Bearer {other_account['access_token']}"},
        )
        assert identity_cards.status_code == 200
        assert identity_cards.json()[0]["title"] == "부산광역시 시민증"
        assert identity_cards.json()[0]["source_mode"] == "SYNTHETIC"
        assert denied.status_code == 401
        assert cross_owner.status_code == 403
    finally:
        db.close()
        engine.dispose()
