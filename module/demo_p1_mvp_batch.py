
"""Dongbaek OnePass P1 integrated MVP simulator.

Strategy: maximize estimated benefit per transaction.

- NeonDB read-only
- PENDING / ASSUMED rules simulated
- Points converted using hypothetical 1P = 1 KRW
- Selected rule usage accumulated in memory
- No automatic top-up
- No payment authorization
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from demo_p1_one_transaction import (
    fetch_customer_and_merchant,
    payment_context,
)
from demo_p1_batch import (
    DEFAULT_TRANSACTIONS,
    validate_transactions,
)

from onepass.p1_rule_repository import P1RuleRepository
from onepass.p1_eligibility_repository import (
    P1EligibilityRepository,
)
from onepass.p1_monthly_db_repository import (
    P1MonthlyDBRepository,
)
from onepass.p1_mvp_quote import quote_mvp_card
from onepass.p1_dongbaek_candidate import (
    DongbaekInputs,
    evaluate_dongbaek_candidate,
)


BASE_DIR = Path(__file__).resolve().parent
DONGBAEK_ID = "PRD_DB_SYN"


def select_mvp_candidate(
    dongbaek,
    bnk_candidates,
):
    """Rank candidates by estimated KRW value.

    Only fully calculated BNK candidate quotes compete.
    An unverified Dongbaek lane is not treated as eligible.
    """

    ranked = []
    excluded = []
    has_partial_bnk = False

    if (
        dongbaek["status"] == "COMPARABLE"
        and dongbaek["payment_possible"] is True
        and dongbaek["cash_benefit_won"] is not None
    ):
        ranked.append({
            "product_id": DONGBAEK_ID,
            "user_card_id": None,
            "best_rule_id": None,
            "estimated_value_won": int(
                dongbaek["cash_benefit_won"]
            ),
            "source": "DONGBAEK",
        })
    else:
        excluded.append({
            "product_id": DONGBAEK_ID,
            "reason": dongbaek["reason"],
        })

    for card in bnk_candidates:
        if card["status"] != "SIMULATED_COMPARABLE":
            has_partial_bnk = True
            excluded.append({
                "product_id": card["product_id"],
                "user_card_id": card["user_card_id"],
                "reason": "PARTIAL_BENEFIT_QUOTE",
                "unresolved_rule_ids": card[
                    "unresolved_rule_ids"
                ],
            })
            continue

        ranked.append({
            "product_id": card["product_id"],
            "user_card_id": card["user_card_id"],
            "best_rule_id": card["best_rule_id"],
            "estimated_value_won": int(
                card["estimated_value_won"]
            ),
            "source": "BNK",
        })

    # Maximize value; Dongbaek wins exact ties.
    # Remaining ties resolved by product_id, then card ID.
    ranked.sort(
        key=lambda c: (
            -c["estimated_value_won"],
            0 if c["source"] == "DONGBAEK" else 1,
            c["product_id"],
            c["user_card_id"] or "",
        )
    )

    winner = ranked[0] if ranked else None

    if winner is None:
        return {
            "selected_card": None,
            "selected_user_card_id": None,
            "selected_rule_id": None,
            "estimated_value_won": None,
            "selection_status": "UNRESOLVED",
            "selection_reason": "NO_COMPARABLE_CANDIDATE",
            "ranked_candidates": ranked,
            "excluded_candidates": excluded,
        }

    # Partial competitors may have unknown higher benefits.
    status = (
        "SIMULATED_PROVISIONAL"
        if has_partial_bnk
        or dongbaek["status"] == "UNRESOLVED"
        else "SIMULATED_SELECTED"
    )

    return {
        "selected_card": winner["product_id"],
        "selected_user_card_id": winner["user_card_id"],
        "selected_rule_id": winner["best_rule_id"],
        "estimated_value_won": winner[
            "estimated_value_won"
        ],
        "selection_status": status,
        "selection_reason": "MAX_ESTIMATED_BENEFIT",
        "ranked_candidates": ranked,
        "excluded_candidates": excluded,
    }


def commit_mvp_bnk_usage(
    usage_state,
    selected_quote,
    selected_rule_id,
    rules_repo,
    as_of,
):
    """Commit chosen rule usage to simulation memory.

    Rule caps count benefits in their original units.
    POINT is not silently converted into CASH usage.
    """

    if selected_rule_id is None:
        return {
            "type": "BNK",
            "benefit_amount": 0,
            "estimated_value_won": 0,
            "reward_unit": None,
            "usage_updated": False,
            "reason": "NO_APPLICABLE_BENEFIT_RULE",
        }

    matched = [
        r for r in selected_quote["rules"]
        if r["rule_id"] == selected_rule_id
        and r["status"] == "ELIGIBLE"
    ]

    if len(matched) != 1:
        raise ValueError(
            "SELECTED_MVP_RULE_NOT_ELIGIBLE:"
            + selected_rule_id
        )

    benefit_rule = matched[0]
    benefit = int(benefit_rule["benefit_amount"])
    reward_unit = benefit_rule["reward_unit"]

    product_id = selected_quote["product_id"]
    user_card_id = selected_quote["user_card_id"]

    matching_models = [
        loaded.rule
        for loaded in rules_repo.load(product_id, as_of)
        if loaded.rule.rule_id == selected_rule_id
    ]

    if len(matching_models) != 1:
        raise ValueError(
            "SELECTED_RULE_MODEL_NOT_FOUND:"
            + selected_rule_id
        )

    rule = matching_models[0]

    key = ("RULE", user_card_id, selected_rule_id)
    previous = usage_state.get(
        key,
        {"count": 0, "benefit_won": 0},
    )

    # The existing RuleUsage engine uses benefit_won
    # as its numeric cap accumulator. In this simulation,
    # POINT rules use point units in the same numeric slot.
    usage_state[key] = {
        "count": previous["count"] + 1,
        "benefit_won": previous["benefit_won"] + benefit,
    }

    group_name = rule.shared_cap_group

    if group_name:
        group_key = (
            "GROUP",
            user_card_id,
            group_name,
        )
        group_before = usage_state.get(
            group_key, {"benefit_won": 0}
        )

        # This is valid only when all rules in the group
        # share one benefit unit.
        usage_state[group_key] = {
            "benefit_won": (
                group_before["benefit_won"] + benefit
            )
        }

    return {
        "type": "BNK",
        "rule_id": selected_rule_id,
        "reward_unit": reward_unit,
        "benefit_amount": benefit,
        "estimated_value_won": int(
            benefit_rule["estimated_value_won"]
        ),
        "rule_usage_after": dict(usage_state[key]),
        "shared_cap_group": group_name,
        "usage_updated": True,
    }


def run_mvp_batch(
    *,
    user_id,
    base_month,
    transactions,
    db_balance,
    db_rate,
    db_cashback_remaining,
    point_rate=Decimal("1"),
):
    simulated_month = validate_transactions(
        transactions, base_month
    )

    if db_balance < 0 or db_cashback_remaining < 0:
        raise ValueError("NEGATIVE_INITIAL_STATE")

    if db_rate < 0 or db_rate > 1:
        raise ValueError("INVALID_CASHBACK_RATE")

    if point_rate < 0:
        raise ValueError("INVALID_POINT_RATE")

    rr = P1RuleRepository()
    er = P1EligibilityRepository()
    mr = P1MonthlyDBRepository()

    state = {
        "dongbaek_balance_won": db_balance,
        "dongbaek_cashback_remaining_won":
            db_cashback_remaining,
        "bnk_usage": {},
    }

    totals = {
        "transaction_count": len(transactions),
        "assigned_count": 0,
        "unresolved_count": 0,
        "dongbaek_count": 0,
        "bnk_count": 0,
        "dongbaek_cashback_won": 0,
        "bnk_cash_discount_won": 0,
        "bnk_points": 0,
        "estimated_total_value_won": 0,
        "assigned_payment_won": 0,
    }

    results = []

    for tx in transactions:
        _, merchant, cards, _ = (
            fetch_customer_and_merchant(
                user_id, tx["merchant_id"]
            )
        )

        payment = payment_context(
            tx["lane"], tx.get("provider")
        )

        bnk_quotes = [
            quote_mvp_card(
                card=card,
                merchant_id=tx["merchant_id"],
                amount=tx["amount_won"],
                payment=payment,
                as_of=tx["date"],
                base_month=base_month,
                rules_repo=rr,
                eligibility_repo=er,
                monthly_repo=mr,
                usage_state=state["bnk_usage"],
                point_krw_rate=point_rate,
            )
            for card in cards
        ]

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

        selection = select_mvp_candidate(
            dongbaek, bnk_quotes
        )

        selected = selection["selected_card"]
        amount = tx["amount_won"]
        state_change = None

        if selected is None:
            totals["unresolved_count"] += 1

        elif selected == DONGBAEK_ID:
            cashback = int(
                dongbaek["cash_benefit_won"]
            )

            state["dongbaek_balance_won"] -= amount
            state[
                "dongbaek_cashback_remaining_won"
            ] -= cashback

            totals["assigned_count"] += 1
            totals["dongbaek_count"] += 1
            totals["assigned_payment_won"] += amount
            totals["dongbaek_cashback_won"] += cashback
            totals["estimated_total_value_won"] += cashback

            state_change = {
                "type": "DONGBAEK",
                "cashback_won": cashback,
                "balance_after": state[
                    "dongbaek_balance_won"
                ],
                "cashback_remaining_after": state[
                    "dongbaek_cashback_remaining_won"
                ],
            }

        else:
            matched = [
                q for q in bnk_quotes
                if q["product_id"] == selected
                and q["user_card_id"] == selection[
                    "selected_user_card_id"
                ]
            ]

            if len(matched) != 1:
                raise ValueError(
                    "AMBIGUOUS_SELECTED_USER_CARD"
                )

            state_change = commit_mvp_bnk_usage(
                state["bnk_usage"],
                matched[0],
                selection["selected_rule_id"],
                rr,
                tx["date"],
            )

            value = int(
                state_change["estimated_value_won"]
            )

            totals["assigned_count"] += 1
            totals["bnk_count"] += 1
            totals["assigned_payment_won"] += amount
            totals["estimated_total_value_won"] += value

            if state_change["reward_unit"] == "CASH":
                totals["bnk_cash_discount_won"] += int(
                    state_change["benefit_amount"]
                )

            if state_change["reward_unit"] == "POINT":
                totals["bnk_points"] += int(
                    state_change["benefit_amount"]
                )

        results.append({
            "transaction_id": tx["transaction_id"],
            "date": tx["date"],
            "merchant_id": tx["merchant_id"],
            "amount_won": amount,
            "lane": tx["lane"],
            "provider": tx.get("provider"),
            "selected_card": selected,
            "selection_status": selection[
                "selection_status"
            ],
            "selected_user_card_id": selection[
                "selected_user_card_id"
            ],
            "selected_rule_id": selection[
                "selected_rule_id"
            ],
            "estimated_value_won": selection[
                "estimated_value_won"
            ],
            "ranking": selection["ranked_candidates"],
            "excluded_candidates": selection[
                "excluded_candidates"
            ],
            "dongbaek_quote": dongbaek,
            "bnk_quotes": bnk_quotes,
            "state_change": state_change,
        })

    return {
        "mode": "MVP_MAX_BENEFIT_SIMULATION",
        "user_id": user_id,
        "base_month": base_month,
        "simulated_month": simulated_month,
        "strategy": "MAX_ESTIMATED_BENEFIT",
        "simulation_assumptions": [
            "PENDING_AND_ASSUMED_RULES_SIMULATED",
            "POINT_RATE_IS_HYPOTHETICAL",
            "DONGBAEK_POLICY_AND_BALANCE_SYNTHETIC",
            "CURRENT_MONTH_USAGE_INITIALIZED_ZERO",
            "NO_REAL_PAYMENT_AUTHORIZATION",
            "NO_AUTO_TOPUP",
            "MAX_SINGLE_BENEFIT_RULE",
            "UNVERIFIED_LANES_EXCLUDED_FROM_CANDIDATES",
        ],
        "point_krw_rate": str(point_rate),
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
                    "key": list(key),
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
    parser.add_argument("--transactions")
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
    parser.add_argument(
        "--point-rate",
        type=Decimal,
        default=Decimal("1"),
    )

    args = parser.parse_args()
    load_dotenv(BASE_DIR / ".env")

    if args.transactions:
        with open(
            args.transactions,
            encoding="utf-8-sig",
        ) as f:
            transactions = json.load(f)
    else:
        transactions = DEFAULT_TRANSACTIONS

    result = run_mvp_batch(
        user_id=args.user_id,
        base_month=args.base_month,
        transactions=transactions,
        db_balance=args.db_balance,
        db_rate=args.db_cashback_rate,
        db_cashback_remaining=args.db_cashback_remaining,
        point_rate=args.point_rate,
    )

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        default=str,
    ))


if __name__ == "__main__":
    main()
