
# onepass/p1_target_evaluator.py

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


class TargetStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class TargetCondition:
    rule_id: str
    target_type: str
    target_code: str
    apply_type: str


@dataclass(frozen=True)
class MerchantContext:
    merchant_id: str
    industry_code: str


@dataclass(frozen=True)
class TargetDecision:
    status: TargetStatus
    reason: str
    matched_targets: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        return self.status == TargetStatus.ELIGIBLE


VALID_TYPES = {"CATEGORY", "MERCHANT"}
VALID_ACTIONS = {"INCLUDE", "EXCLUDE"}


def _nonempty(value: object) -> str:
    return str(value).strip() if value is not None else ""


def evaluate_target(
    *,
    rule_id: str,
    merchant: MerchantContext,
    conditions: Iterable[TargetCondition],
    category_map: Mapping[str, str],
) -> TargetDecision:
    """
    Evaluate merchant eligibility for a single benefit rule.

    category_map:
        original industry_code -> standard category

    Does not evaluate:
        payment lane, provider, performance, caps, or money.
    """

    rule_id = _nonempty(rule_id)
    merchant_id = _nonempty(merchant.merchant_id)
    industry_code = _nonempty(merchant.industry_code)

    if not rule_id or not merchant_id or not industry_code:
        return TargetDecision(
            TargetStatus.UNRESOLVED,
            "MERCHANT_CONTEXT_INCOMPLETE",
        )

    rows = tuple(conditions)

    # Never evaluate rows belonging to another benefit.
    if any(_nonempty(row.rule_id) != rule_id for row in rows):
        return TargetDecision(
            TargetStatus.UNRESOLVED,
            "RULE_ID_MISMATCH",
        )

    if not rows:
        return TargetDecision(
            TargetStatus.UNRESOLVED,
            "TARGET_RULES_MISSING",
        )

    # CHANNEL is intentionally unsupported here.
    # A separate lane evaluator will process it.
    for row in rows:
        if (
            _nonempty(row.target_type) not in VALID_TYPES
            or _nonempty(row.apply_type) not in VALID_ACTIONS
            or not _nonempty(row.target_code)
        ):
            return TargetDecision(
                TargetStatus.UNRESOLVED,
                "UNSUPPORTED_TARGET_CONDITION",
            )

    std_category = _nonempty(category_map.get(industry_code))
    needs_category = any(
        row.target_type == "CATEGORY" for row in rows
    )

    if needs_category and not std_category:
        return TargetDecision(
            TargetStatus.UNRESOLVED,
            "CATEGORY_MAPPING_MISSING",
        )

    includes = []
    excludes = []

    for row in rows:
        if row.target_type == "MERCHANT":
            matched = row.target_code == merchant_id
        else:
            matched = row.target_code == std_category

        if not matched:
            continue

        matched_key = f"{row.target_type}:{row.target_code}"

        if row.apply_type == "EXCLUDE":
            excludes.append(matched_key)
        else:
            includes.append(matched_key)

    # Explicit exclusions always take priority.
    if excludes:
        return TargetDecision(
            TargetStatus.INELIGIBLE,
            "EXPLICITLY_EXCLUDED",
            tuple(sorted(set(excludes))),
        )

    if includes:
        return TargetDecision(
            TargetStatus.ELIGIBLE,
            "INCLUDE_MATCHED",
            tuple(sorted(set(includes))),
        )

    # No inclusion means no benefit for this merchant.
    return TargetDecision(
        TargetStatus.INELIGIBLE,
        "NO_INCLUDE_MATCH",
    )
