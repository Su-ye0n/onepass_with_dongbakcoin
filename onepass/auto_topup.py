
"""Synthetic Dongbaek automatic top-up engine.

Pure in-memory simulation only.
No actual payment, bank transfer, or database write.

Quote: check feasibility without changing state.
Commit: apply funding and payment together in memory.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AutoTopupPolicy:
    enabled: bool
    consent: bool
    min_topup_won: int
    per_topup_cap_won: int
    monthly_topup_cap_won: int
    wallet_holding_cap_won: int


@dataclass
class AutoTopupState:
    wallet_balance_won: int
    funding_balance_won: int
    monthly_topped_up_won: int = 0
    topup_count: int = 0


@dataclass(frozen=True)
class AutoTopupQuote:
    status: str
    payment_amount_won: int
    topup_amount_won: int
    wallet_before_won: int
    funding_before_won: int
    monthly_before_won: int

    @property
    def payment_possible(self) -> bool:
        return self.status in {
            "NOT_REQUIRED",
            "TOPUP_AVAILABLE",
        }


def _validate_policy(policy: AutoTopupPolicy) -> None:
    values = {
        "min_topup_won": policy.min_topup_won,
        "per_topup_cap_won": policy.per_topup_cap_won,
        "monthly_topup_cap_won": (
            policy.monthly_topup_cap_won
        ),
        "wallet_holding_cap_won": (
            policy.wallet_holding_cap_won
        ),
    }

    for name, value in values.items():
        if type(value) is not int or value < 0:
            raise ValueError(
                f"INVALID_TOPUP_POLICY:{name}"
            )

    if (
        policy.min_topup_won
        > policy.per_topup_cap_won
    ):
        raise ValueError(
            "MIN_TOPUP_EXCEEDS_PER_TOPUP_CAP"
        )


def _validate_state(state: AutoTopupState) -> None:
    values = {
        "wallet_balance_won": (
            state.wallet_balance_won
        ),
        "funding_balance_won": (
            state.funding_balance_won
        ),
        "monthly_topped_up_won": (
            state.monthly_topped_up_won
        ),
        "topup_count": state.topup_count,
    }

    for name, value in values.items():
        if type(value) is not int or value < 0:
            raise ValueError(
                f"INVALID_TOPUP_STATE:{name}"
            )


def quote_auto_topup(
    *,
    state: AutoTopupState,
    policy: AutoTopupPolicy,
    amount_won: int,
    wallet_active: bool,
) -> AutoTopupQuote:
    """Check top-up feasibility without changing state."""

    _validate_policy(policy)
    _validate_state(state)

    if type(amount_won) is not int or amount_won <= 0:
        raise ValueError("INVALID_PAYMENT_AMOUNT")

    def result(status: str, topup: int = 0):
        return AutoTopupQuote(
            status=status,
            payment_amount_won=amount_won,
            topup_amount_won=topup,
            wallet_before_won=state.wallet_balance_won,
            funding_before_won=state.funding_balance_won,
            monthly_before_won=(
                state.monthly_topped_up_won
            ),
        )

    if not wallet_active:
        return result("WALLET_NOT_ACTIVE")

    # 기존 잔액으로 결제 가능하면 충전 한도와 무관
    if state.wallet_balance_won >= amount_won:
        return result("NOT_REQUIRED")

    # 추가 충전이 필요한 경우에만 보유 한도 검사
    if (
        state.wallet_balance_won
        > policy.wallet_holding_cap_won
    ):
        return result("WALLET_HOLDING_CAP_EXCEEDED")

    if not policy.enabled:
        return result("AUTO_TOPUP_DISABLED")

    if not policy.consent:
        return result("CONSENT_REQUIRED")

    shortage = (
        amount_won - state.wallet_balance_won
    )

    topup = max(
        shortage,
        policy.min_topup_won,
    )

    if topup > policy.per_topup_cap_won:
        return result("PER_TOPUP_CAP_EXCEEDED")

    if (
        state.monthly_topped_up_won + topup
        > policy.monthly_topup_cap_won
    ):
        return result("MONTHLY_TOPUP_CAP_EXCEEDED")

    if (
        state.wallet_balance_won + topup
        > policy.wallet_holding_cap_won
    ):
        return result("WALLET_HOLDING_CAP_EXCEEDED")

    if topup > state.funding_balance_won:
        return result("INSUFFICIENT_FUNDING_BALANCE")

    return result("TOPUP_AVAILABLE", topup)


def commit_topup_payment(
    *,
    state: AutoTopupState,
    quote: AutoTopupQuote,
    policy: AutoTopupPolicy,
    wallet_active: bool,
) -> dict:
    """Atomically simulate top-up and payment in memory.

    Requires the current state to match the quote.
    Does not perform real authorization.
    """

    _validate_policy(policy)
    _validate_state(state)

    if not quote.payment_possible:
        raise ValueError(
            f"TOPUP_NOT_AVAILABLE:{quote.status}"
        )

    if (
        state.wallet_balance_won
        != quote.wallet_before_won
        or state.funding_balance_won
        != quote.funding_before_won
        or state.monthly_topped_up_won
        != quote.monthly_before_won
    ):
        raise ValueError("STALE_TOPUP_QUOTE")

    # Recheck constraints before changing balances.
    fresh = quote_auto_topup(
        state=state,
        policy=policy,
        amount_won=quote.payment_amount_won,
        wallet_active=wallet_active,
    )

    if (
        fresh.status != quote.status
        or fresh.topup_amount_won
        != quote.topup_amount_won
    ):
        raise ValueError("TOPUP_QUOTE_CHANGED")

    topup = quote.topup_amount_won
    payment = quote.payment_amount_won

    next_wallet = (
        state.wallet_balance_won
        + topup
        - payment
    )
    next_funding = (
        state.funding_balance_won - topup
    )
    next_monthly = (
        state.monthly_topped_up_won + topup
    )

    if next_wallet < 0 or next_funding < 0:
        raise ValueError(
            "NEGATIVE_BALANCE_AFTER_COMMIT"
        )

    # Apply all changes after validation.
    state.wallet_balance_won = next_wallet
    state.funding_balance_won = next_funding
    state.monthly_topped_up_won = next_monthly

    if topup > 0:
        state.topup_count += 1

    return {
        "status": "SIMULATED_COMMITTED",
        "payment_won": payment,
        "topup_won": topup,
        "wallet_after_won": next_wallet,
        "funding_after_won": next_funding,
        "monthly_topped_up_won": next_monthly,
        "topup_count": state.topup_count,
        "real_authorization": False,
    }
