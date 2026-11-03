
from datetime import datetime

from app.core.database import SessionLocal
from app.repositories.ledger_repository import LedgerRepository


TEST_USER_ID = "__nonexistent_test_user__"
TEST_CARD_ID = "__nonexistent_test_card__"
TEST_TX_ID = "__nonexistent_test_tx__"
TEST_REQUEST_ID = "__nonexistent_test_request__"
TEST_MERCHANT_ID = "__nonexistent_test_merchant__"
TEST_EVENT_TYPE = "__nonexistent_test_event__"


def test_get_ledger_by_id_not_found():
    with SessionLocal() as db:
        repository = LedgerRepository(db)

        ledger = repository.get_ledger_by_id(-1)

        assert ledger is None


def test_get_ledgers_by_user_id():
    with SessionLocal() as db:
        repository = LedgerRepository(db)

        ledgers = repository.get_ledgers_by_user_id(
            TEST_USER_ID
        )

        assert ledgers == []


def test_get_ledgers_by_tx_id():
    with SessionLocal() as db:
        repository = LedgerRepository(db)

        ledgers = repository.get_ledgers_by_tx_id(
            TEST_TX_ID
        )

        assert ledgers == []


def test_get_ledgers_by_request_id():
    with SessionLocal() as db:
        repository = LedgerRepository(db)

        ledgers = repository.get_ledgers_by_request_id(
            TEST_REQUEST_ID
        )

        assert ledgers == []


def test_get_ledgers_by_user_card_id():
    with SessionLocal() as db:
        repository = LedgerRepository(db)

        ledgers = repository.get_ledgers_by_user_card_id(
            TEST_CARD_ID
        )

        assert ledgers == []


def test_get_ledgers_by_event_type():
    with SessionLocal() as db:
        repository = LedgerRepository(db)

        ledgers = repository.get_ledgers_by_event_type(
            TEST_EVENT_TYPE
        )

        assert ledgers == []


def test_get_ledgers_by_user_and_period():
    with SessionLocal() as db:
        repository = LedgerRepository(db)

        ledgers = repository.get_ledgers_by_user_and_period(
            user_id=TEST_USER_ID,
            start_at=datetime(2026, 10, 1),
            end_at=datetime(2026, 11, 1),
        )

        assert ledgers == []


def test_get_ledgers_by_merchant_id():
    with SessionLocal() as db:
        repository = LedgerRepository(db)

        ledgers = repository.get_ledgers_by_merchant_id(
            TEST_MERCHANT_ID
        )

        assert ledgers == []
