
"""Diagnose mixed OnePass P1 batch results.

Input: JSON output from demo_p1_batch.py
No DB changes.
"""

import argparse
import json
from pathlib import Path


def load_json(path):
    raw = Path(path).read_bytes()

    # PowerShell 5.1 redirection can produce UTF-16.
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return json.loads(raw.decode("utf-16"))

    if raw.startswith(b"\xef\xbb\xbf"):
        return json.loads(raw.decode("utf-8-sig"))

    return json.loads(raw.decode("utf-8"))


def classify_rule(rule):
    target = rule.get("target_channel_status")
    status = rule.get("status")
    reason = rule.get("reason", "UNKNOWN")

    if target == "INELIGIBLE":
        return "TARGET_OR_CHANNEL_EXCLUDED"

    if target == "UNRESOLVED":
        return "TARGET_OR_CHANNEL_UNRESOLVED"

    if status == "ELIGIBLE":
        return "CASH_BENEFIT_CALCULATED"

    if status == "POINT_INFORMATION":
        return "POINT_BENEFIT_NOT_COMPARABLE"

    if status == "INELIGIBLE":
        return "BENEFIT_CONDITION_NOT_MET"

    if status in {"PENDING_REVIEW", "UNRESOLVED"}:
        return "BENEFIT_RULE_UNRESOLVED"

    return f"OTHER:{status}:{reason}"


def diagnose_transaction(tx):
    candidates = tx.get("bnk_candidates", [])
    comparison = tx.get("bnk_comparison", {})
    change = tx.get("state_change") or {}

    selected = tx.get("selected_card")
    cash_leader = comparison.get("cash_leader")

    reasons = []

    if not candidates:
        reasons.append("RULE_DETAILS_NOT_IN_JSON")

    if comparison.get("review_candidates"):
        reasons.append("SOME_CARD_BENEFITS_UNRESOLVED")

    if cash_leader is None:
        reasons.append("NO_COMPARABLE_CASH_CANDIDATE")

    if selected is None:
        reasons.append("NO_CARD_RECORDED")

    if change.get("updated") is False:
        reasons.append(
            "STATE_UPDATE_FAILED:"
            + str(change.get("reason", "UNKNOWN"))
        )

    if tx.get("lane") != "OFFLINE":
        reasons.append(
            "NON_OFFLINE_LANE_REQUIRES_CHANNEL_REVIEW"
        )

    return reasons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default="mixed_result.json",
    )
    args = parser.parse_args()

    data = load_json(args.path)

    print("=== TRANSACTION DIAGNOSIS ===")

    for tx in data["transactions"]:
        print()
        print(
            f"[{tx['transaction_id']}] "
            f"merchant={tx['merchant_id']} "
            f"lane={tx['lane']}"
        )

        print(
            "selected=",
            tx.get("selected_card"),
            "| status=",
            tx.get("selection_status"),
            "| reason=",
            tx.get("selection_reason"),
        )

        print(
            "payment_eligibility=",
            tx.get(
                "payment_eligibility",
                {"status": "NOT_VERIFIED"},
            ),
        )

        print(
            "recording_reason=",
            tx.get("recording_reason"),
        )

        for reason in diagnose_transaction(tx):
            print("  DIAGNOSIS:", reason)

        for card in tx.get("bnk_candidates", []):
            print(
                "  CARD:",
                card["product_id"],
                "status=", card["status"],
                "cash=", card["cash_benefit_won"],
            )

            for rule in card.get("rules", []):
                print(
                    "    RULE:",
                    rule["rule_id"],
                    "|", classify_rule(rule),
                    "| target=",
                    rule.get("target_channel_status"),
                    "| status=",
                    rule.get("status"),
                    "| benefit=",
                    rule.get("benefit_won"),
                    "| source=",
                    rule.get("source_status"),
                    "| reason=",
                    rule.get("reason"),
                )

    print()
    print("=== SUMMARY ===")
    for key, value in data["totals"].items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
