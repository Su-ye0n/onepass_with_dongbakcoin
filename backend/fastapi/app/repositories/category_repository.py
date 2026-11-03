
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.db_entities.category_entity import (
    BenefitCategoryMap,
    UserCategory,
    UserCategoryPriority,
)




class CategoryRepository:
    """카테고리 매핑 및 사용자 카드 우선순위 데이터 접근 계층"""

    def __init__(self, db: Session):
        self.db = db

    def get_category_map_by_id(
        self,
        map_id: int,
    ) -> BenefitCategoryMap | None:
        """카테고리 매핑 ID로 단건 조회"""

        statement = select(BenefitCategoryMap).where(
            BenefitCategoryMap.map_id == map_id
        )

        return self.db.scalar(statement)

    def get_category_maps_by_industry_code(
        self,
        industry_code: str,
    ) -> list[BenefitCategoryMap]:
        """업종 코드에 해당하는 카테고리 매핑 조회"""

        statement = (
            select(BenefitCategoryMap)
            .where(
                BenefitCategoryMap.industry_code == industry_code
            )
            .order_by(
                BenefitCategoryMap.valid_from,
                BenefitCategoryMap.map_id,
            )
        )

        return list(self.db.scalars(statement).all())

    def get_all_category_maps(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BenefitCategoryMap]:
        """전체 카테고리 매핑 페이지 단위 조회"""

        statement = (
            select(BenefitCategoryMap)
            .order_by(BenefitCategoryMap.map_id)
            .offset(offset)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())

    def get_user_categories(
        self,
        user_id: str,
    ) -> list[UserCategory]:
        """사용자별 카테고리 목록 조회"""

        statement = (
            select(UserCategory)
            .where(UserCategory.user_id == user_id)
            .order_by(
                UserCategory.display_order,
                UserCategory.user_category_code,
            )
        )

        return list(self.db.scalars(statement).all())

    def get_user_category(
        self,
        user_id: str,
        user_category_code: str,
    ) -> UserCategory | None:
        """사용자별 특정 카테고리 조회"""

        statement = select(UserCategory).where(
            UserCategory.user_id == user_id,
            UserCategory.user_category_code == user_category_code,
        )

        return self.db.scalar(statement)

    def get_priorities_by_user_id(
        self,
        user_id: str,
    ) -> list[UserCategoryPriority]:
        """사용자별 카드 우선순위 설정 조회"""

        statement = (
            select(UserCategoryPriority)
            .where(UserCategoryPriority.user_id == user_id)
            .order_by(
                UserCategoryPriority.user_category_code,
                UserCategoryPriority.priority_group,
                UserCategoryPriority.priority_id,
            )
        )

        return list(self.db.scalars(statement).all())

    def get_priorities_by_category(
        self,
        user_id: str,
        user_category_code: str,
    ) -> list[UserCategoryPriority]:
        """사용자별 특정 카테고리의 카드 우선순위 조회"""

        statement = (
            select(UserCategoryPriority)
            .where(
                UserCategoryPriority.user_id == user_id,
                UserCategoryPriority.user_category_code
                == user_category_code,
            )
            .order_by(
                UserCategoryPriority.priority_group,
                UserCategoryPriority.priority_id,
            )
        )

        return list(self.db.scalars(statement).all())

    def get_priority_by_id(
        self,
        priority_id: str,
    ) -> UserCategoryPriority | None:
        """우선순위 설정 ID로 단건 조회"""

        statement = select(UserCategoryPriority).where(
            UserCategoryPriority.priority_id == priority_id
        )

        return self.db.scalar(statement)



    # --------- 카테고리별 카드 우선순위 저장 ------------
    def replace_user_category_priorities(
        self,
        user_id: str,
        priorities: list[UserCategoryPriority],
    ) -> list[UserCategoryPriority]:
        """사용자의 카테고리별 카드 우선순위 전체 교체"""

        statement = delete(UserCategoryPriority).where(
            UserCategoryPriority.user_id == user_id
        )

        try:
            self.db.execute(statement)

            self.db.add_all(priorities)
            self.db.commit()

            for priority in priorities:
                self.db.refresh(priority)

        except Exception:
            self.db.rollback()
            raise

        return priorities