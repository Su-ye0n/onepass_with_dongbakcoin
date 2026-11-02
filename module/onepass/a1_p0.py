
# onepass/a1_p0.py
"""P0 A1: reproducible statistical card selection.

Weights are assumed inputs until validated behavioral
payment-choice statistics are available.

The draw depends on seed and request ID, not iteration order.
No database access or financial state mutation.
"""

from __future__ import annotations

import hashlib
import math
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from .engine import Card


def validate_a1_weights(
    cards: Sequence[Card],
    weights: Mapping[str, object],
) -> dict[str, Decimal]:
    card_ids = [card.id for card in cards]

    if len(card_ids) != len(set(card_ids)):
        raise ValueError("DUPLICATE_CARD_ID")

    if not weights:
        raise ValueError("EMPTY_A1_WEIGHTS")

    unknown = set(weights) - set(card_ids)

    if unknown:
        raise ValueError(
            f"A1_UNKNOWN_CARDS: {sorted(unknown)}"
        )

    normalized = {}

    for card_id in card_ids:
        raw = weights.get(card_id, 0)

        if isinstance(raw, bool):
            raise ValueError(
                f"A1_INVALID_WEIGHT: {card_id}"
            )

        try:
            weight = Decimal(str(raw))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(
                f"A1_INVALID_WEIGHT: {card_id}"
            ) from exc

        if not weight.is_finite() or weight < 0:
            raise ValueError(
                f"A1_INVALID_WEIGHT: {card_id}"
            )

        normalized[card_id] = weight

    total = sum(normalized.values(), Decimal(0))

    if total <= 0:
        raise ValueError("A1_ZERO_TOTAL_WEIGHT")

    return {
        card_id: weight / total
        for card_id, weight in normalized.items()
    }


def select_a1_card(
    *,
    request_id: str,
    cards: Sequence[Card],
    weights: Mapping[str, object],
    seed: int = 2026,
) -> str:
    """Select one card according to relative choice weights.

    Does not pre-filter by eligibility. That is deliberate:
    A1 represents selection behavior before approval.

    Same seed + request ID + weights + cards => same card.
    """

    if not request_id:
        raise ValueError("EMPTY_REQUEST_ID")

    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("A1_SEED_MUST_BE_INTEGER")

    probabilities = validate_a1_weights(
        cards, weights
    )

    # Sort to make sampling independent of card list order.
    card_ids = sorted(probabilities)

    digest = hashlib.sha256(
        f"A1|{seed}|{request_id}".encode("utf-8")
    ).digest()

    # Uniform variate in [0, 1).
    draw = Decimal(
        int.from_bytes(digest[:8], "big")
    ) / Decimal(2**64)

    cumulative = Decimal(0)

    for card_id in card_ids:
        cumulative += probabilities[card_id]

        if draw < cumulative:
            return card_id

    # Defensive fallback against Decimal rounding.
    return next(
        card_id
        for card_id in reversed(card_ids)
        if probabilities[card_id] > 0
    )
