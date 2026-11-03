"""4개 시나리오 실행 결과 파일 읽기 (읽기 전용, 프로세스당 한 번 캐시)."""

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import settings


SCENARIOS = ("S00", "S10", "S01", "S11")


@dataclass(frozen=True)
class UserResult:
    user_id: str
    usage_style: str
    wallet_status: str
    card_count: int
    transaction_count: int
    benefit_won: dict[str, int]


@dataclass(frozen=True)
class TransactionResult:
    transaction_id: str
    user_id: str
    requested_at: str
    merchant_id: str
    amount_won: int
    lane: str
    selected_card: dict[str, str | None]
    benefit_won: dict[str, int]


@dataclass(frozen=True)
class SimulationResults:
    results_dir: Path
    summary: dict
    constants: dict
    users: dict[str, UserResult]
    transactions_by_user: dict[str, list[TransactionResult]]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=4)
def load_results(results_dir: str | None = None) -> SimulationResults:
    base = Path(results_dir) if results_dir else Path(settings.SIMULATION_RESULTS_DIR)

    if not (base / "users.csv").exists():
        raise FileNotFoundError(f"SIMULATION_RESULTS_NOT_FOUND: {base}")

    users = {
        row["user_id"]: UserResult(
            user_id=row["user_id"],
            usage_style=row["usage_style"],
            wallet_status=row["wallet_status"],
            card_count=int(row["card_count"]),
            transaction_count=int(row["transaction_count"]),
            benefit_won={s: int(row[f"{s}_benefit_won"]) for s in SCENARIOS},
        )
        for row in _read_csv(base / "users.csv")
    }

    transactions_by_user: dict[str, list[TransactionResult]] = {}
    for row in _read_csv(base / "transactions.csv"):
        tx = TransactionResult(
            transaction_id=row["transaction_id"],
            user_id=row["user_id"],
            requested_at=row["requested_at"],
            merchant_id=row["merchant_id"],
            amount_won=int(row["amount_won"]),
            lane=row["lane"],
            selected_card={s: row[f"{s}_selected_card"] or None for s in SCENARIOS},
            benefit_won={s: int(row[f"{s}_benefit_won"]) for s in SCENARIOS},
        )
        transactions_by_user.setdefault(tx.user_id, []).append(tx)

    return SimulationResults(
        results_dir=base,
        summary=_read_json(base / "summary.json"),
        constants=_read_json(base / "dashboard_constants.json"),
        users=users,
        transactions_by_user=transactions_by_user,
    )
