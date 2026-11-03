
"""Generate mixed-industry OnePass P1 test transactions.

Reads real merchant IDs from NeonDB.
Writes a local JSON test file only.
Does not modify NeonDB.
"""

import json
from pathlib import Path

from dotenv import load_dotenv
from onepass.db_connection import connect_readonly


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def load_merchants():
    with connect_readonly() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    industry_code,
                    MIN(merchant_id) AS merchant_id,
                    COUNT(*) AS merchant_count
                FROM public.merchant
                WHERE merchant_id IS NOT NULL
                  AND industry_code IS NOT NULL
                  AND industry_code <> ''
                GROUP BY industry_code
                ORDER BY industry_code
            """)

            # dict_row 결과를 기존 함수에서 사용하는
            # (industry_code, merchant_id, merchant_count)
            # 튜플 형태로 변환
            return [
                (
                    row["industry_code"],
                    row["merchant_id"],
                    row["merchant_count"],
                )
                for row in cur.fetchall()
            ]


def choose_merchants(rows, count=4):
    # 가능한 경우 카페·음식·주유·기타 업종 우선
    keywords = [
        ("CAFE", "BAKERY", "COFFEE"),
        ("FOOD", "RESTAURANT", "DINING"),
        ("FUEL", "GAS", "OIL"),
    ]

    selected = []
    used_codes = set()

    for group in keywords:
        for code, merchant_id, merchant_count in rows:
            upper = code.upper()

            if code in used_codes:
                continue

            if any(word in upper for word in group):
                selected.append(
                    (code, merchant_id, merchant_count)
                )
                used_codes.add(code)
                break

    # 실제 업종 코드가 다를 경우 다른 업종으로 보충
    for row in rows:
        if len(selected) >= count:
            break

        code = row[0]

        if code not in used_codes:
            selected.append(row)
            used_codes.add(code)

    if len(selected) < count:
        raise RuntimeError(
            f"최소 {count}개 업종이 필요하지만 "
            f"{len(selected)}개만 조회됐습니다."
        )

    return selected[:count]


def main():
    rows = load_merchants()
    merchants = choose_merchants(rows)

    transactions = []

    for index in range(8):
        code, merchant_id, _ = merchants[index % 4]

        # 같은 가맹점을 OFFLINE / ONLINE에서 각각 검사
        lane = "OFFLINE" if index < 4 else "ONLINE"

        transactions.append({
            "transaction_id": f"MIX{index + 1:03d}",
            "date": f"2026-06-{index + 1:02d}",
            "merchant_id": merchant_id,
            "amount_won": 32000,
            "lane": lane,
            "provider": None,
        })

    output = BASE_DIR / "test_mixed_transactions.json"
    output.write_text(
        json.dumps(
            transactions,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=== SELECTED MERCHANTS ===")
    for code, merchant_id, merchant_count in merchants:
        print(
            f"{merchant_id} | "
            f"{code} | "
            f"available_merchants={merchant_count}"
        )

    print("\n=== GENERATED TRANSACTIONS ===")
    for tx in transactions:
        print(
            tx["transaction_id"],
            tx["merchant_id"],
            tx["lane"],
            tx["amount_won"],
        )

    print(f"\nSaved: {output.name}")


if __name__ == "__main__":
    main()
