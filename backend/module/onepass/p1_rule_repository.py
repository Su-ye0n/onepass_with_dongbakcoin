
# onepass/p1_rule_repository.py

"""Read normalized P1 rules from backend public schema.

Read-only. No rule creation, DB mutations or benefit awarding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from psycopg.rows import dict_row

from .db_connection import connect_readonly
from .p1_rule_engine import NormalizedRule
from .p1_product_ids import ( SELECTED_PRODUCT_IDS,canonical_product_id,)

SELECTED_PRODUCTS = SELECTED_PRODUCT_IDS


@dataclass(frozen=True)
class RuleTarget:
    target_type: str
    target_code: str
    apply_type: str


@dataclass(frozen=True)
class CapTier:
    tier_id: str
    cap_group: str
    perf_min_won: int
    monthly_cap_won: int

# 기존 LoadedRule 전체를 아래로 교체

@dataclass(frozen=True)
class LoadedRule:
    rule: NormalizedRule
    targets: tuple[RuleTarget, ...]
    cap_tiers: tuple[CapTier, ...]
    status: str
    reasons: tuple[str, ...]
    source_status: str = "PENDING"


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _integer(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("INVALID_INTEGER_FIELD")
    return value


def map_db_rule(
    row: Mapping[str, Any],
    targets: list[Mapping[str, Any]],
    cap_tiers: list[Mapping[str, Any]],
) -> LoadedRule:
    """Map one DB row and reject unsupported semantics.

    A rule becomes verified=True ONLY for a narrow,
    explicitly supported subset. Unsupported conditions
    never silently become generic discounts.
    """

    rule_id = _text(row.get("rule_id"))
    product_id = canonical_product_id(
    _text(row.get("product_id"))
    )

    if not rule_id or product_id not in SELECTED_PRODUCTS:
        raise ValueError("INVALID_RULE_ID_OR_PRODUCT")

    reasons: list[str] = []

    source_status = _text(row.get("source_status"))
    if source_status != "VERIFIED":
        reasons.append("SOURCE_NOT_VERIFIED")

    kind = _text(row.get("benefit_type"))
    if kind not in {"RATE", "FIXED"}:
        reasons.append("UNSUPPORTED_BENEFIT_TYPE")

    reward_unit = _text(row.get("reward_unit"))
    if reward_unit != "CASH":
        reasons.append("UNSUPPORTED_REWARD_UNIT")

    if _text(row.get("day_condition")) != "ALL":
        reasons.append("UNSUPPORTED_DAY_CONDITION")

    if _text(row.get("stack_rule")) != "MAX_ONLY":
        reasons.append("UNSUPPORTED_STACK_RULE")

    if _text(row.get("rounding_mode")) != "FLOOR":
        reasons.append("UNSUPPORTED_ROUNDING")

    if row.get("perf_basis_code"):
        reasons.append("PERFORMANCE_BASIS_NOT_RESOLVED")

    channel = _text(row.get("payment_channel_required"))
    if channel == "ONLINE":
        lanes = frozenset({"ONLINE"})
    else:
        lanes = frozenset({
            "OFFLINE", "ONLINE", "SIMPLE_PAY"
        })
        # CARD and ANY cannot prove exact lane/provider
        # eligibility without further semantics.
        reasons.append("PAYMENT_CHANNEL_NOT_NORMALIZED")

    normalized_targets = tuple(
        RuleTarget(
            target_type=_text(t.get("target_type")),
            target_code=_text(t.get("target_code")),
            apply_type=_text(t.get("apply_type")),
        )
        for t in targets
    )

    # A card rule without a target is not automatically
    # a universally applicable discount.
    if not normalized_targets:
        reasons.append("TARGET_NOT_DEFINED")
    else:
        for target in normalized_targets:
            if (
                target.target_type != "CHANNEL"
                or target.target_code != "ONLINE"
                or target.apply_type != "INCLUDE"
            ):
                reasons.append("TARGET_EVALUATOR_REQUIRED")

        if channel != "ONLINE":
            reasons.append("CHANNEL_TARGET_INCONSISTENT")

    normalized_tiers = tuple(
        CapTier(
            tier_id=_text(t.get("tier_id")),
            cap_group=_text(t.get("cap_group")),
            perf_min_won=_integer(t.get("perf_min_won")),
            monthly_cap_won=_integer(t.get("monthly_cap_won")),
        )
        for t in cap_tiers
    )

    shared_group = _text(
        row.get("shared_cap_group")
    ) or None

    if shared_group:
        reasons.append("SHARED_CAP_RESOLUTION_REQUIRED")

    if row.get("monthly_count_cap") is not None:
        # The rule evaluator can enforce this, but the
        # usage state is not loaded in this repository.
        reasons.append("MONTHLY_USAGE_STATE_REQUIRED")

    raw_value = (
        row.get("rate") if kind == "RATE"
        else row.get("fixed_amount_won")
    )

    if raw_value is None:
        reasons.append("BENEFIT_VALUE_MISSING")
        value = Decimal("0")
    else:
        try:
            value = Decimal(str(raw_value))
            if not value.is_finite() or value < 0:
                raise ValueError()
            if kind == "RATE" and value > 1:
                raise ValueError()
        except (ValueError, ArithmeticError):
            reasons.append("INVALID_BENEFIT_VALUE")
            value = Decimal("0")

    try:
        min_payment = _integer(
            row.get("min_amount_won")
        )
        prev_min = _integer(
            row.get("perf_threshold_won")
        )
        per_tx_cap = (
            None if row.get("per_tx_cap_won") is None
            else _integer(row["per_tx_cap_won"])
        )
        monthly_cap = (
            None if row.get("monthly_cap_won") is None
            else _integer(row["monthly_cap_won"])
        )
        count_cap = (
            None if row.get("monthly_count_cap") is None
            else _integer(row["monthly_count_cap"])
        )
    except ValueError:
        reasons.append("INVALID_RULE_NUMERIC_FIELDS")
        min_payment = 0
        prev_min = 0
        per_tx_cap = None
        monthly_cap = None
        count_cap = None

    try:
        normalized_rule = NormalizedRule(
            rule_id=rule_id,
            product_id=product_id,
            calculation_type=(
                kind if kind in {"RATE", "FIXED"}
                else "RATE"
            ),
            value=value,
            verified=False,
            min_payment_won=min_payment,
            prev_month_min_won=prev_min,
            per_tx_cap_won=per_tx_cap,
            monthly_cap_won=monthly_cap,
            monthly_count_cap=count_cap,
            shared_cap_group=shared_group,
            allowed_lanes=lanes,
        )
    except ValueError:
        reasons.append("INVALID_NORMALIZED_RULE")
        normalized_rule = NormalizedRule(
            rule_id=rule_id,
            product_id=product_id,
            calculation_type="RATE",
            value=Decimal("0"),
            verified=False,
        )

    # Only a single explicit ONLINE/INCLUDE channel
    # target and the safe subset may be activated.
    unique_reasons = tuple(dict.fromkeys(reasons))
    verified = (
        not unique_reasons
        and len(normalized_targets) == 1
        and normalized_targets[0] == RuleTarget(
            "CHANNEL", "ONLINE", "INCLUDE"
        )
    )

    if verified:
        normalized_rule = NormalizedRule(
            rule_id=normalized_rule.rule_id,
            product_id=normalized_rule.product_id,
            calculation_type=normalized_rule.calculation_type,
            value=normalized_rule.value,
            verified=True,
            min_payment_won=normalized_rule.min_payment_won,
            prev_month_min_won=normalized_rule.prev_month_min_won,
            per_tx_cap_won=normalized_rule.per_tx_cap_won,
            monthly_cap_won=normalized_rule.monthly_cap_won,
            monthly_count_cap=normalized_rule.monthly_count_cap,
            allowed_lanes=normalized_rule.allowed_lanes,
        )

    return LoadedRule(
        rule=normalized_rule,
        targets=normalized_targets,
        cap_tiers=normalized_tiers,
        status="READY" if verified else "PENDING_REVIEW",
        reasons=unique_reasons,
        source_status=source_status,
    )


class P1RuleRepository:
    """PostgreSQL normalized-rule reader."""

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url

    def load(
        self,
        product_id: str,
        as_of: str,
    ) -> list[LoadedRule]:
        product_id = canonical_product_id(product_id)
        day = date.fromisoformat(as_of)

        with connect_readonly(self.database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM public.benefit_rule
                    WHERE product_id = %s
                      AND (
                          valid_from IS NULL
                          OR valid_from <= %s
                      )
                      AND (
                          valid_to IS NULL
                          OR %s < valid_to
                      )
                    ORDER BY rule_id
                    """,
                    (product_id, day, day),
                )
                rules = cur.fetchall()

                if not rules:
                    return []

                rule_ids = [
                    row["rule_id"] for row in rules
                ]

                cur.execute(
                    """
                    SELECT *
                    FROM public.benefit_industry
                    WHERE rule_id = ANY(%s)
                    ORDER BY
                        rule_id, target_type, target_code
                    """,
                    (rule_ids,),
                )
                target_rows = cur.fetchall()

                cur.execute(
                    """
                    SELECT *
                    FROM public.benefit_cap_tier
                    WHERE product_id = %s
                      AND (
                          valid_from IS NULL
                          OR valid_from <= %s
                      )
                      AND (
                          valid_to IS NULL
                          OR %s < valid_to
                      )
                    ORDER BY cap_group, perf_min_won
                    """,
                    (product_id, day, day),
                )
                tier_rows = cur.fetchall()

        targets_by_rule: dict[str, list] = {}
        for item in target_rows:
            targets_by_rule.setdefault(
                item["rule_id"], []
            ).append(item)

        tiers_by_group: dict[str, list] = {}
        for item in tier_rows:
            tiers_by_group.setdefault(
                item["cap_group"], []
            ).append(item)

        return [
            map_db_rule(
                row,
                targets_by_rule.get(row["rule_id"], []),
                tiers_by_group.get(
                    row.get("shared_cap_group"), []
                ),
            )
            for row in rules
        ]
