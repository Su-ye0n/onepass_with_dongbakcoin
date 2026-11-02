
"""Extract original v3.3 BASE transactions.

No DB writes.
No synthetic transactions generated.

Reads the original ZIP directly and exports:
- original_base_transactions.csv
- original_user_transaction_stats.csv
- original_transaction_summary.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile

from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_ZIP = ROOT / "dongbaek_onepass_synthetic_v3.3(1).zip"

INNER_PATH = (
    "dongbaek_onepass_synthetic_v3.3/"
    "csv/{seed}/tx_requests.csv"
)


def write_csv(path, rows):
    if not rows:
        raise ValueError("EMPTY_OUTPUT")

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=list(rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(rows)


def extract(zip_path, seed, scenario):
    member = INNER_PATH.format(seed=seed)

    with zipfile.ZipFile(zip_path) as z:
        if member not in z.namelist():
            raise ValueError(
                f"ZIP_MEMBER_NOT_FOUND: {member}"
            )

        content = z.read(member).decode("utf-8-sig")

    rows = list(csv.DictReader(io.StringIO(content)))

    selected = [
        r for r in rows
        if r["run_id"] == f"RUN_{scenario}_2026-06"
    ]

    if not selected:
        raise ValueError("SCENARIO_HAS_NO_TRANSACTIONS")

    seen_ids = set()
    cleaned = []

    for row in selected:
        request_id = row["request_id"]

        if request_id in seen_ids:
            raise ValueError(
                f"DUPLICATE_REQUEST_ID:{request_id}"
            )

        seen_ids.add(request_id)

        amount = int(row["gross_amount_won"])

        if amount <= 0:
            raise ValueError(
                f"INVALID_AMOUNT:{request_id}"
            )

        channel = row["payment_channel"]

        if channel not in (
            "OFFLINE", "ONLINE", "SIMPLE_PAY"
        ):
            raise ValueError(
                f"INVALID_CHANNEL:{request_id}"
            )

        provider = row["payment_provider"].strip()

        if (channel == "SIMPLE_PAY") != bool(provider):
            raise ValueError(
                f"INVALID_PROVIDER:{request_id}"
            )

        cleaned.append({
            "transaction_id": request_id,
            "user_id": row["user_id"],
            "requested_at": row["request_at"],
            "date": row["request_at"][:10],
            "event_seq": int(row["event_seq"]),
            "merchant_id": row["merchant_id"],
            "amount_won": amount,
            "lane": channel,
            "provider": provider,
            "payment_path": row["payment_path"],
            "direct_user_card_id":
                row["direct_user_card_id"],
            "scenario": scenario,
            "seed": seed,
        })

    cleaned.sort(
        key=lambda r: (
            r["user_id"],
            r["requested_at"],
            r["event_seq"],
            r["transaction_id"],
        )
    )

    grouped = defaultdict(list)

    for tx in cleaned:
        grouped[tx["user_id"]].append(tx)

    user_stats = []

    for user_id, transactions in sorted(grouped.items()):
        count = len(transactions)
        total = sum(
            t["amount_won"] for t in transactions
        )

        channels = Counter(
            t["lane"] for t in transactions
        )

        user_stats.append({
            "user_id": user_id,
            "transaction_count": count,
            "total_spend_won": total,
            "average_ticket_won": round(total / count, 2),
            "offline_count": channels["OFFLINE"],
            "online_count": channels["ONLINE"],
            "simple_pay_count": channels["SIMPLE_PAY"],
            "min_payment_won": min(
                t["amount_won"] for t in transactions
            ),
            "max_payment_won": max(
                t["amount_won"] for t in transactions
            ),
        })

    total_amount = sum(
        r["amount_won"] for r in cleaned
    )

    summary = {
        "source": zip_path.name,
        "seed": seed,
        "scenario": scenario,
        "month": "2026-06",
        "users": len(grouped),
        "transactions": len(cleaned),
        "total_amount_won": total_amount,
        "average_transactions_per_user": round(
            len(cleaned) / len(grouped), 2
        ),
        "average_ticket_won": round(
            total_amount / len(cleaned), 2
        ),
        "transaction_count_by_lane": dict(
            Counter(t["lane"] for t in cleaned)
        ),
        "user_transaction_count_range": {
            "min": min(
                r["transaction_count"] for r in user_stats
            ),
            "max": max(
                r["transaction_count"] for r in user_stats
            ),
        },
        "notes": [
            "ORIGINAL_SYNTHETIC_TRANSACTIONS",
            "NO_NEW_TRANSACTION_GENERATION",
            "NO_DATABASE_WRITES",
            "ONLY_ONE_SCENARIO_SELECTED",
        ],
    }

    return cleaned, user_stats, summary


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--zip",
        type=Path,
        default=DEFAULT_ZIP,
    )
    parser.add_argument(
        "--seed",
        default="seed_20261023",
    )
    parser.add_argument(
        "--scenario",
        default="BASE",
        choices=(
            "LOW", "BASE", "HIGH",
            "REG45", "REG30",
        ),
    )

    args = parser.parse_args()

    if not args.zip.exists():
        parser.error(
            f"ZIP_NOT_FOUND: {args.zip}"
        )

    transactions, user_stats, summary = extract(
        args.zip,
        args.seed,
        args.scenario,
    )

    out = ROOT / "original_transactions"
    out.mkdir(exist_ok=True)

    write_csv(
        out / "original_base_transactions.csv",
        transactions,
    )

    write_csv(
        out / "original_user_transaction_stats.csv",
        user_stats,
    )

    (out / "original_transaction_summary.json").write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=== ORIGINAL TRANSACTION DATA ===")
    print(json.dumps(
        summary,
        ensure_ascii=False,
        indent=2,
    ))

    print("\nSaved to:", out)


if __name__ == "__main__":
    main()
