
"""S02: OnePass with conditional synthetic auto-topup.

S00/S10/S01/S11 remain unchanged.

Requires explicit user-level consent and funding inputs.
Does not infer consent from Dongbaek membership.

Default: input validation only.
Full simulation requires --run.

No real payment or NeonDB writes.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

import simulate_original_v2 as sim

from onepass.auto_topup import AutoTopupPolicy
from onepass.db_policy_repository import DongbaekDBRepository


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "s02_auto_topup_users.csv"
OUTPUT = ROOT / "s02_auto_topup_analysis"


def parse_bool(value):
    value = str(value).strip().lower()

    if value in {"true", "1", "yes"}:
        return True

    if value in {"false", "0", "no"}:
        return False

    raise ValueError(
        f"INVALID_CONSENT_VALUE:{value}"
    )


def load_assumptions(path):
    """Load explicit user-level synthetic assumptions."""

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)

        required = {
            "user_id",
            "auto_topup_consent",
            "funding_balance_won",
        }

        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                "INVALID_S02_INPUT_COLUMNS"
            )

        rows = list(reader)

    if not rows:
        raise ValueError("EMPTY_S02_ASSUMPTIONS")

    result = {}

    for row in rows:
        user_id = row["user_id"].strip()

        if not user_id:
            raise ValueError("EMPTY_USER_ID")

        if user_id in result:
            raise ValueError(
                f"DUPLICATE_S02_USER:{user_id}"
            )

        consent = parse_bool(
            row["auto_topup_consent"]
        )

        raw_funding = row[
            "funding_balance_won"
        ].strip()

        if not raw_funding:
            raise ValueError(
                f"MISSING_FUNDING_BALANCE:{user_id}"
            )

        try:
            funding = int(raw_funding)
        except ValueError as exc:
            raise ValueError(
                f"INVALID_FUNDING_BALANCE:{user_id}"
            ) from exc

        if funding < 0:
            raise ValueError(
                f"NEGATIVE_FUNDING_BALANCE:{user_id}"
            )

        result[user_id] = {
            "consent": consent,
            "funding_balance_won": funding,
        }

    return result


def make_policy(args, consent):
    """Construct an explicit experimental policy."""

    return AutoTopupPolicy(
        enabled=True,
        consent=consent,
        min_topup_won=args.min_topup,
        per_topup_cap_won=args.per_topup_cap,
        monthly_topup_cap_won=args.monthly_cap,
        wallet_holding_cap_won=args.wallet_cap,
    )


def validate_policy_args(args):
    values = {
        "min_topup": args.min_topup,
        "per_topup_cap": args.per_topup_cap,
        "monthly_cap": args.monthly_cap,
        "wallet_cap": args.wallet_cap,
    }

    for name, value in values.items():
        if value < 0:
            raise ValueError(
                f"NEGATIVE_POLICY_VALUE:{name}"
            )

    if args.min_topup > args.per_topup_cap:
        raise ValueError(
            "MIN_TOPUP_EXCEEDS_PER_TOPUP_CAP"
        )


def write_csv(path, rows):
    if not rows:
        raise ValueError(
            f"EMPTY_OUTPUT:{path.name}"
        )

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0]),
        )
        writer.writeheader()
        writer.writerows(rows)


def check_user_coverage(assumptions, user_ids):
    actual = set(assumptions)
    expected = set(user_ids)

    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)

        raise ValueError(
            f"S02_USER_COVERAGE_MISMATCH:"
            f"missing={missing[:20]}:"
            f"extra={extra[:20]}"
        )


def run_s02(args, assumptions):
    # 1. Original transactions
    grouped_all = sim.read_transactions(
        sim.SOURCE
    )

    user_ids = sorted(grouped_all)

    if args.limit is not None:
        user_ids = user_ids[:args.limit]

    grouped = {
        uid: grouped_all[uid]
        for uid in user_ids
    }

    # All users in the selected cohort must be explicit.
    # --limit may use a subset of a larger assumption file.
    selected_assumptions = {
        uid: assumptions[uid]
        for uid in user_ids
        if uid in assumptions
    }

    check_user_coverage(
        selected_assumptions,
        user_ids,
    )

    # 2. Load shared reference data once
    merchant_ids = sorted({
        tx["merchant_id"]
        for txs in grouped.values()
        for tx in txs
    })

    profiles, slots, merchants = (
        sim.load_population(
            user_ids,
            merchant_ids,
        )
    )

    repository = DongbaekDBRepository()

    # 3. Separate users by consent.
    # All users still participate in S02.
    consent_groups = {
        True: [],
        False: [],
    }

    for uid in user_ids:
        consent = selected_assumptions[
            uid
        ]["consent"]

        consent_groups[consent].append(uid)

    transaction_rows = []
    user_rows = []

    for consent in (True, False):
        group_ids = set(
            consent_groups[consent]
        )

        if not group_ids:
            continue

        group_profiles = [
            p for p in profiles
            if p["user_id"] in group_ids
        ]

        group_slots = [
            s for s in slots
            if s["user_id"] in group_ids
        ]

        group_transactions = {
            uid: grouped[uid]
            for uid in sorted(group_ids)
        }

        funding = {
            uid: selected_assumptions[
                uid
            ]["funding_balance_won"]
            for uid in group_ids
        }

        policy = make_policy(
            args,
            consent=consent,
        )

        print(
            f"S02 consent={consent}, "
            f"users={len(group_ids)}",
            flush=True,
        )

        txs, users = sim.simulate(
            profiles=group_profiles,
            slots=group_slots,
            merchants=merchants,
            grouped_transactions=group_transactions,
            db_repository=repository,
            point_rate=Decimal("1"),
            auto_topup_policy=policy,
            auto_topup_funding_by_user=funding,
        )

        for row in txs:
            row["auto_topup_consent"] = consent

        for row in users:
            row["auto_topup_consent"] = consent

        transaction_rows.extend(txs)
        user_rows.extend(users)

    # 4. Restore stable ordering.
    transaction_rows.sort(
        key=lambda row: (
            row["user_id"],
            row["requested_at"],
            row["transaction_id"],
        )
    )

    user_rows.sort(
        key=lambda row: row["user_id"]
    )

    # 5. Check original population and amounts.
    expected_ids = {
        tx["transaction_id"]
        for txs in grouped.values()
        for tx in txs
    }

    actual_ids = [
        row["transaction_id"]
        for row in transaction_rows
    ]

    if (
        len(actual_ids) != len(expected_ids)
        or set(actual_ids) != expected_ids
    ):
        raise ValueError(
            "S02_TRANSACTION_ID_MISMATCH"
        )

    expected_amount = sum(
        tx["amount_won"]
        for txs in grouped.values()
        for tx in txs
    )

    actual_amount = sum(
        int(row["amount_won"])
        for row in transaction_rows
    )

    if expected_amount != actual_amount:
        raise ValueError(
            "S02_TRANSACTION_AMOUNT_CHANGED"
        )

    if len(user_rows) != len(user_ids):
        raise ValueError(
            "S02_USER_COUNT_MISMATCH"
        )

    # No top-up may be committed for a non-consenting user.
    if any(
        int(row["auto_topup_committed_won"]) != 0
        for row in transaction_rows
        if not row["auto_topup_consent"]
    ):
        raise ValueError(
            "S02_TOPUP_WITHOUT_CONSENT"
        )

    # No top-up may be committed on a BNK transaction.
    if any(
        int(row["auto_topup_committed_won"]) > 0
        and row["selected_card"] != sim.DONGBAEK_ID
        for row in transaction_rows
    ):
        raise ValueError(
            "S02_TOPUP_WITHOUT_DONGBAEK_SELECTION"
        )

    topup_tx_total = sum(
        int(row["auto_topup_committed_won"])
        for row in transaction_rows
    )

    topup_user_total = sum(
        int(row["auto_topup_total_won"])
        for row in user_rows
    )

    if topup_tx_total != topup_user_total:
        raise ValueError(
            "S02_TOPUP_RECONCILIATION_FAILED"
        )

    if sum(
        int(u["assigned"]) + int(u["unresolved"])
        for u in user_rows
    ) != len(transaction_rows):
        raise ValueError(
            "S02_ASSIGNMENT_COUNT_MISMATCH"
        )

    summary = {
        "scenario": "S02",
        "selection_policy": "ONEPASS_GREEDY",
        "wallet_policy": "CONDITIONAL_AUTO_TOPUP",
        "simulation_only": True,
        "real_authorization": False,
        "user_count": len(user_rows),
        "consenting_users": len(
            consent_groups[True]
        ),
        "nonconsenting_users": len(
            consent_groups[False]
        ),
        "transaction_count": len(
            transaction_rows
        ),
        "transaction_amount_won": actual_amount,
        "assigned_count": sum(
            int(u["assigned"])
            for u in user_rows
        ),
        "unresolved_count": sum(
            int(u["unresolved"])
            for u in user_rows
        ),
        "dongbaek_count": sum(
            int(u["dongbaek"])
            for u in user_rows
        ),
        "bnk_count": sum(
            int(u["bnk"])
            for u in user_rows
        ),
        "estimated_benefit_won": sum(
            int(u["estimated_benefit_won"])
            for u in user_rows
        ),
        "auto_topup_total_won": topup_tx_total,
        "auto_topup_event_count": sum(
            int(u["auto_topup_event_count"])
            for u in user_rows
        ),
        "auto_topup_status_counts": dict(
            Counter(
                str(t["auto_topup_status"])
                for t in transaction_rows
            )
        ),
        "assumptions": {
            "consent_source": str(args.assumptions),
            "funding_source": str(args.assumptions),
            "min_topup_won": args.min_topup,
            "per_topup_cap_won": args.per_topup_cap,
            "monthly_topup_cap_won": args.monthly_cap,
            "wallet_holding_cap_won": args.wallet_cap,
            "point_rate": "1_POINT_EQUALS_1_KRW",
            "not_observed_behavior": True,
        },
        "source_count_preserved": True,
        "source_amount_preserved": True,
    }

    output_dir = args.output

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(
        output_dir / "transactions.csv",
        transaction_rows,
    )

    write_csv(
        output_dir / "users.csv",
        user_rows,
    )

    (output_dir / "summary.json").write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== S02 SUMMARY ===")
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )
    print("\nSaved:", output_dir)
    return summary


def main():
    parser = argparse.ArgumentParser()


    parser.add_argument(
        "--assumptions",
        type=Path,
        default=DEFAULT_INPUT,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
    )

    parser.add_argument(
        "--min-topup",
        type=int,
        default=10000,
    )

    parser.add_argument(
        "--per-topup-cap",
        type=int,
        default=100000,
    )

    parser.add_argument(
        "--monthly-cap",
        type=int,
        default=300000,
    )

    parser.add_argument(
        "--wallet-cap",
        type=int,
        default=500000,
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--validate-only",
        action="store_true",
    )

    mode.add_argument(
        "--run",
        action="store_true",
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")

    validate_policy_args(args)

    # No database access required for validation.
    assumptions = load_assumptions(
        args.assumptions
    )

    print("=== S02 ASSUMPTIONS ===")
    print("Users:", len(assumptions))
    print(
        "Consenting:",
        sum(
            row["consent"]
            for row in assumptions.values()
        ),
    )
    print(
        "Nonconsenting:",
        sum(
            not row["consent"]
            for row in assumptions.values()
        ),
    )
    print(
        "Total assumed funding:",
        sum(
            row["funding_balance_won"]
            for row in assumptions.values()
        ),
    )

    if not args.run:
        print(
            "S02 INPUT VALIDATION PASSED"
        )
        print(
            "Simulation not executed."
        )
        return

    load_dotenv(ROOT / ".env")

    run_s02(args, assumptions)


if __name__ == "__main__":
    main()
