
"""Original synthetic transactions + V2 card population.

Dongbaek:
    NeonDB db_policy / db_policy_rate / db_wallet

BNK:
    Existing fast P1 rule and eligibility repositories

Input:
    original_transactions/original_base_transactions.csv

Output:
    original_v2_policy_simulation/

Simulation only. No real payment, DB writes, or bank transfers.

Automatic top-up:
    Disabled by default.
    Quote does not modify balances.
    Commit occurs only when Dongbaek is selected.
"""

from __future__ import annotations

import argparse
import csv
import json

from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from onepass.db_connection import connect_readonly
from onepass.p1_mvp_quote import quote_mvp_card
from onepass.p1_fast_repositories import make_fast_repositories

from onepass.db_policy_repository import (
    DongbaekDBRepository,
    calculate_db_cashback,
)

from onepass.p1_dongbaek_candidate import (
    DongbaekInputs,
    evaluate_dongbaek_candidate,
)

from onepass.auto_topup import (
    AutoTopupPolicy,
    AutoTopupState,
    quote_auto_topup,
    commit_topup_payment,
)

from demo_p1_one_transaction import payment_context

from demo_p1_mvp_batch import (
    select_mvp_candidate,
    commit_mvp_bnk_usage,
)

from simulate_onepass_v2 import (
    BASE_MONTH,
    SCENARIO_ID,
    DONGBAEK_ID,
    V2MonthlyRepository,
    split_user_cards,
    validate_population,
)


ROOT = Path(__file__).resolve().parent

SOURCE = (
    ROOT
    / "original_transactions"
    / "original_base_transactions.csv"
)

OUTPUT = ROOT / "original_v2_policy_simulation"


# ============================================================
# 1. SOURCE TRANSACTIONS
# ============================================================

def read_transactions(path: Path):
    """Read and validate original synthetic transactions."""

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError("EMPTY_TRANSACTIONS")

    required = {
        "transaction_id",
        "user_id",
        "requested_at",
        "merchant_id",
        "amount_won",
        "lane",
        "provider",
    }

    if not required.issubset(rows[0]):
        raise ValueError("INVALID_TRANSACTION_COLUMNS")

    grouped = defaultdict(list)
    seen = set()

    for row in rows:
        tx_id = row["transaction_id"]

        if tx_id in seen:
            raise ValueError(
                f"DUPLICATE_TRANSACTION:{tx_id}"
            )

        seen.add(tx_id)

        amount = int(row["amount_won"])

        if amount <= 0:
            raise ValueError(
                f"INVALID_AMOUNT:{tx_id}"
            )

        lane = row["lane"]
        provider = row["provider"] or None

        if lane not in {
            "OFFLINE",
            "ONLINE",
            "SIMPLE_PAY",
        }:
            raise ValueError(
                f"INVALID_LANE:{tx_id}"
            )

        if (lane == "SIMPLE_PAY") != bool(provider):
            raise ValueError(
                f"INVALID_PROVIDER:{tx_id}"
            )

        if row["requested_at"][:7] != "2026-06":
            raise ValueError(
                f"UNEXPECTED_MONTH:{tx_id}"
            )

        grouped[row["user_id"]].append({
            **row,
            "amount_won": amount,
            "provider": provider,
        })

    for txs in grouped.values():
        txs.sort(
            key=lambda t: (
                t["requested_at"],
                int(t.get("event_seq") or 0),
                t["transaction_id"],
            )
        )

    return grouped


# ============================================================
# 2. NEONDB V2 POPULATION
# ============================================================

def load_population(user_ids, merchant_ids):
    """Load V2 users, card slots, and merchant information."""

    with connect_readonly() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM public.sim_user_profile_v2
                WHERE scenario_id = %s
                  AND base_month = %s
                  AND user_id = ANY(%s)
                ORDER BY user_id
                """,
                (
                    SCENARIO_ID,
                    BASE_MONTH,
                    user_ids,
                ),
            )

            profiles = [
                dict(r) for r in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT *
                FROM public.sim_user_card_slot_v2
                WHERE scenario_id = %s
                  AND base_month = %s
                  AND user_id = ANY(%s)
                ORDER BY user_id, slot_no
                """,
                (
                    SCENARIO_ID,
                    BASE_MONTH,
                    user_ids,
                ),
            )

            slots = [
                dict(r) for r in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT *
                FROM public.merchant
                WHERE merchant_id = ANY(%s)
                """,
                (merchant_ids,),
            )

            merchants = {
                r["merchant_id"]: dict(r)
                for r in cur.fetchall()
            }

    requested_users = set(user_ids)
    profile_ids = {
        p["user_id"] for p in profiles
    }
    slot_users = {
        s["user_id"] for s in slots
    }

    if requested_users != profile_ids:
        raise ValueError(
            "V2_PROFILE_USER_MISMATCH"
        )

    if slot_users != requested_users:
        missing = requested_users - slot_users
        unexpected = slot_users - requested_users

        raise ValueError(
            f"V2_SLOT_USER_MISMATCH:"
            f"missing={sorted(missing)}:"
            f"unexpected={sorted(unexpected)}"
        )

    if set(merchant_ids) != set(merchants):
        raise ValueError(
            "MERCHANT_ID_MISMATCH"
        )

    for slot in slots:
        slot["synthetic_user_card_id"] = (
            f"V2::{slot['user_id']}::"
            f"{slot['slot_no']}"
        )

    return profiles, slots, merchants


# ============================================================
# 3. CSV OUTPUT
# ============================================================

def write_csv(path, rows):
    if not rows:
        raise ValueError(
            f"EMPTY_CSV_OUTPUT:{path}"
        )

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# 4. DONGBAEK EXCLUSION DIAGNOSTICS
# ============================================================

def dongbaek_exclusion_reason(
    *,
    has_dongbaek,
    wallet_status,
    lane,
    merchant,
    db_rate_unknown,
    db_calc,
    balance_won,
    amount_won,
    candidate,
):
    """Classify one diagnostic reason per transaction.

    This function does not change payment eligibility.
    It uses the effective balance already quoted,
    including available simulated top-up funding.
    """

    if not has_dongbaek:
        return "NOT_OWNED"

    if wallet_status != "ACTIVE":
        return wallet_status

    if lane != "OFFLINE":
        return "NON_OFFLINE"

    merchant_status = merchant.get(
        "dongbaek_status"
    )

    if merchant_status == "NOT_REGISTERED":
        return "MERCHANT_NOT_REGISTERED"

    if merchant_status != "REGISTERED":
        return "MERCHANT_REGISTRATION_UNKNOWN"

    if db_rate_unknown:
        return "UNKNOWN_SALES_BAND"

    if balance_won < amount_won:
        return "INSUFFICIENT_BALANCE"

    if db_calc["cashback_rate"] == 0:
        return "ZERO_CASHBACK_RATE"

    if db_calc["remaining_base_won"] <= 0:
        return "MONTHLY_CAP_EXHAUSTED"

    if db_calc["cashback_won"] <= 0:
        return "ZERO_ROUNDED_CASHBACK"

    if (
        candidate["status"] == "COMPARABLE"
        and candidate["payment_possible"] is True
    ):
        return "NONE"

    return (
        candidate.get("reason")
        or "DONGBAEK_UNRESOLVED"
    )


# ============================================================
# 5. AUTO TOP-UP INITIALIZATION
# ============================================================

def initialize_topup_state(
    *,
    user_id,
    initial_balance,
    wallet_status,
    auto_topup_policy,
    auto_topup_funding_by_user,
):
    """Create synthetic funding state for one user.

    Missing funding information is not interpreted
    as zero balance or automatic consent.
    """

    if auto_topup_policy is None:
        return None, "DISABLED"

    if auto_topup_funding_by_user is None:
        raise ValueError(
            "AUTO_TOPUP_FUNDING_DATA_REQUIRED"
        )

    if wallet_status != "ACTIVE":
        return None, "WALLET_NOT_ACTIVE"

    funding = auto_topup_funding_by_user.get(
        user_id
    )

    if funding is None:
        return None, "FUNDING_DATA_MISSING"

    if type(funding) is not int or funding < 0:
        raise ValueError(
            f"INVALID_FUNDING_BALANCE:{user_id}"
        )

    state = AutoTopupState(
        wallet_balance_won=initial_balance,
        funding_balance_won=funding,
    )

    return state, "READY"


# ============================================================
# 6. MAIN SIMULATION ENGINE
# ============================================================

def simulate(
    profiles,
    slots,
    merchants,
    grouped_transactions,
    db_repository,
    point_rate,
    auto_topup_policy: AutoTopupPolicy | None = None,
    auto_topup_funding_by_user: dict[str, int] | None = None,
):
    """Simulate card selection and benefit realization.

    Existing six positional arguments remain unchanged.

    auto_topup_policy=None:
        Original simulation with no automatic top-up.

    auto_topup_policy provided:
        Synthetic top-up is quoted but committed only
        after the selected card is Dongbaek.
    """

    slots_by_user = validate_population(
        profiles,
        slots,
    )

    monthly_repo = V2MonthlyRepository(slots)

    rules_repo, eligibility_repo = (
        make_fast_repositories()
    )

    transaction_rows = []
    user_rows = []
    exclusion_counter = Counter()

    if (
        auto_topup_policy is not None
        and auto_topup_funding_by_user is None
    ):
        raise ValueError(
            "AUTO_TOPUP_FUNDING_DATA_REQUIRED"
        )

    for index, profile in enumerate(
        profiles,
        start=1,
    ):
        user_id = profile["user_id"]

        cards, has_dongbaek = split_user_cards(
            user_id,
            slots_by_user[user_id],
        )

        usage_level = profile[
            "dongbaek_usage_level"
        ]

        expected_member = (
            usage_level != "NON_MEMBER"
        )

        if has_dongbaek != expected_member:
            raise ValueError(
                f"DB_MEMBERSHIP_SLOT_MISMATCH:"
                f"{user_id}:"
                f"level={usage_level}:"
                f"has_slot={has_dongbaek}"
            )

        opening_wallet = (
            db_repository.wallet_for(user_id)
            if has_dongbaek
            else None
        )

        if not has_dongbaek:
            wallet_status = "NOT_OWNED"
        else:
            wallet_state = (
                db_repository.wallet_state_for(user_id)
            )

            if wallet_state == "ACTIVE":
                wallet_status = "ACTIVE"
            elif wallet_state == "MISSING_ROW":
                wallet_status = "WALLET_DATA_MISSING"
            else:
                wallet_status = wallet_state

        if (
            wallet_status == "ACTIVE"
            and opening_wallet is None
        ):
            raise ValueError(
                f"ACTIVE_WALLET_NOT_LOADED:{user_id}"
            )

        initial_balance = (
            opening_wallet.total_won
            if opening_wallet is not None
            else 0
        )

        topup_state, topup_user_status = (
            initialize_topup_state(
                user_id=user_id,
                initial_balance=initial_balance,
                wallet_status=wallet_status,
                auto_topup_policy=auto_topup_policy,
                auto_topup_funding_by_user=(
                    auto_topup_funding_by_user
                ),
            )
        )

        user_topup_total_won = 0
        user_topup_events = 0

        state = {
            "dongbaek_balance_won": initial_balance,
            "dongbaek_monthly_base_used_won": 0,
            "dongbaek_cashback_earned_won": 0,
            "bnk_usage": {},
        }

        counters = {
            "assigned": 0,
            "unresolved": 0,
            "dongbaek": 0,
            "bnk": 0,
            "estimated_benefit_won": 0,
            "dongbaek_cashback_won": 0,
            "bnk_cash_won": 0,
            "bnk_points": 0,
        }

        source_txs = grouped_transactions[user_id]

        for tx in source_txs:
            tx_id = tx["transaction_id"]
            amount = tx["amount_won"]
            merchant_id = tx["merchant_id"]

            merchant = merchants[merchant_id]

            as_of = tx["requested_at"][:10]
            lane = tx["lane"]

            payment = payment_context(
                lane,
                tx["provider"],
            )

            # --------------------------------------------
            # 6-1. BNK benefit quotes
            # --------------------------------------------

            quotes = [
                quote_mvp_card(
                    card=card,
                    merchant_id=merchant_id,
                    amount=amount,
                    payment=payment,
                    as_of=as_of,
                    base_month=BASE_MONTH,
                    rules_repo=rules_repo,
                    eligibility_repo=eligibility_repo,
                    monthly_repo=monthly_repo,
                    usage_state=state["bnk_usage"],
                    point_krw_rate=point_rate,
                    reward_units=(
                        eligibility_repo.reward_units
                    ),
                )
                for card in cards
            ]

            # --------------------------------------------
            # 6-2. Dongbaek policy quote
            # --------------------------------------------

            policy = db_repository.policy_for(as_of)
            sales_band = merchant["sales_band"]

            db_rate_unknown = (
                sales_band not in policy.rates
            )

            if db_rate_unknown:
                db_calc = {
                    "cashback_rate": None,
                    "eligible_base_won": 0,
                    "cashback_won": 0,
                    "remaining_base_won": max(
                        0,
                        policy.monthly_base_cap_won
                        - state[
                            "dongbaek_monthly_base_used_won"
                        ],
                    ),
                }
            else:
                db_calc = calculate_db_cashback(
                    policy=policy,
                    sales_band=sales_band,
                    amount_won=amount,
                    monthly_base_used_won=state[
                        "dongbaek_monthly_base_used_won"
                    ],
                )

            db_can_attempt = (
                has_dongbaek
                and wallet_status == "ACTIVE"
                and opening_wallet is not None
                and not db_rate_unknown
            )

            balance_before = state[
                "dongbaek_balance_won"
            ]

            # --------------------------------------------
            # 6-3. Automatic top-up quote
            # No state mutation here.
            # --------------------------------------------

            topup_quote = None
            topup_status = topup_user_status
            topup_required_won = 0
            committed_topup_won = 0

            eligible_topup_merchant = (
                lane == "OFFLINE"
                and merchant.get("dongbaek_status")
                == "REGISTERED"
                and not db_rate_unknown
            )

            if (
                topup_state is not None
                and db_can_attempt
                and eligible_topup_merchant
            ):
                if (
                    topup_state.wallet_balance_won
                    != balance_before
                ):
                    raise ValueError(
                        f"TOPUP_WALLET_STATE_MISMATCH:"
                        f"{tx_id}"
                    )

                topup_quote = quote_auto_topup(
                    state=topup_state,
                    policy=auto_topup_policy,
                    amount_won=amount,
                    wallet_active=True,
                )

                topup_status = topup_quote.status
                topup_required_won = (
                    topup_quote.topup_amount_won
                )

            # Use only feasible quoted funding.
            # Do not increase the stored wallet balance.

            effective_db_balance = balance_before

            if (
                topup_quote is not None
                and topup_quote.payment_possible
            ):
                effective_db_balance += (
                    topup_quote.topup_amount_won
                )

            # --------------------------------------------
            # 6-4. Dongbaek candidate evaluation
            # --------------------------------------------

            dongbaek = evaluate_dongbaek_candidate(
                merchant=merchant,
                amount_won=amount,
                lane=lane,
                inputs=DongbaekInputs(
                    balance_won=(
                        effective_db_balance
                        if db_can_attempt
                        else 0
                    ),
                    cashback_rate=db_calc[
                        "cashback_rate"
                    ],
                    cashback_remaining_won=db_calc[
                        "cashback_won"
                    ],
                ),
            )

            db_reason = dongbaek_exclusion_reason(
                has_dongbaek=has_dongbaek,
                wallet_status=wallet_status,
                lane=lane,
                merchant=merchant,
                db_rate_unknown=db_rate_unknown,
                db_calc=db_calc,
                balance_won=effective_db_balance,
                amount_won=amount,
                candidate=dongbaek,
            )

            exclusion_counter[db_reason] += 1

            # --------------------------------------------
            # 6-5. Card selection
            # S00/S10 may inject habit selector.
            # --------------------------------------------

            decision = select_mvp_candidate(
                dongbaek,
                quotes,
            )

            selected = decision["selected_card"]

            selected_user_card_id = decision[
                "selected_user_card_id"
            ]

            rule_id = decision["selected_rule_id"]

            benefit_value = 0
            benefit_amount = 0
            benefit_unit = ""

            # --------------------------------------------
            # 6-6. Dongbaek commit
            # --------------------------------------------

            if selected == DONGBAEK_ID:
                if not db_can_attempt:
                    raise ValueError(
                        f"DB_SELECTED_WITHOUT_WALLET:"
                        f"{user_id}:{tx_id}"
                    )

                if (
                    dongbaek["status"] != "COMPARABLE"
                    or dongbaek["payment_possible"]
                    is not True
                ):
                    raise ValueError(
                        f"DB_SELECTED_NOT_COMPARABLE:"
                        f"{tx_id}"
                    )

                benefit_value = int(
                    dongbaek["cash_benefit_won"]
                )

                expected = db_calc["cashback_won"]

                if benefit_value != expected:
                    raise ValueError(
                        f"DB_CASHBACK_MISMATCH:"
                        f"{tx_id}:"
                        f"{benefit_value}!={expected}"
                    )

                # Validate monthly cap BEFORE payment commit.
                next_monthly_base = (
                    state[
                        "dongbaek_monthly_base_used_won"
                    ]
                    + db_calc["eligible_base_won"]
                )

                if (
                    next_monthly_base
                    > policy.monthly_base_cap_won
                ):
                    raise ValueError(
                        "DB_MONTHLY_BASE_CAP_EXCEEDED"
                    )

                # If a top-up state exists, commit both
                # top-up and payment exactly once.

                if topup_state is not None:
                    if topup_quote is None:
                        raise ValueError(
                            f"TOPUP_QUOTE_MISSING:{tx_id}"
                        )

                    if not topup_quote.payment_possible:
                        raise ValueError(
                            f"TOPUP_UNAVAILABLE_BUT_SELECTED:"
                            f"{tx_id}:{topup_quote.status}"
                        )

                    if (
                        topup_state.wallet_balance_won
                        != balance_before
                    ):
                        raise ValueError(
                            f"TOPUP_WALLET_STATE_MISMATCH:"
                            f"{tx_id}"
                        )

                    topup_result = commit_topup_payment(
                        state=topup_state,
                        quote=topup_quote,
                        policy=auto_topup_policy,
                        wallet_active=True,
                    )

                    committed_topup_won = (
                        topup_result["topup_won"]
                    )

                    # commit_topup_payment already
                    # deducted the payment amount.
                    state["dongbaek_balance_won"] = (
                        topup_state.wallet_balance_won
                    )

                    if committed_topup_won > 0:
                        user_topup_total_won += (
                            committed_topup_won
                        )
                        user_topup_events += 1

                else:
                    # Original mode or user without
                    # synthetic funding information.

                    if balance_before < amount:
                        raise ValueError(
                            f"DB_INSUFFICIENT_BALANCE:"
                            f"{tx_id}"
                        )

                    state[
                        "dongbaek_balance_won"
                    ] -= amount

                # Cashback is accounted for as a benefit.
                # Do not silently add it to spendable
                # wallet balance unless a separate
                # crediting event is explicitly modeled.

                state[
                    "dongbaek_monthly_base_used_won"
                ] = next_monthly_base

                state[
                    "dongbaek_cashback_earned_won"
                ] += benefit_value

                benefit_amount = benefit_value
                benefit_unit = "CASH"

                counters["assigned"] += 1
                counters["dongbaek"] += 1

                counters[
                    "dongbaek_cashback_won"
                ] += benefit_value

            # --------------------------------------------
            # 6-7. Unresolved selection
            # --------------------------------------------

            elif selected is None:
                counters["unresolved"] += 1

            # --------------------------------------------
            # 6-8. BNK commit
            # No automatic top-up in this branch.
            # --------------------------------------------

            else:
                matches = [
                    q for q in quotes
                    if (
                        q["product_id"] == selected
                        and q["user_card_id"]
                        == selected_user_card_id
                    )
                ]

                if len(matches) != 1:
                    raise ValueError(
                        f"BNK_SELECTED_CARD_MISMATCH:"
                        f"{user_id}:{tx_id}"
                    )

                change = commit_mvp_bnk_usage(
                    state["bnk_usage"],
                    matches[0],
                    rule_id,
                    rules_repo,
                    as_of,
                )

                benefit_value = int(
                    change["estimated_value_won"]
                )

                benefit_amount = int(
                    change["benefit_amount"]
                )

                benefit_unit = (
                    change["reward_unit"] or ""
                )

                counters["assigned"] += 1
                counters["bnk"] += 1

                if benefit_unit == "CASH":
                    counters[
                        "bnk_cash_won"
                    ] += benefit_amount

                elif benefit_unit == "POINT":
                    counters[
                        "bnk_points"
                    ] += benefit_amount

                # Guard against accidentally mutating
                # top-up state during BNK selection.
                if (
                    topup_state is not None
                    and topup_state.wallet_balance_won
                    != balance_before
                ):
                    raise ValueError(
                        f"TOPUP_COMMITTED_FOR_BNK:"
                        f"{tx_id}"
                    )

            counters[
                "estimated_benefit_won"
            ] += benefit_value

            # --------------------------------------------
            # 6-9. Per-transaction output
            # --------------------------------------------

            transaction_rows.append({
                "user_id": user_id,
                "transaction_id": tx_id,
                "requested_at": tx["requested_at"],
                "merchant_id": merchant_id,
                "industry_code": merchant[
                    "industry_code"
                ],
                "amount_won": amount,
                "lane": lane,
                "provider": tx["provider"] or "",
                "original_payment_path": tx.get(
                    "payment_path", ""
                ),
                "original_direct_user_card_id": (
                    tx.get(
                        "direct_user_card_id",
                        "",
                    )
                ),
                "card_count": profile[
                    "simulated_card_count"
                ],
                "usage_style": profile[
                    "usage_style"
                ],
                "performance_state": profile[
                    "performance_state"
                ],
                "wallet_status": wallet_status,
                "dongbaek_policy_id": policy.policy_id,
                "dongbaek_policy_source_status": (
                    policy.source_status
                ),
                "dongbaek_sales_band": sales_band,
                "dongbaek_policy_rate": (
                    str(db_calc["cashback_rate"])
                    if db_calc["cashback_rate"] is not None
                    else ""
                ),
                "dongbaek_quote_cashback_won": (
                    db_calc["cashback_won"]
                    if not db_rate_unknown
                    else ""
                ),
                "selected_card": selected or "",
                "selected_user_card_id": (
                    selected_user_card_id or ""
                ),
                "selected_rule_id": rule_id or "",
                "selection_status": decision[
                    "selection_status"
                ],
                "estimated_benefit_won": benefit_value,
                "benefit_amount": benefit_amount,
                "benefit_unit": benefit_unit,
                "dongbaek_balance_after": state[
                    "dongbaek_balance_won"
                ],
                "dongbaek_monthly_base_used_after": (
                    state[
                        "dongbaek_monthly_base_used_won"
                    ]
                ),
                "bnk_candidate_count": len(quotes),
                "excluded_candidate_count": len(
                    decision["excluded_candidates"]
                ),
                "dongbaek_policy_evaluation_status": (
                    "UNKNOWN_SALES_BAND"
                    if db_rate_unknown
                    else "POLICY_RATE_RESOLVED"
                ),
                "merchant_dongbaek_status": (
                    merchant.get("dongbaek_status") or ""
                ),
                "dongbaek_candidate_status": (
                    dongbaek.get("status") or ""
                ),
                "dongbaek_candidate_reason": (
                    dongbaek.get("reason") or ""
                ),
                "dongbaek_exclusion_reason": db_reason,

                # New automatic top-up diagnostics
                "auto_topup_enabled": (
                    auto_topup_policy is not None
                ),
                "auto_topup_status": topup_status,
                "auto_topup_quote_won": (
                    topup_required_won
                ),
                "auto_topup_committed_won": (
                    committed_topup_won
                ),
                "auto_topup_funding_after_won": (
                    topup_state.funding_balance_won
                    if topup_state is not None
                    else ""
                ),
            })

        # -----------------------------------------------
        # 6-10. Per-user output
        # -----------------------------------------------

        user_rows.append({
            "user_id": user_id,
            "card_count": profile[
                "simulated_card_count"
            ],
            "usage_style": profile["usage_style"],
            "performance_state": profile[
                "performance_state"
            ],
            "wallet_status": wallet_status,
            "dongbaek_opening_balance_won": (
                initial_balance
            ),
            "dongbaek_closing_balance_won": state[
                "dongbaek_balance_won"
            ],
            "dongbaek_monthly_base_used_won": (
                state[
                    "dongbaek_monthly_base_used_won"
                ]
            ),
            "original_month_spend_won": profile[
                "original_month_spend_won"
            ],
            "source_transaction_count": len(
                source_txs
            ),
            "source_transaction_amount_won": sum(
                t["amount_won"] for t in source_txs
            ),
            "auto_topup_user_status": (
                topup_user_status
            ),
            "auto_topup_total_won": (
                user_topup_total_won
            ),
            "auto_topup_event_count": (
                user_topup_events
            ),
            "auto_topup_funding_after_won": (
                topup_state.funding_balance_won
                if topup_state is not None
                else None
            ),
            **counters,
        })

        if index % 20 == 0:
            print(
                f"Processed {index}/{len(profiles)}",
                flush=True,
            )

    print("\n=== DONGBAEK EXCLUSION DIAGNOSTICS ===")

    for reason, count in exclusion_counter.most_common():
        print(f"{reason}: {count}")

    print("\n=== CACHE PERFORMANCE ===")
    print("Rules:", rules_repo.cache_info())
    print("Eligibility:", eligibility_repo.cache_info())

    return transaction_rows, user_rows


# ============================================================
# 7. SEGMENT REPORT
# ============================================================

def build_segments(users):
    rows = []

    for dimension in (
        "card_count",
        "usage_style",
        "performance_state",
        "wallet_status",
    ):
        groups = defaultdict(list)

        for user in users:
            groups[str(user[dimension])].append(
                user
            )

        for segment, group in sorted(
            groups.items()
        ):
            count = sum(
                u["source_transaction_count"]
                for u in group
            )

            assigned = sum(
                u["assigned"]
                for u in group
            )

            benefits = sum(
                u["estimated_benefit_won"]
                for u in group
            )

            rows.append({
                "dimension": dimension,
                "segment": segment,
                "user_count": len(group),
                "transaction_count": count,
                "assigned_count": assigned,
                "assignment_rate_pct": (
                    round(100 * assigned / count, 2)
                    if count
                    else 0
                ),
                "estimated_benefit_won": benefits,
            })

    return rows


# ============================================================
# 8. CLI MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=SOURCE,
    )

    parser.add_argument(
        "--limit",
        type=int,
    )

    parser.add_argument(
        "--point-rate",
        type=Decimal,
        default=Decimal("1"),
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")

    if (
        not args.point_rate.is_finite()
        or args.point_rate < 0
    ):
        parser.error("INVALID_POINT_RATE")

    load_dotenv(ROOT / ".env")

    grouped = read_transactions(args.input)

    user_ids = sorted(grouped)

    if args.limit is not None:
        user_ids = user_ids[:args.limit]

    selected_grouped = {
        user_id: grouped[user_id]
        for user_id in user_ids
    }

    merchant_ids = sorted({
        tx["merchant_id"]
        for txs in selected_grouped.values()
        for tx in txs
    })

    profiles, slots, merchants = load_population(
        user_ids,
        merchant_ids,
    )

    db_repository = DongbaekDBRepository()

    print("=== ORIGINAL V2 DB POLICY ===")
    print("Users:", len(profiles))
    print("Card slots:", len(slots))

    print(
        "Source transactions:",
        sum(len(txs) for txs in selected_grouped.values()),
    )

    print("Matched merchants:", len(merchants))
    print("DB policies:", len(db_repository.policies))
    print("DB active wallets:", len(db_repository.wallets))

    # CLI intentionally keeps automatic top-up OFF.
    # Separate scenario runner should pass funding
    # assumptions explicitly through simulate().

    tx_rows, user_rows = simulate(
        profiles,
        slots,
        merchants,
        selected_grouped,
        db_repository,
        args.point_rate,
    )

    total_count = sum(
        len(txs)
        for txs in selected_grouped.values()
    )

    total_amount = sum(
        tx["amount_won"]
        for txs in selected_grouped.values()
        for tx in txs
    )

    if len(tx_rows) != total_count:
        raise ValueError(
            "SOURCE_TRANSACTION_COUNT_CHANGED"
        )

    if sum(
        tx["amount_won"] for tx in tx_rows
    ) != total_amount:
        raise ValueError(
            "SOURCE_TRANSACTION_AMOUNT_CHANGED"
        )

    if sum(
        u["assigned"] + u["unresolved"]
        for u in user_rows
    ) != total_count:
        raise ValueError(
            "ASSIGNMENT_COUNT_MISMATCH"
        )

    wallet_status_counts = Counter(
        u["wallet_status"]
        for u in user_rows
    )

    exclusion_counts = Counter(
        t["dongbaek_exclusion_reason"]
        for t in tx_rows
    )

    summary = {
        "scenario_id": SCENARIO_ID,
        "data_source": "ORIGINAL_SYNTHETIC_V3_3_BASE",
        "dongbaek_policy_source": (
            "NEONDB_PUBLIC_DB_POLICY"
        ),
        "user_count": len(user_rows),
        "card_slot_count": len(slots),
        "transaction_count": len(tx_rows),
        "transaction_amount_won": total_amount,
        "assigned_count": sum(
            u["assigned"] for u in user_rows
        ),
        "unresolved_count": sum(
            u["unresolved"] for u in user_rows
        ),
        "dongbaek_count": sum(
            u["dongbaek"] for u in user_rows
        ),
        "bnk_count": sum(
            u["bnk"] for u in user_rows
        ),
        "estimated_total_benefit_won": sum(
            u["estimated_benefit_won"]
            for u in user_rows
        ),
        "dongbaek_cashback_won": sum(
            u["dongbaek_cashback_won"]
            for u in user_rows
        ),
        "bnk_cash_won": sum(
            u["bnk_cash_won"]
            for u in user_rows
        ),
        "bnk_points": sum(
            u["bnk_points"]
            for u in user_rows
        ),
        "wallet_status_counts": dict(
            wallet_status_counts
        ),
        "dongbaek_exclusion_counts": dict(
            exclusion_counts
        ),
        "source_count_preserved": True,
        "source_amount_preserved": True,
        "payment_path_policy": (
            "ALL_REQUESTS_EVALUATED_AS_ONEPASS"
        ),
        "wallet_funding_assumption": (
            "CHARGE_PLUS_CASHBACK_PLUS_POLICY_SUPPORT"
        ),
        "auto_topup": False,
        "simulation_only": True,
    }

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(
        OUTPUT / "transactions.csv",
        tx_rows,
    )

    write_csv(
        OUTPUT / "users.csv",
        user_rows,
    )

    write_csv(
        OUTPUT / "segments.csv",
        build_segments(user_rows),
    )

    (OUTPUT / "summary.json").write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== SUMMARY ===")
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )
    print("\nSaved:", OUTPUT)


if __name__ == "__main__":
    main()
