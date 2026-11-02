import unittest

from onepass.auto_topup import (
    AutoTopupPolicy,
    AutoTopupState,
    quote_auto_topup,
)


def policy(**overrides):
    values = dict(
        enabled=True,
        consent=True,
        min_topup_won=10000,
        per_topup_cap_won=100000,
        monthly_topup_cap_won=300000,
        wallet_holding_cap_won=500000,
    )
    values.update(overrides)
    return AutoTopupPolicy(**values)


def state(
    wallet=5000,
    funding=100000,
    monthly=0,
):
    return AutoTopupState(
        wallet_balance_won=wallet,
        funding_balance_won=funding,
        monthly_topped_up_won=monthly,
        topup_count=0,
    )


def quote(
    *,
    amount=30000,
    wallet=5000,
    funding=100000,
    monthly=0,
    wallet_active=True,
    **policy_changes,
):
    return quote_auto_topup(
        state=state(wallet, funding, monthly),
        policy=policy(**policy_changes),
        amount_won=amount,
        wallet_active=wallet_active,
    )


class AutoTopupEdgeCases(unittest.TestCase):

    def test_01_insufficient_funding(self):
        result = quote(funding=20000)

        self.assertEqual(
            result.status,
            "INSUFFICIENT_FUNDING_BALANCE",
        )
        self.assertEqual(result.topup_amount_won, 0)

    def test_02_per_topup_cap(self):
        result = quote(
            amount=120000,
            per_topup_cap_won=100000,
        )

        self.assertEqual(
            result.status,
            "PER_TOPUP_CAP_EXCEEDED",
        )

    def test_03_monthly_cap(self):
        result = quote(
            monthly=290000,
        )

        self.assertEqual(
            result.status,
            "MONTHLY_TOPUP_CAP_EXCEEDED",
        )

    def test_04_wallet_holding_cap(self):
        result = quote(
            wallet=490000,
            amount=510000,
        )

        self.assertEqual(
            result.status,
            "WALLET_HOLDING_CAP_EXCEEDED",
        )

    def test_05_existing_balance_over_cap(self):
        result = quote(
            wallet=550000,
            amount=10000,
        )

        self.assertEqual(result.status, "NOT_REQUIRED")
        self.assertEqual(result.topup_amount_won, 0)

    def test_06_no_consent(self):
        result = quote(consent=False)

        self.assertEqual(
            result.status,
            "CONSENT_REQUIRED",
        )

    def test_07_disabled(self):
        result = quote(enabled=False)

        self.assertEqual(
            result.status,
            "AUTO_TOPUP_DISABLED",
        )

    def test_08_inactive_wallet(self):
        result = quote(wallet_active=False)

        self.assertEqual(
            result.status,
            "WALLET_NOT_ACTIVE",
        )

    def test_09_valid_topup(self):
        result = quote()

        self.assertEqual(
            result.status,
            "TOPUP_AVAILABLE",
        )
        self.assertEqual(
            result.topup_amount_won,
            25000,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
