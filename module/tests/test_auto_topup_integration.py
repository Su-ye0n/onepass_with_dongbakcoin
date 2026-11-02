
"""Integration tests for simulate_original_v2 auto top-up.

Uses real simulation, selection, cashback and top-up logic.
Mocks only external data/repository dependencies.
No NeonDB connection or database writes.
"""

from __future__ import annotations

import sys
import unittest

from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import simulate_original_v2 as sim

from onepass.auto_topup import AutoTopupPolicy

def make_policy(*, consent=True, enabled=True):
    return AutoTopupPolicy(
        enabled=enabled,
        consent=consent,
        min_topup_won=10000,
        per_topup_cap_won=100000,
        monthly_topup_cap_won=300000,
        wallet_holding_cap_won=500000,
    )

class FakePolicy:
    policy_id = "POLICY_TEST"
    source_status = "TEST_ONLY"
    monthly_base_cap_won = 300000

    rates = {
        "LE_10B": Decimal("0.10"),
    }

    rounding_mode = "FLOOR"

    def rate_for(self, sales_band):
        return self.rates.get(sales_band)

class FakeDBRepository:
    def __init__(self):
        self.wallet = SimpleNamespace(
            user_id="U_TEST",
            wallet_id="W_TEST",
            charge_won=5000,
            cashback_won=0,
            policy_support_won=0,
            total_won=5000,
        )

        self.policy = FakePolicy()

    def wallet_for(self, user_id):
        return self.wallet

    def wallet_state_for(self, user_id):
        return "ACTIVE"

    def policy_for(self, as_of):
        return self.policy


class FakeCacheRepository:
    reward_units = {}

    def cache_info(self):
        return "TEST_CACHE"


def make_transaction(number, amount):
    return {
        "transaction_id": f"T{number}",
        "user_id": "U_TEST",
        "requested_at": (
            f"2026-06-{number:02d}T12:00:00"
        ),
        "merchant_id": "M_TEST",
        "amount_won": amount,
        "lane": "OFFLINE",
        "provider": None,
    }


def run_case(
    *,
    amounts,
    bnk_benefit,
    consent=True,
    funding=100000,
    use_topup=True,
    topup_enabled=True,
):
    
    profile = {
        "user_id": "U_TEST",
        "simulated_card_count": 2,
        "dongbaek_usage_level": "LT_100K",
        "usage_style": "PURPOSE_BASED",
        "performance_state": "NORMAL",
        "original_month_spend_won": 100000,
    }

    slots = [
        {
            "user_id": "U_TEST",
            "slot_no": 1,
            "product_id": "PRD_DB_SYN",
            "performance_state": "NORMAL",
        },
        {
            "user_id": "U_TEST",
            "slot_no": 2,
            "product_id": "BNK_TEST",
            "performance_state": "NORMAL",
        },
    ]

    merchants = {
        "M_TEST": {
            "merchant_id": "M_TEST",
            "industry_code": "TEST",
            "sales_band": "LE_10B",
            "dongbaek_status": "REGISTERED",
        }
    }

    transactions = [
        make_transaction(i, amount)
        for i, amount in enumerate(amounts, start=1)
    ]

    grouped = {"U_TEST": transactions}

    fake_card = {
        "user_card_id": "UC_TEST",
        "product_id": "BNK_TEST",
    }

    def fake_bnk_quote(**kwargs):
        return {
            "status": "SIMULATED_COMPARABLE",
            "product_id": "BNK_TEST",
            "user_card_id": "UC_TEST",
            "best_rule_id": "RULE_TEST",
            "estimated_value_won": bnk_benefit,
        }

    def fake_bnk_commit(*args, **kwargs):
        return {
            "estimated_value_won": bnk_benefit,
            "benefit_amount": bnk_benefit,
            "reward_unit": "CASH",
        }

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                sim,
                "validate_population",
                return_value={"U_TEST": slots},
            )
        )

        stack.enter_context(
            patch.object(
                sim,
                "split_user_cards",
                return_value=([fake_card], True),
            )
        )

        stack.enter_context(
            patch.object(
                sim,
                "V2MonthlyRepository",
                return_value=object(),
            )
        )

        stack.enter_context(
            patch.object(
                sim,
                "make_fast_repositories",
                return_value=(
                    FakeCacheRepository(),
                    FakeCacheRepository(),
                ),
            )
        )

        stack.enter_context(
            patch.object(
                sim,
                "payment_context",
                return_value={},
            )
        )

        stack.enter_context(
            patch.object(
                sim,
                "quote_mvp_card",
                side_effect=fake_bnk_quote,
            )
        )

        stack.enter_context(
            patch.object(
                sim,
                "commit_mvp_bnk_usage",
                side_effect=fake_bnk_commit,
            )
        )


        return sim.simulate(
            profiles=[profile],
            slots=slots,
            merchants=merchants,
            grouped_transactions=grouped,
            db_repository=FakeDBRepository(),
            point_rate=Decimal("0"),
            auto_topup_policy=(
                make_policy(
                    consent=consent,
                    enabled=topup_enabled,
                )
                if use_topup
                else None
            ),
            auto_topup_funding_by_user=(
                {"U_TEST": funding}
                if use_topup
                else None
            ),
        )



class AutoTopupIntegrationTests(unittest.TestCase):

    def test_01_dongbaek_topup_and_payment(self):
        txs, users = run_case(
            amounts=[30000],
            bnk_benefit=100,
        )

        tx = txs[0]
        user = users[0]

        self.assertEqual(
            tx["selected_card"], "PRD_DB_SYN"
        )
        self.assertEqual(
            tx["auto_topup_committed_won"], 25000
        )
        self.assertEqual(
            tx["dongbaek_balance_after"], 0
        )
        self.assertEqual(
            tx["estimated_benefit_won"], 3000
        )
        self.assertEqual(
            user["auto_topup_event_count"], 1
        )
        self.assertEqual(
            user["auto_topup_funding_after_won"], 75000
        )

    def test_02_bnk_selected_no_topup(self):
        txs, users = run_case(
            amounts=[30000],
            bnk_benefit=5000,
        )

        tx = txs[0]
        user = users[0]

        self.assertEqual(
            tx["selected_card"], "BNK_TEST"
        )
        self.assertEqual(
            tx["auto_topup_quote_won"], 25000
        )
        self.assertEqual(
            tx["auto_topup_committed_won"], 0
        )
        self.assertEqual(
            tx["dongbaek_balance_after"], 5000
        )
        self.assertEqual(
            user["auto_topup_funding_after_won"], 100000
        )
        self.assertEqual(
            user["auto_topup_event_count"], 0
        )

    def test_03_no_consent_no_topup(self):
        txs, users = run_case(
            amounts=[30000],
            bnk_benefit=100,
            consent=False,
        )

        tx = txs[0]

        self.assertEqual(
            tx["auto_topup_status"], "CONSENT_REQUIRED"
        )
        self.assertEqual(
            tx["auto_topup_committed_won"], 0
        )
        self.assertEqual(
            tx["selected_card"], "BNK_TEST"
        )
        self.assertEqual(
            users[0]["auto_topup_event_count"], 0
        )

    def test_04_sequential_transactions(self):
        txs, users = run_case(
            amounts=[30000, 10000],
            bnk_benefit=100,
        )

        self.assertEqual(len(txs), 2)

        self.assertEqual(
            [t["selected_card"] for t in txs],
            ["PRD_DB_SYN", "PRD_DB_SYN"],
        )

        self.assertEqual(
            [
                t["auto_topup_committed_won"]
                for t in txs
            ],
            [25000, 10000],
        )

        self.assertEqual(
            users[0]["auto_topup_total_won"], 35000
        )
        self.assertEqual(
            users[0]["auto_topup_event_count"], 2
        )
        self.assertEqual(
            users[0]["auto_topup_funding_after_won"], 65000
        )
        self.assertEqual(
            users[0]["dongbaek_closing_balance_won"], 0
        )
    
    def test_05_s01_equals_s02_without_topup(self):
        """Disabled top-up must reproduce the baseline."""

        baseline_txs, baseline_users = run_case(
            amounts=[30000, 10000, 20000],
            bnk_benefit=100,
            use_topup=False,
        )

        disabled_txs, disabled_users = run_case(
            amounts=[30000, 10000, 20000],
            bnk_benefit=100,
            use_topup=True,
            topup_enabled=False,
            consent=True,
        )

        tx_fields = [
            "selected_card",
            "selected_user_card_id",
            "selected_rule_id",
            "selection_status",
            "estimated_benefit_won",
            "benefit_amount",
            "benefit_unit",
            "dongbaek_balance_after",
            "dongbaek_monthly_base_used_after",
            "dongbaek_exclusion_reason",
        ]

        self.assertEqual(
            len(baseline_txs),
            len(disabled_txs),
        )

        for before, after in zip(
            baseline_txs,
            disabled_txs,
        ):
            self.assertEqual(
                before["transaction_id"],
                after["transaction_id"],
            )

            for field in tx_fields:
                self.assertEqual(
                    before[field],
                    after[field],
                    msg=(
                        f"BASELINE_MISMATCH:"
                        f"{before['transaction_id']}:{field}"
                    ),
                )

            self.assertEqual(
                after["auto_topup_committed_won"],
                0,
            )

        user_fields = [
            "assigned",
            "unresolved",
            "dongbaek",
            "bnk",
            "estimated_benefit_won",
            "dongbaek_cashback_won",
            "bnk_cash_won",
            "bnk_points",
            "dongbaek_closing_balance_won",
            "dongbaek_monthly_base_used_won",
        ]

        for field in user_fields:
            self.assertEqual(
                baseline_users[0][field],
                disabled_users[0][field],
                msg=f"USER_BASELINE_MISMATCH:{field}",
            )

        self.assertEqual(
            disabled_users[0]["auto_topup_total_won"],
            0,
        )

        self.assertEqual(
            disabled_users[0]["auto_topup_event_count"],
            0,
        )

    def test_06_topup_increases_payment_opportunity(self):
        """Top-up changes only feasible payment outcomes."""

        baseline_txs, baseline_users = run_case(
            amounts=[30000],
            bnk_benefit=100,
            use_topup=False,
        )

        topup_txs, topup_users = run_case(
            amounts=[30000],
            bnk_benefit=100,
            use_topup=True,
            topup_enabled=True,
            consent=True,
            funding=100000,
        )

        self.assertEqual(
            baseline_txs[0]["selected_card"],
            "BNK_TEST",
        )

        self.assertEqual(
            topup_txs[0]["selected_card"],
            "PRD_DB_SYN",
        )

        self.assertEqual(
            baseline_txs[0]["estimated_benefit_won"],
            100,
        )

        self.assertEqual(
            topup_txs[0]["estimated_benefit_won"],
            3000,
        )

        self.assertEqual(
            topup_txs[0]["auto_topup_committed_won"],
            25000,
        )

        self.assertEqual(
            topup_txs[0]["dongbaek_balance_after"],
            0,
        )

        self.assertEqual(
            topup_users[0]["auto_topup_total_won"],
            25000,
        )

        self.assertEqual(
            topup_users[0]["auto_topup_event_count"],
            1,
        )

        self.assertEqual(
            baseline_users[0]["auto_topup_total_won"],
            0,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
