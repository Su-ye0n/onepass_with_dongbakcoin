"""P0 API boundary for the existing deterministic OnePass engine.

No database or network dependency. The backend owns authentication and session
lifecycle; the engine owns eligibility, benefit calculations and mutable state.
"""
from __future__ import annotations

from .engine import Card, DbPolicy, Decision, Merchant, Request, State, decide, process


def _validate_merchant(request: Request, merchant: Merchant) -> None:
    if request.merchant_id != merchant.id:
        raise ValueError(
            f"MERCHANT_MISMATCH: request={request.merchant_id}, loaded={merchant.id}"
        )


def quote(
    request: Request,
    merchant: Merchant,
    cards: list[Card],
    state: State,
    policy: DbPolicy,
) -> Decision:
    """Return card candidates and expected benefits WITHOUT updating state."""
    _validate_merchant(request, merchant)
    return decide(request, merchant, cards, state, policy)


def commit(
    request: Request,
    merchant: Merchant,
    cards: list[Card],
    state: State,
    policy: DbPolicy,
) -> Decision:
    """Execute one simulated payment, modifying state only when approved.

    Retries currently return DUPLICATE_REQUEST rather than a cached prior result.
    Production-grade transactional persistence is outside this P0 boundary.
    """
    _validate_merchant(request, merchant)
    return process(request, merchant, cards, state, policy)
