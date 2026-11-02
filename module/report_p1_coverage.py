
"""OnePass P1 coverage and data quality report.

Input:
    mixed_result.json (demo_p1_batch.py output)

Outputs:
    p1_coverage_report.json
    p1_coverage_transactions.csv

Read-only report. No DB access or DB writes.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def read_json(path):
    raw = Path(path).read_bytes()

    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return json.loads(raw.decode("utf-16"))

    if raw.startswith(b"\xef\xbb\xbf"):
        return json.loads(raw.decode("utf-8-sig"))

    return json.loads(raw.decode("utf-8"))


def percentage(count, total):
    if total == 0:
        return 0.0
    return round(count * 100 / total, 2)


def analyze_transaction(tx):
    candidates = tx.get("bnk_candidates", [])
    comparison = tx.get("bnk_comparison") or {}
    dongbaek = tx.get("dongbaek") or {}
    state_change = tx.get("state_change") or {}

    rules = [
        {
            **rule,
            "product_id": card.get("product_id"),
        }
        for card in candidates
        for rule in card.get("rules", [])
    ]

    # 실제로 대상에 해당하는 규칙 중 미확정인 것
    pending_rules = sorted({
        rule["rule_id"]
        for rule in rules
        if rule.get("target_channel_status") == "ELIGIBLE"
        and (
            rule.get("source_status") == "PENDING"
            or rule.get("status") == "PENDING_REVIEW"
        )
    })

    # 적용 대상인 포인트 규칙 중 가치 비교가 불가능한 것
    point_rules = sorted({
        rule["rule_id"]
        for rule in rules
        if rule.get("status") == "POINT_INFORMATION"
    })

    # ASSUMED 규칙으로 실제 현금 혜택 계산
    assumed_cash_rules = sorted({
        rule["rule_id"]
        for rule in rules
        if rule.get("status") == "ELIGIBLE"
        and rule.get("source_status") == "ASSUMED"
        and rule.get("benefit_won") is not None
    })

    cash_leader = comparison.get("cash_leader")
    cash_quote_available = (
        cash_leader is not None
        and cash_leader.get("cash_benefit_won") is not None
    )

    bnk_full_comparison = (
        comparison.get("comparison_complete") is True
    )

    dongbaek_status = dongbaek.get("status", "NOT_RECORDED")
    dongbaek_reason = dongbaek.get("reason")

    dongbaek_lane_unverified = (
        dongbaek_reason == "DONGBAEK_LANE_NOT_VERIFIED"
    )

    # 별도의 카드 승인 정보가 없다면 결제 가능으로 단정하지 않음
    payment = tx.get("payment_eligibility") or {}
    authorization_verified = (
        payment.get("status") == "VERIFIED"
    )

    selected = tx.get("selected_card")
    selection_status = tx.get(
        "selection_status", "UNKNOWN"
    )

    # 선택한 BNK 카드의 혜택만 거래에 실제 반영되었는지
    selected_bnk_benefit_won = (
        state_change.get("benefit_won")
        if state_change.get("type") == "BNK"
        else None
    )

    if state_change.get("type") == "DONGBAEK":
        applied_benefit_won = state_change.get(
            "cashback_earned_won"
        )
    elif state_change.get("type") == "BNK":
        applied_benefit_won = selected_bnk_benefit_won
    else:
        applied_benefit_won = None

    if selection_status == "SELECTED":
        selection_category = "SELECTED_BY_POLICY"
    elif selection_status == "PROVISIONAL":
        selection_category = "PROVISIONAL"
    else:
        selection_category = "UNRESOLVED"

    reasons = []

    if pending_rules:
        reasons.append("SOURCE_PENDING")

    if point_rules:
        reasons.append("POINT_NOT_COMPARABLE")

    if dongbaek_lane_unverified:
        reasons.append("DONGBAEK_LANE_UNVERIFIED")

    if not cash_quote_available:
        reasons.append("NO_BNK_CASH_QUOTE")

    if not bnk_full_comparison:
        reasons.append("BNK_COMPARISON_INCOMPLETE")

    if not authorization_verified:
        reasons.append("AUTHORIZATION_NOT_VERIFIED")

    if selected is None:
        reasons.append("NO_CARD_RECORDED")

    return {
        "transaction_id": tx.get("transaction_id"),
        "date": tx.get("date"),
        "merchant_id": tx.get("merchant_id"),
        "lane": tx.get("lane"),
        "amount_won": tx.get("amount_won"),
        "selected_card": selected,
        "selection_category": selection_category,
        "selection_reason": tx.get("selection_reason"),
        "cash_quote_available": cash_quote_available,
        "cash_quote_won": (
            cash_leader.get("cash_benefit_won")
            if cash_quote_available
            else None
        ),
        "applied_benefit_won": applied_benefit_won,
        "bnk_full_comparison": bnk_full_comparison,
        "source_pending": bool(pending_rules),
        "point_not_comparable": bool(point_rules),
        "dongbaek_lane_unverified": dongbaek_lane_unverified,
        "authorization_verified": authorization_verified,
        "dongbaek_status": dongbaek_status,
        "pending_rule_ids": pending_rules,
        "point_rule_ids": point_rules,
        "assumed_cash_rule_ids": assumed_cash_rules,
        "quality_flags": reasons,
    }


def build_report(data):
    transactions = data.get("transactions", [])

    if not isinstance(transactions, list):
        raise ValueError("transactions must be a list")

    rows = [analyze_transaction(tx) for tx in transactions]
    total = len(rows)

    def metric(key):
        count = sum(bool(row[key]) for row in rows)
        return {
            "count": count,
            "percentage": percentage(count, total),
        }

    selected = sum(
        row["selected_card"] is not None
        for row in rows
    )

    provisional = sum(
        row["selection_category"] == "PROVISIONAL"
        for row in rows
    )

    unresolved = sum(
        row["selection_category"] == "UNRESOLVED"
        for row in rows
    )

    pending_frequency = Counter(
        rule_id
        for row in rows
        for rule_id in row["pending_rule_ids"]
    )

    point_frequency = Counter(
        rule_id
        for row in rows
        for rule_id in row["point_rule_ids"]
    )

    by_lane = {}

    for lane in sorted(set(row["lane"] for row in rows)):
        lane_rows = [r for r in rows if r["lane"] == lane]
        n = len(lane_rows)

        by_lane[lane] = {
            "transactions": n,
            "recorded": sum(
                r["selected_card"] is not None
                for r in lane_rows
            ),
            "cash_quote_available": sum(
                r["cash_quote_available"]
                for r in lane_rows
            ),
            "source_pending": sum(
                r["source_pending"]
                for r in lane_rows
            ),
            "point_not_comparable": sum(
                r["point_not_comparable"]
                for r in lane_rows
            ),
            "recorded_rate_pct": percentage(
                sum(r["selected_card"] is not None
                    for r in lane_rows),
                n,
            ),
        }

    summary = {
        "transaction_count": total,
        "recorded_count": selected,
        "recorded_rate_pct": percentage(selected, total),
        "provisional_count": provisional,
        "provisional_rate_pct": percentage(
            provisional, total
        ),
        "unresolved_count": unresolved,
        "unresolved_rate_pct": percentage(
            unresolved, total
        ),
        "cash_quote_available": metric(
            "cash_quote_available"
        ),
        "bnk_full_comparison": metric(
            "bnk_full_comparison"
        ),
        "source_pending": metric("source_pending"),
        "point_not_comparable": metric(
            "point_not_comparable"
        ),
        "dongbaek_lane_unverified": metric(
            "dongbaek_lane_unverified"
        ),
        "authorization_verified": metric(
            "authorization_verified"
        ),
    }

    return {
        "report_type": "P1_BENEFIT_COVERAGE",
        "mode": data.get("mode"),
        "user_id": data.get("user_id"),
        "base_month": data.get("base_month"),
        "simulated_month": data.get("simulated_month"),
        "summary": summary,
        "by_lane": by_lane,
        "pending_rule_frequency": dict(
            pending_frequency.most_common()
        ),
        "point_rule_frequency": dict(
            point_frequency.most_common()
        ),
        "transactions": rows,
        "definitions": {
            "recorded_count": (
                "Number of transactions assigned to a "
                "payment candidate in simulation. "
                "Not confirmed payments."
            ),
            "cash_quote_available": (
                "At least one BNK candidate has a "
                "numeric simulated cash quote, "
                "including zero."
            ),
            "bnk_full_comparison": (
                "All BNK candidate benefits comparable "
                "under current engine policy."
            ),
            "source_pending": (
                "At least one target-eligible rule is "
                "pending or under review."
            ),
            "point_not_comparable": (
                "At least one applicable point rule "
                "lacks a comparable cash value."
            ),
            "authorization_verified": (
                "Explicit authorization verification "
                "recorded in transaction output."
            ),
        },
        "warnings": [
            "Metrics are not mutually exclusive.",
            "Rates use simulated transactions as denominator.",
            "ASSUMED rules are not verified product terms.",
            "No payment authorization has been performed.",
            "Merchant lane support is not independently verified.",
            "Dongbaek policy and balance may be synthetic.",
            "Not a real-world recommendation accuracy measure.",
        ],
    }


def save_report(report, output_prefix):
    prefix = Path(output_prefix)

    json_path = prefix.with_suffix(".json")
    csv_path = Path(str(prefix) + "_transactions.csv")

    json_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    rows = report["transactions"]

    columns = [
        "transaction_id",
        "date",
        "merchant_id",
        "lane",
        "amount_won",
        "selected_card",
        "selection_category",
        "selection_reason",
        "cash_quote_available",
        "cash_quote_won",
        "applied_benefit_won",
        "bnk_full_comparison",
        "source_pending",
        "point_not_comparable",
        "dongbaek_lane_unverified",
        "authorization_verified",
        "dongbaek_status",
        "pending_rule_ids",
        "point_rule_ids",
        "assumed_cash_rule_ids",
        "quality_flags",
    ]

    with csv_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=columns
        )
        writer.writeheader()

        for row in rows:
            record = dict(row)

            for key in (
                "pending_rule_ids",
                "point_rule_ids",
                "assumed_cash_rule_ids",
                "quality_flags",
            ):
                record[key] = ";".join(record[key])

            writer.writerow({
                key: record.get(key)
                for key in columns
            })

    return json_path, csv_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="mixed_result.json",
    )
    parser.add_argument(
        "--output-prefix",
        default="p1_coverage_report",
    )
    args = parser.parse_args()

    data = read_json(args.input)
    report = build_report(data)

    json_path, csv_path = save_report(
        report, args.output_prefix
    )

    summary = report["summary"]

    print("=== ONEPASS P1 COVERAGE REPORT ===")
    print("Transactions:", summary["transaction_count"])

    for label in (
        "recorded",
        "provisional",
        "unresolved",
    ):
        print(
            f"{label}: "
            f"{summary[label + '_count']} "
            f"({summary[label + '_rate_pct']}%)"
        )

    for key in (
        "cash_quote_available",
        "bnk_full_comparison",
        "source_pending",
        "point_not_comparable",
        "dongbaek_lane_unverified",
        "authorization_verified",
    ):
        item = summary[key]
        print(
            f"{key}: "
            f"{item['count']}/{summary['transaction_count']} "
            f"({item['percentage']}%)"
        )

    print("\n=== BY LANE ===")
    for lane, stats in report["by_lane"].items():
        print(lane, stats)

    print("\n=== PENDING RULES ===")
    for rule, count in report[
        "pending_rule_frequency"
    ].items():
        print(rule, count)

    print("\nSaved:", json_path)
    print("Saved:", csv_path)


if __name__ == "__main__":
    main()
