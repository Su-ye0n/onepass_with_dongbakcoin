
"""V2 upload preflight: local files only.

Checks:
- 240 users / 759 card slots
- 111 Dongbaek members, zero nonmember DB cards
- per-user slot counts and contiguous slot numbers
- latest card-count and usage-style distributions
- original spend total
- scenario/base-month consistency
- exact user coverage against transaction source

No database connections or writes.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
V2 = ROOT / "v2_output"

PROFILE_PATH = V2 / "sim_user_profile_v2.csv"
SLOT_PATH = V2 / "sim_user_card_slot_v2.csv"
SUMMARY_PATH = V2 / "summary.json"

TX_PATH = (
    ROOT
    / "original_transactions"
    / "original_base_transactions.csv"
)

SCENARIO_ID = "ONEPASS_V2_20261029"
BASE_MONTH = "2026-05"
DB_PRODUCT = "PRD_DB_SYN"

EXPECTED_CARD_COUNTS = {
    1: 13,
    2: 60,
    3: 86,
    4: 37,
    5: 44,
}

EXPECTED_USAGE = {
    "SINGLE_CARD": 13,
    "PURPOSE_BASED": 97,
    "MAIN_SUB": 91,
    "UNDIFFERENTIATED": 39,
}


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(path)

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    profiles = read_csv(PROFILE_PATH)
    slots = read_csv(SLOT_PATH)
    transactions = read_csv(TX_PATH)

    with SUMMARY_PATH.open(encoding="utf-8") as f:
        summary = json.load(f)

    print("=== V2 UPLOAD PREFLIGHT ===")

    require(
        len(profiles) == 240,
        f"PROFILE_COUNT:{len(profiles)}",
    )

    require(
        len(slots) == 759,
        f"SLOT_COUNT:{len(slots)}",
    )

    profiles_by_user = {}

    for p in profiles:
        uid = p["user_id"]

        require(
            uid not in profiles_by_user,
            f"DUPLICATE_PROFILE:{uid}",
        )

        require(
            p["scenario_id"] == SCENARIO_ID,
            f"PROFILE_SCENARIO:{uid}",
        )

        require(
            p["base_month"] == BASE_MONTH,
            f"PROFILE_MONTH:{uid}",
        )

        profiles_by_user[uid] = p

    slots_by_user = defaultdict(list)
    slot_keys = set()

    for slot in slots:
        uid = slot["user_id"]
        slot_no = int(slot["slot_no"])
        key = (uid, slot_no)

        require(
            key not in slot_keys,
            f"DUPLICATE_SLOT:{key}",
        )

        slot_keys.add(key)

        require(
            uid in profiles_by_user,
            f"UNKNOWN_SLOT_USER:{uid}",
        )

        require(
            slot["scenario_id"] == SCENARIO_ID,
            f"SLOT_SCENARIO:{key}",
        )

        require(
            slot["base_month"] == BASE_MONTH,
            f"SLOT_MONTH:{key}",
        )

        require(
            slot["usage_style"]
            == profiles_by_user[uid]["usage_style"],
            f"USAGE_STYLE_MISMATCH:{key}",
        )

        require(
            slot["performance_state"]
            == profiles_by_user[uid]["performance_state"],
            f"PERFORMANCE_STATE_MISMATCH:{key}",
        )

        slots_by_user[uid].append(slot)

    transaction_users = {
        tx["user_id"] for tx in transactions
    }

    require(
        set(profiles_by_user) == transaction_users,
        "TRANSACTION_USER_COVERAGE_MISMATCH",
    )

    require(
        set(slots_by_user) == transaction_users,
        "SLOT_USER_COVERAGE_MISMATCH",
    )

    members = set()
    owners = set()

    card_counts = Counter()
    usage_counts = Counter()
    performance_counts = Counter()

    total_previous_spend = 0

    for uid, profile in profiles_by_user.items():
        user_slots = slots_by_user[uid]
        count = int(profile["simulated_card_count"])
        level = profile["dongbaek_usage_level"]
        usage = profile["usage_style"]

        require(
            1 <= count <= 5,
            f"INVALID_CARD_COUNT:{uid}:{count}",
        )

        require(
            len(user_slots) == count,
            f"CARD_SLOT_COUNT_MISMATCH:{uid}",
        )

        slot_numbers = sorted(
            int(s["slot_no"]) for s in user_slots
        )

        require(
            slot_numbers == list(range(1, count + 1)),
            f"NONCONTIGUOUS_SLOTS:{uid}",
        )

        db_slots = [
            s for s in user_slots
            if s["product_id"] == DB_PRODUCT
        ]

        is_member = level != "NON_MEMBER"

        if is_member:
            members.add(uid)

            require(
                len(db_slots) == 1,
                f"MEMBER_DB_SLOT_MISMATCH:{uid}",
            )

        else:
            require(
                len(db_slots) == 0,
                f"NONMEMBER_HAS_DB_SLOT:{uid}",
            )

        if db_slots:
            owners.add(uid)

        if count == 1:
            require(
                usage == "SINGLE_CARD",
                f"SINGLE_CARD_USAGE_MISMATCH:{uid}",
            )
        else:
            require(
                usage != "SINGLE_CARD",
                f"MULTICARD_USAGE_MISMATCH:{uid}",
            )

        card_counts[count] += 1
        usage_counts[usage] += 1

        performance_counts[
            profile["performance_state"]
        ] += 1

        total_previous_spend += int(
            profile["original_month_spend_won"]
        )

    require(
        len(members) == 111,
        f"MEMBER_COUNT:{len(members)}",
    )

    require(
        owners == members,
        "DONGBAEK_MEMBERSHIP_OWNERSHIP_MISMATCH",
    )

    require(
        dict(card_counts) == EXPECTED_CARD_COUNTS,
        f"CARD_DISTRIBUTION:{dict(card_counts)}",
    )

    require(
        dict(usage_counts) == EXPECTED_USAGE,
        f"USAGE_DISTRIBUTION:{dict(usage_counts)}",
    )

    require(
        total_previous_spend == 225899600,
        f"PREVIOUS_SPEND_TOTAL:{total_previous_spend}",
    )

    require(
        len(transactions) == 7540,
        f"TRANSACTION_COUNT:{len(transactions)}",
    )

    transaction_amount = sum(
        int(tx["amount_won"])
        for tx in transactions
    )

    require(
        transaction_amount == 240445000,
        f"TRANSACTION_AMOUNT:{transaction_amount}",
    )

    require(
        summary["scenario_id"] == SCENARIO_ID,
        "SUMMARY_SCENARIO_MISMATCH",
    )

    require(
        summary["base_month"] == BASE_MONTH,
        "SUMMARY_MONTH_MISMATCH",
    )

    require(
        summary["user_count"] == len(profiles),
        "SUMMARY_USER_COUNT_MISMATCH",
    )

    require(
        summary["slot_count"] == len(slots),
        "SUMMARY_SLOT_COUNT_MISMATCH",
    )

    require(
        summary["original_total_spend_won"]
        == total_previous_spend,
        "SUMMARY_SPEND_MISMATCH",
    )

    print("Profiles:", len(profiles))
    print("Slots:", len(slots))
    print("Members:", len(members))
    print("Nonmembers:", 240 - len(members))
    print("Dongbaek owners:", len(owners))
    print("Card counts:", dict(sorted(card_counts.items())))
    print("Usage styles:", dict(sorted(usage_counts.items())))
    print(
        "Performance states:",
        dict(sorted(performance_counts.items())),
    )
    print("Previous-month spend:", total_previous_spend)
    print("Transaction count:", len(transactions))
    print("Transaction amount:", transaction_amount)

    print("\nV2 LOCAL PREFLIGHT: PASSED")
    print("DATABASE: NOT MODIFIED")
    print("UPLOAD: NOT EXECUTED")


if __name__ == "__main__":
    main()
