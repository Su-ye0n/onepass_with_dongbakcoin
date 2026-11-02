
"""Seed demo reference entities. Every value is SIMULATED."""

from pathlib import Path
from contextlib import closing
import sqlite3

ROOT = Path(__file__).resolve().parent.parent


def create_demo(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA foreign_keys=ON")

        # 1. 기본 DB 테이블 생성
        db.executescript(
            (ROOT / "db" / "schema_sqlite_sim.sql").read_text(encoding="utf-8")
        )

        # 2. 기존 DB와의 호환성: 정책 유효기간 컬럼 추가
        columns = {
            row[1]
            for row in db.execute("PRAGMA table_info(db_policy)")
        }

        if "effective_from" not in columns:
            db.execute(
                "ALTER TABLE db_policy ADD COLUMN effective_from TEXT"
            )

        if "effective_to" not in columns:
            db.execute(
                "ALTER TABLE db_policy ADD COLUMN effective_to TEXT"
            )

        # 3. 사용자 초기 상태
        db.executemany(
            "INSERT OR REPLACE INTO sim_user VALUES (?,?,?,?,?)",
            [
                ("U001", 60000, 0, 0, 0),
                ("U002", 25000, 0, 0, 0),
            ],
        )

        # 4. 계좌 초기 잔액
        db.executemany(
            "INSERT OR REPLACE INTO funding_account VALUES (?,?,?)",
            [
                ("U1_ACC", "U001", 100000),
                ("U2_ACC", "U002", 20000),
            ],
        )

        # 5. 카드 상품
        db.executemany(
            "INSERT OR REPLACE INTO card_product VALUES (?,?,?,?)",
            [
                ("P_DB", "Demo Dongbaek check", "DONGBAEK_CHECK", "SIMULATED"),
                ("P_CHECK", "Demo debit", "DEBIT", "SIMULATED"),
                ("P_CREDIT", "Demo credit", "CREDIT", "SIMULATED"),
            ],
        )

        # 6. 사용자 보유 카드
        db.executemany(
            "INSERT OR REPLACE INTO user_card VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("U1_DB", "U001", "P_DB", "U1_ACC", 0, 1, 0, 0, 0),
                ("U1_CK", "U001", "P_CHECK", "U1_ACC", 0, 1, 0, 0, 400000),
                ("U1_CR", "U001", "P_CREDIT", None, 1000000, 1, 0, 0, 400000),
                ("U2_DB", "U002", "P_DB", "U2_ACC", 0, 1, 0, 0, 0),
                ("U2_CR", "U002", "P_CREDIT", None, 100000, 1, 0, 0, 350000),
            ],
        )

        # 7. 가맹점
        db.executemany(
            "INSERT OR REPLACE INTO merchant VALUES (?,?,?,?,?)",
            [
                ("M1", "FOOD", "REGISTERED", "LE_10B", "SIMULATED"),
                ("M2", "CAFE", "NOT_REGISTERED", "GT_30B", "SIMULATED"),
                ("M3", "FOOD", "REGISTERED", "LE_30B", "SIMULATED"),
            ],
        )

        # 8. 카드 혜택 규칙
        db.executemany(
            "INSERT OR REPLACE INTO benefit_rule VALUES (?,?,?,?,?,?,?,?)",
            [
                ("CAFE5", "P_CHECK", "0.05", 300000, 1000, 2000, 10000, "SIMULATED"),
                ("FOOD3", "P_CREDIT", "0.03", 300000, 0, 3000, 10000, "SIMULATED"),
                ("CAFE4", "P_CREDIT", "0.04", 300000, 0, None, 5000, "SIMULATED"),
            ],
        )

        db.executemany(
            "INSERT OR REPLACE INTO benefit_rule_category VALUES (?,?)",
            [
                ("CAFE5", "CAFE"),
                ("FOOD3", "FOOD"),
                ("CAFE4", "CAFE"),
            ],
        )

        # 9. 동백전 시연용 정책
        # 모든 정책은 SIMULATED이며 실제 정책이 아님
        # 종료일은 포함하지 않음

        db.executemany(
            """
            INSERT OR REPLACE INTO db_policy (
                policy_id,
                monthly_applicable_amount_cap,
                assume_partial_cap,
                assume_charge_only,
                source_status,
                effective_from,
                effective_to
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "SIM_POLICY_01",
                    500000,
                    1,
                    1,
                    "SIMULATED",
                    "2026-07-01",
                    "2026-08-01",
                ),
                (
                    "SIM_POLICY_02",
                    300000,
                    1,
                    1,
                    "SIMULATED",
                    "2026-08-01",
                    "2026-09-01",
                ),
            ],
        )

        # 10. 정책별 캐시백률
        db.executemany(
            """
            INSERT OR REPLACE INTO db_policy_rate (
                policy_id,
                band_code,
                cashback_rate
            )
            VALUES (?, ?, ?)
            """,
            [
                # 7월 정책
                ("SIM_POLICY_01", "LE_10B", "0.10"),
                ("SIM_POLICY_01", "LE_30B", "0.08"),
                ("SIM_POLICY_01", "GT_30B", "0"),

                # 8월 정책 (가상 테스트용)
                ("SIM_POLICY_02", "LE_10B", "0.07"),
                ("SIM_POLICY_02", "LE_30B", "0.05"),
                ("SIM_POLICY_02", "GT_30B", "0"),
            ],
        )

        db.commit()

    return path


if __name__ == "__main__":
    print(create_demo(ROOT / "data" / "demo_catalog.sqlite"))
