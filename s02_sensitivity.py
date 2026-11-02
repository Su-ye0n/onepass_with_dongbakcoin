
"""Generate S02 conditional auto-topup sensitivity inputs.

3 consent rates x 3 funding levels = 9 scenarios.

Statistical reference:
부산 지역화폐 '동백전'의 지역경제 기여도 및 정책 개선방안

Observed survey data:
- Jun 2025 monthly usage: 172,000 KRW
- Jul 2025 monthly usage: 177,000 KRW
- Aug 2025 monthly usage: 181,000 KRW
- Continue recharging after cashback cap: 38.4%

Important:
- Monthly usage is NOT the same as available bank funding.
- 38.4% is NOT observed automatic top-up consent.
- Funding amounts and consent cohorts are experimental proxies.

Uses local V2 profiles and original transactions.
No NeonDB writes or simulation execution.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


ROOT = Path(__file__).resolve().parent

PROFILE = (
    ROOT / "v2_output" / "sim_user_profile_v2.csv"
)

TRANSACTIONS = (
    ROOT
    / "original_transactions"
    / "original_base_transactions.csv"
)

OUTPUT = ROOT / "s02_sensitivity_inputs"


# Statistical-reference-based experimental scenarios.
CONSENT_RATES = (25, 38.4, 50)

FUNDING_LEVELS_WON = (
    100000,
    180000,
    300000,
)

# Preserve the original ranking and cohort assignment.
SEED = "ONEPASS_S02_SENSITIVITY_20261030"


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(path)

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError(f"EMPTY_CSV:{path}")

        return list(reader)


def load_profiles(path):
    rows = read_csv(path)

    required = {
        "user_id",
        "dongbaek_usage_level",
    }

    if not rows:
        raise ValueError("EMPTY_PROFILE_DATA")

    if not required.issubset(rows[0]):
        raise ValueError("INVALID_PROFILE_COLUMNS")

    profiles = {}

    for row in rows:
        uid = row["user_id"].strip()
        level = row["dongbaek_usage_level"].strip()

        if not uid:
            raise ValueError("EMPTY_PROFILE_USER_ID")

        if uid in profiles:
            raise ValueError(
                f"DUPLICATE_PROFILE_USER:{uid}"
            )

        if not level:
            raise ValueError(
                f"MISSING_DONGBAEK_USAGE_LEVEL:{uid}"
            )

        profiles[uid] = row

    return profiles


def load_transaction_users(path):
    rows = read_csv(path)

    if not rows:
        raise ValueError("EMPTY_TRANSACTION_DATA")

    if "user_id" not in rows[0]:
        raise ValueError("MISSING_TRANSACTION_USER_ID")

    user_ids = {
        row["user_id"].strip()
        for row in rows
    }

    if not all(user_ids):
        raise ValueError("EMPTY_TRANSACTION_USER_ID")

    return user_ids


def check_population(
    profiles,
    transaction_users,
):
    profile_users = set(profiles)

    if profile_users != transaction_users:
        missing = sorted(
            transaction_users - profile_users
        )

        extra = sorted(
            profile_users - transaction_users
        )

        raise ValueError(
            "PROFILE_TRANSACTION_USER_MISMATCH:"
            f"missing={missing[:20]}:"
            f"extra={extra[:20]}"
        )

    members = sorted(
        uid
        for uid, row in profiles.items()
        if row["dongbaek_usage_level"]
        != "NON_MEMBER"
    )

    nonmembers = sorted(
        uid
        for uid, row in profiles.items()
        if row["dongbaek_usage_level"]
        == "NON_MEMBER"
    )

    return members, nonmembers


def consent_rank(user_id):
    """Stable pseudo-random ordering across scenarios."""

    value = f"{SEED}:{user_id}"

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def consent_count(member_count, rate_pct):
    """Calculate consent count using decimal-safe rounding."""

    value = (
        Decimal(member_count)
        * Decimal(str(rate_pct))
        / Decimal(100)
    )

    return int(
        value.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def consent_rate_label(rate_pct):
    """Convert 38.4 to 38P4 for stable filenames."""

    return str(rate_pct).replace(".", "P")


def scenario_id(rate_pct, funding_won):
    label = consent_rate_label(rate_pct)

    return (
        f"S02_C{label}_F{funding_won}"
    )


def make_scenario(
    *,
    all_users,
    ranked_members,
    rate_pct,
    funding_won,
):
    count = consent_count(
        len(ranked_members),
        rate_pct,
    )

    consenting_users = set(
        ranked_members[:count]
    )

    rows = []

    for uid in all_users:
        consent = uid in consenting_users

        rows.append({
            "user_id": uid,
            "auto_topup_consent": (
                "true" if consent else "false"
            ),
            "funding_balance_won": (
                funding_won if consent else 0
            ),
        })

    return rows, consenting_users


def write_csv(path, rows):
    if not rows:
        raise ValueError("EMPTY_SCENARIO_ROWS")

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "user_id",
                "auto_topup_consent",
                "funding_balance_won",
            ],
        )

        writer.writeheader()
        writer.writerows(rows)


def build_sensitivity(
    *,
    profile_path,
    transaction_path,
    output_dir,
    overwrite=False,
):
    # 1. Load and validate population.
    profiles = load_profiles(profile_path)

    transaction_users = load_transaction_users(
        transaction_path
    )

    members, nonmembers = check_population(
        profiles,
        transaction_users,
    )

    all_users = sorted(transaction_users)

    # 2. Preserve a consistent consent ranking.
    ranked_members = sorted(
        members,
        key=lambda uid: (
            consent_rank(uid),
            uid,
        ),
    )

    if len(all_users) != 240:
        raise ValueError(
            f"UNEXPECTED_USER_COUNT:{len(all_users)}"
        )

    if len(members) != 111:
        raise ValueError(
            f"UNEXPECTED_MEMBER_COUNT:{len(members)}"
        )

    if len(nonmembers) != 129:
        raise ValueError(
            "UNEXPECTED_NONMEMBER_COUNT:"
            f"{len(nonmembers)}"
        )

    # 3. Generate all 9 scenarios.
    scenarios = []
    scenario_rows = []
    consent_sets = {}

    for rate in CONSENT_RATES:
        for funding in FUNDING_LEVELS_WON:

            sid = scenario_id(
                rate,
                funding,
            )

            filename = f"{sid}.csv"

            rows, consenting = make_scenario(
                all_users=all_users,
                ranked_members=ranked_members,
                rate_pct=rate,
                funding_won=funding,
            )

            if len(rows) != len(all_users):
                raise ValueError(
                    f"SCENARIO_ROW_COUNT:{sid}"
                )

            if consenting - set(members):
                raise ValueError(
                    f"NONMEMBER_CONSENT:{sid}"
                )

            consent_sets[(rate, funding)] = (
                consenting
            )

            scenarios.append({
                "scenario_id": sid,
                "consent_rate_assumption_pct": rate,
                "funding_per_consent_user_won": (
                    funding
                ),
                "consenting_user_count": len(
                    consenting
                ),
                "nonconsenting_user_count": (
                    len(all_users) - len(consenting)
                ),
                "total_assumed_funding_won": (
                    len(consenting) * funding
                ),
                "input_file": filename,
            })

            scenario_rows.append(
                (filename, rows)
            )

    # 4. Consent sets must remain nested.
    for funding in FUNDING_LEVELS_WON:
        previous = set()

        for rate in CONSENT_RATES:
            current = consent_sets[(rate, funding)]

            if not previous.issubset(current):
                raise ValueError(
                    "CONSENT_NESTING_FAILED:"
                    f"{funding}:{rate}"
                )

            previous = current

    # 5. Same consent cohort at each funding level.
    for rate in CONSENT_RATES:
        reference = consent_sets[
            (rate, FUNDING_LEVELS_WON[0])
        ]

        for funding in FUNDING_LEVELS_WON[1:]:
            current = consent_sets[
                (rate, funding)
            ]

            if current != reference:
                raise ValueError(
                    "CONSENT_COHORT_CHANGED:"
                    f"{rate}:{funding}"
                )

    if len(scenarios) != 9:
        raise ValueError(
            "INVALID_SENSITIVITY_SCENARIO_COUNT"
        )

    # 6. Prevent unintended overwriting.
    output_files = [
        output_dir / filename
        for filename, _ in scenario_rows
    ]

    manifest_path = output_dir / "manifest.json"
    output_files.append(manifest_path)

    existing = [
        str(path)
        for path in output_files
        if path.exists()
    ]

    if existing and not overwrite:
        raise FileExistsError(
            "OUTPUT_EXISTS_USE_OVERWRITE:"
            + ", ".join(existing[:5])
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 7. Save inputs.
    for filename, rows in scenario_rows:
        write_csv(
            output_dir / filename,
            rows,
        )

    # 8. Save assumptions and statistical evidence.
    manifest = {
        "experiment": (
            "S02_AUTO_TOPUP_SENSITIVITY"
        ),
        "scenario_count": len(scenarios),
        "user_count": len(all_users),
        "dongbaek_member_count": len(members),
        "nonmember_count": len(nonmembers),
        "consent_denominator": (
            "DONGBAEK_MEMBERS_ONLY"
        ),
        "selection_method": (
            "DETERMINISTIC_SHA256_RANKING"
        ),
        "selection_seed": SEED,
        "nested_consent_cohorts": True,
        "data_source": {
            "profiles": str(profile_path),
            "transactions": str(transaction_path),
        },
        "statistical_basis": {
            "source": (
                "부산 지역화폐 동백전의 지역경제 "
                "기여도 및 정책 개선방안"
            ),
            "survey_reference_period": (
                "2025-06_to_2025-08"
            ),
            "observed_monthly_usage_won": {
                "2025-06": 172000,
                "2025-07": 177000,
                "2025-08": 181000,
            },
            "observed_common_usage_band_won": {
                "lower_bound": 100000,
                "upper_bound_exclusive": 300000,
                "share_pct": 28.8,
            },
            "observed_continue_recharging_pct": (
                38.4
            ),
            "assumed_consent_rates_pct": list(
                CONSENT_RATES
            ),
            "assumed_funding_won": list(
                FUNDING_LEVELS_WON
            ),
            "funding_scenario_explanation": {
                "low": (
                    "100000_WON_COMMON_USAGE_BAND_LOWER"
                ),
                "reference": (
                    "180000_WON_ROUNDED_MONTHLY_USAGE"
                ),
                "high": (
                    "300000_WON_COMMON_USAGE_BAND_UPPER"
                ),
            },
            "limitations": [
                (
                    "MONTHLY_USAGE_IS_NOT_OBSERVED_"
                    "AVAILABLE_BANK_FUNDING"
                ),
                (
                    "CONTINUE_RECHARGING_38_4_PERCENT_"
                    "IS_NOT_AUTOTOPUP_CONSENT"
                ),
                (
                    "25_AND_50_PERCENT_ARE_"
                    "SENSITIVITY_ASSUMPTIONS"
                ),
                (
                    "ALL_CONSENTING_USERS_AT_SAME_"
                    "FUNDING_LEVEL_RECEIVE_EQUAL_FUNDING"
                ),
                (
                    "SYNTHETIC_USER_ASSIGNMENT_"
                    "NOT_OBSERVED_USER_BEHAVIOR"
                ),
            ],
        },
        "interpretation": (
            "STATISTICALLY_ANCHORED_EXPERIMENTAL_"
            "ASSUMPTIONS_NOT_OBSERVED_AUTO_TOPUP"
        ),
        "simulation_executed": False,
        "scenarios": scenarios,
    }

    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 9. Display validation summary.
    print("\n=== S02 SENSITIVITY INPUTS ===")
    print("Users:", len(all_users))
    print("Dongbaek members:", len(members))
    print("Nonmembers:", len(nonmembers))
    print("Scenarios:", len(scenarios))

    for scenario in scenarios:
        print(
            scenario["scenario_id"],
            "| consenting:",
            scenario["consenting_user_count"],
            "| funding:",
            scenario[
                "funding_per_consent_user_won"
            ],
        )

    print("\nCONSENT NESTING: PASSED")
    print("CONSENT COHORT CONSISTENCY: PASSED")
    print("INPUT GENERATION: PASSED")
    print("SIMULATION: NOT EXECUTED")
    print("DATABASE: NOT MODIFIED")
    print("Saved:", output_dir)

    return manifest


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--profiles",
        type=Path,
        default=PROFILE,
    )

    parser.add_argument(
        "--transactions",
        type=Path,
        default=TRANSACTIONS,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    args = parser.parse_args()

    build_sensitivity(
        profile_path=args.profiles,
        transaction_path=args.transactions,
        output_dir=args.output,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
