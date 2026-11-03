
"""동백원패스 v0.7: 전략 선택 차이 및 혜택 악화 진단."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def load_csv(path):
    with Path(path).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))


def save_csv(path, rows, columns):
    with Path(path).open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=columns
        )
        writer.writeheader()
        writer.writerows(rows)


def approved(row):
    return row["approved"].lower() == "true"


def transaction_key(row):
    # 사용자별로 요청 ID가 중복되지 않는다는
    # 현재 batch.py의 입력 검증을 전제
    return (
        row["user_id"],
        row["request_id"]
    )


def diagnose(output_dir):
    output_dir = Path(output_dir)

    tx = load_csv(
        output_dir / "strategy_tx.csv"
    )

    comparison = load_csv(
        output_dir / "strategy_comparison.csv"
    )

    if not tx or not comparison:
        raise ValueError(
            "전략별 시뮬레이션 결과가 비어 있습니다."
        )

    strategies = ("A1", "A2", "A3", "B")

    # 1. 전략과 거래 ID로 결과 인덱싱
    indexed = {}
    ids_by_strategy = {
        s: set() for s in strategies
    }

    for row in tx:
        s = row["strategy"]

        if s not in ids_by_strategy:
            raise ValueError(
                f"Unknown strategy: {s}"
            )

        key = transaction_key(row)
        composite = (s, *key)

        if composite in indexed:
            raise ValueError(
                f"Duplicate transaction: {composite}"
            )

        indexed[composite] = row
        ids_by_strategy[s].add(key)

    # 전략별 동일 거래 입력 여부 검사
    common_ids = ids_by_strategy["B"]

    for s in strategies:
        if ids_by_strategy[s] != common_ids:
            raise ValueError(
                f"{s}의 요청 집합이 B와 다릅니다."
            )

    # 2. A2와 A3의 실제 선택 비교
    duplicate_rows = []

    same_card = 0
    same_result = 0

    for uid, request_id in sorted(common_ids):

        a2 = indexed["A2", uid, request_id]
        a3 = indexed["A3", uid, request_id]

        card_equal = (
            a2["selected_card_id"]
            == a3["selected_card_id"]
        )

        result_equal = (
            card_equal
            and a2["approved"] == a3["approved"]
            and a2["benefit_won"] == a3["benefit_won"]
        )

        same_card += card_equal
        same_result += result_equal

        if not result_equal:
            duplicate_rows.append({
                "user_id": uid,
                "request_id": request_id,
                "a2_card": a2["selected_card_id"],
                "a3_card": a3["selected_card_id"],
                "a2_approved": a2["approved"],
                "a3_approved": a3["approved"],
                "a2_benefit_won": a2["benefit_won"],
                "a3_benefit_won": a3["benefit_won"],
            })

    save_csv(
        output_dir / "diagnosis_a2_a3.csv",
        duplicate_rows,
        [
            "user_id", "request_id",
            "a2_card", "a3_card",
            "a2_approved", "a3_approved",
            "a2_benefit_won", "a3_benefit_won"
        ]
    )

    print("\n=== A2 vs A3 선택 결과 ===")
    print("전체 거래:", len(common_ids))
    print("선택 카드 일치:", same_card)
    print("승인·혜택까지 일치:", same_result)
    print("결과 불일치:", len(duplicate_rows))

    # 3. B보다 A1이 유리했던 사용자-월 추출
    negative_rows = [
        r for r in comparison
        if r["baseline"] == "A1"
        and int(r["difference_won"]) < 0
    ]

    negative_rows.sort(
        key=lambda r: int(r["difference_won"])
    )

    save_csv(
        output_dir / "diagnosis_negative_users.csv",
        negative_rows,
        [
            "user_id", "month", "baseline",
            "baseline_benefit_won",
            "onepass_benefit_won",
            "difference_won",
            "baseline_approved_amount_won",
            "onepass_approved_amount_won",
            "comparable_approval_amount",
        ]
    )

    print("\n=== 원패스가 A1보다 불리한 사용자-월 ===")
    print("악화된 사용자-월 수:", len(negative_rows))

    for row in negative_rows[:10]:
        print(
            row["user_id"],
            row["month"],
            f'{int(row["difference_won"]):+,}원'
        )

    # 4. 악화된 사용자들의 거래별 혜택 차이
    negative_keys = {
        (r["user_id"], r["month"])
        for r in negative_rows
    }

    tradeoff_rows = []
    totals = defaultdict(int)

    for uid, request_id in sorted(common_ids):
        a1 = indexed["A1", uid, request_id]
        b = indexed["B", uid, request_id]

        month = b["requested_at"][:7]

        if (uid, month) not in negative_keys:
            continue

        a1_benefit = int(a1["benefit_won"])
        b_benefit = int(b["benefit_won"])
        diff = b_benefit - a1_benefit

        totals[(uid, month)] += diff

        tradeoff_rows.append({
            "user_id": uid,
            "month": month,
            "request_id": request_id,
            "requested_at": b["requested_at"],
            "merchant_id": b["merchant_id"],
            "amount_won": b["amount_won"],
            "a1_card_id": a1["selected_card_id"],
            "b_card_id": b["selected_card_id"],
            "a1_approved": a1["approved"],
            "b_approved": b["approved"],
            "a1_benefit_won": a1_benefit,
            "b_benefit_won": b_benefit,
            "difference_won": diff,
            "card_changed": (
                a1["selected_card_id"]
                != b["selected_card_id"]
            ),
        })

    tradeoff_rows.sort(
        key=lambda r: (
            r["user_id"],
            r["requested_at"],
            r["request_id"]
        )
    )

    save_csv(
        output_dir / "diagnosis_tradeoffs.csv",
        tradeoff_rows,
        [
            "user_id", "month", "request_id",
            "requested_at", "merchant_id",
            "amount_won",
            "a1_card_id", "b_card_id",
            "a1_approved", "b_approved",
            "a1_benefit_won", "b_benefit_won",
            "difference_won", "card_changed",
        ]
    )

    # 5. 월간 차이와 거래별 차이 합계 검증
    for row in negative_rows:
        key = (row["user_id"], row["month"])

        calculated = totals[key]
        expected = int(row["difference_won"])

        if calculated != expected:
            raise AssertionError(
                f"{key}: 거래별 차이 합계 "
                f"{calculated} != 월간 차이 {expected}"
            )

    adverse = [
        r for r in tradeoff_rows
        if r["difference_won"] < 0
    ]

    favorable = [
        r for r in tradeoff_rows
        if r["difference_won"] > 0
    ]

    print("\n=== 악화 사용자 거래 분석 ===")
    print("분석 거래:", len(tradeoff_rows))
    print("B가 유리했던 거래:", len(favorable))
    print("B가 불리했던 거래:", len(adverse))
    print(
        "카드 선택 변경 거래:",
        sum(
            str(r["card_changed"]) == "True"
            for r in tradeoff_rows
        )
    )

    print("\n혜택 차이가 가장 불리한 거래 TOP 10")

    for row in sorted(
        adverse,
        key=lambda r: r["difference_won"]
    )[:10]:
        print(
            row["user_id"],
            row["request_id"],
            row["a1_card_id"],
            "->",
            row["b_card_id"],
            f'{row["difference_won"]:+,}원'
        )

    print("\n=== 생성된 파일 ===")
    for filename in (
        "diagnosis_a2_a3.csv",
        "diagnosis_negative_users.csv",
        "diagnosis_tradeoffs.csv",
    ):
        print(output_dir / filename)


def main():
    root = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "output" / "synthetic"
    )

    args = parser.parse_args()
    diagnose(args.output)


if __name__ == "__main__":
    main()
