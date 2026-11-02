
"""OnePass P1 sequential transaction demo.

- NeonDB read-only
- No automatic top-up
- Dongbaek balance/cashback state updated in memory
- BNK rule/group usage updated in memory
- No real card authorization
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from demo_p1_one_transaction import (
    payment_context,
    fetch_customer_and_merchant,
    quote_bnk_card,
    compare_bnk_candidates,
)

from onepass.p1_rule_repository import P1RuleRepository
from onepass.p1_eligibility_repository import P1EligibilityRepository
from onepass.p1_monthly_db_repository import P1MonthlyDBRepository

from onepass.p1_dongbaek_candidate import (
    DongbaekInputs,
    evaluate_dongbaek_candidate,
    select_onepass_card,
)
from onepass.p1_mvp_quote import (
    quote_mvp_card,
    compare_mvp_cards,
)

# 동일 사용자의 6월 신규 시뮬레이션 거래
DEFAULT_TRANSACTIONS = [
    {
        "transaction_id": "TX001",
        "date": "2026-06-01",
        "merchant_id": "M00336",
        "amount_won": 32000,
        "lane": "OFFLINE",
        "provider": None,
    },
    {
        "transaction_id": "TX002",
        "date": "2026-06-02",
        "merchant_id": "M00336",
        "amount_won": 32000,
        "lane": "OFFLINE",
        "provider": None,
    },
    {
        "transaction_id": "TX003",
        "date": "2026-06-03",
        "merchant_id": "M00336",
        "amount_won": 32000,
        "lane": "OFFLINE",
        "provider": None,
    },
    {
        "transaction_id": "TX004",
        "date": "2026-06-04",
        "merchant_id": "M00336",
        "amount_won": 32000,
        "lane": "OFFLINE",
        "provider": None,
    },
]


def update_bnk_usage(
    usage_state: dict,
    selected_card: dict,
    quote: dict,
    rules_repo,
    as_of: str,
):
    """
    실제로 선택된 BNK 카드의 현금성 혜택만 반영.
    포인트 혜택이나 미확정 규칙은 갱신하지 않음.
    """
    product_id = selected_card["product_id"]
    user_card_id = selected_card["user_card_id"]

    eligible_rules = [
        r for r in quote.get("rules", [])
        if r["status"] == "ELIGIBLE"
        and r.get("benefit_won") is not None
    ]

    if not eligible_rules:
        return {
            "updated": False,
            "reason": "NO_CALCULATED_CASH_RULE",
        }

    best_rule = max(
        eligible_rules,
        key=lambda r: r["benefit_won"],
    )
    benefit = int(best_rule["benefit_won"])
    rule_id = best_rule["rule_id"]

    matching_rules = {
        loaded.rule.rule_id: loaded.rule
        for loaded in rules_repo.load(product_id, as_of)
    }
    rule = matching_rules.get(rule_id)

    if rule is None:
        return {
            "updated": False,
            "reason": "SELECTED_RULE_NOT_FOUND",
        }

    rule_key = ("RULE", user_card_id, rule_id)
    old_rule = usage_state.get(
        rule_key,
        {"count": 0, "benefit_won": 0},
    )

    usage_state[rule_key] = {
        "count": old_rule["count"] + 1,
        "benefit_won": old_rule["benefit_won"] + benefit,
    }

    group = rule.shared_cap_group

    if group is not None:
        group_key = ("GROUP", user_card_id, group)
        old_group = usage_state.get(
            group_key,
            {"benefit_won": 0},
        )
        usage_state[group_key] = {
            "benefit_won": old_group["benefit_won"] + benefit,
        }

    return {
        "updated": True,
        "rule_id": rule_id,
        "benefit_won": benefit,
        "rule_usage_after": usage_state[rule_key],
        "shared_cap_group": group,
    }


def validate_transactions(transactions, base_month):
    """한 개 월의 시간순 거래만 허용."""
    if not isinstance(transactions, list) or not transactions:
        raise ValueError("TRANSACTIONS_MUST_BE_NONEMPTY_LIST")

    # 전월 마감 데이터가 기준이므로,
    # 거래월은 해당 마감월 바로 다음 달이어야 한다.
    year, month = map(int, base_month.split("-"))
    next_year = year + (month == 12)
    next_month = 1 if month == 12 else month + 1
    expected_month = f"{next_year:04d}-{next_month:02d}"

    seen = set()
    previous_key = None

    for tx in transactions:
        required = {
            "transaction_id",
            "date",
            "merchant_id",
            "amount_won",
            "lane",
        }
        if not required.issubset(tx):
            raise ValueError("TRANSACTION_FIELDS_MISSING")

        tx_date = date.fromisoformat(tx["date"])

        if tx_date.strftime("%Y-%m") != expected_month:
            raise ValueError(
                "TRANSACTION_MONTH_MUST_FOLLOW_BASE_MONTH"
            )

        tx_id = tx["transaction_id"]

        if tx_id in seen:
            raise ValueError(f"DUPLICATE_TRANSACTION_ID:{tx_id}")
        seen.add(tx_id)

        order_key = (tx["date"], tx_id)
        if previous_key is not None and order_key < previous_key:
            raise ValueError("TRANSACTIONS_NOT_SORTED")
        previous_key = order_key

        if (
            type(tx["amount_won"]) is not int
            or tx["amount_won"] <= 0
        ):
            raise ValueError("INVALID_TRANSACTION_AMOUNT")

        if tx["lane"] not in {
            "OFFLINE", "ONLINE", "SIMPLE_PAY"
        }:
            raise ValueError("INVALID_LANE")

        provider = tx.get("provider")
        if (tx["lane"] == "SIMPLE_PAY") != bool(provider):
            raise ValueError("INVALID_PROVIDER_FOR_LANE")

    return expected_month


def run_batch(
    user_id,
    base_month,
    transactions,
    db_balance,
    db_rate,
    db_cashback_remaining,
):
    simulated_month = validate_transactions(
        transactions, base_month
    )

    rr = P1RuleRepository()
    er = P1EligibilityRepository()
    mr = P1MonthlyDBRepository()

    # 최초 가상 상태
    state = {
        "dongbaek_balance_won": db_balance,
        "dongbaek_cashback_remaining_won":
            db_cashback_remaining,
        "bnk_usage": {},
    }

    results = []
    totals = {
        "transaction_count": len(transactions),
        "selected_count": 0,
        "unresolved_count": 0,
        "dongbaek_count": 0,
        "bnk_count": 0,
        "dongbaek_payment_won": 0,
        "bnk_payment_won": 0,
        "dongbaek_cashback_won": 0,
        "bnk_cash_benefit_won": 0,
        "provisional_count": 0,
    }

    for tx in transactions:
        actual_user, merchant, cards, _ = (
            fetch_customer_and_merchant(
                user_id,
                tx["merchant_id"],
            )
        )

        pay = payment_context(
            tx["lane"], tx.get("provider")
        )

        candidates = [
            quote_bnk_card(
                card=card,
                merchant_id=tx["merchant_id"],
                amount=tx["amount_won"],
                payment=pay,
                as_of=tx["date"],
                base_month=base_month,
                rules_repo=rr,
                eligibility_repo=er,
                monthly_repo=mr,
                usage_state=state["bnk_usage"],
            )
            for card in cards
        ]

        comparison = compare_bnk_candidates(candidates)
        # 별도 MVP 계산. 기존 보수적 결과는 그대로 유지.
        mvp_candidates = [
            quote_mvp_card(
                card=card,
                merchant_id=tx["merchant_id"],
                amount=tx["amount_won"],
                payment=pay,
                as_of=tx["date"],
                base_month=base_month,
                rules_repo=rr,
                eligibility_repo=er,
                monthly_repo=mr,
                usage_state=state["bnk_usage"],
            )
            for card in cards
        ]

        mvp_comparison = compare_mvp_cards(mvp_candidates)

        dongbaek = evaluate_dongbaek_candidate(
            merchant=merchant,
            amount_won=tx["amount_won"],
            lane=tx["lane"],
            inputs=DongbaekInputs(
                balance_won=state[
                    "dongbaek_balance_won"
                ],
                cashback_rate=db_rate,
                cashback_remaining_won=state[
                    "dongbaek_cashback_remaining_won"
                ],
            ),
        )

        decision = select_onepass_card(
            dongbaek, comparison
        )

        # 최초 카드 제안 결과 별도 보존
        original_proposed_card = decision.get("selected_card")

        selected = decision["selected_card"]
        status = decision["selection_status"]

        amount = tx["amount_won"]
        state_change = None

        if selected is None:
            totals["unresolved_count"] += 1

        elif selected == "PRD_DB_SYN":
            cashback = dongbaek["cash_benefit_won"]

            # 시뮬레이션상 동백전 결제 승인으로 간주.
            state["dongbaek_balance_won"] -= amount
            state[
                "dongbaek_cashback_remaining_won"
            ] -= cashback

            totals["dongbaek_count"] += 1
            totals["selected_count"] += 1
            totals["dongbaek_payment_won"] += amount
            totals["dongbaek_cashback_won"] += cashback

            state_change = {
                "type": "DONGBAEK",
                "balance_after": state[
                    "dongbaek_balance_won"
                ],
                "cashback_remaining_after": state[
                    "dongbaek_cashback_remaining_won"
                ],
                "cashback_earned_won": cashback,
            }

        else:
            matching_cards = [
                c for c in cards
                if c["product_id"] == selected
            ]
            matching_quotes = [
                c for c in candidates
                if c["product_id"] == selected
            ]

            # 같은 상품이 여러 장이면 이 시연에서는
            # 어느 카드를 사용할지 알 수 없으므로 보류.
            if (
                len(matching_cards) != 1
                or len(matching_quotes) != 1
            ):
                selected = None
                status = "UNRESOLVED"
                totals["unresolved_count"] += 1
                state_change = {
                    "reason": "AMBIGUOUS_BNK_CARD",
                }

            else:
                update = update_bnk_usage(
                    state["bnk_usage"],
                    matching_cards[0],
                    matching_quotes[0],
                    rr,
                    tx["date"],
                )


                if update["updated"]:
                    # 현금 할인 혜택을 실제로 계산한 가상 거래
                    benefit = int(update["benefit_won"])

                    totals["bnk_count"] += 1
                    totals["selected_count"] += 1
                    totals["bnk_payment_won"] += amount
                    totals["bnk_cash_benefit_won"] += benefit

                    if status == "PROVISIONAL":
                        totals["provisional_count"] += 1

                    state_change = {
                        "type": "BNK",
                        "benefit_applied": True,
                        **update,
                    }

                elif (
                    update["reason"] == "NO_CALCULATED_CASH_RULE"
                    and matching_quotes[0]["status"] == "COMPARABLE"
                    and matching_quotes[0]["cash_benefit_won"] == 0
                ):
                    # 할인 혜택은 소진됐지만,
                    # 카드 자체는 가상 결제수단으로 배정한다.
                    # 실제 승인 가능 여부는 검증하지 않음.
                    totals["bnk_count"] += 1
                    totals["selected_count"] += 1
                    totals["bnk_payment_won"] += amount

                    if status == "PROVISIONAL":
                        totals["provisional_count"] += 1

                    state_change = {
                        "type": "BNK",
                        "benefit_applied": False,
                        "benefit_won": 0,
                        "reason": "NO_CASH_BENEFIT_AVAILABLE",
                        "usage_updated": False,
                        "authorization_verified": False,
                    }

                else:
                    selected = None
                    status = "UNRESOLVED"
                    totals["unresolved_count"] += 1
                    state_change = update

                    # 기존 선택 결과와 실제 기록 상태를 일치시킨다.
                    decision = {
                        **decision,
                        "selected_card": None,
                        "selection_status": "UNRESOLVED",
                        "reason": update["reason"],
                    }

        results.append({
            "proposed_card": original_proposed_card,
            "recorded_card": selected,
            "recorded_status": status,
            "recording_reason": (
                state_change.get("reason")
                if isinstance(state_change, dict)
                else None
            ),
            
            "transaction_id": tx["transaction_id"],
            "date": tx["date"],
            "merchant_id": tx["merchant_id"],
            "amount_won": amount,
            "lane": tx["lane"],
            "provider": tx.get("provider"),
            "selected_card": selected,
            "selection_status": status,
            "selection_reason": decision["reason"],
            "dongbaek": dongbaek,
            "bnk_comparison": comparison,
            "state_change": state_change,
            "bnk_candidates": candidates,
            "payment_eligibility": {
                "status": "NOT_VERIFIED",
                "reason": "NO_CARD_AUTHORIZATION_OR_ACCOUNT_BALANCE_CHECK",
            },
            "benefit_status": (
                "PARTIAL"
                if comparison.get("review_candidates")
                else (
                    "COMPARABLE"
                    if comparison.get("cash_candidates")
                    else "UNRESOLVED"
                )
            ),
            "mvp_candidates": mvp_candidates,
            "mvp_comparison": mvp_comparison,
        })

    return {
        "mode": "READ_ONLY_SEQUENTIAL_SIMULATION",
        "user_id": user_id,
        "base_month": base_month,
        "simulated_month": simulated_month,
        "simulation_assumptions": [
            "DONGBAEK_BALANCE_MANUALLY_INITIALIZED",
            "DONGBAEK_POLICY_MANUALLY_INITIALIZED",
            "CURRENT_MONTH_BNK_USAGE_STARTS_AT_ZERO",
            "NO_REAL_PAYMENT_AUTHORIZATION",
            "BNK_PROVISIONAL_SELECTION_ALLOWED",
            "ASSUMED_BENEFIT_RULES_USED",
            "NO_AUTO_TOPUP",
        ],
        "totals": totals,
        "transactions": results,
        "final_state": {
            "dongbaek_balance_won": state[
                "dongbaek_balance_won"
            ],
            "dongbaek_cashback_remaining_won":
                state[
                    "dongbaek_cashback_remaining_won"
                ],
            "bnk_usage": [
                {
                    "state_key": list(key),
                    **value,
                }
                for key, value in state[
                    "bnk_usage"
                ].items()
            ],
        },
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--user-id", default="U0004")
    parser.add_argument("--base-month", default="2026-05")
    parser.add_argument(
        "--transactions",
        help="JSON file containing ordered transactions",
    )

    parser.add_argument(
        "--db-balance", type=int, default=70000
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

    args = parser.parse_args()

    if args.db_balance < 0:
        parser.error("DB balance cannot be negative")
    if args.db_cashback_remaining < 0:
        parser.error("Cashback remaining cannot be negative")

    load_dotenv(
        Path(__file__).resolve().parent / ".env"
    )

    if args.transactions:
        with open(
            args.transactions,
            "r",
            encoding="utf-8",
        ) as f:
            transactions = json.load(f)
    else:
        transactions = DEFAULT_TRANSACTIONS

    result = run_batch(
        user_id=args.user_id,
        base_month=args.base_month,
        transactions=transactions,
        db_balance=args.db_balance,
        db_rate=args.db_cashback_rate,
        db_cashback_remaining=args.db_cashback_remaining,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
