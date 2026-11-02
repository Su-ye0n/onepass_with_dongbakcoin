
"""OnePass Dongbaek missed-benefit counterfactual.

Scenario A: Original NeonDB wallet balances.
Scenario B: Same wallets, but with sufficient virtual funding.

Only users with an existing active wallet can receive
virtual funding. No new wallets, cards, or transactions.

Uses existing OnePass V2 simulation engine.
Read-only DB access. No real charging or authorization.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

import simulate_original_v2 as sim

from onepass.db_policy_repository import (
    DongbaekDBRepository,
)


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "topup_opportunity_analysis"


class SufficientBalanceRepository:
    """Theoretical sufficient-balance scenario.

    Virtual funding is applied only to existing
    active wallets.

    This is NOT automatic top-up and does not
    modify the database.
    """

    def __init__(
        self,
        original_repo,
        transactions_by_user,
    ):
        self.original = original_repo
        self.extra_by_user = {}

        for user_id, transactions in (
            transactions_by_user.items()
        ):
            if (
                original_repo.wallet_state_for(user_id)
                != "ACTIVE"
            ):
                continue

            wallet = original_repo.wallet_for(user_id)

            if wallet is None:
                raise ValueError(
                    f"ACTIVE_WALLET_MISSING:{user_id}"
                )

            self.extra_by_user[user_id] = sum(
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

        extra = self.extra_by_user.get(user_id, 0)

        return replace(
            wallet,
            charge_won=wallet.charge_won + extra,
        )

    def wallet_state_for(self, user_id):
        return self.original.wallet_state_for(user_id)

    def policy_for(self, as_of):
        return self.original.policy_for(as_of)


def write_csv(path, rows):
    if not rows:
        raise ValueError(
            f"EMPTY_OUTPUT:{path}"
        )

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(rows)


def index_unique(rows, key):
    result = {}

    for row in rows:
        identifier = row[key]

        if identifier in result:
            raise ValueError(
                f"DUPLICATE_{key}:{identifier}"
            )

        result[identifier] = row

    return result


def check_source_consistency(a_rows, b_rows):
    a = index_unique(
        a_rows, "transaction_id"
    )
    b = index_unique(
        b_rows, "transaction_id"
    )

    if set(a) != set(b):
        raise ValueError(
            "SCENARIO_TRANSACTION_IDS_DIFFER"
        )

    source_fields = (
        "user_id",
        "requested_at",
        "merchant_id",
        "amount_won",
        "lane",
        "provider",
    )

    for tx_id, before in a.items():
        after = b[tx_id]

        for field in source_fields:
            if before[field] != after[field]:
                raise ValueError(
                    f"TRANSACTION_CHANGED:"
                    f"{tx_id}:{field}"
                )

    return a, b


def summarize(tx_rows, user_rows):
    return {
        "user_count": len(user_rows),
        "transaction_count": len(tx_rows),
        "transaction_amount_won": sum(
            int(r["amount_won"])
            for r in tx_rows
        ),
        "assigned_count": sum(
            int(u["assigned"])
            for u in user_rows
        ),
        "unresolved_count": sum(
            int(u["unresolved"])
            for u in user_rows
        ),
        "dongbaek_count": sum(
            int(u["dongbaek"])
            for u in user_rows
        ),
        "bnk_count": sum(
            int(u["bnk"])
            for u in user_rows
        ),
        "estimated_total_benefit_won": sum(
            int(u["estimated_benefit_won"])
            for u in user_rows
        ),
        "dongbaek_cashback_won": sum(
            int(u["dongbaek_cashback_won"])
            for u in user_rows
        ),
        "bnk_cash_won": sum(
            int(u["bnk_cash_won"])
            for u in user_rows
        ),
        "bnk_points": sum(
            int(u["bnk_points"])
            for u in user_rows
        ),
        "wallet_status_counts": dict(
            Counter(
                u["wallet_status"]
                for u in user_rows
            )
        ),
    }


def main():
    load_dotenv(ROOT / ".env")

    # Original transactions: no regeneration.
    grouped = sim.read_transactions(
        sim.SOURCE
    )

    user_ids = sorted(grouped)

    merchant_ids = sorted({
        tx["merchant_id"]
        for transactions in grouped.values()
        for tx in transactions
    })

    profiles, slots, merchants = (
        sim.load_population(
            user_ids, merchant_ids
        )
    )

    repo_a = DongbaekDBRepository()

    repo_b = SufficientBalanceRepository(
        repo_a, grouped
    )

    print("=== COUNTERFACTUAL SETUP ===")
    print("Users:", len(profiles))
    print("Card slots:", len(slots))
    print(
        "Transactions:",
        sum(len(v) for v in grouped.values())
    )
    print(
        "Active wallets:",
        len(repo_a.wallets)
    )

    print("\n=== SCENARIO A: CURRENT BALANCE ===")
    tx_a, users_a = sim.simulate(
        profiles,
        slots,
        merchants,
        grouped,
        repo_a,
        Decimal("1"),
    )

    print("\n=== SCENARIO B: SUFFICIENT BALANCE ===")
    tx_b, users_b = sim.simulate(
        profiles,
        slots,
        merchants,
        grouped,
        repo_b,
        Decimal("1"),
    )

    a_index, b_index = (
        check_source_consistency(
            tx_a, tx_b
        )
    )

    a_users = index_unique(
        users_a, "user_id"
    )
    b_users = index_unique(
        users_b, "user_id"
    )

    if set(a_users) != set(b_users):
        raise ValueError(
            "SCENARIO_USER_IDS_DIFFER"
        )

    tx_comparison = []
    gained = Counter()
    lost = Counter()

    for tx_id, before in a_index.items():
        after = b_index[tx_id]
        user_id = before["user_id"]

        value_a = int(
            before["estimated_benefit_won"]
        )
        value_b = int(
            after["estimated_benefit_won"]
        )

        delta = value_b - value_a

        a_card = before["selected_card"]
        b_card = after["selected_card"]

        if delta > 0:
            gained[user_id] += delta
        elif delta < 0:
            lost[user_id] += -delta

        if (
            a_card != sim.DONGBAEK_ID
            and b_card == sim.DONGBAEK_ID
        ):
            transition = "TO_DONGBAEK"
        elif (
            a_card == sim.DONGBAEK_ID
            and b_card != sim.DONGBAEK_ID
        ):
            transition = "FROM_DONGBAEK"
        elif a_card == b_card:
            transition = "UNCHANGED_CARD"
        else:
            transition = "OTHER_CHANGE"

        tx_comparison.append({
            "transaction_id": tx_id,
            "user_id": user_id,
            "requested_at": before[
                "requested_at"
            ],
            "merchant_id": before[
                "merchant_id"
            ],
            "amount_won": before[
                "amount_won"
            ],
            "lane": before["lane"],
            "wallet_status": before[
                "wallet_status"
            ],
            "a_selected_card": a_card,
            "b_selected_card": b_card,
            "a_benefit_won": value_a,
            "b_benefit_won": value_b,
            "delta_benefit_won": delta,
            "positive_gain_won": max(
                0, delta
            ),
            "a_db_balance_before": (
                before.get(
                    "dongbaek_balance_before",
                    "",
                )
            ),
            "a_db_exclusion_reason": (
                before.get(
                    "dongbaek_exclusion_reason",
                    "",
                )
            ),
            "a_db_quote_won": before.get(
                "dongbaek_quote_cashback_won",
                0,
            ),
            "b_db_quote_won": after.get(
                "dongbaek_quote_cashback_won",
                0,
            ),
            "selection_transition": transition,
        })

    tx_comparison.sort(
        key=lambda r: (
            r["user_id"],
            r["requested_at"],
            r["transaction_id"],
        )
    )

    user_comparison = []

    for user_id in sorted(a_users):
        a = a_users[user_id]
        b = b_users[user_id]

        a_benefit = int(
            a["estimated_benefit_won"]
        )
        b_benefit = int(
            b["estimated_benefit_won"]
        )

        delta = b_benefit - a_benefit

        if (
            a["wallet_status"]
            != b["wallet_status"]
        ):
            raise ValueError(
                f"WALLET_STATUS_CHANGED:{user_id}"
            )

        if (
            a["source_transaction_count"]
            != b["source_transaction_count"]
        ):
            raise ValueError(
                f"USER_TRANSACTION_COUNT_CHANGED:"
                f"{user_id}"
            )

        if (
            a["source_transaction_amount_won"]
            != b["source_transaction_amount_won"]
        ):
            raise ValueError(
                f"USER_TRANSACTION_AMOUNT_CHANGED:"
                f"{user_id}"
            )

        # Minimum replenishment needed to execute
        # B's chosen Dongbaek spending schedule,
        # under the fungible-balance assumption.
        db_spend_b = sum(
            int(r["amount_won"])
            for r in tx_b
            if (
                r["user_id"] == user_id
                and r["selected_card"]
                == sim.DONGBAEK_ID
            )
        )

        opening_balance = int(
            a["dongbaek_opening_balance_won"]
        )

        min_funding_for_b = (
            max(
                0,
                db_spend_b - opening_balance,
            )
            if a["wallet_status"] == "ACTIVE"
            else 0
        )

        user_comparison.append({
            "user_id": user_id,
            "wallet_status": a["wallet_status"],
            "card_count": a["card_count"],
            "usage_style": a["usage_style"],
            "performance_state": a[
                "performance_state"
            ],
            "transaction_count": a[
                "source_transaction_count"
            ],
            "transaction_amount_won": a[
                "source_transaction_amount_won"
            ],
            "a_benefit_won": a_benefit,
            "b_benefit_won": b_benefit,
            "net_gain_won": delta,
            "positive_tx_gains_won": (
                gained[user_id]
            ),
            "negative_tx_changes_won": (
                lost[user_id]
            ),
            "a_dongbaek_count": a["dongbaek"],
            "b_dongbaek_count": b["dongbaek"],
            "a_dongbaek_cashback_won": (
                a["dongbaek_cashback_won"]
            ),
            "b_dongbaek_cashback_won": (
                b["dongbaek_cashback_won"]
            ),
            "a_opening_balance_won": (
                opening_balance
            ),
            "b_selected_db_spend_won": (
                db_spend_b
            ),
            "min_funding_for_b_won": (
                min_funding_for_b
            ),
        })

    summary_a = summarize(
        tx_a, users_a
    )
    summary_b = summarize(
        tx_b, users_b
    )

    net_gain = (
        summary_b["estimated_total_benefit_won"]
        - summary_a["estimated_total_benefit_won"]
    )

    sum_user_gains = sum(
        r["net_gain_won"]
        for r in user_comparison
    )

    sum_tx_gains = sum(
        r["delta_benefit_won"]
        for r in tx_comparison
    )

    if not (
        net_gain
        == sum_user_gains
        == sum_tx_gains
    ):
        raise ValueError(
            "GAIN_RECONCILIATION_FAILED"
        )

    if (
        summary_a["transaction_count"]
        != summary_b["transaction_count"]
        or summary_a["transaction_amount_won"]
        != summary_b["transaction_amount_won"]
    ):
        raise ValueError(
            "SOURCE_TOTALS_CHANGED"
        )

    if len(user_ids) == 240:
        if (
            summary_a["transaction_count"] != 7540
            or summary_a["transaction_amount_won"]
            != 240445000
        ):
            raise ValueError(
                "ORIGINAL_V3_TOTALS_CHANGED"
            )

        # Regression check against the completed
        # baseline, with unchanged code and DB.
        if (
            summary_a["estimated_total_benefit_won"]
            != 2691539
        ):
            print(
                "WARNING: Baseline differs from "
                "previously recorded 2,691,539 KRW."
            )

    changed_users = [
        r for r in user_comparison
        if r["net_gain_won"] != 0
    ]

    summary = {
        "study": (
            "DONGBAEK_BALANCE_CONSTRAINT_"
            "COUNTERFACTUAL"
        ),
        "scenario_a": summary_a,
        "scenario_b": summary_b,
        "net_additional_benefit_won": (
            net_gain
        ),
        "users_with_changed_benefit": len(
            changed_users
        ),
        "users_with_positive_net_gain": sum(
            r["net_gain_won"] > 0
            for r in user_comparison
        ),
        "users_with_negative_net_gain": sum(
            r["net_gain_won"] < 0
            for r in user_comparison
        ),
        "transactions_with_positive_gain": sum(
            r["delta_benefit_won"] > 0
            for r in tx_comparison
        ),
        "transactions_with_negative_change": sum(
            r["delta_benefit_won"] < 0
            for r in tx_comparison
        ),
        "total_minimum_funding_for_b_won": sum(
            r["min_funding_for_b_won"]
            for r in user_comparison
        ),
        "important_assumptions": [
            "Both scenarios independently replay "
            "the same original synthetic transactions.",
            "Only existing active-wallet owners "
            "receive sufficient virtual funding.",
            "Users without wallets are not "
            "automatically enrolled.",
            "The B scenario removes the balance "
            "constraint; it is not a legal top-up "
            "schedule or a real payment authorization.",
            "Both scenarios retain original policy "
            "rates, monthly cashback limits and "
            "BNK rules.",
            "One BNK point is valued at one KRW "
            "for simulation.",
            "Opportunity loss is a counterfactual "
            "estimate, not a realized financial loss.",
        ],
    }

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(
        OUTPUT / "transactions_comparison.csv",
        tx_comparison,
    )

    write_csv(
        OUTPUT / "users_comparison.csv",
        user_comparison,
    )

    (
        OUTPUT / "summary.json"
    ).write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== OPPORTUNITY LOSS RESULT ===")
    print(
        json.dumps(
            {
                "A_total_benefit_won":
                    summary_a[
                        "estimated_total_benefit_won"
                    ],
                "B_total_benefit_won":
                    summary_b[
                        "estimated_total_benefit_won"
                    ],
                "net_additional_benefit_won":
                    net_gain,
                "users_with_positive_net_gain":
                    summary[
                        "users_with_positive_net_gain"
                    ],
                "users_with_negative_net_gain":
                    summary[
                        "users_with_negative_net_gain"
                    ],
                "transactions_with_positive_gain":
                    summary[
                        "transactions_with_positive_gain"
                    ],
                "minimum_funding_for_B_won":
                    summary[
                        "total_minimum_funding_for_b_won"
                    ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\nSaved:", OUTPUT)


if __name__ == "__main__":
    main()
