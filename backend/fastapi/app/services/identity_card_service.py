from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_entities.identity_card_entity import UserIdentityCard


class IdentityCardService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_identity_cards(self, user_id: str) -> list[UserIdentityCard]:
        statement = (
            select(UserIdentityCard)
            .where(UserIdentityCard.user_id == user_id)
            .order_by(UserIdentityCard.card_type, UserIdentityCard.identity_card_id)
        )
        return list(self.db.scalars(statement).all())
