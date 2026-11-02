
# onepass/p1_lane_evaluator.py

"""P1 payment-lane eligibility evaluation.

Evaluates known payment-channel conditions only.
Does not calculate, award, or commit financial benefits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Any

from .p1_payment_p0 import (
    PaymentContext,
    PaymentLane,
    PaymentProvider,
)
from .p1_product_ids import canonical_product_id

LaneDecision = Literal[
    "NOT_APPLICABLE",
    "CHANNEL_MATCHED",
    "NEEDS_RULE_REVIEW",
]

# Verified against the imported catalog example:
# P09_R01: P(Pay) 간편결제 - NAVER/KAKAO/SAMSUNG PAY.
# This is a channel mapping, not verification of every
# contractual discount condition.
KNOWN_PROVIDER_RULES = {
    "P09_R01": frozenset({
        PaymentProvider.NAVERPAY,
        PaymentProvider.KAKAOPAY,
        PaymentProvider.SAMSUNGPAY,
    })
}


@dataclass(frozen=True)
class LaneEvaluation:
    rule_id: str
    product_id: str
    target_original: str
    decision: LaneDecision
    reason: str

    @property
    def can_calculate_benefit(self) -> bool:
        # Even CHANNEL_MATCHED does not mean the full
        # financial benefit rule has been validated.
        return False


def evaluate_lane(
    benefit: Mapping[str, Any],
    payment: PaymentContext,
) -> LaneEvaluation:
    rule_id = str(
        benefit.get("source_rule_id") or ""
    ).strip()
    product_id = str(
        benefit.get("product_id") or ""
    ).strip()
    target = str(
        benefit.get("target_original") or ""
    ).strip()

    if not rule_id or not product_id:
        raise ValueError("INVALID_BENEFIT_RECORD")

    # Confirm that the known mapping still refers
    # to the expected product and original benefit.
    if rule_id == "P09_R01":
        if (
            product_id != "P09"
            or "간편결제" not in target
            or not all(
                word in target
                for word in (
                    "네이버페이",
                    "카카오페이",
                    "삼성페이",
                )
            )
        ):
            return LaneEvaluation(
                rule_id,
                product_id,
                target,
                "NEEDS_RULE_REVIEW",
                "SOURCE_RULE_CHANGED",
            )

        if payment.lane != PaymentLane.SIMPLE_PAY:
            return LaneEvaluation(
                rule_id,
                product_id,
                target,
                "NOT_APPLICABLE",
                "SIMPLE_PAY_REQUIRED",
            )

        allowed = KNOWN_PROVIDER_RULES[rule_id]

        if payment.payment_provider not in allowed:
            return LaneEvaluation(
                rule_id,
                product_id,
                target,
                "NOT_APPLICABLE",
                "PAYMENT_PROVIDER_NOT_ALLOWED",
            )

        return LaneEvaluation(
            rule_id,
            product_id,
            target,
            "CHANNEL_MATCHED",
            "PROVIDER_MATCHED_OTHER_CONDITIONS_PENDING",
        )

    # A general benefit may apply in multiple lanes.
    # Do not automatically exclude or approve it
    # merely because no channel-specific parser exists.
    return LaneEvaluation(
        rule_id,
        product_id,
        target,
        "NEEDS_RULE_REVIEW",
        "RULE_CONDITIONS_NOT_YET_NORMALIZED",
    )


def evaluate_card_lanes(
    card: Mapping[str, Any],
    payment: PaymentContext,
) -> list[LaneEvaluation]:
    benefits = card.get("benefits")

    if not isinstance(benefits, list):
        raise ValueError("CARD_BENEFITS_NOT_LIST")

    results = []

    for benefit in benefits:
        results.append(
            evaluate_lane(benefit, payment)
        )

    return results
