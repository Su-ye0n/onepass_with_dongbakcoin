"""Compare S02 auto-topup sensitivity results with the exact S01 baseline.

Default --validate-only: validates experiment inputs and configuration only.
--run: reads completed CSV/JSON output; does not run simulation or write to DB.

Strictly checks transaction identity, amount, users, per-row & per-user benefit
reconciliation, summary totals, auto-topup consent/selection, and data version.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "s02_sensitivity_inputs"
BASELINE = ROOT / "four_scenario_analysis_v34"
S02_RESULTS = ROOT / "s02_sensitivity_results"
OUTPUT = ROOT / "s02_sensitivity_comparison_v34"
EXPECTED_USERS = 240
EXPECTED_TRANSACTIONS = 7540
EXPECTED_AMOUNT = 217449500
EXPECTED_RATES = {Decimal("25"), Decimal("38.4"), Decimal("50")}
EXPECTED_FUNDING = {100000, 180000, 300000}
DB_CARD = "PRD_DB_SYN"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def get_json(path):
    require(path.is_file(), f"MISSING_FILE:{path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def get_csv(path, required):
    require(path.is_file(), f"MISSING_FILE:{path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        require(set(required).issubset(reader.fieldnames or []),
                f"INVALID_COLUMNS:{path.name}:{sorted(set(required)-set(reader.fieldnames or []))}")
        rows = list(reader)
    require(rows, f"EMPTY_CSV:{path}")
    return rows


def as_int(value, label):
    try:
        result = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"INVALID_INTEGER:{label}:{value}") from exc
    return result


def index_rows(rows, field, label):
    index = {}
    for r in rows:
        key = r[field]
        require(bool(key), f"EMPTY_KEY:{label}")
        require(key not in index, f"DUPLICATE_KEY:{label}:{key}")
        index[key] = r
    return index


def signature(rows):
    """Deterministic transaction content fingerprint, independent of row order."""
    parts = sorted(
        (r["transaction_id"], r["user_id"], r["merchant_id"],
         str(as_int(r["amount_won"], "amount_won")), r["requested_at"], r["lane"])
        for r in rows
    )
    h = hashlib.sha256()
    for row in parts:
        h.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def read_manifest(input_dir):
    doc = get_json(input_dir / "manifest.json")
    require(doc.get("scenario_count") == 9 and len(doc.get("scenarios", [])) == 9,
            "INVALID_SCENARIO_COUNT")
    require(doc.get("user_count") == EXPECTED_USERS, "INVALID_MANIFEST_USERS")
    require(doc.get("dongbaek_member_count") == 111, "INVALID_MANIFEST_MEMBERS")
    require(doc.get("nonmember_count") == 129, "INVALID_MANIFEST_NONMEMBERS")
    require(doc.get("nested_consent_cohorts") is True, "NESTING_NOT_CONFIRMED")
    seen, combos, cohorts = set(), set(), {}
    scenarios = []
    reference_users = None
    for e in doc["scenarios"]:
        rate = Decimal(str(e["consent_rate_assumption_pct"]))
        funding = as_int(e["funding_per_consent_user_won"], "funding")
        require(rate in EXPECTED_RATES and funding in EXPECTED_FUNDING,
                f"UNEXPECTED_SCENARIO_PARAMETERS:{rate}:{funding}")
        label = format(rate, "f")
        if "." in label:
            label = label.rstrip("0").rstrip(".")
        sid = f"S02_C{label.replace('.', 'P')}_F{funding}"
        require(e["scenario_id"] == sid and e["input_file"] == f"{sid}.csv",
                f"SCENARIO_ID_OR_FILE_MISMATCH:{sid}")
        require(sid not in seen and (rate, funding) not in combos,
                f"DUPLICATE_SCENARIO:{sid}")
        seen.add(sid)
        combos.add((rate, funding))
        assumptions = get_csv(input_dir / f"{sid}.csv",
                              ("user_id", "auto_topup_consent", "funding_balance_won"))
        by_user = index_rows(assumptions, "user_id", sid)
        require(len(by_user) == EXPECTED_USERS, f"ASSUMPTION_USER_COUNT:{sid}")
        if reference_users is None:
            reference_users = set(by_user)
        require(set(by_user) == reference_users, f"ASSUMPTION_COHORT_MISMATCH:{sid}")
        consenting = set()
        for uid, row in by_user.items():
            val = row["auto_topup_consent"].lower().strip()
            require(val in ("true", "false", "1", "0"), f"INVALID_CONSENT:{sid}:{uid}")
            consent = val in ("true", "1")
            expected_funding = funding if consent else 0
            require(as_int(row["funding_balance_won"], "funding_balance_won") == expected_funding,
                    f"FUNDING_MISMATCH:{sid}:{uid}")
            if consent:
                consenting.add(uid)
        require(len(consenting) == as_int(e["consenting_user_count"], "consenting_user_count"),
                f"CONSENT_COUNT_MISMATCH:{sid}")
        require(len(consenting) * funding == as_int(e["total_assumed_funding_won"], "total_assumed_funding_won"),
                f"FUNDING_TOTAL_MISMATCH:{sid}")
        cohorts[(rate, funding)] = consenting
        scenarios.append({"scenario_id": sid, "consent_rate_pct": float(rate),
                          "rate": rate, "funding_won": funding,
                          "consenting_users": consenting, "assumptions": by_user})
    require(combos == {(r, f) for r in EXPECTED_RATES for f in EXPECTED_FUNDING},
            "SCENARIO_GRID_MISMATCH")
    for rate in EXPECTED_RATES:
        require(len({frozenset(cohorts[(rate, f)]) for f in EXPECTED_FUNDING}) == 1,
                f"CONSENT_COHORT_DIFFERS_BY_FUNDING:{rate}")
    for funding in EXPECTED_FUNDING:
        prev = set()
        for rate in sorted(EXPECTED_RATES):
            current = cohorts[(rate, funding)]
            require(prev.issubset(current), f"CONSENT_NESTING_FAILED:{rate}:{funding}")
            prev = current
    scenarios.sort(key=lambda x: (x["rate"], x["funding_won"]))
    return scenarios, reference_users


def baseline_data(base_dir):
    report = get_json(base_dir / "summary.json")
    meta = report.get("methodology", {})
    require("V3_4" in str(meta.get("data", "")).upper() or report.get("data_version") == "v3.4",
            "BASELINE_DATA_VERSION_NOT_V34")
    rows = get_csv(base_dir / "transactions.csv",
                   ("transaction_id", "user_id", "merchant_id", "amount_won", "requested_at", "lane",
                    "S01_selected_card", "S01_benefit_won"))
    users = get_csv(base_dir / "users.csv", ("user_id", "S01_benefit_won"))
    tx = index_rows(rows, "transaction_id", "S01_TX")
    by_user = index_rows(users, "user_id", "S01_USER")
    require(len(tx) == EXPECTED_TRANSACTIONS and len(by_user) == EXPECTED_USERS,
            "S01_POPULATION_MISMATCH")
    require(sum(as_int(r["amount_won"], "S01_AMOUNT") for r in rows) == EXPECTED_AMOUNT,
            "S01_AMOUNT_NOT_V34")
    s01_sum = sum(as_int(r["S01_benefit_won"], "S01_BENEFIT") for r in rows)
    require(s01_sum == sum(as_int(r["S01_benefit_won"], "S01_USER_BENEFIT") for r in users),
            "S01_USER_TX_BENEFIT_MISMATCH")
    require(s01_sum == as_int(report["summaries"]["S01"]["estimated_benefit_won"], "S01_SUMMARY_BENEFIT"),
            "S01_REPORTED_BENEFIT_MISMATCH")
    return report, rows, tx, by_user, signature(rows), s01_sum


def analyze_one(s, baseline_rows, base_tx, base_users, base_sig, base_total, result_dir):
    sid = s["scenario_id"]
    folder = result_dir / sid
    meta = get_json(folder / "summary.json")
    rows = get_csv(folder / "transactions.csv",
                   ("transaction_id", "user_id", "merchant_id", "amount_won", "requested_at", "lane",
                    "selected_card", "estimated_benefit_won", "auto_topup_committed_won", "auto_topup_consent"))
    users = get_csv(folder / "users.csv",
                    ("user_id", "estimated_benefit_won", "auto_topup_total_won", "auto_topup_event_count"))
    tx = index_rows(rows, "transaction_id", sid + "_TX")
    usr = index_rows(users, "user_id", sid + "_USER")
    require(set(tx) == set(base_tx), f"TRANSACTION_IDS_MISMATCH:{sid}")
    require(set(usr) == set(base_users), f"USER_IDS_MISMATCH:{sid}")
    require(signature(rows) == base_sig, f"TRANSACTION_CONTENT_MISMATCH:{sid}")
    require(len(tx) == EXPECTED_TRANSACTIONS and len(usr) == EXPECTED_USERS,
            f"POPULATION_MISMATCH:{sid}")
    require(meta.get("selection_policy") == "ONEPASS_GREEDY" and
            meta.get("wallet_policy") == "CONDITIONAL_AUTO_TOPUP", f"POLICY_MISMATCH:{sid}")
    require(meta.get("simulation_only") is True and meta.get("real_authorization") is False,
            f"SIMULATION_METADATA_MISMATCH:{sid}")
    require(meta.get("consenting_users") == len(s["consenting_users"]),
            f"CONSENT_COUNT_MISMATCH:{sid}")
    require(meta.get("transaction_count") == EXPECTED_TRANSACTIONS and
            meta.get("transaction_amount_won") == EXPECTED_AMOUNT and
            meta.get("user_count") == EXPECTED_USERS, f"SUMMARY_POPULATION_MISMATCH:{sid}")
    require(str(meta.get("assumptions", {}).get("consent_source", "")).endswith(f"{sid}.csv"),
            f"ASSUMPTION_SOURCE_MISMATCH:{sid}")
    s02_sum, topup_sum, events, db_count, changes, upshift = 0, 0, 0, 0, 0, 0
    benefit_by_user = defaultdict(int)
    topup_by_user = defaultdict(int)
    rows_comparison = []
    for base in baseline_rows:
        tid = base["transaction_id"]
        current = tx[tid]
        uid = current["user_id"]
        benefit_before = as_int(base["S01_benefit_won"], "base_benefit")
        benefit_after = as_int(current["estimated_benefit_won"], "s02_benefit")
        topup = as_int(current["auto_topup_committed_won"], "topup")
        consent = uid in s["consenting_users"]
        actual_consent = str(current["auto_topup_consent"]).strip().lower() in ("true", "1")
        require(actual_consent == consent, f"CONSENT_TX_MISMATCH:{sid}:{tid}")
        require(topup >= 0 and (consent or topup == 0), f"TOPUP_WITHOUT_CONSENT:{sid}:{tid}")
        require(current["selected_card"] == DB_CARD or topup == 0,
                f"TOPUP_WITHOUT_DB_SELECTION:{sid}:{tid}")
        s02_sum += benefit_after
        topup_sum += topup
        benefit_by_user[uid] += benefit_after
        topup_by_user[uid] += topup
        db_count += current["selected_card"] == DB_CARD
        changed = current["selected_card"] != base["S01_selected_card"]
        changes += changed
        upshift += current["selected_card"] == DB_CARD and base["S01_selected_card"] != DB_CARD
        rows_comparison.append({"scenario_id": sid, "transaction_id": tid, "user_id": uid,
                                "amount_won": base["amount_won"],
                                "S01_selected_card": base["S01_selected_card"],
                                "S02_selected_card": current["selected_card"],
                                "S01_benefit_won": benefit_before,
                                "S02_benefit_won": benefit_after,
                                "benefit_delta_won": benefit_after - benefit_before,
                                "topup_committed_won": topup})
    for uid, row in usr.items():
        require(as_int(row["estimated_benefit_won"], "USER_BENEFIT") == benefit_by_user[uid],
                f"USER_BENEFIT_RECONCILIATION:{sid}:{uid}")
        require(as_int(row["auto_topup_total_won"], "USER_TOPUP") == topup_by_user[uid],
                f"USER_TOPUP_RECONCILIATION:{sid}:{uid}")
        events += as_int(row["auto_topup_event_count"], "EVENT_COUNT")
    require(s02_sum == meta["estimated_benefit_won"], f"SUMMARY_BENEFIT_MISMATCH:{sid}")
    require(topup_sum == meta["auto_topup_total_won"] and events == meta["auto_topup_event_count"],
            f"SUMMARY_TOPUP_MISMATCH:{sid}")
    require(db_count == meta["dongbaek_count"], f"SUMMARY_DB_COUNT_MISMATCH:{sid}")
    delta = s02_sum - base_total
    result = {"scenario_id": sid, "consent_rate_pct": s["consent_rate_pct"],
              "consenting_users": len(s["consenting_users"]), "funding_per_user_won": s["funding_won"],
              "assumed_total_funding_won": len(s["consenting_users"]) * s["funding_won"],
              "S01_benefit_won": base_total, "S02_benefit_won": s02_sum,
              "benefit_increase_won": delta,
              "benefit_increase_pct": round(delta / base_total * 100, 4) if base_total else None,
              "benefit_increase_per_consent_user_won": round(delta / len(s["consenting_users"]), 2)
              if s["consenting_users"] else None,
              "S01_dongbaek_count": sum(r["S01_selected_card"] == DB_CARD for r in baseline_rows),
              "S02_dongbaek_count": db_count, "new_dongbaek_selections": upshift,
              "changed_card_selections": changes,
              "auto_topup_total_won": topup_sum, "auto_topup_event_count": events,
              "source_transaction_sha256": base_sig}
    result["dongbaek_selection_increase"] = result["S02_dongbaek_count"] - result["S01_dongbaek_count"]
    return result, rows_comparison


def write_csv(path, rows):
    require(bool(rows), f"NO_OUTPUT_ROWS:{path}")
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", type=Path, default=INPUT)
    ap.add_argument("--baseline-dir", type=Path, default=BASELINE)
    ap.add_argument("--s02-results-dir", type=Path, default=S02_RESULTS)
    ap.add_argument("--output-dir", type=Path, default=OUTPUT)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = ap.parse_args()

    scenarios, users = read_manifest(args.input_dir)
    print("=== S02 ANALYSIS CONFIG VALIDATION ===")
    print("Users:", len(users), "| Scenarios:", len(scenarios))
    print("Consent cohorts:", sorted({len(s["consenting_users"]) for s in scenarios}))
    print("Funding levels:", sorted(EXPECTED_FUNDING))
    print("SCENARIO CONFIGURATION: PASSED")
    if not args.run:
        print("RESULT FILES: NOT REQUIRED")
        print("SIMULATION: NOT EXECUTED")
        print("DATABASE: NOT MODIFIED")
        return

    report, baseline_rows, base_tx, base_users, base_sig, benefit = baseline_data(args.baseline_dir)
    require(set(base_users) == users, "BASELINE_USERS_DIFFER_FROM_ASSUMPTIONS")
    print("S01 BASELINE:", benefit, "| Transaction SHA256:", base_sig)
    results, detail = [], []
    for scenario in scenarios:
        item, rows = analyze_one(scenario, baseline_rows, base_tx, base_users,
                                 base_sig, benefit, args.s02_results_dir)
        print(item["scenario_id"], "| delta:", item["benefit_increase_won"],
              "| topup:", item["auto_topup_total_won"])
        results.append(item)
        detail.extend(rows)

    # Same rate: funding increases should not reduce benefit in the greedy model
    # is NOT guaranteed because sequential choices and caps may interact.
    # Report any observed decline, do not silently normalize results.
    comparisons = []
    for rate in sorted(EXPECTED_RATES):
        group = sorted((r for r in results if Decimal(str(r["consent_rate_pct"])) == rate),
                       key=lambda x: x["funding_per_user_won"])
        for previous, current in zip(group, group[1:]):
            comparisons.append({"consent_rate_pct": float(rate),
                                "from_funding_won": previous["funding_per_user_won"],
                                "to_funding_won": current["funding_per_user_won"],
                                "additional_benefit_won": current["S02_benefit_won"] - previous["S02_benefit_won"],
                                "no_additional_benefit_observed": current["S02_benefit_won"] == previous["S02_benefit_won"]})
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"ANALYSIS_OUTPUT_DIR_NOT_EMPTY:{args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "s02_vs_s01_summary.csv", results)
    write_csv(args.output_dir / "s02_vs_s01_transactions.csv", detail)
    write_csv(args.output_dir / "funding_step_comparison.csv", comparisons)
    (args.output_dir / "analysis.json").write_text(json.dumps({"data_version": "v3.4",
        "baseline": "S01_ONEPASS_CURRENT_BALANCE", "scenario": "S02_CONDITIONAL_AUTO_TOPUP",
        "source_transaction_sha256": base_sig,
        "observed_auto_topup_consent": False,
        "funding_is_observed_bank_balance": False,
        "comparison_results": results, "funding_step_comparisons": comparisons},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESULT RECONCILIATION: PASSED")
    print("ANALYSIS SAVED:", args.output_dir)
    print("DATABASE: NOT MODIFIED")


if __name__ == "__main__":
    main()
