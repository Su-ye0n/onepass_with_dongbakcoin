
"""
Dongbaek OnePass - V2 Synthetic Population Simulator

Reads:
    public.sim_user_profile_v2
    public.sim_user_card_slot_v2
    public.merchant
    Existing BNK benefit rules

Outputs:
    v2_simulation/transactions.csv
    v2_simulation/users.csv
    v2_simulation/segments.csv
    v2_simulation/summary.json

DB READ ONLY.
NO AUTO TOP-UP.
NO REAL PAYMENT AUTHORIZATION.
"""

from __future__ import annotations

import argparse
import csv
import json

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

from onepass.db_connection import connect_readonly
from onepass.p1_rule_repository import P1RuleRepository
from onepass.p1_eligibility_repository import (
    P1EligibilityRepository,
)
from onepass.p1_product_ids import canonical_product_id
from onepass.p1_mvp_quote import quote_mvp_card
from onepass.p1_dongbaek_candidate import (
    DongbaekInputs,
    evaluate_dongbaek_candidate,
)

from demo_p1_one_transaction import payment_context
from demo_p1_mvp_batch import (
    select_mvp_candidate,
    commit_mvp_bnk_usage,
)


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "v2_simulation"

SCENARIO_ID = "ONEPASS_V2_20261029"
BASE_MONTH = "2026-05"
DONGBAEK_ID = "PRD_DB_SYN"

TEST_INDUSTRIES = [
    "CAFE_BAKERY",
    "RESTAURANT",
    "FUEL_AUTO",
    "ACADEMY",
]

TEST_PAYMENT_WON = 32000
SIM_START = date(2026, 6, 1)


# --------------------------------------------------
# 1. V2 전월 실적 어댑터
# --------------------------------------------------

class V2MonthlyRepository:
    """
    기존 card_month_close 대신 V2 슬롯 실적 사용.

    NORMAL:
        V2에 배분된 실적

    ZERO_WON:
        확인된 0원

    MISSING_ROW / NULL_VALUE:
        실적 미확정(None)

    기존 DB 실적을 대신 조회하지 않음.
    """

    def __init__(self, slots):
        self.by_card_id = {}

        for slot in slots:
            card_id = slot["synthetic_user_card_id"]
            status = slot["performance_state"]
            value = slot["sim_month_spend_won"]

            if status == "NORMAL":
                if value is None:
                    raise ValueError(
                        f"NORMAL_PERFORMANCE_IS_NULL:{card_id}"
                    )

                spend = int(value)

            elif status == "ZERO_WON":
                spend = 0

            elif status in (
                "MISSING_ROW",
                "NULL_VALUE",
            ):
                spend = None

            else:
                raise ValueError(
                    f"UNKNOWN_PERFORMANCE_STATE:{status}"
                )

            self.by_card_id[card_id] = {
                "status": status,
                "spend": spend,
            }

    def load(self, *, user_card_id, base_month):
        if base_month != BASE_MONTH:
            raise ValueError(
                "V2_BASE_MONTH_MISMATCH"
            )

        item = self.by_card_id.get(user_card_id)

        if item is None:
            raise ValueError(
                f"V2_CARD_SLOT_NOT_FOUND:{user_card_id}"
            )

        return SimpleNamespace(
            spend_total_won=item["spend"],
            rules=[],
        )


# --------------------------------------------------
# 2. NeonDB V2 데이터 조회
# --------------------------------------------------

def load_v2_data(limit=None):

    with connect_readonly() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT *
                FROM public.sim_user_profile_v2
                WHERE scenario_id = %s
                  AND base_month = %s
                ORDER BY user_id
                """,
                (SCENARIO_ID, BASE_MONTH),
            )

            profiles = [
                dict(row)
                for row in cur.fetchall()
            ]

            if limit is not None:
                profiles = profiles[:limit]

            if not profiles:
                raise ValueError("NO_V2_PROFILES")

            user_ids = [
                profile["user_id"]
                for profile in profiles
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
                dict(row)
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT
                    merchant_id,
                    merchant_name,
                    industry_code,
                    dongbaek_status,
                    sales_band,
                    source_status
                FROM public.merchant
                WHERE industry_code = ANY(%s)
                ORDER BY industry_code, merchant_id
                """,
                (TEST_INDUSTRIES,),
            )

            merchants = [
                dict(row)
                for row in cur.fetchall()
            ]

    for slot in slots:
        slot["synthetic_user_card_id"] = (
            f"V2::{slot['user_id']}::{slot['slot_no']}"
        )

    return profiles, slots, merchants


# --------------------------------------------------
# 3. 사용자와 카드 슬롯 검증
# --------------------------------------------------

def validate_population(profiles, slots):

    index = defaultdict(list)

    for slot in slots:
        index[slot["user_id"]].append(slot)

    for profile in profiles:
        user_id = profile["user_id"]
        user_slots = index[user_id]

        if len(user_slots) != profile["simulated_card_count"]:
            raise ValueError(
                f"V2_SLOT_COUNT_MISMATCH:{user_id}"
            )

        expected_state = profile["performance_state"]

        for slot in user_slots:
            if slot["performance_state"] != expected_state:
                raise ValueError(
                    f"V2_PERFORMANCE_STATE_MISMATCH:{user_id}"
                )

        product_ids = [
            s["product_id"]
            for s in user_slots
        ]

        if len(product_ids) != len(set(product_ids)):
            raise ValueError(
                f"DUPLICATE_V2_PRODUCT:{user_id}"
            )

    return index


# --------------------------------------------------
# 4. BNK 카드와 동백전 분리
# --------------------------------------------------

def split_user_cards(user_id, user_slots):
    """
    동백전은 BNK 혜택 엔진에 전달하지 않는다.

    Returns:
        cards: BNK 상품만
        has_dongbaek: 동백전 보유 여부
    """

    cards = []
    has_dongbaek = False

    for slot in user_slots:
        product_id = slot["product_id"]

        if product_id == DONGBAEK_ID:
            has_dongbaek = True
            continue

        try:
            normalized_id = canonical_product_id(
                product_id
            )

        except ValueError as exc:
            raise ValueError(
                "V2_UNSUPPORTED_CARD_PRODUCT:"
                f"user={user_id},"
                f"product={product_id}"
            ) from exc

        cards.append({
            "user_card_id":
                slot["synthetic_user_card_id"],
            "product_id": normalized_id,
        })

    return cards, has_dongbaek


# --------------------------------------------------
# 5. 업종별 테스트 가맹점 선택
# --------------------------------------------------

def build_test_merchants(merchants):

    by_industry = {}

    for merchant in merchants:
        industry = merchant["industry_code"]

        if industry not in by_industry:
            by_industry[industry] = merchant

    missing = [
        industry
        for industry in TEST_INDUSTRIES
        if industry not in by_industry
    ]

    if missing:
        raise ValueError(
            "TEST_MERCHANTS_MISSING:"
            + ",".join(missing)
        )

    return by_industry


# --------------------------------------------------
# 6. 가상 거래 생성
# --------------------------------------------------

def make_user_transactions(
    user_id,
    merchant_index,
    transaction_count,
    amount_won,
):

    transactions = []

    for i in range(transaction_count):

        industry = TEST_INDUSTRIES[
            i % len(TEST_INDUSTRIES)
        ]

        merchant = merchant_index[industry]

        tx_date = SIM_START + timedelta(days=i)

        transactions.append({
            "transaction_id":
                f"V2_{user_id}_{i + 1:03d}",
            "date": tx_date.isoformat(),
            "merchant_id": merchant["merchant_id"],
            "merchant_name": merchant["merchant_name"],
            "industry_code": industry,
            "amount_won": amount_won,
            "lane": "OFFLINE",
            "provider": None,
            "merchant": merchant,
        })

    return transactions


# --------------------------------------------------
# 7. CSV 출력
# --------------------------------------------------

def write_csv(path, rows):

    if not rows:
        return

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys()),
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


# --------------------------------------------------
# 8. 사용자별 연속 거래 시뮬레이션
# --------------------------------------------------

def run_population(
    profiles,
    slots,
    merchants,
    transaction_count,
    amount_won,
    db_balance,
    db_cashback_rate,
    db_cashback_remaining,
    point_rate,
):

    slots_by_user = validate_population(
        profiles,
        slots,
    )

    merchant_index = build_test_merchants(
        merchants
    )

    monthly_repo = V2MonthlyRepository(slots)
    rules_repo = P1RuleRepository()
    eligibility_repo = P1EligibilityRepository()

    tx_rows = []
    user_rows = []

    for number, profile in enumerate(profiles, 1):

        user_id = profile["user_id"]
        user_slots = slots_by_user[user_id]

        # 중요:
        # PRD_DB_SYN을 BNK 카드 목록에서 제외
        cards, has_dongbaek = split_user_cards(
            user_id,
            user_slots,
        )

        transactions = make_user_transactions(
            user_id,
            merchant_index,
            transaction_count,
            amount_won,
        )

        # 모든 사용자의 상태를 독립적으로 관리
        state = {
            "dongbaek_balance_won": (
                db_balance if has_dongbaek else 0
            ),
            "dongbaek_cashback_remaining_won": (
                db_cashback_remaining
                if has_dongbaek else 0
            ),
            "bnk_usage": {},
        }

        user_assigned = 0
        user_unresolved = 0
        user_db_count = 0
        user_bnk_count = 0

        user_benefit = 0
        user_cashback = 0
        user_cash_discount = 0
        user_points = 0

        for tx in transactions:

            payment = payment_context(
                tx["lane"],
                tx["provider"],
            )

            # ------------------------------
            # BNK 카드 예상 혜택
            # ------------------------------

            bnk_quotes = [
                quote_mvp_card(
                    card=card,
                    merchant_id=tx["merchant_id"],
                    amount=tx["amount_won"],
                    payment=payment,
                    as_of=tx["date"],
                    base_month=BASE_MONTH,
                    rules_repo=rules_repo,
                    eligibility_repo=eligibility_repo,
                    monthly_repo=monthly_repo,
                    usage_state=state["bnk_usage"],
                    point_krw_rate=point_rate,
                )
                for card in cards
            ]

            # ------------------------------
            # 동백전 예상 혜택
            # ------------------------------

            dongbaek_quote = evaluate_dongbaek_candidate(
                merchant=tx["merchant"],
                amount_won=tx["amount_won"],
                lane=tx["lane"],
                inputs=DongbaekInputs(
                    balance_won=state[
                        "dongbaek_balance_won"
                    ],
                    cashback_rate=db_cashback_rate,
                    cashback_remaining_won=state[
                        "dongbaek_cashback_remaining_won"
                    ],
                ),
            )

            # ------------------------------
            # 최대 예상 혜택 카드 선택
            # ------------------------------

            decision = select_mvp_candidate(
                dongbaek_quote,
                bnk_quotes,
            )

            selected = decision["selected_card"]

            selected_rule_id = decision[
                "selected_rule_id"
            ]

            benefit_won = 0
            benefit_amount = 0
            benefit_unit = None

            # ------------------------------
            # 선택 불가
            # ------------------------------

            if selected is None:
                user_unresolved += 1

            # ------------------------------
            # 동백전 선택
            # ------------------------------

            elif selected == DONGBAEK_ID:

                # 방어적 검증:
                # 미보유 사용자에게 동백전 선택 금지
                if not has_dongbaek:
                    raise ValueError(
                        f"DONGBAEK_NOT_OWNED:{user_id}"
                    )

                benefit_won = int(
                    dongbaek_quote["cash_benefit_won"]
                )

                benefit_amount = benefit_won
                benefit_unit = "CASH"

                state[
                    "dongbaek_balance_won"
                ] -= tx["amount_won"]

                state[
                    "dongbaek_cashback_remaining_won"
                ] -= benefit_won

                if state["dongbaek_balance_won"] < 0:
                    raise ValueError(
                        f"NEGATIVE_DONGBAEK_BALANCE:{user_id}"
                    )

                user_db_count += 1
                user_cashback += benefit_won
                user_assigned += 1

            # ------------------------------
            # BNK 카드 선택
            # ------------------------------

            else:

                matched = [
                    quote
                    for quote in bnk_quotes
                    if (
                        quote["product_id"] == selected
                        and quote["user_card_id"]
                        == decision["selected_user_card_id"]
                    )
                ]

                if len(matched) != 1:
                    raise ValueError(
                        f"V2_SELECTED_CARD_AMBIGUOUS:{user_id}"
                    )

                change = commit_mvp_bnk_usage(
                    state["bnk_usage"],
                    matched[0],
                    selected_rule_id,
                    rules_repo,
                    tx["date"],
                )

                benefit_won = int(
                    change["estimated_value_won"]
                )

                benefit_amount = int(
                    change["benefit_amount"]
                )

                benefit_unit = change["reward_unit"]

                user_bnk_count += 1
                user_assigned += 1

                if benefit_unit == "CASH":
                    user_cash_discount += benefit_amount

                elif benefit_unit == "POINT":
                    user_points += benefit_amount

            user_benefit += benefit_won

            # ------------------------------
            # 거래별 결과 저장
            # ------------------------------

            tx_rows.append({
                "scenario_id": SCENARIO_ID,
                "user_id": user_id,
                "transaction_id": tx["transaction_id"],
                "date": tx["date"],
                "merchant_id": tx["merchant_id"],
                "industry_code": tx["industry_code"],
                "amount_won": tx["amount_won"],
                "lane": tx["lane"],
                "card_count": profile[
                    "simulated_card_count"
                ],
                "bnk_card_count": len(cards),
                "has_dongbaek": has_dongbaek,
                "usage_style": profile["usage_style"],
                "performance_state": profile[
                    "performance_state"
                ],
                "selected_card": selected,
                "selected_user_card_id": decision[
                    "selected_user_card_id"
                ],
                "selected_rule_id": selected_rule_id,
                "selection_status": decision[
                    "selection_status"
                ],
                "estimated_benefit_won": benefit_won,
                "benefit_amount": benefit_amount,
                "benefit_unit": benefit_unit,
                "dongbaek_balance_after": state[
                    "dongbaek_balance_won"
                ],
                "bnk_candidate_count": len(bnk_quotes),
                "excluded_candidate_count": len(
                    decision["excluded_candidates"]
                ),
            })

        # ------------------------------
        # 사용자별 결과 저장
        # ------------------------------

        user_rows.append({
            "scenario_id": SCENARIO_ID,
            "user_id": user_id,
            "card_count": profile[
                "simulated_card_count"
            ],
            "bnk_card_count": len(cards),
            "has_dongbaek": has_dongbaek,
            "usage_style": profile["usage_style"],
            "performance_state": profile[
                "performance_state"
            ],
            "original_month_spend_won": profile[
                "original_month_spend_won"
            ],
            "transaction_count": len(transactions),
            "assigned_count": user_assigned,
            "unresolved_count": user_unresolved,
            "dongbaek_count": user_db_count,
            "bnk_count": user_bnk_count,
            "dongbaek_cashback_won": user_cashback,
            "bnk_cash_discount_won": user_cash_discount,
            "bnk_points": user_points,
            "estimated_total_value_won": user_benefit,
            "dongbaek_balance_after": state[
                "dongbaek_balance_won"
            ],
        })

        if number % 20 == 0:
            print(
                f"Simulated {number}/{len(profiles)} users",
                flush=True,
            )

    return tx_rows, user_rows


# --------------------------------------------------
# 9. 세그먼트별 통계
# --------------------------------------------------

def build_segments(users):

    segments = []

    dimensions = (
        "card_count",
        "usage_style",
        "performance_state",
        "has_dongbaek",
    )

    for dimension in dimensions:

        values = sorted({
            str(user[dimension])
            for user in users
        })

        for value in values:

            group = [
                user
                for user in users
                if str(user[dimension]) == value
            ]

            n_users = len(group)

            n_transactions = sum(
                user["transaction_count"]
                for user in group
            )

            n_assigned = sum(
                user["assigned_count"]
                for user in group
            )

            total_benefit = sum(
                user["estimated_total_value_won"]
                for user in group
            )

            segments.append({
                "dimension": dimension,
                "segment": value,
                "users": n_users,
                "transactions": n_transactions,
                "assigned_transactions": n_assigned,
                "assignment_rate_pct": (
                    round(
                        n_assigned / n_transactions * 100,
                        2,
                    )
                    if n_transactions else 0
                ),
                "estimated_total_benefit_won":
                    total_benefit,
                "average_benefit_per_user_won": (
                    round(total_benefit / n_users, 2)
                    if n_users else 0
                ),
            })

    return segments


# --------------------------------------------------
# 10. 실행
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--transactions-per-user",
        type=int,
        default=4,
    )

    parser.add_argument(
        "--amount",
        type=int,
        default=TEST_PAYMENT_WON,
    )

    parser.add_argument(
        "--db-balance",
        type=int,
        default=70000,
    )

    parser.add_argument(
        "--db-cashback-rate",
        type=Decimal,
        default=Decimal("0.10"),
    )

    parser.add_argument(
        "--db-cashback-remaining",
        type=int,
        default=20000,
    )

    parser.add_argument(
        "--point-rate",
        type=Decimal,
        default=Decimal("1"),
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")

    if not 1 <= args.transactions_per_user <= 30:
        parser.error(
            "--transactions-per-user must be 1~30"
        )

    if args.amount <= 0:
        parser.error("--amount must be positive")

    if args.db_balance < 0:
        parser.error("--db-balance cannot be negative")

    if args.db_cashback_remaining < 0:
        parser.error(
            "--db-cashback-remaining cannot be negative"
        )

    if not (
        Decimal("0")
        <= args.db_cashback_rate
        <= Decimal("1")
    ):
        parser.error(
            "--db-cashback-rate must be between 0 and 1"
        )

    if args.point_rate < 0:
        parser.error("--point-rate cannot be negative")

    load_dotenv(ROOT / ".env")

    profiles, slots, merchants = load_v2_data(
        args.limit
    )

    print("=== V2 POPULATION LOADED ===")
    print("Users:", len(profiles))
    print("Card slots:", len(slots))
    print("Merchants:", len(merchants))

    tx_rows, user_rows = run_population(
        profiles=profiles,
        slots=slots,
        merchants=merchants,
        transaction_count=args.transactions_per_user,
        amount_won=args.amount,
        db_balance=args.db_balance,
        db_cashback_rate=args.db_cashback_rate,
        db_cashback_remaining=args.db_cashback_remaining,
        point_rate=args.point_rate,
    )

    segments = build_segments(user_rows)

    summary = {
        "scenario_id": SCENARIO_ID,
        "mode": "V2_SYNTHETIC_POPULATION",
        "user_count": len(user_rows),
        "card_slot_count": len(slots),
        "transaction_count": len(tx_rows),
        "assigned_transactions": sum(
            u["assigned_count"]
            for u in user_rows
        ),
        "unresolved_transactions": sum(
            u["unresolved_count"]
            for u in user_rows
        ),
        "dongbaek_transactions": sum(
            u["dongbaek_count"]
            for u in user_rows
        ),
        "bnk_transactions": sum(
            u["bnk_count"]
            for u in user_rows
        ),
        "estimated_total_benefit_won": sum(
            u["estimated_total_value_won"]
            for u in user_rows
        ),
        "dongbaek_cashback_won": sum(
            u["dongbaek_cashback_won"]
            for u in user_rows
        ),
        "bnk_cash_discount_won": sum(
            u["bnk_cash_discount_won"]
            for u in user_rows
        ),
        "bnk_points": sum(
            u["bnk_points"]
            for u in user_rows
        ),
        "performance_state_distribution": dict(
            Counter(
                u["performance_state"]
                for u in user_rows
            )
        ),
        "assumptions": [
            "SYNTHETIC_TRANSACTIONS_NOT_LEDGER_DATA",
            "SAME_TRANSACTION_PATTERN_PER_USER",
            "SYNTHETIC_CARD_SLOTS",
            "V2_PERFORMANCE_OVERRIDE",
            "NO_ORIGINAL_PERFORMANCE_FALLBACK",
            "NO_REAL_PAYMENT_AUTHORIZATION",
            "NO_AUTO_TOPUP",
            "POINT_TO_KRW_HYPOTHETICAL",
        ],
    }

    OUTPUT.mkdir(exist_ok=True)

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
        segments,
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

    print("\n=== V2 SIMULATION SUMMARY ===")
    print(json.dumps(
        summary,
        ensure_ascii=False,
        indent=2,
    ))

    print("\nOutput:", OUTPUT)


if __name__ == "__main__":
    main()
