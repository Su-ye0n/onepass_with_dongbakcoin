"""Resume the 9-scenario S02 v3.4 experiment without overwriting finished runs.
Place next to run_s02_sensitivity_batch.py and run_s02_auto_topup.py.
Read-only NeonDB; creates missing local output directories and aggregate summaries.
"""
import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import run_s02_sensitivity_batch as batch

FIELDS = [
    "user_count", "consenting_users", "transaction_count",
    "transaction_amount_won", "assigned_count", "unresolved_count",
    "dongbaek_count", "bnk_count", "estimated_benefit_won",
    "auto_topup_total_won", "auto_topup_event_count",
]


def check(summary, scenario):
    sid = scenario["scenario_id"]
    for field in FIELDS:
        if field not in summary:
            raise ValueError(f"MISSING_SUMMARY_FIELD:{sid}:{field}")
    expected = {
        "user_count": batch.EXPECTED_USERS,
        "transaction_count": batch.EXPECTED_TRANSACTIONS,
        "transaction_amount_won": batch.EXPECTED_V34_AMOUNT,
        "consenting_users": scenario["consenting_users"],
    }
    for field, value in expected.items():
        if summary[field] != value:
            raise ValueError(f"SUMMARY_MISMATCH:{sid}:{field}:{summary[field]} != {value}")
    if summary["assigned_count"] + summary["unresolved_count"] != summary["transaction_count"]:
        raise ValueError(f"COUNT_NOT_CONSERVED:{sid}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", type=Path, default=Path("s02_sensitivity_inputs"))
    p.add_argument("--output-dir", type=Path, default=Path("s02_sensitivity_results"))
    p.add_argument("--min-topup", type=int, default=10000)
    p.add_argument("--per-topup-cap", type=int, default=100000)
    p.add_argument("--monthly-cap", type=int, default=300000)
    p.add_argument("--wallet-cap", type=int, default=500000)
    p.add_argument("--validate-only", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--data-v34-confirmed", action="store_true")
    args = p.parse_args()
    batch.runner.validate_policy_args(args)
    scenarios = batch.validate_inputs(args.input_dir)  # checks complete 9-scenario manifest and nested cohorts
    completed, pending = [], []
    for s in scenarios:
        target = args.output_dir / s["scenario_id"]
        summary_file = target / "summary.json"
        if summary_file.is_file():
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
            check(summary, s)
            # Require all files from completed scenario, not merely the JSON.
            for name in ("transactions.csv", "users.csv"):
                if not (target / name).is_file():
                    raise FileNotFoundError(f"INCOMPLETE_SAVED_RUN:{target / name}")
            completed.append(s["scenario_id"])
        elif target.exists():
            raise FileExistsError(f"PARTIAL_RUN_DIRECTORY_REQUIRES_REVIEW:{target}")
        else:
            pending.append(s)
    print("\n=== RESUME PLAN ===")
    print("Already complete:", len(completed), completed)
    print("Pending:", len(pending), [s["scenario_id"] for s in pending])
    if not args.run:
        print("DRY RUN: NO CHANGES")
        return
    if not args.data_v34_confirmed:
        raise ValueError("V34_DATA_CONFIRMATION_REQUIRED")
    batch.verify_v34_source()
    if (args.output_dir / "sensitivity_summary.json").exists() or (args.output_dir / "sensitivity_summary.csv").exists():
        raise FileExistsError("AGGREGATE_SUMMARY_ALREADY_EXISTS: no overwrite allowed")
    for s in pending:
        sid = s["scenario_id"]
        print("\nRUNNING MISSING:", sid, flush=True)
        run_args = SimpleNamespace(
            assumptions=s["input_path"],
            output=args.output_dir / sid,
            limit=None,
            min_topup=args.min_topup,
            per_topup_cap=args.per_topup_cap,
            monthly_cap=args.monthly_cap,
            wallet_cap=args.wallet_cap,
        )
        assumptions = batch.runner.load_assumptions(run_args.assumptions)
        summary = batch.runner.run_s02(run_args, assumptions)
        check(summary, s)
    results = []
    for s in scenarios:
        summary = json.loads((args.output_dir / s["scenario_id"] / "summary.json").read_text(encoding="utf-8"))
        check(summary, s)
        results.append({
            "scenario_id": s["scenario_id"],
            "consent_rate_pct": float(s["rate"]),
            "funding_per_user_won": s["funding"],
            **{field: summary[field] for field in FIELDS},
        })
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "sensitivity_summary.csv").open("x", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    with (args.output_dir / "sensitivity_summary.json").open("x", encoding="utf-8") as f:
        json.dump({
            "experiment": "S02_AUTO_TOPUP_SENSITIVITY_V34",
            "data_version": "v3.4",
            "scenario_count": 9,
            "simulation_only": True,
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print("\nBATCH RESUMED AND COMPLETE: 9/9")
    print("Saved:", args.output_dir)


if __name__ == "__main__":
    main()
