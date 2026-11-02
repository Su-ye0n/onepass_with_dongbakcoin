
"""P1 MVP benefit quotes.

Simulation only. Reads NeonDB, never writes to it.
PENDING and ASSUMED source rules may be simulated.
Points are valued at a configurable hypothetical rate.
"""

from dataclasses import replace
from decimal import Decimal, ROUND_FLOOR

from psycopg.rows import dict_row

from onepass.db_connection import connect_readonly
from onepass.p1_rule_engine import RuleUsage, quote_rule


def quote_mvp_card(
    *,
    card,
    merchant_id,
    amount,
    payment,
    as_of,
    base_month,
    rules_repo,
    eligibility_repo,
    monthly_repo,
    usage_state=None,
    point_krw_rate=Decimal("1"),
    default_shared_cap=10000,
    reward_units=None,  # 추가
):
    
    usage_state = usage_state or {}
    product_id = card["product_id"]
    user_card_id = card["user_card_id"]

    # Original rule metadata is retained.
    loaded_rules = rules_repo.load(product_id, as_of)

    monthly = monthly_repo.load(
        user_card_id=user_card_id,
        base_month=base_month,
    )
    monthly_by_rule = {
        r.rule_id: r for r in monthly.rules
    }

    # Reward unit is not included in NormalizedRule.
    rule_ids = [x.rule.rule_id for x in loaded_rules]
    details = {}

    if reward_units is not None:
        details = {
            rid: reward_units.get(rid)
            for rid in rule_ids
        }

    elif rule_ids:
        # 기존 모드는 기존 DB 조회 방식 유지
        with connect_readonly() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT rule_id, reward_unit
                    FROM public.benefit_rule
                    WHERE rule_id = ANY(%s)
                    """,
                    (rule_ids,),
                )
                details = {
                    r["rule_id"]: r["reward_unit"]
                    for r in cur.fetchall()
                }

    results = []
    total_cash = []
    total_point_value = []
    unresolved = []

    for loaded in loaded_rules:
        rule = loaded.rule
        rid = rule.rule_id
        unit = details.get(rid)

        record = {
            "rule_id": rid,
            "source_status": loaded.source_status,
            "reward_unit": unit,
            "status": "UNRESOLVED",
            "target_status": None,
            "benefit_amount": None,
            "estimated_value_won": None,
            "reason": None,
            "assumptions": [],
        }

        eligibility = eligibility_repo.evaluate(
            rule_id=rid,
            merchant_id=merchant_id,
            payment=payment,
            as_of=as_of,
        )

        record["target_status"] = eligibility.status

        if eligibility.status == "INELIGIBLE":
            record.update(
                status="INELIGIBLE",
                benefit_amount=0,
                estimated_value_won=0,
                reason=eligibility.reason,
            )
            results.append(record)
            continue

        if eligibility.status != "ELIGIBLE":
            record["reason"] = "TARGET_NOT_RESOLVED"
            unresolved.append(rid)
            results.append(record)
            continue

        # MVP permits source PENDING/ASSUMED,
        # but never changes the source status in DB.
        if loaded.source_status not in {
            "PENDING", "ASSUMED", "VERIFIED"
        }:
            record["reason"] = "UNKNOWN_SOURCE_STATUS"
            unresolved.append(rid)
            results.append(record)
            continue

        if unit not in {"CASH", "POINT"}:
            record["reason"] = "UNKNOWN_REWARD_UNIT"
            unresolved.append(rid)
            results.append(record)
            continue

        if any(
            reason in loaded.reasons
            for reason in (
                "INVALID_NORMALIZED_RULE",
                "INVALID_RULE_NUMERIC_FIELDS",
                "INVALID_BENEFIT_VALUE",
                "BENEFIT_VALUE_MISSING",
                "UNSUPPORTED_BENEFIT_TYPE",
            )
        ):
            record["reason"] = "INVALID_RULE_DATA"
            unresolved.append(rid)
            results.append(record)
            continue

        month_rule = monthly_by_rule.get(rid)

        if (
            month_rule is not None
            and month_rule.eligible_perf_won is not None
        ):
            prev_spend = month_rule.eligible_perf_won
            record["assumptions"].append(
                "DB_ELIGIBLE_PERFORMANCE_USED"
            )
        elif monthly.spend_total_won is not None:
            prev_spend = monthly.spend_total_won
            record["assumptions"].append(
                "TOTAL_SPEND_USED_AS_PERFORMANCE_PROXY"
            )
        else:
            record["reason"] = "PREVIOUS_SPEND_MISSING"
            unresolved.append(rid)
            results.append(record)
            continue

        rule_key = ("RULE", user_card_id, rid)
        rule_used = usage_state.get(
            rule_key, {"count": 0, "benefit_won": 0}
        )

        group_used = usage_state.get(
            ("GROUP", user_card_id, rule.shared_cap_group),
            {"benefit_won": 0},
        )

        usage = RuleUsage(
            monthly_count=rule_used["count"],
            rule_benefit_used_won=rule_used["benefit_won"],
            shared_benefit_used_won=group_used["benefit_won"],
        )

        effective_cap = None

        if rule.shared_cap_group:
            tiers = [
                t for t in loaded.cap_tiers
                if t.perf_min_won <= prev_spend
            ]

            if tiers:
                effective_cap = max(
                    tiers, key=lambda t: t.perf_min_won
                ).monthly_cap_won
            else:
                effective_cap = default_shared_cap
                record["assumptions"].append(
                    "DEFAULT_SHARED_CAP_APPLIED"
                )

        if loaded.source_status != "VERIFIED":
            record["assumptions"].append(
                "UNVERIFIED_SOURCE_SIMULATED"
            )

        if "PAYMENT_CHANNEL_NOT_NORMALIZED" in loaded.reasons:
            record["assumptions"].append(
                "CHANNEL_ASSUMED_FROM_TARGET_MATCH"
            )

        if unit == "POINT":
            record["assumptions"].append(
                "POINT_TO_KRW_SIMULATION_RATE"
            )

        # Use the existing cap/count/per-tx calculations.
        simulated_rule = replace(rule, verified=True)

        quote = quote_rule(
            simulated_rule,
            amount_won=amount,
            prev_month_spend_won=prev_spend,
            payment=payment,
            usage=usage,
            effective_monthly_cap_won=effective_cap,
        )

        record["status"] = quote.decision
        record["reason"] = quote.reason
        record["prev_month_spend_won"] = prev_spend
        record["effective_monthly_cap_won"] = effective_cap

        if quote.decision == "PENDING_REVIEW":
            unresolved.append(rid)
            results.append(record)
            continue

        benefit = (
            quote.benefit_won
            if quote.decision == "ELIGIBLE"
            else 0
        )

        record["benefit_amount"] = benefit

        if unit == "CASH":
            value_won = benefit
            if quote.decision == "ELIGIBLE":
                total_cash.append((value_won, rid))
        else:
            value_won = int(
                (
                    Decimal(benefit) * point_krw_rate
                ).to_integral_value(rounding=ROUND_FLOOR)
            )
            if quote.decision == "ELIGIBLE":
                total_point_value.append((value_won, rid))

        record["estimated_value_won"] = value_won
        results.append(record)

    # MAX_ONLY assumption: take the largest independent
    # rule benefit. Do not blindly sum overlapping rules.
    eligible_values = total_cash + total_point_value

    if eligible_values:
        best_value, best_rule_id = max(
            eligible_values,
            key=lambda x: (x[0], x[1]),
        )
    else:
        best_value = 0
        best_rule_id = None

    return {
        "product_id": product_id,
        "user_card_id": user_card_id,
        "status": (
            "SIMULATED_PARTIAL"
            if unresolved
            else "SIMULATED_COMPARABLE"
        ),
        "estimated_value_won": best_value,
        "best_rule_id": best_rule_id,
        "unresolved_rule_ids": unresolved,
        "rules": results,
        "comparison_basis": "MAX_SINGLE_RULE",
        "point_krw_rate": str(point_krw_rate),
        "simulation_only": True,
    }


def compare_mvp_cards(candidates):
    ranked = sorted(
        [
            c for c in candidates
            if c["status"] == "SIMULATED_COMPARABLE"
        ],
        key=lambda c: (
            -c["estimated_value_won"],
            c["product_id"],
        ),
    )

    partial = [
        c["product_id"]
        for c in candidates
        if c["status"] != "SIMULATED_COMPARABLE"
    ]

    winner = ranked[0] if ranked else None

    return {
        "cash_and_points_compared": True,
        "estimated_best_product_id": (
            winner["product_id"] if winner else None
        ),
        "estimated_best_value_won": (
            winner["estimated_value_won"]
            if winner else None
        ),
        "status": (
            "SIMULATED_COMPLETE"
            if winner and not partial
            else "SIMULATED_PARTIAL"
        ),
        "unresolved_products": partial,
        "ranking": [
            {
                "product_id": c["product_id"],
                "estimated_value_won": c["estimated_value_won"],
                "best_rule_id": c["best_rule_id"],
            }
            for c in ranked
        ],
    }
