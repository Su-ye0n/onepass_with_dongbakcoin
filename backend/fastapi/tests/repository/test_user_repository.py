
from app.core.database import SessionLocal
from app.repositories.user_repository import UserRepository


TEST_USER_ID = "__nonexistent_test_user__"
TEST_ACCOUNT_ID = "__nonexistent_test_account__"
TEST_WALLET_ID = "__nonexistent_test_wallet__"
TEST_ONECARD_ID = "__nonexistent_test_onecard__"


def test_get_user_by_id_not_found():
    with SessionLocal() as db:
        repository = UserRepository(db)

        user = repository.get_user_by_id(TEST_USER_ID)

        assert user is None


def test_get_users():
    with SessionLocal() as db:
        repository = UserRepository(db)

        users = repository.get_users(limit=5, offset=0)

        assert isinstance(users, list)
        assert len(users) <= 5

        print(f"조회된 사용자 수: {len(users)}")


def test_get_accounts_by_user_id():
    with SessionLocal() as db:
        repository = UserRepository(db)

        accounts = repository.get_accounts_by_user_id(
            TEST_USER_ID
        )

        assert accounts == []


def test_get_account_by_id_not_found():
    with SessionLocal() as db:
        repository = UserRepository(db)

        account = repository.get_account_by_id(
            TEST_ACCOUNT_ID
        )

        assert account is None


def test_get_wallets_by_user_id():
    with SessionLocal() as db:
        repository = UserRepository(db)

        wallets = repository.get_wallets_by_user_id(
            TEST_USER_ID
        )

        assert wallets == []


def test_get_wallet_by_id_not_found():
    with SessionLocal() as db:
        repository = UserRepository(db)

        wallet = repository.get_wallet_by_id(
            TEST_WALLET_ID
        )

        assert wallet is None


def test_get_onecards_by_user_id():
    with SessionLocal() as db:
        repository = UserRepository(db)

        onecards = repository.get_onecards_by_user_id(
            TEST_USER_ID
        )

        assert onecards == []


def test_get_onecard_by_id_not_found():
    with SessionLocal() as db:
        repository = UserRepository(db)

        onecard = repository.get_onecard_by_id(
            TEST_ONECARD_ID
        )

        assert onecard is None
