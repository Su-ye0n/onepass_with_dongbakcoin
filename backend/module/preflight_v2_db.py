
"""Read-only comparison of local V2 CSV and NeonDB.

Checks:
- Profile keys
- Card slot keys
- Stale database rows
- Dongbaek card ownership after hypothetical upsert
- Active wallet matching

No database writes.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv

from onepass.db_connection import connect_readonly
from onepass.db_policy_repository import DongbaekDBRepository

ROOT = Path(__file__).resolve().parent
V2 = ROOT / "v2_output"

SCENARIO_ID = "ONEPASS_V2_20261029"
BASE_MONTH = "2026-05"
DB_PRODUCT = "PRD_DB_SYN"


def read_csv(path):
    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def main():
    load_dotenv(ROOT / ".env")

    profiles = read_csv(
        V2 / "sim_user_profile_v2.csv"
    )
    slots = read_csv(
        V2 / "sim_user_card_slot_v2.csv"
    )

    local_profiles = {
        p["user_id"]: p for p in profiles
    }

    local_slots = {
        (s["user_id"], int(s["slot_no"])): s
        for s in slots
    }

    if (
        len(local_profiles) != len(profiles)
        or len(local_slots) != len(slots)
    ):
        raise ValueError("DUPLICATE_LOCAL_KEYS")

    with connect_readonly() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id
                FROM public.sim_user_profile_v2
                WHERE scenario_id = %s
                  AND base_month = %s
                """,
                (SCENARIO_ID, BASE_MONTH),
            )
            db_profiles = {
                r["user_id"]
                for r in cur.fetchall()
            }

            cur.execute(
                """
                SELECT user_id, slot_no, product_id
                FROM public.sim_user_card_slot_v2
                WHERE scenario_id = %s
                  AND base_month = %s
                """,
                (SCENARIO_ID, BASE_MONTH),
            )
            db_slots = {
                (r["user_id"], int(r["slot_no"])): r
                for r in cur.fetchall()
            }           

    local_profile_ids = set(local_profiles)
    db_profile_ids = set(db_profiles)

    local_slot_keys = set(local_slots)
    db_slot_keys = set(db_slots)

    stale_profiles = (
        db_profile_ids - local_profile_ids
    )

    stale_slots = (
        db_slot_keys - local_slot_keys
    )

    new_profiles = (
        local_profile_ids - db_profile_ids
    )

    new_slots = (
        local_slot_keys - db_slot_keys
    )

    changed_products = [
        key
        for key in local_slot_keys & db_slot_keys
        if (
            local_slots[key]["product_id"]
            != db_slots[key]["product_id"]
        )
    ]

    # Simulate the key-level result of an upsert:
    # existing stale rows would remain.
    effective_slots = {
        key: row["product_id"]
        for key, row in db_slots.items()
    }

    effective_slots.update({
        key: row["product_id"]
        for key, row in local_slots.items()
    })

    effective_db_owners = {
        uid
        for (uid, _), product in effective_slots.items()
        if product == DB_PRODUCT
    }

    expected_members = {
        uid
        for uid, p in local_profiles.items()
        if p["dongbaek_usage_level"]
        != "NON_MEMBER"
    }

    nonmember_owners = (
        effective_db_owners - expected_members
    )

    members_without_card = (
        expected_members - effective_db_owners
    )

    # 기존 저장소의 지갑 상태 판정 재사용
    repo = DongbaekDBRepository()

    active_wallet_users = {
        uid
        for uid in expected_members
        if repo.wallet_state_for(uid) == "ACTIVE"
        and repo.wallet_for(uid) is not None
    }

    members_without_active_wallet = (
        expected_members - active_wallet_users
    )

    members_without_active_wallet = (
        expected_members - active_wallet_users
    )

    print("=== V2 NEONDB READ-ONLY PREFLIGHT ===")

    print("\n[PROFILES]")
    print("Local:", len(local_profile_ids))
    print("DB:", len(db_profile_ids))
    print("New keys:", len(new_profiles))
    print("Stale keys:", len(stale_profiles))

    print("\n[CARD SLOTS]")
    print("Local:", len(local_slot_keys))
    print("DB:", len(db_slot_keys))
    print("New keys:", len(new_slots))
    print("Stale keys:", len(stale_slots))
    print("Changed products:", len(changed_products))

    print("\n[AFTER HYPOTHETICAL UPSERT]")
    print("Expected members:", len(expected_members))
    print(
        "Effective Dongbaek owners:",
        len(effective_db_owners),
    )
    print(
        "Nonmember owners:",
        len(nonmember_owners),
    )
    print(
        "Members without card:",
        len(members_without_card),
    )
    print(
        "Members without ACTIVE wallet:",
        len(members_without_active_wallet),
    )

    if stale_profiles:
        print(
            "\nSTALE PROFILES:",
            sorted(stale_profiles)[:30],
        )

    if stale_slots:
        print(
            "\nSTALE SLOTS:",
            sorted(stale_slots)[:30],
        )

    if nonmember_owners:
        print(
            "\nNONMEMBER DB OWNERS:",
            sorted(nonmember_owners)[:30],
        )

    if members_without_card:
        print(
            "\nMEMBERS WITHOUT CARD:",
            sorted(members_without_card)[:30],
        )

    if members_without_active_wallet:
        print(
            "\nMEMBERS WITHOUT ACTIVE WALLET:",
            sorted(members_without_active_wallet)[:30],
        )

    problems = {
        "stale_profiles": len(stale_profiles),
        "stale_slots": len(stale_slots),
        "nonmember_owners": len(nonmember_owners),
        "members_without_card": len(members_without_card),
        "members_without_active_wallet": len(
            members_without_active_wallet
        ),
    }

    if any(problems.values()):
        print("\nDB PREFLIGHT: REVIEW REQUIRED")
    else:
        print("\nDB PREFLIGHT: PASSED")

    print("DATABASE MODIFIED: NO")
    print("UPLOAD EXECUTED: NO")


if __name__ == "__main__":
    main()
