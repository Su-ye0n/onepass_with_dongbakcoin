
"""동백원패스 v0.3: 기존 방식 A1~A3과 원패스 B 비교."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

from .batch import (
    load_configuration,
    read_requests,
    write_csv,
)
from .engine import (
    CardType,
    Decision,
    evaluate,
    apply,
    decide,
)

STRATEGIES = ("A1", "A2", "A3", "B")

TX_FIELDS = [
    "strategy", "user_id", "request_id",
    "requested_at", "merchant_id", "amount_won",
    "approved", "selected_card_id",
    "benefit_won", "reason",
]

MONTH_FIELDS = [
    "strategy", "user_id", "month",
    "requests", "approved", "approved_amount_won",
    "total_benefit_won", "db_cashback_won",
    "db_applied_won",
]

COMPARE_FIELDS = [
    "user_id", "month", "baseline",
    "baseline_benefit_won", "onepass_benefit_won",
    "difference_won", "baseline_approved_amount_won",
    "onepass_approved_amount_won",
    "comparable_approval_amount",
]


# ─────────────────────────────────────
# A1. 확률 기반 카드 사용 모델
# ─────────────────────────────────────

def weighted_order(
    cards, uid, request_id, seed, weights
):
    # 거래마다 같은 난수 결과를 재현하도록 설정
    digest = hashlib.sha256(
        f"{seed}|{uid}|{request_id}".encode()
    ).digest()

    rng = random.Random(
        int.from_bytes(digest[:8], "big")
    )

    available = list(cards)
    ordered = []

    while available:
        probabilities = [
            max(0, weights.get(c.type.value, 1))
            for c in available
        ]

        if not any(probabilities):
            probabilities = [1] * len(available)

        picked = rng.choices(
            available,
            weights=probabilities,
            k=1,
        )[0]

        ordered.append(picked)
        available.remove(picked)

    return ordered


# ─────────────────────────────────────
# A1·A2·A3 카드 선택 순서
# ─────────────────────────────────────

def order_cards(
    strategy, cards, merchant,
    uid, request_id, seed, weights
):
    if strategy == "A1":
        return weighted_order(
            cards, uid, request_id, seed, weights
        )

    if strategy == "A2":
        # 등록된 첫 번째 카드를 기본카드로 가정
        return list(cards)

    if strategy == "A3":
        # 동백전 가맹점이면 동백전 카드 우선
        return sorted(
            cards,
            key=lambda c: (
                not (
                    merchant.db_registered
                    and c.type == CardType.DONGBAEK_CHECK
                ),
                cards.index(c),
            ),
        )

    raise ValueError(f"Unknown strategy: {strategy}")

# ─────────────────────────────────────
# 기존 방식 결제 판단
# ─────────────────────────────────────

def baseline_decision(
    strategy, req, merchant, cards,
    state, policy, uid, seed, weights
):
    if req.id in state.processed_requests:
        return Decision(
            req.id, False, None, 0,
            "DUPLICATE_REQUEST", ()
        )

    if req.amount <= 0:
        return Decision(
            req.id, False, None, 0,
            "INVALID_AMOUNT", ()
        )

    # A1~A3는 기존 실물카드 사용 방식이므로
    # 원카드 활성 상태를 검사하지 않음

    candidates = tuple(
        evaluate(
            card, merchant, req.amount, state, policy
        )
        for card in cards
    )

    by_id = {
        c.card_id: c for c in candidates
    }

    ordered = order_cards(
        strategy, cards, merchant,
        uid, req.id, seed, weights
    )

    for card in ordered:
        candidate = by_id[card.id]

        if candidate.eligible:
            return Decision(
                req.id,
                True,
                card.id,
                candidate.expected_benefit,
                f"{strategy}_CHOICE",
                candidates,
            )

    return Decision(
        req.id, False, None, 0,
        "NO_ELIGIBLE_CARD", candidates
    )


# ─────────────────────────────────────
# A1·A2·A3·B 독립 시뮬레이션
# ─────────────────────────────────────

def run_comparison(
    config_path,
    requests_path,
    output_dir,
    seed=42,
    weights=None,
):
    # A1 임시 사용 가중치 (실측 비율 아님)
    weights = weights or {
        "DONGBAEK_CHECK": 3,
        "DEBIT": 2,
        "CREDIT": 5,
    }

    merchants, initial_users, policy = (
        load_configuration(Path(config_path))
    )

    requests = read_requests(
        Path(requests_path),
        merchants,
        initial_users,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(
        parents=True, exist_ok=True
    )

    tx_rows = []

    month_data = defaultdict(
        lambda: {
            "requests": 0,
            "approved": 0,
            "approved_amount_won": 0,
            "total_benefit_won": 0,
            "db_cashback_won": 0,
            "db_applied_won": 0,
        }
    )

    for strategy in STRATEGIES:

        # 전략별 초기 상태를 독립적으로 복사
        users = copy.deepcopy(initial_users)

        for dt, _, uid, mid, req in requests:
            cards, state = users[uid]
            merchant = merchants[mid]

            
            # DIRECT: 모든 전략에서 지정 실물카드로만 결제
            if req.payment_path == "DIRECT":
                decision = decide(
                    req, merchant, cards, state, policy
                )

            # ONECARD + B: 최대 혜택 자동 배정
            elif strategy == "B":
                decision = decide(
                    req, merchant, cards, state, policy
                )

            # A1~A3: 기존 카드 사용 행동 시뮬레이션
            else:
                decision = baseline_decision(
                    strategy,
                    req,
                    merchant,
                    cards,
                    state,
                    policy,
                    uid,
                    seed,
                    weights
                )

            applied = 0
            is_db = False

            if decision.approved:
                candidate = next(
                    c for c in decision.candidates
                    if c.card_id == decision.selected_card_id
                )

                applied = candidate.db_applied

                selected_card = next(
                    c for c in cards
                    if c.id == decision.selected_card_id
                )

                is_db = (
                    selected_card.type
                    == CardType.DONGBAEK_CHECK
                )

                # 기존 상태 관리 엔진으로 결제 확정
                apply(
                    decision, req, cards, state
                )

            month = dt.strftime("%Y-%m")
            agg = month_data[
                strategy, uid, month
            ]

            agg["requests"] += 1
            agg["approved"] += int(
                decision.approved
            )

            if decision.approved:
                agg["approved_amount_won"] += req.amount
                agg["total_benefit_won"] += (
                    decision.benefit_won
                )

                if is_db:
                    agg["db_cashback_won"] += (
                        decision.benefit_won
                    )
                    agg["db_applied_won"] += applied

            tx_rows.append({
                "strategy": strategy,
                "user_id": uid,
                "request_id": req.id,
                "requested_at": dt.isoformat(
                    timespec="seconds"
                ),
                "merchant_id": mid,
                "amount_won": req.amount,
                "approved": decision.approved,
                "selected_card_id": (
                    decision.selected_card_id or ""
                ),
                "benefit_won": decision.benefit_won,
                "reason": decision.reason,
            })

    # 전략별 월간 합계
    month_rows = [
        dict(
            strategy=s,
            user_id=uid,
            month=month,
            **vals
        )
        for (s, uid, month), vals
        in sorted(month_data.items())
    ]

    lookup = {
        (
            row["strategy"],
            row["user_id"],
            row["month"]
        ): row
        for row in month_rows
    }

    # 각 기준선과 원패스 B 비교
    comparison_rows = []

    for (s, uid, month), row in sorted(
        lookup.items()
    ):
        if s == "B":
            continue

        b = lookup["B", uid, month]

        comparison_rows.append({
            "user_id": uid,
            "month": month,
            "baseline": s,
            "baseline_benefit_won": (
                row["total_benefit_won"]
            ),
            "onepass_benefit_won": (
                b["total_benefit_won"]
            ),
            "difference_won": (
                b["total_benefit_won"]
                - row["total_benefit_won"]
            ),
            "baseline_approved_amount_won": (
                row["approved_amount_won"]
            ),
            "onepass_approved_amount_won": (
                b["approved_amount_won"]
            ),
            "comparable_approval_amount": (
                row["approved_amount_won"]
                == b["approved_amount_won"]
            ),
        })

    # 결과 CSV 3종 저장
    write_csv(
        output_dir / "strategy_tx.csv",
        TX_FIELDS,
        tx_rows,
    )

    write_csv(
        output_dir / "strategy_monthly.csv",
        MONTH_FIELDS,
        month_rows,
    )

    write_csv(
        output_dir / "strategy_comparison.csv",
        COMPARE_FIELDS,
        comparison_rows,
    )

    return {
        "requests_per_strategy": len(requests),
        "strategies": list(STRATEGIES),
        "monthly_rows": len(month_rows),
        "comparison_rows": len(comparison_rows),
        "output_dir": str(output_dir),
    }


def main():
    root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser()

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
        "--seed", type=int, default=42
    )

    args = parser.parse_args()

    result = run_comparison(
        args.config,
        args.requests,
        args.output,
        args.seed,
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
