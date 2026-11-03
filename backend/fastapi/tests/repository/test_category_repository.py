
from app.core.database import SessionLocal
from app.repositories.category_repository import CategoryRepository


TEST_USER_ID = "__nonexistent_test_user__"
TEST_CATEGORY_CODE = "__nonexistent_test_category__"
TEST_INDUSTRY_CODE = "__nonexistent_test_industry__"
TEST_PRIORITY_ID = "__nonexistent_test_priority__"


def test_get_category_map_by_id_not_found():
    with SessionLocal() as db:
        repository = CategoryRepository(db)

        category_map = repository.get_category_map_by_id(-1)

        assert category_map is None


def test_get_category_maps_by_industry_code():
    with SessionLocal() as db:
        repository = CategoryRepository(db)

        category_maps = (
            repository.get_category_maps_by_industry_code(
                TEST_INDUSTRY_CODE
            )
        )

        assert category_maps == []


def test_get_all_category_maps():
    with SessionLocal() as db:
        repository = CategoryRepository(db)

        category_maps = repository.get_all_category_maps(
            limit=5,
            offset=0,
        )

        assert isinstance(category_maps, list)
        assert len(category_maps) <= 5

        print(f"조회된 카테고리 매핑 수: {len(category_maps)}")


def test_get_user_categories():
    with SessionLocal() as db:
        repository = CategoryRepository(db)

        categories = repository.get_user_categories(
            TEST_USER_ID
        )

        assert categories == []


def test_get_user_category_not_found():
    with SessionLocal() as db:
        repository = CategoryRepository(db)

        category = repository.get_user_category(
            TEST_USER_ID,
            TEST_CATEGORY_CODE,
        )

        assert category is None


def test_get_priorities_by_user_id():
    with SessionLocal() as db:
        repository = CategoryRepository(db)

        priorities = repository.get_priorities_by_user_id(
            TEST_USER_ID
        )

        assert priorities == []


def test_get_priorities_by_category():
    with SessionLocal() as db:
        repository = CategoryRepository(db)

        priorities = repository.get_priorities_by_category(
            TEST_USER_ID,
            TEST_CATEGORY_CODE,
        )

        assert priorities == []


def test_get_priority_by_id_not_found():
    with SessionLocal() as db:
        repository = CategoryRepository(db)

        priority = repository.get_priority_by_id(
            TEST_PRIORITY_ID
        )

        assert priority is None