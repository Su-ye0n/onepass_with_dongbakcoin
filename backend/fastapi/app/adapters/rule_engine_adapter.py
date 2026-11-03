"""FastAPI 추천 요청을 backend/module/ 규칙 엔진 입력으로 변환한다.

기존 FastAPI 라우터·스키마와 backend/module/ 내부 코드는 수정하지 않는다.
PaymentService.engine.recommend(user_id, merchant_id, amount_won) 계약만 맞춘다.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.db_entities.card_entity import CardMonthClose
from app.repositories.card_repository import CardRepository
from app.repositories.merchant_repository import MerchantRepository
from app.repositories.policy_repository import PolicyRepository
from app.repositories.user_repository import UserRepository


_MODULE_DIR = Path(__file__).resolve().parents[3] / "module"
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

from onepass.p1_dongbaek_candidate import (  # noqa: E402
    DongbaekInputs,
    evaluate_dongbaek_candidate,
)
from onepass.p1_eligibility_repository import P1EligibilityRepository  # noqa: E402
from onepass.p1_monthly_db_repository import P1MonthlyDBRepository  # noqa: E402
from onepass.p1_mvp_quote import quote_mvp_card  # noqa: E402
from onepass.p1_payment_p0 import (  # noqa: E402
    PaymentContext,
    PaymentLane,
    SalesChannel,
)
from onepass.p1_product_ids import SELECTED_PRODUCT_IDS  # noqa: E402
from onepass.p1_rule_repository import P1RuleRepository  # noqa: E402


DONGBAEK_PRODUCT_IDS = frozenset({"PRD_DB_SYN"})
DEFAULT_LANE = "OFFLINE"


def _ensure_database_url() -> None:
    if not os.getenv("DATABASE_URL"):
        os.environ["DATABASE_URL"] = settings.DATABASE_URL


def _is_dongbaek_product(product_id: str | None, card_type: str | None) -> bool:
    if product_id in DONGBAEK_PRODUCT_IDS:
        return True
    return "DONGBAEK" in (card_type or "").upper()


def _wallet_balance_won(wallet) -> int | None:
    if wallet is None:
        return None
    return (
        (wallet.charge_won or 0)
        + (wallet.cashback_won or 0)
        + (wallet.policy_support_won or 0)
    )


def _previous_calendar_month(today: date) -> str:
    if today.month == 1:
        return f"{today.year - 1:04d}-12"
    return f"{today.year:04d}-{today.month - 1:02d}"


def _resolve_base_month(db: Session, user_card_ids: list[str]) -> str:
    fallback = _previous_calendar_month(date.today())
    if not user_card_ids:
        return fallback

    latest = db.scalar(
        select(CardMonthClose.base_month)
        .where(CardMonthClose.user_card_id.in_(user_card_ids))
        .order_by(CardMonthClose.base_month.desc())
        .limit(1)
    )
    return latest or fallback


def _best_rule_reason(quote: dict) -> str | None:
    best_rule_id = quote.get("best_rule_id")
    rules = quote.get("rules") or []
    if best_rule_id:
        for rule in rules:
            if rule.get("rule_id") == best_rule_id:
                return rule.get("reason")
    if rules:
        return rules[0].get("reason")
    unresolved = quote.get("unresolved_rule_ids") or []
    if unresolved:
        return "UNRESOLVED_RULES"
    return quote.get("status")


class RuleEngineAdapter:
    """backend/module/ P1 견적 함수를 기존 추천 API 응답 형태로 감싼다."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def recommend(
        self,
        user_id: str,
        merchant_id: str,
        amount_won: int,
    ) -> dict:
        _ensure_database_url()

        if self.db is not None:
            return self._recommend(self.db, user_id, merchant_id, amount_won)

        with SessionLocal() as db:
            return self._recommend(db, user_id, merchant_id, amount_won)

    def _recommend(
        self,
        db: Session,
        user_id: str,
        merchant_id: str,
        amount_won: int,
    ) -> dict:
        empty = {
            "user_id": user_id,
            "merchant_id": merchant_id,
            "amount_won": amount_won,
            "recommended_user_card_id": None,
            "expected_benefit_won": 0,
            "candidates": [],
        }

        merchant = MerchantRepository(db).get_merchant_by_id(merchant_id)
        if merchant is None:
            return empty

        card_repo = CardRepository(db)
        user_cards = card_repo.get_user_cards(user_id)
        if not user_cards:
            return empty

        user_card_ids = [card.user_card_id for card in user_cards]
        base_month = _resolve_base_month(db, user_card_ids)
        as_of = date.today().isoformat()
        payment = PaymentContext(
            lane=PaymentLane.OFFLINE,
            sales_channel=SalesChannel.OFFLINE,
        )

        dongbaek_inputs = self._build_dongbaek_inputs(db, user_id, merchant)
        rules_repo = P1RuleRepository()
        eligibility_repo = P1EligibilityRepository()
        monthly_repo = P1MonthlyDBRepository()

        candidates: list[dict] = []

        for user_card in user_cards:
            product = None
            if user_card.product_id:
                product = card_repo.get_product_by_id(user_card.product_id)

            product_id = user_card.product_id
            product_name = product.product_name if product is not None else None
            card_type = product.card_type if product is not None else None

            if _is_dongbaek_product(product_id, card_type):
                candidates.append(
                    self._quote_dongbaek(
                        user_card_id=user_card.user_card_id,
                        product_id=product_id,
                        product_name=product_name,
                        merchant=merchant,
                        amount_won=amount_won,
                        inputs=dongbaek_inputs,
                    )
                )
                continue

            if product_id not in SELECTED_PRODUCT_IDS:
                candidates.append(
                    {
                        "user_card_id": user_card.user_card_id,
                        "product_id": product_id,
                        "product_name": product_name,
                        "expected_benefit_won": 0,
                        "eligible": False,
                        "reason": "UNSUPPORTED_PRODUCT_ID",
                    }
                )
                continue

            try:
                quote = quote_mvp_card(
                    card={
                        "product_id": product_id,
                        "user_card_id": user_card.user_card_id,
                    },
                    merchant_id=merchant_id,
                    amount=amount_won,
                    payment=payment,
                    as_of=as_of,
                    base_month=base_month,
                    rules_repo=rules_repo,
                    eligibility_repo=eligibility_repo,
                    monthly_repo=monthly_repo,
                )
            except Exception as exc:
                candidates.append(
                    {
                        "user_card_id": user_card.user_card_id,
                        "product_id": product_id,
                        "product_name": product_name,
                        "expected_benefit_won": 0,
                        "eligible": False,
                        "reason": f"{type(exc).__name__}:{exc}",
                    }
                )
                continue

            benefit = int(quote.get("estimated_value_won") or 0)
            status = quote.get("status")
            eligible = status == "SIMULATED_COMPARABLE"

            candidates.append(
                {
                    "user_card_id": user_card.user_card_id,
                    "product_id": product_id,
                    "product_name": product_name,
                    "expected_benefit_won": max(benefit, 0),
                    "eligible": eligible,
                    "reason": _best_rule_reason(quote),
                }
            )

        recommended = None
        comparable = [item for item in candidates if item["eligible"]]
        if comparable:
            recommended = min(
                comparable,
                key=lambda item: (
                    -item["expected_benefit_won"],
                    item["user_card_id"],
                ),
            )

        return {
            "user_id": user_id,
            "merchant_id": merchant_id,
            "amount_won": amount_won,
            "recommended_user_card_id": (
                recommended["user_card_id"] if recommended else None
            ),
            "expected_benefit_won": (
                recommended["expected_benefit_won"] if recommended else 0
            ),
            "candidates": candidates,
        }

    def _build_dongbaek_inputs(self, db: Session, user_id: str, merchant) -> DongbaekInputs:
        user_repo = UserRepository(db)
        wallets = user_repo.get_wallets_by_user_id(user_id)
        wallet = next(
            (
                item
                for item in wallets
                if (item.wallet_status or "ACTIVE").upper() == "ACTIVE"
            ),
            wallets[0] if wallets else None,
        )

        policies = PolicyRepository(db).get_all_policies()
        policy = policies[0] if policies else None
        cashback_rate = None
        cashback_remaining = None

        if policy is not None and merchant.sales_band:
            rate_row = PolicyRepository(db).get_rate_by_sales_band(
                policy.policy_id,
                merchant.sales_band,
            )
            if rate_row is not None and rate_row.cashback_rate is not None:
                cashback_rate = Decimal(str(rate_row.cashback_rate))
            cashback_remaining = policy.monthly_cashback_base_cap_won

        return DongbaekInputs(
            balance_won=_wallet_balance_won(wallet),
            cashback_rate=cashback_rate,
            cashback_remaining_won=cashback_remaining,
        )

    def _quote_dongbaek(
        self,
        *,
        user_card_id: str,
        product_id: str | None,
        product_name: str | None,
        merchant,
        amount_won: int,
        inputs: DongbaekInputs,
    ) -> dict:
        result = evaluate_dongbaek_candidate(
            merchant={"dongbaek_status": merchant.dongbaek_status},
            amount_won=amount_won,
            lane=DEFAULT_LANE,
            inputs=inputs,
        )
        benefit = int(result.get("cash_benefit_won") or 0)
        eligible = (
            result.get("status") == "COMPARABLE"
            and result.get("payment_possible") is True
        )
        return {
            "user_card_id": user_card_id,
            "product_id": product_id,
            "product_name": product_name,
            "expected_benefit_won": max(benefit, 0) if eligible else 0,
            "eligible": eligible,
            "reason": result.get("reason"),
        }
