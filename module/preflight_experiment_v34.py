
"""OnePass v3.4 experiment preflight and provenance audit.

Validates:
- Local V2 population and card slots
- Nine S02 sensitivity inputs
- Simulator transaction source identity
- SHA256 fingerprints for reproducibility

Does NOT:
- modify NeonDB
- execute payment simulations
- change synthetic data
- claim merchant DB upload is complete

Usage:
    python preflight_experiment_v34.py
    python preflight_experiment_v34.py --require-v34
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import simulate_original_v2 as sim

from run_s02_sensitivity_batch import validate_inputs


ROOT = Path(__file__).resolve().parent

V2_DIR = ROOT / "v2_output"
S02_DIR = ROOT / "s02_sensitivity_inputs"

REPORT = ROOT / "experiment_preflight_v34.json"

EXPECTED_USERS = 240
EXPECTED_MEMBERS = 111
EXPECTED_SLOTS = 759
EXPECTED_TX = 7540
EXPECTED_V34_TOTAL = 217449500


def sha256_file(path):
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(path)

    digest = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def read_csv(path):
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(path)

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def check_local_v2():
    profile_path = (
        V2_DIR / "sim_user_profile_v2.csv"
    )

    slot_path = (
        V2_DIR / "sim_user_card_slot_v2.csv"
    )

    profiles = read_csv(profile_path)
    slots = read_csv(slot_path)

    profile_ids = [
        p["user_id"] for p in profiles
    ]

    slot_keys = [
        (
            s["user_id"],
            int(s["slot_no"]),
        )
        for s in slots
    ]

    if len(profiles) != EXPECTED_USERS:
        raise ValueError("V2_USER_COUNT_MISMATCH")

    if len(slots) != EXPECTED_SLOTS:
        raise ValueError("V2_SLOT_COUNT_MISMATCH")

    if len(set(profile_ids)) != len(profile_ids):
        raise ValueError("V2_DUPLICATE_USERS")

    if len(set(slot_keys)) != len(slot_keys):
        raise ValueError("V2_DUPLICATE_SLOTS")

    if not {
        uid for uid, _ in slot_keys
    }.issubset(set(profile_ids)):
        raise ValueError("V2_UNKNOWN_SLOT_USER")

    members = {
        p["user_id"]
        for p in profiles
        if p["dongbaek_usage_level"]
        != "NON_MEMBER"
    }

    db_owners = {
        s["user_id"]
        for s in slots
        if s["product_id"] == "PRD_DB_SYN"
    }

    if len(members) != EXPECTED_MEMBERS:
        raise ValueError("V2_MEMBER_COUNT_MISMATCH")

    if members != db_owners:
        raise ValueError(
            "V2_DONGBAEK_OWNER_MISMATCH"
        )

    return {
        "user_count": len(profiles),
        "member_count": len(members),
        "slot_count": len(slots),
        "profile_sha256": sha256_file(
            profile_path
        ),
        "slot_sha256": sha256_file(
            slot_path
        ),
        "user_ids": set(profile_ids),
    }


def check_transaction_source():
    source = Path(sim.SOURCE).resolve()

    grouped = sim.read_transactions(
        sim.SOURCE
    )

    txs = [
        tx
        for user_txs in grouped.values()
        for tx in user_txs
    ]

    tx_ids = [
        tx["transaction_id"]
        for tx in txs
    ]

    amount = sum(
        int(tx["amount_won"])
        for tx in txs
    )

    if len(grouped) != EXPECTED_USERS:
        raise ValueError(
            "SOURCE_USER_COUNT_MISMATCH"
        )

    if len(txs) != EXPECTED_TX:
        raise ValueError(
            "SOURCE_TRANSACTION_COUNT_MISMATCH"
        )

    if len(tx_ids) != len(set(tx_ids)):
        raise ValueError(
            "SOURCE_DUPLICATE_TRANSACTION_ID"
        )

    if any(
        int(tx["amount_won"]) <= 0
        for tx in txs
    ):
        raise ValueError(
            "SOURCE_INVALID_TRANSACTION_AMOUNT"
        )

    is_v34 = amount == EXPECTED_V34_TOTAL

    return {
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "user_count": len(grouped),
        "transaction_count": len(txs),
        "transaction_amount_won": amount,
        "expected_v34_amount_won": (
            EXPECTED_V34_TOTAL
        ),
        "amount_matches_v34": is_v34,
        "user_ids": set(grouped),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--require-v34",
        action="store_true",
        help=(
            "Fail if simulator source does not "
            "match v3.4 expected amount"
        ),
    )

    parser.add_argument(
        "--report",
        type=Path,
        default=REPORT,
    )

    args = parser.parse_args()

    print("=== ONEPASS V3.4 EXPERIMENT PREFLIGHT ===")

    # 1. Local V2 input
    v2 = check_local_v2()

    print("\n[V2]")
    print("Users:", v2["user_count"])
    print("Members:", v2["member_count"])
    print("Slots:", v2["slot_count"])

    # 2. S02 scenario validation
    scenarios = validate_inputs(
        S02_DIR
    )

    if len(scenarios) != 9:
        raise ValueError(
            "S02_SCENARIO_COUNT_MISMATCH"
        )

    scenario_hashes = {
        item["scenario_id"]: sha256_file(
            item["input_path"]
        )
        for item in scenarios
    }

    # 3. Actual simulator input
    source = check_transaction_source()

    print("\n[SIMULATOR SOURCE]")
    print("Path:", source["source_path"])
    print("Users:", source["user_count"])
    print(
        "Transactions:",
        source["transaction_count"],
    )
    print(
        "Amount:",
        source["transaction_amount_won"],
    )
    print(
        "v3.4 amount match:",
        source["amount_matches_v34"],
    )

    # 4. Cross-input user consistency
    if v2["user_ids"] != source["user_ids"]:
        raise ValueError(
            "V2_SOURCE_USER_SET_MISMATCH"
        )

    # 5. Record provenance.
    # This does not verify merchant DB contents.
    report = {
        "experiment": "ONEPASS_V34",
        "generated_at_utc": (
            datetime.now(timezone.utc).isoformat()
        ),
        "data_version_expected": "v3.4",
        "v2_population": {
            k: v
            for k, v in v2.items()
            if k != "user_ids"
        },
        "transaction_source": {
            k: v
            for k, v in source.items()
            if k != "user_ids"
        },
        "s02": {
            "scenario_count": len(scenarios),
            "manifest_sha256": sha256_file(
                S02_DIR / "manifest.json"
            ),
            "scenario_input_sha256": (
                scenario_hashes
            ),
        },
        "auto_topup_assumptions": {
            "consent_rates_pct": [
                25,
                38.4,
                50,
            ],
            "funding_levels_won": [
                100000,
                180000,
                300000,
            ],
            "consent_is_observed": False,
            "funding_is_observed_balance": False,
        },
        "merchant_db_version_verified": False,
        "database_modified": False,
        "simulation_executed": False,
        "status": (
            "SOURCE_V34_AMOUNT_MATCHED_"
            "MERCHANT_DB_UNVERIFIED"
            if source["amount_matches_v34"]
            else "BLOCKED_OLD_TRANSACTION_SOURCE"
        ),
    }

    args.report.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.report.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== PREFLIGHT RESULT ===")
    print("Status:", report["status"])
    print("Report:", args.report)
    print("DATABASE MODIFIED: NO")
    print("SIMULATION: NOT EXECUTED")

    if (
        args.require_v34
        and not source["amount_matches_v34"]
    ):
        raise ValueError(
            "V34_SOURCE_NOT_READY"
        )


if __name__ == "__main__":
    main()
