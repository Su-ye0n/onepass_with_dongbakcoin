
# onepass/api_contract_p0.py
"""P0 backend-to-rule-engine API adapter.

The backend owns authentication, card registration, storage
and HTTP status codes.

This adapter owns request validation and DTO conversion.
No real payment or network access.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .engine import (
    Card,
    DbPolicy,
    Decision,
    Merchant,
    Request,
    State,
)
from .service import quote, commit


class APIContractError(ValueError):
    """Invalid input to the P0 rule-engine interface."""


def parse_payment_request(
    payload: Mapping[str, Any],
) -> Request:
    """Validate a backend request and create an engine Request."""

    if not isinstance(payload, Mapping):
        raise APIContractError("INVALID_PAYLOAD")

    request_id = payload.get("request_id")
    merchant_id = payload.get("merchant_id")
    amount = payload.get("amount_won")
    payment_path = payload.get("payment_path", "ONECARD")
    direct_card_id = payload.get("direct_card_id")
    onecard_active = payload.get("onecard_active", True)

    if not isinstance(request_id, str) or not request_id.strip():
        raise APIContractError("INVALID_REQUEST_ID")

    if not isinstance(merchant_id, str) or not merchant_id.strip():
        raise APIContractError("INVALID_MERCHANT_ID")

    if (
        isinstance(amount, bool)
        or not isinstance(amount, int)
        or amount <= 0
    ):
        raise APIContractError("INVALID_AMOUNT_WON")

    if payment_path not in ("ONECARD", "DIRECT"):
        raise APIContractError("INVALID_PAYMENT_PATH")

    if not isinstance(onecard_active, bool):
        raise APIContractError("INVALID_ONECARD_ACTIVE")

    if payment_path == "DIRECT":
        if (
            not isinstance(direct_card_id, str)
            or not direct_card_id.strip()
        ):
            raise APIContractError("DIRECT_CARD_ID_REQUIRED")
    elif direct_card_id is not None:
        raise APIContractError(
            "DIRECT_CARD_ID_NOT_ALLOWED_FOR_ONECARD"
        )

    return Request(
        id=request_id,
        merchant_id=merchant_id,
        amount=amount,
        onecard_active=onecard_active,
        payment_path=payment_path,
        direct_card_id=direct_card_id,
    )


def decision_to_dict(
    decision: Decision,
) -> dict[str, Any]:
    """Convert engine decision into a JSON-compatible result."""

    candidates = [
        {
            "user_card_id": c.card_id,
            "eligible": c.eligible,
            "reason": c.reason,
            "expected_benefit_won": c.expected_benefit,
            "funding_mode": c.funding_mode,
            "benefit_rule_id": c.rule_id or None,
        }
        for c in decision.candidates
    ]

    return {
        "request_id": decision.request_id,
        "approved": decision.approved,
        "selected_user_card_id": decision.selected_card_id,
        "benefit_won": decision.benefit_won,
        "reason": decision.reason,
        "candidates": candidates,
    }


def execute_engine_request(
    *,
    payload: Mapping[str, Any],
    merchant: Merchant,
    cards: Sequence[Card],
    state: State,
    policy: DbPolicy,
    mode: str,
) -> dict[str, Any]:
    """Run either read-only preview or simulated payment.

    mode = "QUOTE"  -> no state mutation
    mode = "COMMIT" -> simulate payment and update state

    The backend must load trusted merchant, card and state
    objects for the authenticated user.
    """

    if mode not in ("QUOTE", "COMMIT"):
        raise APIContractError("INVALID_EXECUTION_MODE")

    request = parse_payment_request(payload)

    card_list = list(cards)

    if mode == "QUOTE":
        decision = quote(
            request,
            merchant,
            card_list,
            state,
            policy,
        )
    else:
        decision = commit(
            request,
            merchant,
            card_list,
            state,
            policy,
        )

    return decision_to_dict(decision)
