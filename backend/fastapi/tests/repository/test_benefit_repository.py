
from app.core.database import SessionLocal
from app.repositories.benefit_repository import BenefitRepository


def test_get_rule_by_id_not_found():
    with SessionLocal() as db:
        repository = BenefitRepository(db)

        rule = repository.get_rule_by_id(
            "__nonexistent_test_rule__"
        )

        assert rule is None


def test_get_rules_by_product_id():
    with SessionLocal() as db:
        repository = BenefitRepository(db)

        rules = repository.get_rules_by_product_id(
            "__nonexistent_test_product__"
        )

        assert isinstance(rules, list)
        assert rules == []


def test_get_industries_by_rule_id():
    with SessionLocal() as db:
        repository = BenefitRepository(db)

        industries = repository.get_industries_by_rule_id(
            "__nonexistent_test_rule__"
        )

        assert isinstance(industries, list)
        assert industries == []


def test_get_cap_tiers_by_product_id():
    with SessionLocal() as db:
        repository = BenefitRepository(db)

        tiers = repository.get_cap_tiers_by_product_id(
            "__nonexistent_test_product__"
        )

        assert isinstance(tiers, list)
        assert tiers == []


def test_get_perf_excludes_by_product_id():
    with SessionLocal() as db:
        repository = BenefitRepository(db)

        excludes = repository.get_perf_excludes_by_product_id(
            "__nonexistent_test_product__"
        )

        assert isinstance(excludes, list)
        assert excludes == []


def test_get_perf_excludes_by_rule_id():
    with SessionLocal() as db:
        repository = BenefitRepository(db)

        excludes = repository.get_perf_excludes_by_rule_id(
            "__nonexistent_test_rule__"
        )

        assert isinstance(excludes, list)
        assert excludes == []
