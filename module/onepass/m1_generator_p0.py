
# onepass/m1_generator_p0.py
"""P0 M1: parameter-driven synthetic transaction generator.

All distributions are caller-supplied.
No claim that example parameters represent real Busan behavior.
No database writes.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from .engine import Merchant, Request
from .replay_p0 import ReplayItem


KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class SyntheticProfile:
    user_id: str
    district_code: str
    age_band: str


@dataclass(frozen=True)
class CategoryParameter:
    category: str
    weight: Decimal
    min_amount_won: int
    max_amount_won: int


@dataclass(frozen=True)
class GeneratedMonth:
    user_id: str
    month: str
    items: list[ReplayItem]


def _month_bounds(month: str) -> tuple[date, date]:
    if len(month) != 7:
        raise ValueError(f"INVALID_MONTH: {month}")

    try:
        first = date.fromisoformat(month + "-01")
    except ValueError as exc:
        raise ValueError(f"INVALID_MONTH: {month}") from exc

    if first.strftime("%Y-%m") != month:
        raise ValueError(f"INVALID_MONTH: {month}")

    if first.month == 12:
        next_first = date(first.year + 1, 1, 1)
    else:
        next_first = date(first.year, first.month + 1, 1)

    return first, next_first


def _decimal_weight(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("INVALID_CATEGORY_WEIGHT")

    try:
        weight = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("INVALID_CATEGORY_WEIGHT") from exc

    if not weight.is_finite() or weight < 0:
        raise ValueError("INVALID_CATEGORY_WEIGHT")

    return weight


def _seed_for(
    seed: int,
    user_id: str,
    month: str,
) -> int:
    digest = hashlib.sha256(
        f"M1|{seed}|{user_id}|{month}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:16], "big")


def generate_month_p0(
    *,
    profile: SyntheticProfile,
    month: str,
    transaction_count: int,
    category_parameters: Sequence[CategoryParameter],
    merchants: Mapping[str, Merchant],
    seed: int = 2026,
) -> GeneratedMonth:
    """Generate ordered ReplayItems for one user and one month.

    Category weights control transaction-count distribution.
    Amounts are uniformly sampled in the supplied inclusive
    range, rounded to integer KRW.

    These are synthetic assumptions, NOT fitted distributions.
    """

    first, next_first = _month_bounds(month)

    if not profile.user_id:
        raise ValueError("EMPTY_USER_ID")

    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("INVALID_SEED")

    if (
        isinstance(transaction_count, bool)
        or not isinstance(transaction_count, int)
        or transaction_count < 0
    ):
        raise ValueError("INVALID_TRANSACTION_COUNT")

    if not category_parameters:
        raise ValueError("EMPTY_CATEGORY_PARAMETERS")

    categories = []
    weights = []
    seen_categories = set()

    for param in category_parameters:
        if not param.category or param.category in seen_categories:
            raise ValueError("DUPLICATE_OR_EMPTY_CATEGORY")

        seen_categories.add(param.category)

        weight = _decimal_weight(param.weight)

        if (
            isinstance(param.min_amount_won, bool)
            or isinstance(param.max_amount_won, bool)
            or not isinstance(param.min_amount_won, int)
            or not isinstance(param.max_amount_won, int)
            or param.min_amount_won <= 0
            or param.max_amount_won < param.min_amount_won
        ):
            raise ValueError(
                f"INVALID_AMOUNT_RANGE: {param.category}"
            )

        categories.append(param)
        weights.append(weight)

    if sum(weights, Decimal(0)) <= 0:
        raise ValueError("ZERO_CATEGORY_WEIGHTS")

    # Match only explicitly supplied merchant categories.
    merchants_by_category: dict[str, list[str]] = {}

    for merchant_id, merchant in merchants.items():
        if merchant.id != merchant_id:
            raise ValueError(
                f"MERCHANT_ID_MISMATCH: {merchant_id}"
            )

        merchants_by_category.setdefault(
            merchant.category, []
        ).append(merchant_id)

    for ids in merchants_by_category.values():
        ids.sort()

    for param, weight in zip(categories, weights, strict=True):
        if weight > 0 and not merchants_by_category.get(
            param.category
        ):
            raise ValueError(
                f"NO_MERCHANT_FOR_CATEGORY: {param.category}"
            )

    rng = random.Random(
        _seed_for(seed, profile.user_id, month)
    )

    # Cumulative weights for deterministic Decimal sampling.
    weighted_categories = [
        (param, weight)
        for param, weight in zip(
            categories, weights, strict=True
        )
        if weight > 0
    ]

    total_weight = sum(
        (weight for _, weight in weighted_categories),
        Decimal(0),
    )

    month_days = (next_first - first).days
    generated = []

    for index in range(transaction_count):
        draw = (
            Decimal(rng.getrandbits(64))
            / Decimal(2**64)
            * total_weight
        )

        cumulative = Decimal(0)
        selected_category = weighted_categories[-1][0]

        for param, weight in weighted_categories:
            cumulative += weight
            if draw < cumulative:
                selected_category = param
                break

        merchant_id = rng.choice(
            merchants_by_category[selected_category.category]
        )

        amount = rng.randint(
            selected_category.min_amount_won,
            selected_category.max_amount_won,
        )

        day_offset = rng.randrange(month_days)
        hour = rng.randrange(8, 23)
        minute = rng.randrange(60)
        second = rng.randrange(60)

        event_at = datetime(
            first.year,
            first.month,
            first.day,
            hour,
            minute,
            second,
            tzinfo=KST,
        ) + timedelta(days=day_offset)

        generated.append(
            (event_at, index, merchant_id, amount)
        )

    generated.sort(key=lambda row: (row[0], row[1]))

    items = []

    for index, (event_at, _, merchant_id, amount) in enumerate(
        generated, start=1
    ):
        request_id = (
            f"SYN_{profile.user_id}_{month.replace('-', '')}"
            f"_{index:06d}"
        )

        items.append(
            ReplayItem(
                event_at=event_at.isoformat(),
                event_seq=index,
                request=Request(
                    id=request_id,
                    merchant_id=merchant_id,
                    amount=amount,
                ),
            )
        )

    return GeneratedMonth(
        user_id=profile.user_id,
        month=month,
        items=items,
    )


def generate_months_p0(
    *,
    profile: SyntheticProfile,
    counts_by_month: Mapping[str, int],
    category_parameters: Sequence[CategoryParameter],
    merchants: Mapping[str, Merchant],
    seed: int = 2026,
) -> dict[str, list[ReplayItem]]:
    """Create ordered, contiguous months for S2 multimonth replay."""

    output = {}
    previous = None

    for month, count in sorted(counts_by_month.items()):
        first, _ = _month_bounds(month)
        current = first.year * 12 + first.month

        if previous is not None and current != previous + 1:
            raise ValueError(
                "MONTHS_MUST_BE_CONTIGUOUS_AND_ORDERED"
            )

        output[month] = generate_month_p0(
            profile=profile,
            month=month,
            transaction_count=count,
            category_parameters=category_parameters,
            merchants=merchants,
            seed=seed,
        ).items

        previous = current

    if not output:
        raise ValueError("NO_MONTHS")

    return output
