
# onepass/m1_users_p0.py
"""P0 M1: synthetic users, card ownership and opening balances.

All distributions and monetary values are supplied by the caller.
Example parameters are NOT official Busan statistics.
No SQLite writes.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from .engine import (
    BenefitRule,
    Card,
    CardType,
    State,
    WalletBalance,
)
from .m1_generator_p0 import SyntheticProfile


@dataclass(frozen=True)
class BankCardTemplate:
    product_id: str
    card_type: CardType
    credit_limit_won: int = 0
    rules: tuple[BenefitRule, ...] = ()


@dataclass(frozen=True)
class PopulationConfig:
    district_weights: Mapping[str, object]
    age_weights: Mapping[str, object]
    bank_card_count_weights: Mapping[int, object]

    opening_account_won: int = 100000
    opening_db_charge_won: int = 30000
    opening_db_cashback_won: int = 0
    opening_db_grant_won: int = 0


@dataclass
class SyntheticUser:
    profile: SyntheticProfile
    cards: list[Card]
    state: State
    default_card_id: str
    a1_weights: dict[str, Decimal]


def _weights(values: Mapping) -> list[tuple[object, Decimal]]:
    if not values:
        raise ValueError("EMPTY_DISTRIBUTION")

    result = []

    for key, raw in sorted(
        values.items(), key=lambda item: str(item[0])
    ):
        if isinstance(raw, bool):
            raise ValueError("INVALID_DISTRIBUTION_WEIGHT")

        try:
            weight = Decimal(str(raw))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(
                "INVALID_DISTRIBUTION_WEIGHT"
            ) from exc

        if not weight.is_finite() or weight < 0:
            raise ValueError("INVALID_DISTRIBUTION_WEIGHT")

        if weight > 0:
            result.append((key, weight))

    if not result:
        raise ValueError("ZERO_DISTRIBUTION_WEIGHT")

    return result


def _pick(rng: random.Random, weighted: list):
    total = sum((w for _, w in weighted), Decimal(0))
    draw = (
        Decimal(rng.getrandbits(64))
        / Decimal(2**64)
        * total
    )

    cumulative = Decimal(0)

    for value, weight in weighted:
        cumulative += weight
        if draw < cumulative:
            return value

    return weighted[-1][0]


def _rng(seed: int, user_id: str) -> random.Random:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("INVALID_SEED")

    digest = hashlib.sha256(
        f"M1_USER|{seed}|{user_id}".encode("utf-8")
    ).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def generate_user_p0(
    *,
    user_id: str,
    config: PopulationConfig,
    bank_products: Sequence[BankCardTemplate],
    seed: int = 2026,
) -> SyntheticUser:
    """Create one independent synthetic user's cards and state."""

    if not user_id or not user_id.strip():
        raise ValueError("EMPTY_USER_ID")

    monetary_values = (
        config.opening_account_won,
        config.opening_db_charge_won,
        config.opening_db_cashback_won,
        config.opening_db_grant_won,
    )

    if any(
        isinstance(v, bool)
        or not isinstance(v, int)
        or v < 0
        for v in monetary_values
    ):
        raise ValueError("INVALID_OPENING_BALANCE")

    products = list(bank_products)
    product_ids = [p.product_id for p in products]

    if len(product_ids) != len(set(product_ids)):
        raise ValueError("DUPLICATE_PRODUCT_ID")

    if any(not product_id for product_id in product_ids):
        raise ValueError("EMPTY_PRODUCT_ID")

    if any(
        p.card_type not in (CardType.DEBIT, CardType.CREDIT)
        or isinstance(p.credit_limit_won, bool)
        or not isinstance(p.credit_limit_won, int)
        or p.credit_limit_won < 0
        for p in products
    ):
        raise ValueError("INVALID_BANK_PRODUCT")

    counts = _weights(config.bank_card_count_weights)

    if any(
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 1
        or count > len(products)
        for count, _ in counts
    ):
        raise ValueError("INVALID_BANK_CARD_COUNT")

    rng = _rng(seed, user_id)

    district = _pick(
        rng, _weights(config.district_weights)
    )
    age = _pick(
        rng, _weights(config.age_weights)
    )
    count = _pick(rng, counts)

    if not isinstance(district, str) or not district:
        raise ValueError("INVALID_DISTRICT_CODE")

    if not isinstance(age, str) or not age:
        raise ValueError("INVALID_AGE_BAND")

    # Deterministic product sample without replacement.
    chosen = rng.sample(
        sorted(products, key=lambda p: p.product_id),
        count,
    )

    account_id = f"ACC_{user_id}"
    wallet_id = f"WAL_{user_id}"

    cards = [
        Card(
            id=f"UC_{user_id}_DB",
            type=CardType.DONGBAEK_CHECK,
            account_id=account_id,
            wallet_id=wallet_id,
        )
    ]

    for product in chosen:
        cards.append(
            Card(
                id=f"UC_{user_id}_{product.product_id}",
                type=product.card_type,
                account_id=(
                    account_id
                    if product.card_type == CardType.DEBIT
                    else None
                ),
                credit_limit=product.credit_limit_won,
                rules=product.rules,
            )
        )

    # P0 baseline assumptions:
    # One Dongbaek card and multiple general cards.
    # Shared funding account for debit cards.
    state = State(
        accounts={
            account_id: config.opening_account_won
        },
        wallets={
            wallet_id: WalletBalance(
                charge=config.opening_db_charge_won,
                cashback=config.opening_db_cashback_won,
                grant=config.opening_db_grant_won,
            )
        },
    )

    default_card_id = cards[1].id

    # Temporary behavioral weights, NOT inferred statistics.
    # Equal probabilities among currently generated cards.
    equal_weight = Decimal(1) / Decimal(len(cards))
    a1_weights = {
        card.id: equal_weight
        for card in cards
    }

    return SyntheticUser(
        profile=SyntheticProfile(
            user_id=user_id,
            district_code=district,
            age_band=age,
        ),
        cards=cards,
        state=state,
        default_card_id=default_card_id,
        a1_weights=a1_weights,
    )


def generate_population_p0(
    *,
    user_count: int,
    config: PopulationConfig,
    bank_products: Sequence[BankCardTemplate],
    seed: int = 2026,
) -> list[SyntheticUser]:
    """Generate a reproducible population of independent users."""

    if (
        isinstance(user_count, bool)
        or not isinstance(user_count, int)
        or user_count <= 0
    ):
        raise ValueError("INVALID_USER_COUNT")

    return [
        generate_user_p0(
            user_id=f"SYN_U{i:06d}",
            config=config,
            bank_products=bank_products,
            seed=seed,
        )
        for i in range(1, user_count + 1)
    ]
