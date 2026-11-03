import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db_entities.auth_entity import UserCredential, UserSession
from app.db_entities.user_entity import DbWallet, User, UserProfile
from app.schemas.auth_schema import AuthResponse, AuthUserResponse


PASSWORD_ITERATIONS = 310_000
SESSION_LIFETIME = timedelta(days=30)
DUMMY_SALT = bytes(16)
DUMMY_PASSWORD_HASH = hashlib.pbkdf2_hmac(
    "sha256",
    b"invalid-login",
    DUMMY_SALT,
    PASSWORD_ITERATIONS,
)


class UsernameTakenError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def register(self, username: str, password: str) -> AuthResponse:
        normalized_username = username.lower()
        if self.db.get(UserCredential, normalized_username) is not None:
            raise UsernameTakenError

        now = self._now()
        user_id = f"USR_{uuid4().hex}"
        wallet_id = f"WALLET_{uuid4().hex}"
        user = User(
            user_id=user_id,
            user_type="REGISTERED",
            origin_type="ACCOUNT",
            user_status="ACTIVE",
            created_at=now,
        )
        self.db.add(user)
        self.db.add(
            UserCredential(
                username=normalized_username,
                user_id=user_id,
                password_hash=self._hash_password(password),
                created_at=now,
            )
        )
        self.db.add(
            UserProfile(
                user_id=user_id,
                display_name=username,
                source_mode="REGISTERED",
                created_at=now,
                updated_at=now,
            )
        )
        self.db.add(
            DbWallet(
                wallet_id=wallet_id,
                user_id=user_id,
                charge_won=0,
                cashback_won=0,
                policy_support_won=0,
                opening_balance_at=now,
                wallet_status="ACTIVE",
                origin_type="ACCOUNT",
            )
        )
        token = secrets.token_urlsafe(32)
        expires_at = now + SESSION_LIFETIME
        self.db.add(
            UserSession(
                token_hash=self._hash_token(token),
                user_id=user_id,
                created_at=now,
                expires_at=expires_at,
            )
        )

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if self.db.get(UserCredential, normalized_username) is not None:
                raise UsernameTakenError from None
            raise

        return self._response(token, expires_at, user_id, username)

    def login(self, username: str, password: str) -> AuthResponse:
        normalized_username = username.lower()
        credential = self.db.get(UserCredential, normalized_username)
        valid_password = self._verify_password(
            password,
            credential.password_hash if credential else None,
        )
        if credential is None or not valid_password:
            raise InvalidCredentialsError

        user = self.db.get(User, credential.user_id)
        if user is None or user.user_status != "ACTIVE":
            raise InvalidCredentialsError

        now = self._now()
        token = secrets.token_urlsafe(32)
        expires_at = now + SESSION_LIFETIME
        self.db.add(
            UserSession(
                token_hash=self._hash_token(token),
                user_id=user.user_id,
                created_at=now,
                expires_at=expires_at,
            )
        )
        self.db.commit()
        return self._response(token, expires_at, user.user_id, normalized_username)

    def logout(self, token: str) -> None:
        session = self.db.get(UserSession, self._hash_token(token))
        if session is not None:
            self.db.delete(session)
            self.db.commit()

    @staticmethod
    def _response(
        token: str,
        expires_at: datetime,
        user_id: str,
        username: str,
    ) -> AuthResponse:
        return AuthResponse(
            access_token=token,
            expires_at=expires_at.replace(tzinfo=timezone.utc),
            user=AuthUserResponse(user_id=user_id, username=username),
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PASSWORD_ITERATIONS,
        )
        return "pbkdf2_sha256${}${}${}".format(
            PASSWORD_ITERATIONS,
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )

    @staticmethod
    def _verify_password(password: str, encoded_hash: str | None) -> bool:
        if encoded_hash is None:
            salt = DUMMY_SALT
            expected = DUMMY_PASSWORD_HASH
        else:
            try:
                algorithm, iterations, encoded_salt, encoded_digest = encoded_hash.split("$")
                if algorithm != "pbkdf2_sha256":
                    raise ValueError("Unsupported password hash")
                salt = base64.urlsafe_b64decode(encoded_salt)
                expected = base64.urlsafe_b64decode(encoded_digest)
                iteration_count = int(iterations)
            except (ValueError, TypeError):
                return False
            if iteration_count != PASSWORD_ITERATIONS:
                return False

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PASSWORD_ITERATIONS,
        )
        return hmac.compare_digest(actual, expected)


def get_current_user_id(db: Session, token: str) -> str | None:
    token_hash = AuthService._hash_token(token)
    session = db.get(UserSession, token_hash)
    if session is None or session.expires_at <= AuthService._now():
        return None

    user = db.get(User, session.user_id)
    if user is None or user.user_status != "ACTIVE":
        return None
    return user.user_id
