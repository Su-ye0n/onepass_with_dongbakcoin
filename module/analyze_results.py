
"""동백원패스 v0.6: 월간 비교 결과 분석."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def read_csv(path):
    with Path(path).open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        return list(csv.DictReader(file))


def money(value):
    return f"{value:,.0f}원"


def analyze(output_dir):
    output_dir = Path(output_dir)

    monthly = read_csv(
        output_dir / "strategy_monthly.csv"
    )
    comparison = read_csv(
        output_dir / "strategy_comparison.csv"
    )

    if not monthly or not comparison:
        raise ValueError(
            "Comparison results are empty"
        )

    # 1. 전략별 전체 성과
    totals = defaultdict(
        lambda: {
            "users": 0,
            "requests": 0,
            "approved": 0,
            "approved_amount": 0,
            "benefit": 0,
        }
    )

    for row in monthly:
        strategy = row["strategy"]
        item = totals[strategy]

        item["users"] += 1
        item["requests"] += int(row["requests"])
        item["approved"] += int(row["approved"])
        item["approved_amount"] += int(
            row["approved_amount_won"]
        )
        item["benefit"] += int(
            row["total_benefit_won"]
        )

    print("\n=== 전략별 월간 성과 ===")

    for strategy in ("A1", "A2", "A3", "B"):
        item = totals[strategy]

        if item["requests"] == 0:
            continue

        approval_rate = (
            100 * item["approved"] / item["requests"]
        )

        print(f"\n[{strategy}]")
        print(f"Users: {item['users']}")
        print(f"Requests: {item['requests']}")
        print(f"Approved: {item['approved']}")
        print(f"Approval rate: {approval_rate:.2f}%")
        print(
            "Approved amount:",
            money(item["approved_amount"])
        )
        print(
            "Total benefit:",
            money(item["benefit"])
        )

    # 2. 원패스 대비 혜택 차이
    grouped = defaultdict(list)

    for row in comparison:
        grouped[row["baseline"]].append(row)

    summary_rows = []

    print("\n=== 원패스 B vs 기존 방식 ===")

    for baseline in ("A1", "A2", "A3"):
        rows = grouped[baseline]

        if not rows:
            continue

        increases = [
            int(row["difference_won"])
            for row in rows
        ]

        improved = sum(
            value > 0 for value in increases
        )

        unchanged = sum(
            value == 0 for value in increases
        )

        worsened = sum(
            value < 0 for value in increases
        )

        total_diff = sum(increases)
        avg_diff = total_diff / len(rows)

        comparable = [
            row for row in rows
            if row["comparable_approval_amount"].lower()
            == "true"
        ]

        # 승인금액이 동일한 사용자만 별도 집계
        comparable_diff = sum(
            int(row["difference_won"])
            for row in comparable
        )

        baseline_benefit = sum(
            int(row["baseline_benefit_won"])
            for row in rows
        )

        improvement_rate = (
            100 * total_diff / baseline_benefit
            if baseline_benefit > 0
            else None
        )

        print(f"\n[B vs {baseline}]")
        print(
            "Total benefit difference:",
            money(total_diff)
        )
        print(
            "Average difference per user-month:",
            money(avg_diff)
        )
        print(
            "Improved:",
            f"{improved}/{len(rows)}"
        )
        print(
            "Unchanged:",
            f"{unchanged}/{len(rows)}"
        )
        print(
            "Worsened:",
            f"{worsened}/{len(rows)}"
        )
        print(
            "Same approved amount:",
            f"{len(comparable)}/{len(rows)}"
        )
        print(
            "Benefit difference (same amount only):",
            money(comparable_diff)
        )

        if improvement_rate is not None:
            print(
                "Aggregate benefit growth:",
                f"{improvement_rate:.2f}%"
            )

        summary_rows.append({
            "baseline": baseline,
            "user_month_count": len(rows),
            "improved_count": improved,
            "unchanged_count": unchanged,
            "worsened_count": worsened,
            "total_difference_won": total_diff,
            "average_difference_won": round(
                avg_diff, 2
            ),
            "same_approved_amount_count": len(
                comparable
            ),
            "same_amount_difference_won": (
                comparable_diff
            ),
            "aggregate_growth_percent": (
                round(improvement_rate, 2)
                if improvement_rate is not None
                else ""
            ),
        })

    # 3. 분석 요약 저장
    summary_path = (
        output_dir / "analysis_summary.csv"
    )

    with summary_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(summary_rows[0].keys())
        )

        writer.writeheader()
        writer.writerows(summary_rows)

    print("\nSaved:", summary_path)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        type=Path,
        default=(
            Path(__file__).resolve().parent
            / "output"
            / "synthetic"
        )
    )

    args = parser.parse_args()
    analyze(args.output)


if __name__ == "__main__":
    main()
