
"""
Dongbaek OnePass - Synthetic User Data V2

목적
1. 기존 NeonDB 사용자 240명과 월 이용 실적 조회
2. 설문 기반 카드 보유 수 1~5장 재구성
3. 카드 사용 방식 3종 부여
4. 전월 실적 정상/누락/NULL/0원 시나리오 생성
5. CSV, JSON 검증 결과 출력
6. 선택적으로 NeonDB V2 전용 테이블에 적재

주의
- 기존 user, user_card, card_month_close, ledger 수정하지 않음
- 실제 고객 결제 정보가 아닌 합성 시나리오
- 기본 실행은 읽기 전용
- --upload 실행 시에만 DB 쓰기
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random

from collections import Counter
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from onepass.db_connection import connect_readonly


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "v2_output"

BASE_MONTH = "2026-05"
SCENARIO_ID = "ONEPASS_V2_20261029"
SEED = 20261029

# 설문 응답 비율을 240명으로 환산한 목표 분포
CARD_COUNT_TARGETS = {
    1: 13,
    2: 60,
    3: 86,
    4: 37,
    5: 44,
}

# 946명 설문 응답을 참고한 사용 행태
# 카드 2장 이상 사용자에게만 적용
# 카드 1장 사용자는 SINGLE_CARD로 별도 분리
USAGE_STYLE_WEIGHTS = {
    "PURPOSE_BASED": 42.8,
    "MAIN_SUB": 40.2,
    "UNDIFFERENTIATED": 17.0,
}

# 엔진 경계조건 테스트용 설정
PERFORMANCE_TARGETS = {
    "NORMAL": 210,
    "MISSING_ROW": 12,
    "NULL_VALUE": 12,
    "ZERO_WON": 6,
}


def money_int(value):
    if value is None:
        return 0
    return int(Decimal(str(value)))


def stable_int(*values):
    raw = "|".join(map(str, values))
    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()
    return int(digest[:16], 16)


def distribute_labels(users, targets, seed):
    """
    사용자 ID별로 재현 가능한 임의 배정.
    목표 인원 합계는 전체 사용자 수와 같아야 함.
    """
    if sum(targets.values()) != len(users):
        raise ValueError(
            f"TARGET_TOTAL_MISMATCH:"
            f" expected={len(users)}, "
            f"target={sum(targets.values())}"
        )

    shuffled = sorted(users)
    random.Random(seed).shuffle(shuffled)

    assigned = {}
    offset = 0

    for label, count in targets.items():
        selected = shuffled[offset:offset + count]

        for user_id in selected:
            assigned[user_id] = label

        offset += count

    return assigned

def assign_usage_styles(card_counts):
    """
    카드 1장 사용자는 SINGLE_CARD.
    카드 2장 이상 사용자에게만 오픈서베이 사용 행태 적용.
    """
    single_users = [
        uid for uid, count in card_counts.items()
        if count == 1
    ]

    multi_users = [
        uid for uid, count in card_counts.items()
        if count >= 2
    ]

    total = len(multi_users)

    raw = {
        style: total * weight / 100
        for style, weight in USAGE_STYLE_WEIGHTS.items()
    }

    targets = {
        style: int(value)
        for style, value in raw.items()
    }

    remainder = total - sum(targets.values())

    order = sorted(
        raw,
        key=lambda style: (
            -(raw[style] - targets[style]),
            style,
        ),
    )

    for style in order[:remainder]:
        targets[style] += 1

    assigned = distribute_labels(
        multi_users,
        targets,
        SEED + 2,
    )

    for uid in single_users:
        assigned[uid] = "SINGLE_CARD"

    return assigned, targets

def allocate_integer_total(total, weights):
    """
    정수 합계를 정확히 보존하는 금액 분배.

    예:
    total=100000, 카드 3장
    -> 분배 합계는 반드시 100000원
    """
    if not weights:
        return []

    if total < 0:
        raise ValueError("NEGATIVE_SPEND")

    weight_sum = sum(weights)

    if weight_sum <= 0:
        raise ValueError("INVALID_WEIGHTS")

    raw = [
        Decimal(total) * Decimal(str(w))
        / Decimal(str(weight_sum))
        for w in weights
    ]

    floors = [int(x) for x in raw]
    remainder = total - sum(floors)

    ranking = sorted(
        range(len(weights)),
        key=lambda i: (
            -(raw[i] - floors[i]),
            i,
        ),
    )

    for i in ranking[:remainder]:
        floors[i] += 1

    assert sum(floors) == total

    return floors


def load_source_users():
    """
    확인된 NeonDB 구조만 사용.

    user
    user_card
    card_month_close
    card_product

    2026-05 카드별 월 실적을 사용자별 합산.
    """
    with connect_readonly() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    u.user_id,
                    u.user_type,
                    u.origin_type,
                    u.age_band,
                    u.district_code,
                    u.spend_band,
                    u.dongbaek_usage_level,
                    COUNT(DISTINCT uc.user_card_id)
                        AS original_card_count,
                    COALESCE(
                        SUM(cm.spend_total_won), 0
                    ) AS original_month_spend_won,
                    COUNT(DISTINCT cm.user_card_id)
                        AS month_close_card_count
                FROM public."user" u
                JOIN public.user_card uc
                    ON uc.user_id = u.user_id
                LEFT JOIN public.card_month_close cm
                    ON cm.user_card_id = uc.user_card_id
                   AND cm.base_month = %s
                GROUP BY
                    u.user_id,
                    u.user_type,
                    u.origin_type,
                    u.age_band,
                    u.district_code,
                    u.spend_band,
                    u.dongbaek_usage_level
                ORDER BY u.user_id
                """,
                (BASE_MONTH,),
            )

            users = [
                dict(row) for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT DISTINCT
                    uc.user_id,
                    uc.product_id,
                    cp.card_type
                FROM public.user_card uc
                JOIN public.card_product cp
                    ON cp.product_id = uc.product_id
                ORDER BY uc.user_id, uc.product_id
                """
            )

            owned = [
                dict(row) for row in cur.fetchall()
            ]

    return users, owned


def build_product_catalog(owned):
    by_user = {}
    catalog = {}

    for row in owned:
        user_id = row["user_id"]
        product_id = row["product_id"]
        card_type = row["card_type"]

        by_user.setdefault(user_id, []).append({
            "product_id": product_id,
            "card_type": card_type,
        })

        catalog[product_id] = {
            "product_id": product_id,
            "card_type": card_type,
        }

    return by_user, [
        catalog[key] for key in sorted(catalog)
    ]


def assign_card_products(
    user_id,
    count,
    owned,
    catalog,
    dongbaek_usage_level,
):
    """
    동백전 가입 여부를 보존하면서 카드 상품 배정.

    - NON_MEMBER: 동백전 슬롯 금지
    - 가입자: 동백전 슬롯 반드시 1개
    - 동백전 슬롯은 전체 카드 슬롯 수에 포함
    """

    has_db = dongbaek_usage_level != "NON_MEMBER"

    existing = owned.get(user_id, [])
    selected = []
    used_products = set()

    if has_db:
        db_products = [
            p for p in catalog
            if p["product_id"] == "PRD_DB_SYN"
        ]

        if len(db_products) != 1:
            raise ValueError(
                f"DONGBAEK_PRODUCT_NOT_FOUND:{user_id}"
            )

        db_product = db_products[0]
        selected.append(db_product)
        used_products.add(db_product["product_id"])

    for product in existing:
        if len(selected) >= count:
            break

        pid = product["product_id"]

        if pid == "PRD_DB_SYN":
            continue

        if pid in used_products:
            continue

        selected.append(product)
        used_products.add(pid)

    remaining = [
        p for p in catalog
        if p["product_id"] != "PRD_DB_SYN"
        and p["product_id"] not in used_products
    ]

    random.Random(
        stable_int(SEED, user_id, "PRODUCTS")
    ).shuffle(remaining)

    for product in remaining:
        if len(selected) >= count:
            break

        selected.append(product)
        used_products.add(product["product_id"])

    if len(selected) != count:
        raise ValueError(
            f"INSUFFICIENT_DISTINCT_PRODUCTS:{user_id}:"
            f"{len(selected)}/{count}"
        )

    return selected


def build_data(source_users, owned):
    user_ids = [
        u["user_id"] for u in source_users
    ]

    if len(user_ids) != len(set(user_ids)):
        raise ValueError("DUPLICATE_SOURCE_USER")

    card_counts = distribute_labels(
        user_ids,
        CARD_COUNT_TARGETS,
        SEED + 1,
    )

    usage_styles, usage_style_targets = (
        assign_usage_styles(card_counts)
    )

    perf_states = distribute_labels(
        user_ids,
        PERFORMANCE_TARGETS,
        SEED + 3,
    )

    by_user, catalog = build_product_catalog(owned)

    if len(catalog) < max(CARD_COUNT_TARGETS):
        raise ValueError(
            "NOT_ENOUGH_CARD_PRODUCTS_FOR_TARGET"
        )

    profiles = []
    slots = []

    for source in source_users:
        user_id = source["user_id"]
        count = card_counts[user_id]
        style = usage_styles[user_id]
        perf_state = perf_states[user_id]

        original_spend = money_int(
            source["original_month_spend_won"]
        )

        products = assign_card_products(
            user_id,
            count,
            by_user,
            catalog,
            source["dongbaek_usage_level"],
        )

        rng = random.Random(
            stable_int(SEED, user_id, "SPEND")
        )


        # 카드 사용 방식에 따라 전월 실적 배분 가중치 생성
        if style == "SINGLE_CARD":
            weights = [1]

        elif style == "PURPOSE_BASED":
            # 목적별 사용: 카드 간 비교적 고르게 분배
            weights = [
                rng.randint(60, 140)
                for _ in range(count)
            ]

        elif style == "MAIN_SUB":
            # 주 사용 카드에 높은 비중 배분
            weights = [
                700,
                *[
                    rng.randint(50, 150)
                    for _ in range(count - 1)
                ],
            ]

        elif style == "UNDIFFERENTIATED":
            # 명확한 사용 구분 없는 카드 이용
            weights = [
                rng.randint(20, 300)
                for _ in range(count)
            ]

        else:
            raise ValueError(
                f"UNKNOWN_USAGE_STYLE:{style}"
            )


        # 데이터 원본의 이용금액은 별도로 보존.
        # 누락/NULL/0원은 V2 실적 시나리오에만 반영.
        if perf_state == "NORMAL":
            allocated = allocate_integer_total(
                original_spend, weights
            )
        elif perf_state == "ZERO_WON":
            allocated = [0] * count
        else:
            allocated = [None] * count

        profiles.append({
            "scenario_id": SCENARIO_ID,
            "user_id": user_id,
            "base_month": BASE_MONTH,
            "original_card_count": int(
                source["original_card_count"]
            ),
            "simulated_card_count": count,
            "usage_style": style,
            "performance_state": perf_state,
            "original_month_spend_won": original_spend,
            "age_band": source["age_band"],
            "district_code": source["district_code"],
            "spend_band": source["spend_band"],
            "dongbaek_usage_level":
                source["dongbaek_usage_level"],
        })

        for idx, (product, allocated_amount) in enumerate(
            zip(products, allocated),
            start=1,
        ):
            slots.append({
                "scenario_id": SCENARIO_ID,
                "user_id": user_id,
                "slot_no": idx,
                "product_id": product["product_id"],
                "card_type": product["card_type"],
                "base_month": BASE_MONTH,
                "usage_style": style,
                "performance_state": perf_state,
                "sim_month_spend_won": allocated_amount,
                "is_primary": (
                    style == "MAIN_SUB" and idx == 1
                ),
            })

    return profiles, slots


def validate_data(profiles, slots, source_users):
    if len(profiles) != len(source_users):
        raise ValueError("USER_COUNT_CHANGED")

    by_user = Counter(
        s["user_id"] for s in slots
    )

    card_distribution = Counter(
        p["simulated_card_count"] for p in profiles
    )

    usage_distribution = Counter(
        p["usage_style"] for p in profiles
    )

    perf_distribution = Counter(
        p["performance_state"] for p in profiles
    )

    if dict(card_distribution) != CARD_COUNT_TARGETS:
        raise ValueError("CARD_DISTRIBUTION_MISMATCH")

    expected_multi = sum(
        1 for p in profiles
        if p["simulated_card_count"] >= 2
    )

    expected = {
        "SINGLE_CARD": sum(
            1 for p in profiles
            if p["simulated_card_count"] == 1
        )
    }

    raw = {
        style: expected_multi * weight / 100
        for style, weight in USAGE_STYLE_WEIGHTS.items()
    }

    for style, value in raw.items():
        expected[style] = int(value)

    remainder = expected_multi - sum(
        expected[s] for s in USAGE_STYLE_WEIGHTS
    )

    order = sorted(
        raw,
        key=lambda style: (
            -(raw[style] - int(raw[style])),
            style,
        ),
    )

    for style in order[:remainder]:
        expected[style] += 1

    if dict(usage_distribution) != expected:
        raise ValueError(
            f"USAGE_DISTRIBUTION_MISMATCH: "
            f"actual={dict(usage_distribution)} "
            f"expected={expected}"
        )

    for p in profiles:
        if (
            p["simulated_card_count"] == 1
            and p["usage_style"] != "SINGLE_CARD"
        ):
            raise ValueError(
                f"INVALID_SINGLE_CARD_STYLE:"
                f"{p['user_id']}"
            )

    if dict(perf_distribution) != PERFORMANCE_TARGETS:
        raise ValueError("PERFORMANCE_DISTRIBUTION_MISMATCH")

    source_total = sum(
        money_int(u["original_month_spend_won"])
        for u in source_users
    )

    preserved_total = sum(
        p["original_month_spend_won"]
        for p in profiles
    )

    if source_total != preserved_total:
        raise ValueError("SOURCE_SPEND_TOTAL_CHANGED")

    slot_index = {}

    for slot in slots:
        slot_index.setdefault(
            slot["user_id"], []
        ).append(slot)

    for profile in profiles:
        user_id = profile["user_id"]
        user_slots = slot_index.get(user_id, [])

        if len(user_slots) != profile["simulated_card_count"]:
            raise ValueError(
                f"CARD_SLOT_COUNT_MISMATCH:{user_id}"
            )

        # Dongbaek membership and synthetic card-slot ownership must agree.
        level = profile["dongbaek_usage_level"]
        if level is None or str(level).strip() == "":
            raise ValueError(f"UNKNOWN_DONGBAEK_USAGE_LEVEL:{user_id}")

        db_slot_count = sum(
            slot["product_id"] == "PRD_DB_SYN"
            for slot in user_slots
        )
        expected_db_count = 0 if level == "NON_MEMBER" else 1
        if db_slot_count != expected_db_count:
            raise ValueError(
                f"DB_OWNERSHIP_MISMATCH:{user_id}:"
                f"level={level}:"
                f"actual={db_slot_count}:"
                f"expected={expected_db_count}"
            )

        # 동일 상품 중복 슬롯 생성 방지
        product_ids = [
            s["product_id"] for s in user_slots
        ]

        if len(product_ids) != len(set(product_ids)):
            raise ValueError(
                f"DUPLICATE_CARD_PRODUCT:{user_id}"
            )

        status = profile["performance_state"]
        values = [
            s["sim_month_spend_won"]
            for s in user_slots
        ]

        if status == "NORMAL":
            if any(v is None for v in values):
                raise ValueError(
                    f"NORMAL_HAS_NULL:{user_id}"
                )

            if sum(values) != profile[
                "original_month_spend_won"
            ]:
                raise ValueError(
                    f"NORMAL_TOTAL_MISMATCH:{user_id}"
                )

        elif status == "ZERO_WON":
            if any(v != 0 for v in values):
                raise ValueError(
                    f"ZERO_SCENARIO_INVALID:{user_id}"
                )

        elif status in ("MISSING_ROW", "NULL_VALUE"):
            if any(v is not None for v in values):
                raise ValueError(
                    f"UNKNOWN_PERFORMANCE_HAS_VALUE:{user_id}"
                )

    profile_user_ids = {p["user_id"] for p in profiles}
    extra_slot_users = set(slot_index) - profile_user_ids
    if extra_slot_users:
        raise ValueError(
            f"UNEXPECTED_SLOT_USERS:{sorted(extra_slot_users)}"
        )

    expected_slots = sum(
        p["simulated_card_count"]
        for p in profiles
    )

    if len(slots) != expected_slots:
        raise ValueError("SLOT_TOTAL_MISMATCH")

    return {
        "scenario_id": SCENARIO_ID,
        "base_month": BASE_MONTH,
        "user_count": len(profiles),
        "slot_count": len(slots),
        "original_total_spend_won": source_total,
        "original_total_preserved": True,
        "dongbaek_member_count": sum(
            p["dongbaek_usage_level"] != "NON_MEMBER"
            for p in profiles
        ),
        "dongbaek_slot_user_count": sum(
            any(s["product_id"] == "PRD_DB_SYN" for s in slot_index[p["user_id"]])
            for p in profiles
        ),
        "dongbaek_nonmember_slot_count": 0,
        "card_count_distribution": dict(
            sorted(card_distribution.items())
        ),
        "usage_style_distribution": dict(
            sorted(usage_distribution.items())
        ),
        "performance_state_distribution": dict(
            sorted(perf_distribution.items())
        ),
        "normal_allocated_spend_won": sum(
            s["sim_month_spend_won"]
            for s in slots
            if s["performance_state"] == "NORMAL"
        ),
        "notes": [
            "SYNTHETIC_USER_PROFILES",
            "EXISTING_DB_TABLES_UNMODIFIED",
            "SOURCE_MONTH_TOTAL_RETAINED_IN_PROFILES",
            "NORMAL_USERS_HAVE_EXACT_SLOT_SUM",
            "MISSING_ROW_AND_NULL_VALUE_ARE_DISTINCT_STATES",
            "ZERO_WON_IS_AN_EXPLICIT_TEST_SCENARIO",
            "NEW_CARD_SLOTS_ARE_NOT_ACTUAL_ISSUED_CARDS",
        ],
    }


def write_csv(filename, rows):
    OUT.mkdir(exist_ok=True)
    path = OUT / filename

    with path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        if rows:
            writer = csv.DictWriter(
                f, fieldnames=list(rows[0].keys())
            )
            writer.writeheader()
            writer.writerows(rows)

    return path


def write_outputs(profiles, slots, summary):
    OUT.mkdir(exist_ok=True)

    p1 = write_csv(
        "sim_user_profile_v2.csv",
        profiles,
    )

    p2 = write_csv(
        "sim_user_card_slot_v2.csv",
        slots,
    )

    p3 = OUT / "summary.json"

    p3.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return p1, p2, p3


def upload_to_neondb(profiles, slots):
    """
    V2 테이블만 생성/UPSERT.

    기존 테이블 수정 없음.
    별도 환경변수 사용.
    """
    url = os.getenv("ONEPASS_WRITE_DATABASE_URL")

    if not url:
        raise RuntimeError(
            "ONEPASS_WRITE_DATABASE_URL_NOT_SET"
        )

    with psycopg.connect(
        url,
        autocommit=False,
    ) as conn:
        try:
            with conn.cursor() as cur:

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS
                    public.sim_user_profile_v2 (
                        scenario_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        base_month TEXT NOT NULL,
                        original_card_count INTEGER NOT NULL,
                        simulated_card_count INTEGER NOT NULL,
                        usage_style TEXT NOT NULL,
                        performance_state TEXT NOT NULL,
                        original_month_spend_won BIGINT NOT NULL,
                        age_band TEXT,
                        district_code TEXT,
                        spend_band TEXT,
                        dongbaek_usage_level TEXT,
                        PRIMARY KEY (scenario_id, user_id)
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS
                    public.sim_user_card_slot_v2 (
                        scenario_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        slot_no INTEGER NOT NULL,
                        product_id TEXT NOT NULL,
                        card_type TEXT,
                        base_month TEXT NOT NULL,
                        usage_style TEXT NOT NULL,
                        performance_state TEXT NOT NULL,
                        sim_month_spend_won BIGINT,
                        is_primary BOOLEAN NOT NULL,
                        PRIMARY KEY (
                            scenario_id,
                            user_id,
                            slot_no
                        )
                    )
                """)

                profile_columns = [
                    "scenario_id",
                    "user_id",
                    "base_month",
                    "original_card_count",
                    "simulated_card_count",
                    "usage_style",
                    "performance_state",
                    "original_month_spend_won",
                    "age_band",
                    "district_code",
                    "spend_band",
                    "dongbaek_usage_level",
                ]

                profile_sql = """
                    INSERT INTO public.sim_user_profile_v2 (
                        scenario_id,
                        user_id,
                        base_month,
                        original_card_count,
                        simulated_card_count,
                        usage_style,
                        performance_state,
                        original_month_spend_won,
                        age_band,
                        district_code,
                        spend_band,
                        dongbaek_usage_level
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (scenario_id, user_id)
                    DO UPDATE SET
                        base_month = EXCLUDED.base_month,
                        original_card_count =
                            EXCLUDED.original_card_count,
                        simulated_card_count =
                            EXCLUDED.simulated_card_count,
                        usage_style = EXCLUDED.usage_style,
                        performance_state =
                            EXCLUDED.performance_state,
                        original_month_spend_won =
                            EXCLUDED.original_month_spend_won,
                        age_band = EXCLUDED.age_band,
                        district_code = EXCLUDED.district_code,
                        spend_band = EXCLUDED.spend_band,
                        dongbaek_usage_level =
                            EXCLUDED.dongbaek_usage_level
                """

                cur.executemany(
                    profile_sql,
                    [
                        tuple(p[k] for k in profile_columns)
                        for p in profiles
                    ],
                )

                slot_columns = [
                    "scenario_id",
                    "user_id",
                    "slot_no",
                    "product_id",
                    "card_type",
                    "base_month",
                    "usage_style",
                    "performance_state",
                    "sim_month_spend_won",
                    "is_primary",
                ]

                slot_sql = """
                    INSERT INTO public.sim_user_card_slot_v2 (
                        scenario_id,
                        user_id,
                        slot_no,
                        product_id,
                        card_type,
                        base_month,
                        usage_style,
                        performance_state,
                        sim_month_spend_won,
                        is_primary
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (
                        scenario_id,
                        user_id,
                        slot_no
                    )
                    DO UPDATE SET
                        product_id = EXCLUDED.product_id,
                        card_type = EXCLUDED.card_type,
                        base_month = EXCLUDED.base_month,
                        usage_style = EXCLUDED.usage_style,
                        performance_state =
                            EXCLUDED.performance_state,
                        sim_month_spend_won =
                            EXCLUDED.sim_month_spend_won,
                        is_primary = EXCLUDED.is_primary
                """

                cur.executemany(
                    slot_sql,
                    [
                        tuple(s[k] for k in slot_columns)
                        for s in slots
                    ],
                )

                cur.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM public.sim_user_profile_v2
                    WHERE scenario_id = %s
                    """,
                    (SCENARIO_ID,),
                )
                profile_count = cur.fetchone()[0]

                cur.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM public.sim_user_card_slot_v2
                    WHERE scenario_id = %s
                    """,
                    (SCENARIO_ID,),
                )
                slot_count = cur.fetchone()[0]

                if profile_count != len(profiles):
                    raise ValueError(
                        "UPLOAD_PROFILE_COUNT_MISMATCH"
                    )

                if slot_count != len(slots):
                    raise ValueError(
                        "UPLOAD_SLOT_COUNT_MISMATCH"
                    )

            conn.commit()

            return {
                "uploaded": True,
                "profile_rows": profile_count,
                "slot_rows": slot_count,
                "scenario_id": SCENARIO_ID,
            }

        except Exception:
            conn.rollback()
            raise


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload validated V2 rows to NeonDB",
    )

    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    print("=== ONEPASS SYNTHETIC V2 ===")
    print("Loading original DB data...")

    source_users, owned = load_source_users()

    print("Users loaded:", len(source_users))

    profiles, slots = build_data(
        source_users, owned
    )

    summary = validate_data(
        profiles,
        slots,
        source_users,
    )

    paths = write_outputs(
        profiles, slots, summary
    )

    print("\n=== VALIDATION ===")
    print(json.dumps(
        summary,
        ensure_ascii=False,
        indent=2,
    ))

    print("\n=== GENERATED FILES ===")
    for path in paths:
        print(path)

    if args.upload:
        print("\n=== DATABASE UPLOAD ===")

        result = upload_to_neondb(
            profiles, slots
        )

        print(json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(
            "\nDRY RUN COMPLETE."
            "\nDB data was not modified."
            "\nUse --upload to insert V2 tables."
        )


if __name__ == "__main__":
    main()
