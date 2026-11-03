
from app.core.database import SessionLocal
from app.repositories.registration_repository import (
    RegistrationRepository,
)


TEST_ISSUANCE_ID = "__nonexistent_test_issuance__"
TEST_OWNER_ID = "__nonexistent_test_owner__"
TEST_USER_ID = "__nonexistent_test_user__"
TEST_OWNED_CARD_ID = "__nonexistent_test_owned_card__"
TEST_PRODUCT_ID = "__nonexistent_test_product__"


def test_get_verifier_by_issuance_id_not_found():
    with SessionLocal() as db:
        repository = RegistrationRepository(db)

        verifier = repository.get_verifier_by_issuance_id(
            TEST_ISSUANCE_ID
        )

        assert verifier is None


def test_get_verifiers_by_owner_id():
    with SessionLocal() as db:
        repository = RegistrationRepository(db)

        verifiers = repository.get_verifiers_by_owner_id(
            TEST_OWNER_ID
        )

        assert verifiers == []


def test_get_issued_card_by_id_not_found():
    with SessionLocal() as db:
        repository = RegistrationRepository(db)

        issued_card = repository.get_issued_card_by_id(
            TEST_ISSUANCE_ID
        )

        assert issued_card is None


def test_get_issued_cards_by_owner_id():
    with SessionLocal() as db:
        repository = RegistrationRepository(db)

        issued_cards = repository.get_issued_cards_by_owner_id(
            TEST_OWNER_ID
        )

        assert issued_cards == []


def test_get_owned_card_by_id_not_found():
    with SessionLocal() as db:
        repository = RegistrationRepository(db)

        owned_card = repository.get_owned_card_by_id(
            TEST_OWNED_CARD_ID
        )

        assert owned_card is None


def test_get_owned_cards_by_user_id():
    with SessionLocal() as db:
        repository = RegistrationRepository(db)

        owned_cards = repository.get_owned_cards_by_user_id(
            TEST_USER_ID
        )

        assert owned_cards == []


def test_get_owned_card_by_user_and_issuance():
    with SessionLocal() as db:
        repository = RegistrationRepository(db)

        owned_card = (
            repository.get_owned_card_by_user_and_issuance(
                TEST_USER_ID,
                TEST_ISSUANCE_ID,
            )
        )

        assert owned_card is None


def test_get_owned_cards_by_product_id():
    with SessionLocal() as db:
        repository = RegistrationRepository(db)

        owned_cards = repository.get_owned_cards_by_product_id(
            TEST_PRODUCT_ID
        )

        assert owned_cards == []
