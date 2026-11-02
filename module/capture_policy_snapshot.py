"""Read-only OnePass experiment state fingerprint.

Commands:
    python capture_policy_snapshot.py --validate-only
    python capture_policy_snapshot.py --capture --label S01
    python capture_policy_snapshot.py --capture --label S02
    python capture_policy_snapshot.py --compare snapshots/S01.json snapshots/S02.json

Only --capture connects to NeonDB, using a read-only repeatable-read transaction.
Hashes are derived from full DB rows; raw values/PII/database credentials aren't saved.
A comparison proves the sampled records matched at capture time, NOT that the
simulation consumed them or that the state stayed unchanged during execution.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "policy_snapshots_v34"

# Grounded in simulate_original_v2.py and its repositories.
POLICY_TABLES = (
    "db_policy", "db_policy_rate",
    "benefit_rule", "benefit_industry", "benefit_cap_tier",
    "benefit_category_map",
)
# Separate operational state from published policy (different reasons to change).
STATE_TABLES = (
    "merchant", "db_wallet", "sim_user_profile_v2",
    "sim_user_card_slot_v2",
    "card_product", "card_source_detail", "card_benefit_source",
    "card_month_close", "card_perf_month_close", "user_card",
)
# A change to simulation code can change results with unchanged DB tables.
CODE_FILES = (
    "simulate_original_v2.py", "simulate_onepass_v2.py",
    "run_s02_auto_topup.py", "run_s02_sensitivity_batch.py",
    "compare_four_scenarios.py",
    "demo_p1_one_transaction.py", "demo_p1_mvp_batch.py",
    "onepass/db_policy_repository.py", "onepass/db_connection.py",
    "onepass/p1_fast_repositories.py", "onepass/p1_rule_repository.py",
    "onepass/p1_rule_engine.py", "onepass/p1_mvp_quote.py",
    "onepass/p1_eligibility_repository.py", "onepass/p1_target_evaluator.py",
    "onepass/p1_channel_evaluator.py", "onepass/p1_monthly_db_repository.py",
    "onepass/p1_monthly_limits.py", "onepass/p1_monthly_state.py",
    "onepass/p1_dongbaek_candidate.py", "onepass/auto_topup.py",
)


def clean(value):
    """Canonical, type-stable JSON encoding for hashing; never exposed raw."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return {"decimal": str(value.normalize()) if value else "0"}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("NONFINITE_DB_FLOAT")
        return {"float": repr(value)}
    if isinstance(value, (datetime, date, time)):
        return {"date_time": value.isoformat()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"bytes": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    raise TypeError(f"UNSUPPORTED_DB_TYPE:{type(value).__name__}")


def canonical(obj):
    return json.dumps(clean(obj), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def local_hashes():
    result = {}
    for name in CODE_FILES:
        path = ROOT / name
        if path.exists():
            result[name] = file_hash(path)
        else:
            result[name] = None
    return result


def table_hash(cur, name):
    # Names are fixed in this file, never supplied by CLI or user input.
    cur.execute(f'SELECT * FROM public."{name}"')
    names = [c.name for c in cur.description]
    entries = []
    for row in cur:
        item = dict(zip(names, row)) if not isinstance(row, dict) else row
        entries.append(digest(canonical(item)))
    entries.sort()  # stable regardless of SQL row iteration order
    return {"count": len(entries), "sha256": digest(canonical(entries))}


def capture(label, output):
    from onepass.db_connection import connect_readonly
    # Repeatable-read ensures all queries in this capture see one consistent DB snapshot.
    with connect_readonly() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cur.execute("SELECT current_database()")
            db_row = cur.fetchone()
            db_name = db_row["current_database"] if isinstance(db_row, dict) else db_row[0]
            policies = {t: table_hash(cur, t) for t in POLICY_TABLES}
            states = {t: table_hash(cur, t) for t in STATE_TABLES}
        conn.rollback()  # explicitly no persistence

    code = local_hashes()
    # Do not store DB name or credentials; hash db name only as an advisory identifier.
    report = {
        "schema_version": 1,
        "label": label,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "db_name_sha256": digest(str(db_name).encode("utf-8")),
        "policy_tables": policies,
        "state_tables": states,
        "policy_fingerprint": digest(canonical(policies)),
        "state_fingerprint": digest(canonical(states)),
        "code_files": code,
        "code_fingerprint": digest(canonical(code)),
        "read_only": True,
        "consistency": "single_read_only_repeatable_read_db_snapshot",
        "limitation": "capture alone does not verify what engine consumed during a run",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Never silently overwrite an existing evidence snapshot.
    with output.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return report


def compare(a_path, b_path):
    a = json.loads(Path(a_path).read_text(encoding="utf-8"))
    b = json.loads(Path(b_path).read_text(encoding="utf-8"))
    if a.get("schema_version") != 1 or b.get("schema_version") != 1:
        raise ValueError("INCOMPATIBLE_SNAPSHOT_SCHEMA")
    print("=== SNAPSHOT COMPARISON ===")
    failed = []
    for key in ("db_name_sha256", "policy_fingerprint",
                "state_fingerprint", "code_fingerprint"):
        equal = a.get(key) == b.get(key)
        print(f"{key}: {'MATCH' if equal else 'DIFFERENT'}")
        if not equal:
            failed.append(key)
    for section in ("policy_tables", "state_tables", "code_files"):
        differences = sorted(k for k in set(a.get(section, {})) | set(b.get(section, {}))
                             if a.get(section, {}).get(k) != b.get(section, {}).get(k))
        if differences:
            print(section + " changes: " + ", ".join(differences))
    if failed:
        raise SystemExit("SNAPSHOTS_DIFFER: " + ", ".join(failed))
    print("SNAPSHOTS MATCH (at capture time only)")


def main():
    p = argparse.ArgumentParser()
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument("--validate-only", action="store_true")
    m.add_argument("--capture", action="store_true")
    m.add_argument("--compare", nargs=2, metavar=("FIRST_JSON", "SECOND_JSON"))
    p.add_argument("--label", choices=("PRE", "POST", "S00", "S10", "S01", "S11", "S02"))
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    if args.validate_only:
        print("=== POLICY SNAPSHOT CONFIG VALIDATION ===")
        print("Policy tables:", len(POLICY_TABLES))
        print("State tables:", len(STATE_TABLES))
        local = local_hashes()
        missing = [name for name, value in local.items() if value is None]
        if missing:
            print("Missing optional tracked files:", ", ".join(missing))
            print("WARNING: update CODE_FILES for actual engine sources")
        print("CONFIGURATION:", "INCOMPLETE_LOCAL_SOURCES" if missing else "PASSED")
        print("DATABASE: NOT ACCESSED")
        print("SIMULATION: NOT EXECUTED")
        return

    if args.compare:
        compare(*args.compare)
        return

    if not args.label:
        p.error("--capture requires --label")
    output = args.output or OUT / (args.label + ".json")
    report = capture(args.label, output)
    print("CAPTURE SAVED:", output)
    print("POLICY SHA256:", report["policy_fingerprint"])
    print("STATE SHA256:", report["state_fingerprint"])
    print("CODE SHA256:", report["code_fingerprint"])
    print("DATABASE MODIFIED: NO")


if __name__ == "__main__":
    main()
