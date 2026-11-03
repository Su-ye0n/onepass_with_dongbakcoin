
"""Read-only Dongbaek policy and wallet repository.

Reads existing NeonDB tables:
    db_policy, db_policy_rate, db_wallet

No ZIP reads, DB writes, or automatic top-ups.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN

from onepass.db_connection import connect_readonly


@dataclass(frozen=True)
class DongbaekPolicy:
    policy_id: str
    valid_from: date
    valid_to: date
    monthly_base_cap_won: int
    rates: dict[str, Decimal]
    source_status: str
    rounding_mode: str

    def rate_for(self, sales_band: str) -> Decimal:
        if sales_band not in self.rates:
            raise ValueError(
                f"UNKNOWN_SALES_BAND:{sales_band}"
            )
        return self.rates[sales_band]

    def applies(self, as_of: str) -> bool:
        d = date.fromisoformat(as_of[:10])
        return self.valid_from <= d < self.valid_to


@dataclass(frozen=True)
class Wallet:
    user_id: str
    wallet_id: str
    charge_won: int
    cashback_won: int
    policy_support_won: int

    @property
    def total_won(self) -> int:
        return (
            self.charge_won
            + self.cashback_won
            + self.policy_support_won
        )


class DongbaekDBRepository:
    def __init__(self):
        self.policies: list[DongbaekPolicy] = []
        self.wallets: dict[str, Wallet] = {}

        # 활성 여부와 관계없이 DB의 지갑 상태 기록
        self.wallet_statuses: dict[str, str] = {}
        self.wallet_row_counts: dict[str, int] = {}

        # 1. NeonDB 데이터 조회 (읽기 전용)
        with connect_readonly() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        policy_id,
                        valid_from,
                        valid_to,
                        monthly_cashback_base_cap_won,
                        source_status,
                        rounding_mode
                    FROM public.db_policy
                """)
                policy_rows = [
                    dict(r) for r in cur.fetchall()
                ]

                cur.execute("""
                    SELECT
                        policy_id,
                        sales_band,
                        cashback_rate
                    FROM public.db_policy_rate
                """)
                rate_rows = [
                    dict(r) for r in cur.fetchall()
                ]

                cur.execute("""
                    SELECT
                        wallet_id,
                        user_id,
                        charge_won,
                        cashback_won,
                        policy_support_won,
                        wallet_status
                    FROM public.db_wallet
                """)
                wallet_rows = [
                    dict(r) for r in cur.fetchall()
                ]

        # 2. 정책별 캐시백률 구성
        rates_by_policy = {}

        for row in rate_rows:
            policy_id = row["policy_id"]
            band = row["sales_band"]

            rates = rates_by_policy.setdefault(
                policy_id, {}
            )

            if band in rates:
                raise ValueError(
                    f"DUPLICATE_DB_POLICY_RATE:"
                    f"{policy_id}:{band}"
                )

            rate = Decimal(str(row["cashback_rate"]))

            if not Decimal("0") <= rate <= Decimal("1"):
                raise ValueError(
                    f"INVALID_DB_RATE:{policy_id}:{band}"
                )

            rates[band] = rate

        # 3. 동백전 정책 객체 생성
        for row in policy_rows:
            policy_id = row["policy_id"]

            rates = rates_by_policy.get(
                policy_id, {}
            )

            if not rates:
                raise ValueError(
                    f"DB_POLICY_HAS_NO_RATES:{policy_id}"
                )

            cap = row[
                "monthly_cashback_base_cap_won"
            ]

            if cap is None or int(cap) < 0:
                raise ValueError(
                    f"INVALID_DB_MONTHLY_CAP:{policy_id}"
                )

            self.policies.append(
                DongbaekPolicy(
                    policy_id=policy_id,
                    valid_from=row["valid_from"],
                    valid_to=row["valid_to"],
                    monthly_base_cap_won=int(cap),
                    rates=rates,
                    source_status=row["source_status"],
                    rounding_mode=row["rounding_mode"],
                )
            )

        # 4. 지갑 상태 기록 및 활성 지갑 로딩
        for row in wallet_rows:
            user_id = row["user_id"]
            status = row["wallet_status"]

            # 활성/비활성 관계없이 모든 지갑 행 집계
            self.wallet_row_counts[user_id] = (
                self.wallet_row_counts.get(user_id, 0) + 1
            )

            if user_id in self.wallet_statuses:
                previous = self.wallet_statuses[user_id]

                if previous != status:
                    self.wallet_statuses[user_id] = (
                        "MULTIPLE_STATUSES"
                    )
            else:
                self.wallet_statuses[user_id] = status

            # 활성 지갑만 결제 가능 대상으로 로딩
            if status != "ACTIVE":
                continue

            if user_id in self.wallets:
                raise ValueError(
                    f"MULTIPLE_ACTIVE_WALLETS:{user_id}"
                )

            amounts = [
                int(row[k] or 0)
                for k in (
                    "charge_won",
                    "cashback_won",
                    "policy_support_won",
                )
            ]

            if any(value < 0 for value in amounts):
                raise ValueError(
                    f"NEGATIVE_WALLET_BALANCE:{user_id}"
                )

            self.wallets[user_id] = Wallet(
                user_id=user_id,
                wallet_id=row["wallet_id"],
                charge_won=amounts[0],
                cashback_won=amounts[1],
                policy_support_won=amounts[2],
            )

    def policy_for(self, as_of: str) -> DongbaekPolicy:
        """거래일에 적용되는 동백전 정책 조회."""
        matches = [
            p for p in self.policies
            if p.applies(as_of)
        ]

        if len(matches) != 1:
            raise ValueError(
                f"DB_POLICY_NOT_UNIQUE_FOR_DATE:"
                f"{as_of}:matches={len(matches)}"
            )

        return matches[0]

    def wallet_for(self, user_id: str) -> Wallet | None:
        """활성 지갑만 반환. 없으면 None."""
        if self.wallet_row_counts.get(user_id, 0) > 1:
            return None

        return self.wallets.get(user_id)

    def wallet_state_for(self, user_id: str) -> str:
        """지갑의 존재 여부와 실제 상태를 구분한다.

        Returns:
            ACTIVE: 정상 활성 지갑
            MISSING_ROW: 지갑 데이터 자체가 없음
            MULTIPLE_WALLETS: 지갑 행이 둘 이상
            UNKNOWN_STATUS: 지갑 상태가 NULL
            INACTIVE:<status>: 비활성 지갑
        """
        count = self.wallet_row_counts.get(user_id, 0)

        if count == 0:
            return "MISSING_ROW"

        if count > 1:
            return "MULTIPLE_WALLETS"

        status = self.wallet_statuses[user_id]

        if status is None:
            return "UNKNOWN_STATUS"

        if status == "ACTIVE":
            if user_id not in self.wallets:
                raise ValueError(
                    f"ACTIVE_WALLET_NOT_LOADED:{user_id}"
                )
            return "ACTIVE"

        return f"INACTIVE:{status}"


def calculate_db_cashback(
    *,
    policy: DongbaekPolicy,
    sales_band: str,
    amount_won: int,
    monthly_base_used_won: int,
):
    """동백전 캐시백 계산.

    - 가맹점 매출 구간별 캐시백률 적용
    - 월간 캐시백 인정 결제금액 한도 적용
    - 0% 캐시백 거래는 인정 한도 소진 없음
    - FLOOR 방식으로 원 단위 절사
    """
    if amount_won <= 0:
        raise ValueError("INVALID_TRANSACTION_AMOUNT")

    if monthly_base_used_won < 0:
        raise ValueError("NEGATIVE_MONTHLY_BASE_USED")

    if policy.rounding_mode != "FLOOR":
        raise ValueError(
            f"UNSUPPORTED_DB_ROUNDING:"
            f"{policy.rounding_mode}"
        )

    rate = policy.rate_for(sales_band)

    remaining_base = max(
        0,
        policy.monthly_base_cap_won
        - monthly_base_used_won,
    )

    # 0% 캐시백 거래는 월간 인정 한도 차감 없음
    eligible_base = (
        min(amount_won, remaining_base)
        if rate > 0
        else 0
    )

    cashback = int(
        (
            Decimal(eligible_base) * rate
        ).to_integral_value(
            rounding=ROUND_DOWN
        )
    )

    return {
        "cashback_rate": rate,
        "eligible_base_won": eligible_base,
        "cashback_won": cashback,
        "remaining_base_won": remaining_base,
    }
