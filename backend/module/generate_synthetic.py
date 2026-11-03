
"""동백원패스 v0.6: 재현 가능한 합성 소비 데이터 생성."""

import argparse
import copy
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "sample_config.json"
TARGET = ROOT / "data" / "synthetic"

REQUEST_FIELDS = [
    "request_id",
    "user_id",
    "requested_at",
    "merchant_id",
    "amount_won",
    "onecard_active",
    "payment_path",
    "direct_card_id",
]


def make_user(template, index, rng):
    user = copy.deepcopy(template)
    uid = f"S{index:04d}"
    user["user_id"] = uid

    # 원본 계좌 ID를 사용자 전용 ID로 교체
    initial = user["initial_state"]

    account_map = {
        old_id: f"{uid}_ACC{n:02d}"
        for n, old_id in enumerate(
            initial["accounts"], start=1
        )
    }

    initial["accounts"] = {
        new_id: rng.randint(1_500_000, 3_000_000)
        for new_id in account_map.values()
    }

    # 기존 카드/규칙 ID도 사용자별로 분리
    card_map = {}
    rule_map = {}

    for n, card in enumerate(user["cards"], start=1):
        old_card_id = card["id"]
        new_card_id = f"{uid}_CARD{n:02d}"

        card_map[old_card_id] = new_card_id
        card["id"] = new_card_id

        old_account = card.get("account_id")
        if old_account is not None:
            card["account_id"] = account_map[old_account]

        if card["type"] == "CREDIT":
            card["credit_limit"] = 2_000_000

        card["active"] = True
        card["lost"] = False
        card["expired"] = False

        # 가상 전월 실적
        card["prev_month_perf"] = rng.randint(
            300_000, 700_000
        )

        for rule_no, rule in enumerate(
            card.get("rules", []), start=1
        ):
            old_rule_id = rule["id"]
            new_rule_id = (
                f"{uid}_R{n:02d}_{rule_no:02d}"
            )

            rule_map[old_rule_id] = new_rule_id
            rule["id"] = new_rule_id

    # 초기 상태의 참조 키도 새 ID에 맞게 변경
    initial["credit_used"] = {
        card_map[k]: v
        for k, v in initial.get(
            "credit_used", {}
        ).items()
    }

    initial["benefit_used"] = {
        rule_map[k]: v
        for k, v in initial.get(
            "benefit_used", {}
        ).items()
    }

    # 한 달 시작 시점 상태
    initial["db_charge"] = rng.randint(
        100_000, 300_000
    )
    initial["db_cashback"] = 0
    initial["db_grant"] = 0
    initial["db_month_applied"] = 0

    return user


def generate(
    users_count=100,
    transactions_per_user=40,
    seed=42,
):
    if users_count < 1:
        raise ValueError("users_count must be >= 1")

    if transactions_per_user < 1:
        raise ValueError(
            "transactions_per_user must be >= 1"
        )

    rng = random.Random(seed)

    source = json.loads(
        SOURCE.read_text(encoding="utf-8")
    )

    templates = source["users"]
    merchants = source["merchants"]

    if not templates or not merchants:
        raise ValueError(
            "Sample configuration is empty"
        )

    TARGET.mkdir(
        parents=True, exist_ok=True
    )

    new_users = []
    requests = []

    # 2026년 7월 한 달의 가상 거래
    start_date = datetime(2026, 7, 1)

    for i in range(1, users_count + 1):
        template = templates[(i - 1) % len(templates)]

        user = make_user(template, i, rng)
        new_users.append(user)

        uid = user["user_id"]

        # 가상 소비 성향별 거래금액 범위
        spending_group = (i - 1) % 3

        if spending_group == 0:
            amount_range = (3_000, 20_000)
        elif spending_group == 1:
            amount_range = (10_000, 50_000)
        else:
            amount_range = (20_000, 80_000)

        # 월간 거래 시점 생성
        moments = []

        for _ in range(transactions_per_user):
            day_offset = rng.randrange(31)
            hour = rng.randint(8, 22)
            minute = rng.randint(0, 59)

            dt = (
                start_date
                + timedelta(
                    days=day_offset,
                    hours=hour,
                    minutes=minute
                )
            )

            moments.append(dt)

        moments.sort()

        for j, dt in enumerate(moments, start=1):
            merchant = rng.choice(merchants)

            # 1,000원 단위 가상 결제금액
            amount = rng.randint(
                amount_range[0] // 1000,
                amount_range[1] // 1000
            ) * 1000

            requests.append({
                "request_id": f"{uid}_T{j:04d}",
                "user_id": uid,
                "requested_at": dt.isoformat(
                    timespec="seconds"
                ),
                "merchant_id": merchant["id"],
                "amount_won": amount,
                "onecard_active": "true",
                "payment_path": "ONECARD",
                "direct_card_id": "",
            })

    requests.sort(
        key=lambda row: (
            row["requested_at"],
            row["request_id"]
        )
    )

    configuration = {
        "merchants": merchants,
        "users": new_users,
    }

    config_path = TARGET / "synthetic_config.json"
    request_path = TARGET / "synthetic_requests.csv"

    config_path.write_text(
        json.dumps(
            configuration,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    with request_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=REQUEST_FIELDS
        )
        writer.writeheader()
        writer.writerows(requests)

    print("Synthetic data created")
    print(f"Users: {len(new_users)}")
    print(f"Requests: {len(requests)}")
    print(f"Seed: {seed}")
    print(f"Config: {config_path}")
    print(f"Requests file: {request_path}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--users", type=int, default=100
    )
    parser.add_argument(
        "--transactions", type=int, default=40
    )
    parser.add_argument(
        "--seed", type=int, default=42
    )

    args = parser.parse_args()

    generate(
        users_count=args.users,
        transactions_per_user=args.transactions,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
