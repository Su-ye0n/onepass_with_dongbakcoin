
"""동백원패스 CSV/DB 배치 실행 및 결과 저장."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .engine import (
    Card,
    CardType,
    BenefitRule,
    Merchant,
    DbPolicy,
    Request,
    State,
    process,
)

TX_FIELDS = [
    "run_id", "user_id", "request_id", "requested_at",
    "merchant_id", "amount_won", "approved",
    "selected_card_id", "benefit_won", "reason",
]

CAND_FIELDS = [
    "run_id", "user_id", "request_id", "card_id",
    "eligible", "reason", "expected_benefit_won",
    "funding_mode", "rule_id", "db_applied_won",
]

LEDGER_FIELDS = [
    "run_id", "user_id", "request_id", "card_id",
    "amount_won", "benefit_won", "funding_mode",
]

SUMMARY_FIELDS = [
    "run_id", "user_id", "request_count",
    "approved_count", "rejected_count",
    "approved_amount_won", "total_benefit_won",
    "ending_db_charge_won", "ending_db_cashback_won",
    "ending_db_grant_won", "ending_db_month_applied_won",
    "ending_accounts_json", "ending_credit_used_json",
]


def load_configuration(path: Path):
    """기존 JSON 설정을 엔진 객체로 변환한다."""

    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    merchants = {
        r["id"]: Merchant(
            r["id"],
            r["category"],
            r["db_registered"],
            r.get("annual_sales_band", "LE_10B"),
        )
        for r in raw["merchants"]
    }

    users = {}
    seen_card_ids = set()

    for user in raw["users"]:
        uid = user["user_id"]

        if uid in users:
            raise ValueError(f"duplicate user_id: {uid}")

        cards = []

        for card_raw in user["cards"]:
            card_id = card_raw["id"]

            if card_id in seen_card_ids:
                raise ValueError(
                    f"card id must be globally unique: {card_id}"
                )

            seen_card_ids.add(card_id)

            rules = tuple(
                BenefitRule(
                    rule["id"],
                    tuple(rule["categories"]),
                    Decimal(str(rule["rate"])),
                    rule.get("prev_month_min", 0),
                    rule.get("min_payment", 0),
                    rule.get("per_tx_cap"),
                    rule.get("monthly_cap"),
                )
                for rule in card_raw.get("rules", [])
            )

            cards.append(
                Card(
                    card_id,
                    CardType(card_raw["type"]),
                    card_raw.get("account_id"),
                    card_raw.get("credit_limit", 0),
                    card_raw.get("active", True),
                    card_raw.get("lost", False),
                    card_raw.get("expired", False),
                    card_raw.get("prev_month_perf", 0),
                    rules,
                )
            )

        initial = user["initial_state"]

        state = State(
            accounts=dict(initial["accounts"]),
            credit_used=dict(initial.get("credit_used", {})),
            db_charge=initial.get("db_charge", 0),
            db_cashback=initial.get("db_cashback", 0),
            db_grant=initial.get("db_grant", 0),
            db_month_applied=initial.get("db_month_applied", 0),
            benefit_used=dict(initial.get("benefit_used", {})),
        )

        users[uid] = (cards, state)

    return merchants, users, DbPolicy()


def read_requests(path: Path, merchants, users):
    """CSV 요청을 읽고 시간순으로 정렬한다."""

    path = Path(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        required = {
            "request_id",
            "user_id",
            "requested_at",
            "merchant_id",
            "amount_won",
            "onecard_active",
        }

        columns = set(reader.fieldnames or [])

        if not required.issubset(columns):
            raise ValueError(
                f"missing request columns: "
                f"{sorted(required - columns)}"
            )

        records = []

        for number, row in enumerate(reader, start=2):
            uid = row["user_id"].strip()
            mid = row["merchant_id"].strip()

            if uid not in users or mid not in merchants:
                raise ValueError(
                    f"row {number}: unknown user_id/"
                    f"merchant_id: {uid}/{mid}"
                )

            request_id = row["request_id"].strip()
            requested_at = row["requested_at"].strip()

            if not request_id or not requested_at:
                raise ValueError(
                    f"row {number}: request_id/"
                    f"requested_at required"
                )

            active = row["onecard_active"].strip().lower()

            if active not in ("true", "false", "1", "0"):
                raise ValueError(
                    f"row {number}: onecard_active "
                    f"must be true/false/1/0"
                )

            try:
                parsed_at = datetime.fromisoformat(requested_at)
                amount = int(row["amount_won"])
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"row {number}: invalid requested_at "
                    f"or amount_won"
                ) from exc

            if parsed_at.tzinfo is not None:
                raise ValueError(
                    f"row {number}: use local naive "
                    f"ISO datetime consistently"
                )

            # DIRECT / ONECARD 경로 유지
            payment_path = (
                row.get("payment_path") or "ONECARD"
            ).strip().upper()

            direct_card_id = (
                row.get("direct_card_id") or ""
            ).strip() or None

            if payment_path not in ("ONECARD", "DIRECT"):
                raise ValueError(
                    f"row {number}: invalid payment_path: "
                    f"{payment_path}"
                )

            if payment_path == "DIRECT" and not direct_card_id:
                raise ValueError(
                    f"row {number}: DIRECT requires direct_card_id"
                )

            request = Request(
                id=request_id,
                merchant_id=mid,
                amount=amount,
                onecard_active=active in ("true", "1"),
                payment_path=payment_path,
                direct_card_id=direct_card_id,
            )

            records.append(
                (parsed_at, number, uid, mid, request)
            )

    return sorted(records, key=lambda item: (item[0], item[1]))


def write_csv(path: Path, fields, rows):
    """결과 CSV를 UTF-8 BOM 형식으로 저장한다."""

    path = Path(path)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)


def reset_monthly_state(state: State):
    """
    월 변경 시 월간 누적값만 초기화한다.

    초기화:
      - 동백전 월 캐시백 적용 누적액
      - 일반카드 규칙별 월 혜택 사용액

    유지:
      - 예금계좌 잔액
      - 동백전 충전금/캐시백/지원금 잔액
      - 신용카드 사용액
      - 처리한 요청 ID와 원장
    """

    state.db_month_applied = 0
    state.benefit_used.clear()


def run_batch(
    config_path: Path,
    request_path: Path,
    output_dir: Path,
    run_id="DEMO-001",
    *,
    loaded=None,
    policy_resolver=None,
):
    """
    배치 시뮬레이션 실행.

    loaded:
        DB에서 읽은 (merchants, users, policy).
        None이면 기존 JSON 설정을 사용한다.

    policy_resolver:
        거래일 YYYY-MM-DD를 받아 DbPolicy를 반환하는 함수.
        None이면 단일 기본 정책을 사용한다.
    """

    if loaded is not None:
        merchants, users, policy = loaded
    else:
        merchants, users, policy = load_configuration(
            Path(config_path)
        )

    requests = read_requests(
        Path(request_path),
        merchants,
        users,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tx_rows = []
    candidate_rows = []
    ledger_rows = []
    totals = {}

    # 사용자별 마지막 처리 월
    # 다른 사용자와 월별 누적 상태가 섞이지 않도록 분리
    last_month_by_user = {}

    for at, _, uid, mid, req in requests:
        cards, state = users[uid]

        # 1. 거래월 확인
        current_month = at.strftime("%Y-%m")
        previous_month = last_month_by_user.get(uid)

        # 2. 월 변경 감지 및 월간 한도 초기화
        # 첫 번째 거래에서는 입력 초기 상태를 그대로 사용
        if (
            previous_month is not None
            and previous_month != current_month
        ):
            reset_monthly_state(state)

        last_month_by_user[uid] = current_month

        # 3. 거래일에 유효한 정책 조회
        effective_policy = (
            policy_resolver(at.date().isoformat())
            if policy_resolver is not None
            else policy
        )

        # 4. 결제 의사결정 및 상태 갱신
        decision = process(
            req,
            merchants[mid],
            cards,
            state,
            effective_policy,
        )

        # 5. 거래 결과 기록
        tx_rows.append({
            "run_id": run_id,
            "user_id": uid,
            "request_id": req.id,
            "requested_at": at.isoformat(timespec="seconds"),
            "merchant_id": mid,
            "amount_won": req.amount,
            "approved": decision.approved,
            "selected_card_id": decision.selected_card_id or "",
            "benefit_won": decision.benefit_won,
            "reason": decision.reason,
        })

        # 6. 카드 후보별 판단 결과 기록
        for candidate in decision.candidates:
            candidate_rows.append({
                "run_id": run_id,
                "user_id": uid,
                "request_id": req.id,
                "card_id": candidate.card_id,
                "eligible": candidate.eligible,
                "reason": candidate.reason,
                "expected_benefit_won": (
                    candidate.expected_benefit
                ),
                "funding_mode": candidate.funding_mode,
                "rule_id": candidate.rule_id,
                "db_applied_won": candidate.db_applied,
            })

        # 7. 승인 거래 원장 기록
        if decision.approved:
            event = state.ledger[-1]

            ledger_rows.append({
                "run_id": run_id,
                "user_id": uid,
                "request_id": req.id,
                "card_id": event["card_id"],
                "amount_won": event["amount"],
                "benefit_won": event["benefit_won"],
                "funding_mode": event["funding"],
            })

        # 8. 사용자별 누적 집계
        aggregate = totals.setdefault(
            uid,
            {
                "count": 0,
                "approved": 0,
                "amount": 0,
                "benefit": 0,
            },
        )

        aggregate["count"] += 1

        if decision.approved:
            aggregate["approved"] += 1
            aggregate["amount"] += req.amount
            aggregate["benefit"] += decision.benefit_won

    # 9. 사용자별 최종 상태 요약
    summary = []

    for uid, (cards, state) in users.items():
        total = totals.get(
            uid,
            {
                "count": 0,
                "approved": 0,
                "amount": 0,
                "benefit": 0,
            },
        )

        summary.append({
            "run_id": run_id,
            "user_id": uid,
            "request_count": total["count"],
            "approved_count": total["approved"],
            "rejected_count": (
                total["count"] - total["approved"]
            ),
            "approved_amount_won": total["amount"],
            "total_benefit_won": total["benefit"],
            "ending_db_charge_won": state.db_charge,
            "ending_db_cashback_won": state.db_cashback,
            "ending_db_grant_won": state.db_grant,
            "ending_db_month_applied_won": (
                state.db_month_applied
            ),
            "ending_accounts_json": json.dumps(
                state.accounts,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "ending_credit_used_json": json.dumps(
                state.credit_used,
                ensure_ascii=False,
                sort_keys=True,
            ),
        })

    # 10. 결과 저장
    write_csv(
        output_dir / "engine_tx.csv",
        TX_FIELDS,
        tx_rows,
    )

    write_csv(
        output_dir / "engine_candidate.csv",
        CAND_FIELDS,
        candidate_rows,
    )

    write_csv(
        output_dir / "engine_ledger.csv",
        LEDGER_FIELDS,
        ledger_rows,
    )

    write_csv(
        output_dir / "user_summary.csv",
        SUMMARY_FIELDS,
        summary,
    )

    return {
        "requests": len(tx_rows),
        "approved": sum(
            row["approved"]
            for row in tx_rows
        ),
        "benefit_won": sum(
            row["benefit_won"]
            for row in tx_rows
        ),
        "users": len(users),
        "output_dir": str(output_dir),
    }


def main():
    root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(
        description="Dongbaek OnePass CSV transaction batch"
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=root / "data" / "sample_config.json",
    )

    parser.add_argument(
        "--requests",
        type=Path,
        default=root / "data" / "tx_requests.csv",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=root / "output",
    )

    parser.add_argument(
        "--run-id",
        default="DEMO-001",
    )

    args = parser.parse_args()

    result = run_batch(
        args.config,
        args.requests,
        args.output,
        args.run_id,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
