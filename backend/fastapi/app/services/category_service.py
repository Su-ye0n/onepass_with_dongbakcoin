from uuid import uuid4

from app.db_entities.category_entity import UserCategoryPriority
from app.repositories.card_repository import CardRepository
from app.repositories.category_repository import CategoryRepository
from app.schemas.category_priority_schema import CategoryPriorityItem


class CategoryService:
    """사용자 카테고리별 카드 우선순위 관리"""

    def __init__(
        self,
        category_repository: CategoryRepository,
        card_repository: CardRepository,
    ):
        self.category_repository = category_repository
        self.card_repository = card_repository

    def get_category_priorities(
        self,
        user_id: str,
    ) -> list[UserCategoryPriority]:
        """사용자의 카테고리별 카드 우선순위 조회"""

        return self.category_repository.get_priorities_by_user_id(
            user_id
        )

    def update_category_priorities(
        self,
        user_id: str,
        items: list[CategoryPriorityItem],
    ) -> list[UserCategoryPriority]:
        """카테고리별 카드 우선순위 전체 저장"""

        active_cards = self.card_repository.get_user_cards(user_id)

        active_card_ids = {
            card.user_card_id for card in active_cards
        }

        user_categories = self.category_repository.get_user_categories(
            user_id
        )

        enabled_category_codes = {
            category.user_category_code
            for category in user_categories
            if category.is_enabled == 1
        }

        for item in items:
            if item.user_card_id not in active_card_ids:
                raise ValueError(
                    "사용자 소유의 활성 카드만 설정할 수 있습니다."
                )

            if item.user_category_code not in enabled_category_codes:
                raise ValueError(
                    "사용할 수 없는 카테고리입니다."
                )

        # 카테고리별 우선순위가 1부터 연속되는지 확인
        ranks_by_category: dict[str, set[int]] = {}

        for item in items:
            ranks_by_category.setdefault(
                item.user_category_code, set()
            ).add(item.priority_group)

        for ranks in ranks_by_category.values():
            if ranks != set(range(1, len(ranks) + 1)):
                raise ValueError(
                    "우선순위는 카테고리별로 1부터 연속되어야 합니다."
                )

        priorities = [
            UserCategoryPriority(
                priority_id=str(uuid4()),
                user_id=user_id,
                user_category_code=item.user_category_code,
                user_card_id=item.user_card_id,
                priority_group=item.priority_group,
            )
            for item in items
        ]

        return self.category_repository.replace_user_category_priorities(
            user_id=user_id,
            priorities=priorities,
        )