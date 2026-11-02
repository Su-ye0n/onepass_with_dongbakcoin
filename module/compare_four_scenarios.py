
"""Four-scenario Dongbaek OnePass experiment.

S00: synthetic habit + current wallet
S10: synthetic habit + sufficient wallet
S01: OnePass greedy selection + current wallet
S11: OnePass greedy selection + sufficient wallet

Reads existing NeonDB and original transaction CSV.
No DB writes. No new transactions. No real payments.

Behavior choices are synthetic assumptions, not observations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

import simulate_original_v2 as sim
from onepass.db_policy_repository import DongbaekDBRepository


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "four_scenario_analysis_v34"

DATA_VERSION = "v3.4"
EXPECTED_USERS = 240
EXPECTED_TRANSACTIONS = 7540
EXPECTED_TOTAL_WON = 217449500

def stable_number(*parts):
    value = "|".join(str(x) for x in parts)
    digest = hashlib.sha256(
        value.encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big")


class SufficientBalanceRepository:
    """Theoretical sufficient-balance counterfactual.

    Existing active wallets only.
    Does not perform real or simulated top-up events.
    No database writes.
    """

    def __init__(self, original, grouped):
        self.original = original
        self.extra = {}

        for user_id, transactions in grouped.items():
            # 실제 활성 지갑이 있는 사용자만 대상
            if original.wallet_state_for(user_id) != "ACTIVE":
                continue

            wallet = original.wallet_for(user_id)

            if wallet is None:
                raise ValueError(
                    f"ACTIVE_WALLET_MISSING:{user_id}"
                )

            # 기존 S10/S11 계산과 동일한 이론적 잔액
            self.extra[user_id] = sum(
                int(t["amount_won"])
                for t in transactions
            )

    def wallet_for(self, user_id):
        if self.wallet_state_for(user_id) != "ACTIVE":
            return None

        wallet = self.original.wallet_for(user_id)

        if wallet is None:
            raise ValueError(
                f"ACTIVE_WALLET_MISSING:{user_id}"
            )

        return replace(
            wallet,
            charge_won=(
                wallet.charge_won
                + self.extra.get(user_id, 0)
            ),
        )

    def wallet_state_for(self, user_id):
        """Preserve the actual wallet status."""
        return self.original.wallet_state_for(user_id)

    def policy_for(self, as_of):
        return self.original.policy_for(as_of)


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"EMPTY_OUTPUT:{path}")

    with path.open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=list(rows[0])
        )
        writer.writeheader()
        writer.writerows(rows)


def unique_index(rows, field):
    result = {}

    for row in rows:
        key = row[field]

        if key in result:
            raise ValueError(
                f"DUPLICATE_{field}:{key}"
            )

        result[key] = row

    return result


def validate_source_population(grouped, *, full_run):
    """Validate source identity before any simulation.

    This checks the transaction file consumed by
    simulate_original_v2, not the merchant DB version.
    """
    user_count = len(grouped)

    transactions = [
        tx
        for txs in grouped.values()
        for tx in txs
    ]

    transaction_count = len(transactions)

    ids = [
        str(tx["transaction_id"])
        for tx in transactions
    ]

    if len(set(ids)) != transaction_count:
        raise ValueError(
            "DUPLICATE_SOURCE_TRANSACTION_ID"
        )

    total_amount = sum(
        int(tx["amount_won"])
        for tx in transactions
    )

    if any(
        int(tx["amount_won"]) <= 0
        for tx in transactions
    ):
        raise ValueError(
            "INVALID_SOURCE_TRANSACTION_AMOUNT"
        )

    if full_run:
        if user_count != EXPECTED_USERS:
            raise ValueError(
                f"SOURCE_USER_COUNT_MISMATCH:"
                f"{user_count}"
            )

        if transaction_count != EXPECTED_TRANSACTIONS:
            raise ValueError(
                f"SOURCE_TRANSACTION_COUNT_MISMATCH:"
                f"{transaction_count}"
            )

        if total_amount != EXPECTED_TOTAL_WON:
            raise ValueError(
                "SOURCE_VERSION_AMOUNT_MISMATCH:"
                f"actual={total_amount}:"
                f"expected={EXPECTED_TOTAL_WON}"
            )

    return {
        "data_version": DATA_VERSION,
        "source_user_count": user_count,
        "source_transaction_count": transaction_count,
        "source_transaction_amount_won": total_amount,
        "source_id_uniqueness_checked": True,
        "v34_amount_check_performed": full_run,
    }

def build_behavior_context(
    profiles, slots, merchants, grouped
):
    """Build stable preferences and exact transaction order."""

    slots_by_user = defaultdict(list)

    for slot in slots:
        slots_by_user[slot["user_id"]].append(
            slot
        )

    for values in slots_by_user.values():
        values.sort(
            key=lambda s: int(s["slot_no"])
        )

    profile_by_user = {
        p["user_id"]: p
        for p in profiles
    }

    tx_order = []

    for profile in profiles:
        user_id = profile["user_id"]

        for tx in grouped[user_id]:
            tx_order.append(tx)

    return {
        "slots_by_user": slots_by_user,
        "profiles": profile_by_user,
        "merchants": merchants,
        "tx_order": tx_order,
    }


def preference_order(user_id, merchant, context):
    """Return preferred V2 slot order, independent of benefits."""

    slots = context["slots_by_user"][user_id]

    if not slots:
        raise ValueError(f"NO_V2_CARDS:{user_id}")

    style = context["profiles"][user_id][
        "usage_style"
    ]
    # 카드 1장 사용자는 선택할 다른 카드가 없음
    if style == "SINGLE_CARD":
        if len(slots) != 1:
            raise ValueError(
                f"SINGLE_CARD_SLOT_MISMATCH:{user_id}"
            )
        return slots
    
    if style == "MAIN_SUB":
        # Prefer the V2 primary card.
        primary = [
            s for s in slots
            if s.get("is_primary") is True
        ]
        other = [
            s for s in slots
            if s.get("is_primary") is not True
        ]

        return primary + other

    if style == "PURPOSE_BASED":
        # A user has a stable preferred card for each
        # industry. No per-transaction benefit comparison.
        industry = (
            merchant.get("industry_code") or "UNKNOWN"
        )

        start = stable_number(
            "PURPOSE", user_id, industry
        ) % len(slots)

        return slots[start:] + slots[:start]

    if style == "UNDIFFERENTIATED":
        # Stable user-specific ordering, unchanged across
        # industries and transaction dates.
        start = stable_number(
            "UNDIFFERENTIATED", user_id
        ) % len(slots)

        return slots[start:] + slots[:start]

    raise ValueError(
        f"UNKNOWN_USAGE_STYLE:{user_id}:{style}"
    )


def make_habit_selector(context):
    """Adapt synthetic habits to the existing selector API.

    Only existing comparable candidates are selectable.
    Never override merchant eligibility, wallet balance,
    monthly caps or BNK rule availability.
    """

    index = 0
    tx_order = context["tx_order"]

    def select(dongbaek, bnk_quotes):
        nonlocal index

        if index >= len(tx_order):
            raise ValueError("HABIT_TX_ORDER_OVERFLOW")

        tx = tx_order[index]
        index += 1

        user_id = tx["user_id"]
        merchant = context["merchants"][
            tx["merchant_id"]
        ]

        candidates = {}

        if (
            dongbaek.get("status") == "COMPARABLE"
            and dongbaek.get("payment_possible") is True
        ):
            candidates[("DB", None)] = {
                "product_id": sim.DONGBAEK_ID,
                "user_card_id": None,
                "best_rule_id": None,
                "estimated_value_won": int(
                    dongbaek["cash_benefit_won"]
                ),
                "source": "DONGBAEK",
            }

        for quote in bnk_quotes:
            if quote.get("status") != (
                "SIMULATED_COMPARABLE"
            ):
                continue

            card_id = quote["user_card_id"]

            candidates[("BNK", card_id)] = {
                "product_id": quote["product_id"],
                "user_card_id": card_id,
                "best_rule_id": quote.get(
                    "best_rule_id"
                ),
                "estimated_value_won": int(
                    quote["estimated_value_won"]
                ),
                "source": "BNK",
            }

        ordered = []

        for slot in preference_order(
            user_id, merchant, context
        ):
            if slot["product_id"] == sim.DONGBAEK_ID:
                key = ("DB", None)
            else:
                key = (
                    "BNK",
                    slot["synthetic_user_card_id"],
                )

            candidate = candidates.get(key)

            if candidate is not None:
                ordered.append(candidate)

        if not ordered:
            return {
                "selected_card": None,
                "selected_user_card_id": None,
                "selected_rule_id": None,
                "estimated_value_won": 0,
                "selection_status": "UNRESOLVED",
                "selection_reason": (
                    "NO_COMPARABLE_CANDIDATE"
                ),
                "ranked_candidates": [],
                "excluded_candidates": [],
            }

        chosen = ordered[0]

        return {
            "selected_card": chosen["product_id"],
            "selected_user_card_id": chosen[
                "user_card_id"
            ],
            "selected_rule_id": chosen[
                "best_rule_id"
            ],
            "estimated_value_won": chosen[
                "estimated_value_won"
            ],
            "selection_status": (
                "SIMULATED_SELECTED"
            ),
            "selection_reason": (
                "SYNTHETIC_BEHAVIOR_ASSUMPTION"
            ),
            "ranked_candidates": ordered,
            "excluded_candidates": [],
        }

    def assert_finished():
        if index != len(tx_order):
            raise ValueError(
                f"HABIT_TX_COUNT_MISMATCH:"
                f"{index}/{len(tx_order)}"
            )

    return select, assert_finished


def run_scenario(
    name,
    profiles,
    slots,
    merchants,
    grouped,
    repository,
    context,
):
    print(f"\n=== {name} ===", flush=True)

    original_selector = (
        sim.select_mvp_candidate
    )

    if name in ("S00", "S10"):
        selector, assert_finished = (
            make_habit_selector(context)
        )
        sim.select_mvp_candidate = selector
    else:
        assert_finished = lambda: None

    try:
        tx_rows, user_rows = sim.simulate(
            profiles,
            slots,
            merchants,
            grouped,
            repository,
            Decimal("0"),
        )
        assert_finished()

    finally:
        sim.select_mvp_candidate = (
            original_selector
        )

    return tx_rows, user_rows


def scenario_summary(tx_rows, users):
    return {
        "users": len(users),
        "transactions": len(tx_rows),
        "transaction_amount_won": sum(
            int(t["amount_won"])
            for t in tx_rows
        ),
        "estimated_benefit_won": sum(
            int(u["estimated_benefit_won"])
            for u in users
        ),
        "dongbaek_count": sum(
            int(u["dongbaek"]) for u in users
        ),
        "bnk_count": sum(
            int(u["bnk"]) for u in users
        ),
        "unresolved_count": sum(
            int(u["unresolved"]) for u in users
        ),
        "dongbaek_cashback_won": sum(
            int(u["dongbaek_cashback_won"])
            for u in users
        ),
        "bnk_cash_won": sum(
            int(u["bnk_cash_won"]) for u in users
        ),
        "bnk_points": sum(
            int(u["bnk_points"]) for u in users
        ),
    }


def check_scenarios(results):
    ids = None
    fixed_fields = (
        "user_id",
        "requested_at",
        "merchant_id",
        "amount_won",
        "lane",
        "provider",
    )

    reference = None

    for name, (tx_rows, _) in results.items():
        current = unique_index(
            tx_rows, "transaction_id"
        )

        if ids is None:
            ids = set(current)
            reference = current
            continue

        if set(current) != ids:
            raise ValueError(
                f"TRANSACTION_ID_MISMATCH:{name}"
            )

        for tx_id in ids:
            for field in fixed_fields:
                if current[tx_id][field] != (
                    reference[tx_id][field]
                ):
                    raise ValueError(
                        f"SOURCE_CHANGED:"
                        f"{name}:{tx_id}:{field}"
                    )

    return sorted(ids)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=None
    )
    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")

    load_dotenv(ROOT / ".env")

    grouped_all = sim.read_transactions(
        sim.SOURCE
    )

    user_ids = sorted(grouped_all)

    if args.limit is not None:
        user_ids = user_ids[:args.limit]

    grouped = {
        uid: grouped_all[uid]
        for uid in user_ids
    }

    source_metadata = validate_source_population(
        grouped,
        full_run=(args.limit is None),
    )

    print("\n=== INPUT SOURCE VALIDATION ===")
    print("Data version:", DATA_VERSION)
    print("Users:", source_metadata["source_user_count"])
    print(
        "Transactions:",
        source_metadata["source_transaction_count"],
    )
    print(
        "Amount:",
        source_metadata["source_transaction_amount_won"],
    )
    print("SOURCE VALIDATION: PASSED")

    merchant_ids = sorted({
        t["merchant_id"]
        for transactions in grouped.values()
        for t in transactions
    })

    profiles, slots, merchants = (
        sim.load_population(
            user_ids, merchant_ids
        )
    )

    current_repo = DongbaekDBRepository()

    sufficient_repo = (
        SufficientBalanceRepository(
            current_repo, grouped
        )
    )

    context = build_behavior_context(
        profiles, slots, merchants, grouped
    )

    print("=== FOUR SCENARIO EXPERIMENT ===")
    print("Users:", len(profiles))
    print("Card slots:", len(slots))
    print(
        "Transactions:",
        sum(len(x) for x in grouped.values())
    )
    print("Behavior data: SYNTHETIC_ASSUMPTIONS")
    print("Policy source: NeonDB")
    print("Auto-topup: False")

    results = {}

    setups = (
        ("S00", current_repo),
        ("S10", sufficient_repo),
        ("S01", current_repo),
        ("S11", sufficient_repo),
    )

    for name, repo in setups:
        results[name] = run_scenario(
            name,
            profiles,
            slots,
            merchants,
            grouped,
            repo,
            context,
        )

    tx_ids = check_scenarios(results)

    by_tx = {
        name: unique_index(
            results[name][0],
            "transaction_id",
        )
        for name in results
    }

    by_user = {
        name: unique_index(
            results[name][1],
            "user_id",
        )
        for name in results
    }

    summaries = {
        name: scenario_summary(*results[name])
        for name in results
    }

    baseline_count = len(tx_ids)
    baseline_amount = summaries["S00"][
        "transaction_amount_won"
    ]

    for name, summary in summaries.items():
        if (
            summary["transactions"] != baseline_count
            or summary["transaction_amount_won"]
            != baseline_amount
        ):
            raise ValueError(
                f"TOTALS_CHANGED:{name}"
            )


    if baseline_count != source_metadata[
        "source_transaction_count"
    ]:
        raise ValueError(
            "RESULT_TRANSACTION_COUNT_CHANGED"
        )

    if baseline_amount != source_metadata[
        "source_transaction_amount_won"
    ]:
        raise ValueError(
            "RESULT_TRANSACTION_AMOUNT_CHANGED"
        )

    if len(user_ids) != source_metadata[
        "source_user_count"
    ]:
        raise ValueError(
            "RESULT_USER_COUNT_CHANGED"
        )

    comparison_rows = []

    for tx_id in tx_ids:
        base = by_tx["S00"][tx_id]

        row = {
            "transaction_id": tx_id,
            "user_id": base["user_id"],
            "requested_at": base["requested_at"],
            "merchant_id": base["merchant_id"],
            "amount_won": base["amount_won"],
            "lane": base["lane"],
        }

        for name in results:
            item = by_tx[name][tx_id]
            row[f"{name}_selected_card"] = (
                item["selected_card"]
            )
            row[f"{name}_benefit_won"] = int(
                item["estimated_benefit_won"]
            )

        row["total_change_S11_S00"] = (
            row["S11_benefit_won"]
            - row["S00_benefit_won"]
        )

        comparison_rows.append(row)

    user_rows = []

    for user_id in user_ids:
        a = by_user["S00"][user_id]

        values = {
            name: int(
                by_user[name][user_id][
                    "estimated_benefit_won"
                ]
            )
            for name in results
        }

        s00 = values["S00"]
        s10 = values["S10"]
        s01 = values["S01"]
        s11 = values["S11"]

        # Two-factor Shapley decomposition.
        balance_effect = Decimal(
            (s10 - s00) + (s11 - s01)
        ) / Decimal("2")

        behavior_effect = Decimal(
            (s01 - s00) + (s11 - s10)
        ) / Decimal("2")

        interaction = (
            s11 - s10 - s01 + s00
        )

        total = s11 - s00

        if (
            balance_effect + behavior_effect
            != Decimal(total)
        ):
            raise ValueError(
                f"EFFECT_DECOMPOSITION_FAILED:"
                f"{user_id}"
            )

        user_rows.append({
            "user_id": user_id,
            "usage_style": a["usage_style"],
            "wallet_status": a["wallet_status"],
            "card_count": a["card_count"],
            "transaction_count": a[
                "source_transaction_count"
            ],
            "S00_benefit_won": s00,
            "S10_benefit_won": s10,
            "S01_benefit_won": s01,
            "S11_benefit_won": s11,
            "total_change_won": total,
            "balance_effect_won": str(
                balance_effect
            ),
            "behavior_effect_won": str(
                behavior_effect
            ),
            "interaction_won": interaction,
            "balance_effect_at_habit_won":
                s10 - s00,
            "balance_effect_at_onepass_won":
                s11 - s01,
            "onepass_effect_current_won":
                s01 - s00,
            "onepass_effect_sufficient_won":
                s11 - s10,
        })

    benefits = {
        name: summaries[name][
            "estimated_benefit_won"
        ]
        for name in results
    }

    s00 = benefits["S00"]
    s10 = benefits["S10"]
    s01 = benefits["S01"]
    s11 = benefits["S11"]

    balance_effect = Decimal(
        s10 - s00 + s11 - s01
    ) / 2

    behavior_effect = Decimal(
        s01 - s00 + s11 - s10
    ) / 2

    interaction = (
        s11 - s10 - s01 + s00
    )

    if (
        balance_effect + behavior_effect
        != Decimal(s11 - s00)
    ):
        raise ValueError(
            "TOTAL_EFFECT_DECOMPOSITION_FAILED"
        )

    if sum(
        Decimal(u["balance_effect_won"])
        for u in user_rows
    ) != balance_effect:
        raise ValueError(
            "USER_BALANCE_RECONCILIATION_FAILED"
        )

    if sum(
        Decimal(u["behavior_effect_won"])
        for u in user_rows
    ) != behavior_effect:
        raise ValueError(
            "USER_BEHAVIOR_RECONCILIATION_FAILED"
        )

    report = {
        "scenario_benefits_won": benefits,
        "total_change_S11_minus_S00_won":
            s11 - s00,
        "shapley_balance_effect_won":
            str(balance_effect),
        "shapley_behavior_effect_won":
            str(behavior_effect),
        "interaction_effect_won": interaction,
        "balance_effect_at_onepass_won":
            s11 - s01,
        "onepass_effect_at_current_balance_won":
            s01 - s00,
        "summaries": summaries,
        "methodology": {
            "data": "ORIGINAL_SYNTHETIC_V3_4_BASE",
            "policy": "NEONDB_DB_POLICY",
            "behavior": (
                "V2_USAGE_STYLE_SYNTHETIC_ASSUMPTION"
            ),
            "wallet_B": (
                "SUFFICIENT_BALANCE_THEORETICAL"
            ),
            "choice_engine": (
                "SEQUENTIAL_GREEDY_NOT_GLOBAL_OPTIMUM"
            ),
            "shapley": (
                "AVERAGE_OF_TWO_INTERVENTION_ORDERS"
            ),
            "point_rate": "NON_CASH_REWARD_VALUE_ZERO",
            "real_authorization": False,
            "auto_topup": False,
            "data_version": DATA_VERSION,
            "source_metadata": source_metadata,
        },
    }

    OUTPUT.mkdir(
        parents=True, exist_ok=True
    )

    write_csv(
        OUTPUT / "transactions.csv",
        comparison_rows
    )
    write_csv(
        OUTPUT / "users.csv",
        user_rows
    )

    (OUTPUT / "summary.json").write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== FOUR SCENARIO RESULTS ===")

    for name in (
        "S00", "S10", "S01", "S11"
    ):
        print(
            name,
            f"{benefits[name]:,} KRW",
        )

    print(
        "\nTotal improvement:",
        f"{s11 - s00:,} KRW"
    )
    print(
        "Balance effect (Shapley):",
        balance_effect
    )
    print(
        "Behavior effect (Shapley):",
        behavior_effect
    )
    print(
        "Interaction:",
        interaction
    )
    print("\nSaved:", OUTPUT)


if __name__ == "__main__":
    main()
