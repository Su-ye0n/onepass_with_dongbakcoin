
# onepass/p1_monthly_limits.py

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


class LimitError(ValueError):
    pass


def money(value):
    if isinstance(value, bool):
        raise LimitError("INVALID_MONEY")

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise LimitError("INVALID_MONEY") from None

    if not amount.is_finite() or amount < 0:
        raise LimitError("INVALID_MONEY")

    if amount != amount.to_integral_value():
        raise LimitError("WON_MUST_BE_INTEGER")

    return int(amount)


def nonnegative_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise LimitError(f"INVALID_{name}")

    if value < 0:
        raise LimitError(f"INVALID_{name}")

    return value


@dataclass(frozen=True)
class CapTier:
    perf_min_won: int
    monthly_cap_won: int

    def __post_init__(self):
        money(self.perf_min_won)
        money(self.monthly_cap_won)


@dataclass(frozen=True)
class LimitRule:
    rule_id: str
    product_id: str
    perf_threshold_won: int | None = None
    monthly_cap_won: int | None = None
    monthly_count_cap: int | None = None
    shared_cap_group: str | None = None

    def __post_init__(self):
        if not self.rule_id or not self.product_id:
            raise LimitError("RULE_ID_OR_PRODUCT_ID_MISSING")

        if self.perf_threshold_won is not None:
            money(self.perf_threshold_won)

        if self.monthly_cap_won is not None:
            money(self.monthly_cap_won)

        if self.monthly_count_cap is not None:
            nonnegative_int(
                self.monthly_count_cap,
                "COUNT_CAP",
            )


@dataclass
class MonthlyUsage:
    # A separate instance is required per user/card/month.
    # Keys are rule_id and shared_cap_group.
    benefit_used_won: dict[str, int] = field(
        default_factory=dict
    )
    benefit_count: dict[str, int] = field(
        default_factory=dict
    )
    shared_used_won: dict[str, int] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class LimitDecision:
    status: str
    reason: str
    allowed_won: int = 0
    effective_monthly_cap_won: int | None = None
    remaining_rule_cap_won: int | None = None
    remaining_shared_cap_won: int | None = None
    remaining_count: int | None = None

    @property
    def eligible(self):
        return self.status == "ELIGIBLE"


def resolve_cap_tier(
    *,
    prev_month_spend_won: int,
    tiers: tuple[CapTier, ...],
):
    """
    Highest qualifying tier wins.

    No qualifying tier -> 0 cap.
    Same threshold with different caps -> unresolved.
    """
    previous = money(prev_month_spend_won)

    if not tiers:
        return None

    qualified = [
        tier for tier in tiers
        if previous >= money(tier.perf_min_won)
    ]

    if not qualified:
        return 0

    highest = max(
        tier.perf_min_won for tier in qualified
    )

    caps = {
        money(tier.monthly_cap_won)
        for tier in qualified
        if tier.perf_min_won == highest
    }

    if len(caps) != 1:
        raise LimitError("AMBIGUOUS_CAP_TIER")

    return caps.pop()


def evaluate_monthly_limits(
    *,
    rule: LimitRule,
    quoted_benefit_won: int,
    previous_spend_won: int | None,
    usage: MonthlyUsage | None,
    tiers: tuple[CapTier, ...] = (),
    performance_basis_confirmed: bool = False,
    usage_state_confirmed: bool = False,
):
    """
    Check performance, rule cap, shared cap, count cap.

    quoted_benefit_won must be the result of the
    existing benefit calculation engine.

    This function never mutates usage.
    """
    quoted = money(quoted_benefit_won)

    def unresolved(reason):
        return LimitDecision(
            status="UNRESOLVED",
            reason=reason,
        )

    if not performance_basis_confirmed:
        return unresolved("PERFORMANCE_BASIS_NOT_RESOLVED")

    if previous_spend_won is None:
        return unresolved("PREVIOUS_SPEND_MISSING")

    previous = money(previous_spend_won)

    if not usage_state_confirmed or usage is None:
        return unresolved("MONTHLY_USAGE_STATE_REQUIRED")

    # Validate all supplied usage values, even if unused.
    for collection in (
        usage.benefit_used_won,
        usage.shared_used_won,
    ):
        for value in collection.values():
            money(value)

    for value in usage.benefit_count.values():
        nonnegative_int(value, "USAGE_COUNT")

    threshold = rule.perf_threshold_won

    if threshold is not None and previous < threshold:
        return LimitDecision(
            "INELIGIBLE",
            "PERFORMANCE_THRESHOLD_NOT_MET",
        )

    try:
        tier_cap = resolve_cap_tier(
            prev_month_spend_won=previous,
            tiers=tiers,
        )
    except LimitError as exc:
        return unresolved(str(exc))

    rule_cap = (
        money(rule.monthly_cap_won)
        if rule.monthly_cap_won is not None
        else None
    )

    used = usage.benefit_used_won.get(
        rule.rule_id, 0
    )

    # Rule-level and tier-level caps are independent.
    remaining_rule = (
        max(0, rule_cap - used)
        if rule_cap is not None
        else None
    )

    remaining_shared = None

    if rule.shared_cap_group:
        if tier_cap is None:
            return unresolved(
                "SHARED_CAP_TIER_MISSING"
            )

        shared_used = usage.shared_used_won.get(
            rule.shared_cap_group, 0
        )

        remaining_shared = max(
            0, tier_cap - shared_used
        )

    elif tier_cap is not None:
        # A tier can also limit a single rule.
        tier_remaining = max(
            0, tier_cap - used
        )

        remaining_rule = (
            tier_remaining
            if remaining_rule is None
            else min(remaining_rule, tier_remaining)
        )

    count_limit = rule.monthly_count_cap
    count_used = usage.benefit_count.get(
        rule.rule_id, 0
    )

    remaining_count = (
        max(0, count_limit - count_used)
        if count_limit is not None
        else None
    )

    if remaining_count == 0:
        return LimitDecision(
            "INELIGIBLE",
            "MONTHLY_COUNT_EXHAUSTED",
            remaining_count=0,
        )

    allowed = quoted

    for remaining in (
        remaining_rule,
        remaining_shared,
    ):
        if remaining is not None:
            allowed = min(allowed, remaining)

    if quoted > 0 and allowed == 0:
        return LimitDecision(
            "INELIGIBLE",
            "MONTHLY_CAP_EXHAUSTED",
            remaining_rule_cap_won=remaining_rule,
            remaining_shared_cap_won=remaining_shared,
            remaining_count=remaining_count,
        )

    return LimitDecision(
        status="ELIGIBLE",
        reason="MONTHLY_LIMITS_MATCHED",
        allowed_won=allowed,
        effective_monthly_cap_won=tier_cap,
        remaining_rule_cap_won=remaining_rule,
        remaining_shared_cap_won=remaining_shared,
        remaining_count=remaining_count,
    )


def apply_monthly_benefit(
    *,
    rule: LimitRule,
    decision: LimitDecision,
    usage: MonthlyUsage,
):
    """
    Apply a previously evaluated positive benefit.

    Only call after payment approval and after all
    other benefit conditions have passed.
    """
    if not decision.eligible:
        raise LimitError("DECISION_NOT_ELIGIBLE")

    amount = money(decision.allowed_won)

    if amount == 0:
        return

    usage.benefit_used_won[rule.rule_id] = (
        usage.benefit_used_won.get(rule.rule_id, 0)
        + amount
    )

    usage.benefit_count[rule.rule_id] = (
        usage.benefit_count.get(rule.rule_id, 0)
        + 1
    )

    if rule.shared_cap_group:
        group = rule.shared_cap_group

        usage.shared_used_won[group] = (
            usage.shared_used_won.get(group, 0)
            + amount
        )
