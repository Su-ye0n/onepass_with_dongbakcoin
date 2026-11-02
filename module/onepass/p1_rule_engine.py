
# onepass/p1_rule_engine.py

"""P1 rule evaluator: verified normalized rules only.

Pure quote evaluation; no database writes or state mutation.
The caller must commit counters only after a confirmed
simulated approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_FLOOR
from typing import Literal

from .p1_payment_p0 import PaymentContext, PaymentLane


Decision = Literal[
    "ELIGIBLE",
    "INELIGIBLE",
    "PENDING_REVIEW",
]


@dataclass(frozen=True)
class NormalizedRule:
    rule_id: str
    product_id: str
    calculation_type: Literal["RATE", "FIXED"]
    value: Decimal

    verified: bool = False

    min_payment_won: int = 0
    prev_month_min_won: int = 0

    per_tx_cap_won: int | None = None
    monthly_cap_won: int | None = None
    monthly_count_cap: int | None = None
    shared_cap_group: str | None = None

    allowed_lanes: frozenset[str] = field(
        default_factory=lambda: frozenset({
            "OFFLINE", "ONLINE", "SIMPLE_PAY"
        })
    )
    allowed_providers: frozenset[str] = field(
        default_factory=frozenset
    )

    def __post_init__(self):
        if not self.rule_id or not self.product_id:
            raise ValueError("INVALID_RULE_ID")

        if self.calculation_type not in ("RATE", "FIXED"):
            raise ValueError("UNSUPPORTED_CALCULATION_TYPE")

        if not self.value.is_finite() or self.value < 0:
            raise ValueError("INVALID_BENEFIT_VALUE")

        if self.calculation_type == "RATE" and self.value > 1:
            raise ValueError("INVALID_RATE")

        for amount in (
            self.min_payment_won,
            self.prev_month_min_won,
        ):
            if isinstance(amount, bool) or not isinstance(
                amount, int
            ) or amount < 0:
                raise ValueError("INVALID_RULE_AMOUNT")

        for amount in (
            self.per_tx_cap_won,
            self.monthly_cap_won,
        ):
            if amount is not None and (
                isinstance(amount, bool)
                or not isinstance(amount, int)
                or amount < 0
            ):
                raise ValueError("INVALID_RULE_CAP")

        if self.monthly_count_cap is not None and (
            isinstance(self.monthly_count_cap, bool)
            or not isinstance(self.monthly_count_cap, int)
            or self.monthly_count_cap <= 0
        ):
            raise ValueError("INVALID_MONTHLY_COUNT_CAP")

        valid_lanes = {
            "OFFLINE", "ONLINE", "SIMPLE_PAY"
        }
        if (
            not self.allowed_lanes
            or not self.allowed_lanes.issubset(valid_lanes)
        ):
            raise ValueError("INVALID_ALLOWED_LANES")

        valid_providers = {
            "NAVERPAY", "KAKAOPAY", "SAMSUNGPAY"
        }
        if not self.allowed_providers.issubset(
            valid_providers
        ):
            raise ValueError("INVALID_ALLOWED_PROVIDERS")

        if self.allowed_providers and (
            "SIMPLE_PAY" not in self.allowed_lanes
        ):
            raise ValueError("PROVIDER_REQUIRES_SIMPLE_PAY")


@dataclass(frozen=True)
class RuleUsage:
    """Snapshot of usage before the proposed transaction."""

    monthly_count: int = 0
    rule_benefit_used_won: int = 0
    shared_benefit_used_won: int = 0


@dataclass(frozen=True)
class RuleQuote:
    rule_id: str
    decision: Decision
    benefit_won: int
    reason: str


def quote_rule(
    rule: NormalizedRule,
    *,
    amount_won: int,
    prev_month_spend_won: int,
    payment: PaymentContext,
    usage: RuleUsage = RuleUsage(),
    effective_monthly_cap_won: int | None = None,
) -> RuleQuote:
    """Calculate one eligible benefit without updating usage.

    effective_monthly_cap_won represents a resolved
    shared-group cap, if any. For a shared group it must
    come from verified product/cap-tier configuration.
    """

    if not rule.verified:
        return RuleQuote(
            rule.rule_id, "PENDING_REVIEW", 0,
            "RULE_NOT_VERIFIED"
        )

    if (
        isinstance(amount_won, bool)
        or not isinstance(amount_won, int)
        or amount_won <= 0
        or isinstance(prev_month_spend_won, bool)
        or not isinstance(prev_month_spend_won, int)
        or prev_month_spend_won < 0
    ):
        raise ValueError("INVALID_TRANSACTION_AMOUNT")

    for value in (
        usage.monthly_count,
        usage.rule_benefit_used_won,
        usage.shared_benefit_used_won,
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            raise ValueError("INVALID_RULE_USAGE")

    if rule.shared_cap_group is not None and (
        effective_monthly_cap_won is None
    ):
        return RuleQuote(
            rule.rule_id, "PENDING_REVIEW", 0,
            "SHARED_CAP_NOT_RESOLVED"
        )

    if effective_monthly_cap_won is not None and (
        isinstance(effective_monthly_cap_won, bool)
        or not isinstance(effective_monthly_cap_won, int)
        or effective_monthly_cap_won < 0
    ):
        raise ValueError("INVALID_EFFECTIVE_CAP")

    lane = payment.lane.value

    if lane not in rule.allowed_lanes:
        return RuleQuote(
            rule.rule_id, "INELIGIBLE", 0,
            "PAYMENT_LANE_MISMATCH"
        )

    provider = (
        payment.payment_provider.value
        if payment.payment_provider is not None
        else None
    )

    if rule.allowed_providers and (
        provider not in rule.allowed_providers
    ):
        return RuleQuote(
            rule.rule_id, "INELIGIBLE", 0,
            "PAYMENT_PROVIDER_MISMATCH"
        )

    if amount_won < rule.min_payment_won:
        return RuleQuote(
            rule.rule_id, "INELIGIBLE", 0,
            "MIN_PAYMENT_NOT_MET"
        )

    if prev_month_spend_won < rule.prev_month_min_won:
        return RuleQuote(
            rule.rule_id, "INELIGIBLE", 0,
            "PREV_MONTH_PERFORMANCE_NOT_MET"
        )

    if (
        rule.monthly_count_cap is not None
        and usage.monthly_count >= rule.monthly_count_cap
    ):
        return RuleQuote(
            rule.rule_id, "INELIGIBLE", 0,
            "MONTHLY_COUNT_EXHAUSTED"
        )

    if rule.calculation_type == "RATE":
        raw_benefit = (
            Decimal(amount_won) * rule.value
        )
    else:
        raw_benefit = rule.value

    benefit = int(
        raw_benefit.to_integral_value(
            rounding=ROUND_FLOOR
        )
    )

    if rule.per_tx_cap_won is not None:
        benefit = min(
            benefit, rule.per_tx_cap_won
        )

    if rule.monthly_cap_won is not None:
        remaining = max(
            0,
            rule.monthly_cap_won
            - usage.rule_benefit_used_won
        )
        benefit = min(benefit, remaining)

    if effective_monthly_cap_won is not None:
        remaining_shared = max(
            0,
            effective_monthly_cap_won
            - usage.shared_benefit_used_won
        )
        benefit = min(
            benefit, remaining_shared
        )

    if benefit <= 0:
        return RuleQuote(
            rule.rule_id, "INELIGIBLE", 0,
            "BENEFIT_CAP_EXHAUSTED_OR_ZERO"
        )

    return RuleQuote(
        rule.rule_id,
        "ELIGIBLE",
        benefit,
        "ALL_SUPPORTED_CONDITIONS_MET",
    )
