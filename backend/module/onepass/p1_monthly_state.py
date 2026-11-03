
# onepass/p1_monthly_state.py

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .p1_monthly_limits import (
    LimitError,
    MonthlyUsage,
    money,
    nonnegative_int,
)


class MonthlyStateError(ValueError):
    pass


@dataclass(frozen=True)
class MonthlyKey:
    user_id: str
    card_id: str
    month: str

    def __post_init__(self):
        if not self.user_id or not self.card_id:
            raise MonthlyStateError("USER_OR_CARD_MISSING")

        try:
            parsed = date.fromisoformat(
                self.month + "-01"
            )
        except (ValueError, TypeError):
            raise MonthlyStateError(
                "INVALID_MONTH"
            ) from None

        if parsed.strftime("%Y-%m") != self.month:
            raise MonthlyStateError("INVALID_MONTH")


@dataclass(frozen=True)
class RuleUsageRecord:
    rule_id: str
    used_won: int
    used_count: int
    shared_cap_group: str | None = None

    def __post_init__(self):
        if not self.rule_id:
            raise MonthlyStateError("RULE_ID_MISSING")

        try:
            money(self.used_won)
            nonnegative_int(
                self.used_count,
                "USAGE_COUNT",
            )
        except LimitError as exc:
            raise MonthlyStateError(str(exc)) from exc


@dataclass(frozen=True)
class MonthlySnapshot:
    key: MonthlyKey
    previous_spend_won: int
    usage: MonthlyUsage
    performance_basis_confirmed: bool
    usage_state_confirmed: bool


class MonthlyStateRegistry:
    """
    Stores independent calculation state
    for each user/card/month.

    Not a database persistence layer.
    """

    def __init__(self):
        self._snapshots = {}

    def add(self, snapshot: MonthlySnapshot):
        if snapshot.key in self._snapshots:
            raise MonthlyStateError(
                "DUPLICATE_MONTHLY_SNAPSHOT"
            )

        self._snapshots[snapshot.key] = snapshot

    def get(self, key: MonthlyKey):
        if key not in self._snapshots:
            raise MonthlyStateError(
                "MONTHLY_SNAPSHOT_NOT_LOADED"
            )

        return self._snapshots[key]


def build_monthly_snapshot(
    *,
    key: MonthlyKey,
    previous_spend_won: int | None,
    records: Iterable[RuleUsageRecord],
    expected_rule_ids: set[str],
    performance_basis_confirmed: bool,
    usage_state_confirmed: bool,
    zero_usage_confirmed: bool = False,
) -> MonthlySnapshot:
    """
    Convert a complete monthly-close snapshot
    into a calculation state.

    A missing row is never silently interpreted
    as zero usage unless explicitly confirmed.
    """

    if previous_spend_won is None:
        raise MonthlyStateError(
            "PREVIOUS_SPEND_MISSING"
        )

    try:
        previous_spend = money(
            previous_spend_won
        )
    except LimitError as exc:
        raise MonthlyStateError(str(exc)) from exc

    if not performance_basis_confirmed:
        raise MonthlyStateError(
            "PERFORMANCE_BASIS_NOT_CONFIRMED"
        )

    if not usage_state_confirmed:
        raise MonthlyStateError(
            "USAGE_STATE_NOT_CONFIRMED"
        )

    if not expected_rule_ids:
        raise MonthlyStateError(
            "EXPECTED_RULE_IDS_MISSING"
        )

    rows = list(records)
    seen = set()
    used = {}
    counts = {}
    groups = {}

    for row in rows:
        if row.rule_id in seen:
            raise MonthlyStateError(
                "DUPLICATE_RULE_USAGE"
            )

        seen.add(row.rule_id)

        if row.rule_id not in expected_rule_ids:
            raise MonthlyStateError(
                "UNKNOWN_RULE_USAGE"
            )

        used[row.rule_id] = money(row.used_won)
        counts[row.rule_id] = nonnegative_int(
            row.used_count,
            "USAGE_COUNT",
        )

        if row.shared_cap_group:
            group = row.shared_cap_group
            groups[group] = (
                groups.get(group, 0)
                + row.used_won
            )

    missing = expected_rule_ids - seen

    if missing and not zero_usage_confirmed:
        raise MonthlyStateError(
            "INCOMPLETE_RULE_USAGE: "
            + ",".join(sorted(missing))
        )

    if zero_usage_confirmed:
        for rule_id in missing:
            used[rule_id] = 0
            counts[rule_id] = 0

    return MonthlySnapshot(
        key=key,
        previous_spend_won=previous_spend,
        usage=MonthlyUsage(
            benefit_used_won=used,
            benefit_count=counts,
            shared_used_won=groups,
        ),
        performance_basis_confirmed=True,
        usage_state_confirmed=True,
    )
