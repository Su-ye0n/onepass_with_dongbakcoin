
from app.core.database import SessionLocal
from app.repositories.policy_repository import PolicyRepository


def test_get_policy_by_id_not_found():
    with SessionLocal() as db:
        repository = PolicyRepository(db)

        policy = repository.get_policy_by_id(
            "__nonexistent_test_policy__"
        )

        assert policy is None


def test_get_all_policies():
    with SessionLocal() as db:
        repository = PolicyRepository(db)

        policies = repository.get_all_policies()

        assert isinstance(policies, list)

        print(f"전체 정책 수: {len(policies)}")


def test_get_rates_by_policy_id():
    with SessionLocal() as db:
        repository = PolicyRepository(db)

        rates = repository.get_rates_by_policy_id(
            "__nonexistent_test_policy__"
        )

        assert isinstance(rates, list)
        assert rates == []


def test_get_rate_by_sales_band_not_found():
    with SessionLocal() as db:
        repository = PolicyRepository(db)

        rate = repository.get_rate_by_sales_band(
            "__nonexistent_test_policy__",
            "__nonexistent_test_band__",
        )

        assert rate is None


def test_get_bonuses_by_policy_id():
    with SessionLocal() as db:
        repository = PolicyRepository(db)

        bonuses = repository.get_bonuses_by_policy_id(
            "__nonexistent_test_policy__"
        )

        assert isinstance(bonuses, list)
        assert bonuses == []


def test_get_bonus_by_id_not_found():
    with SessionLocal() as db:
        repository = PolicyRepository(db)

        bonus = repository.get_bonus_by_id(-1)

        assert bonus is None