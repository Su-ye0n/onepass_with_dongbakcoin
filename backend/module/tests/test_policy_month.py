
import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.seed import create_demo
from onepass.batch import run_batch
from onepass.repository import CatalogRepository


class PolicyMonthTests(unittest.TestCase):

    def test_policy_switch_by_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = create_demo(Path(tmp) / "demo.sqlite")
            repo = CatalogRepository(db_path)

            july = repo.load_policy_at("2026-07-15")
            august = repo.load_policy_at("2026-08-15")

            self.assertEqual(
                july.monthly_applicable_amount_cap,
                500000
            )
            self.assertEqual(
                august.monthly_applicable_amount_cap,
                300000
            )

            self.assertEqual(
                july.cashback_rates["LE_10B"],
                Decimal("0.10")
            )
            self.assertEqual(
                august.cashback_rates["LE_10B"],
                Decimal("0.07")
            )

            with self.assertRaises(ValueError):
                repo.load_policy_at("2026-09-01")

    def test_monthly_cap_resets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = create_demo(root / "demo.sqlite")
            repo = CatalogRepository(db_path)

            merchants, users, policy = repo.load()

            # 7월 캐시백 적용한도를 모두 소진한 상태
            cards, state = users["U001"]
            state.db_month_applied = 500000

            requests_path = root / "requests.csv"

            with requests_path.open(
                "w",
                encoding="utf-8",
                newline=""
            ) as f:
                writer = csv.writer(f)

                writer.writerow([
                    "request_id", "user_id",
                    "requested_at", "merchant_id",
                    "amount_won", "onecard_active",
                    "payment_path", "direct_card_id"
                ])

                writer.writerow([
                    "JULY_01", "U001",
                    "2026-07-15T12:00:00",
                    "M1", 10000, "false",
                    "DIRECT", "U1_DB"
                ])

                writer.writerow([
                    "AUG_01", "U001",
                    "2026-08-01T12:00:00",
                    "M1", 10000, "false",
                    "DIRECT", "U1_DB"
                ])

            output_dir = root / "output"

            run_batch(
                None,
                requests_path,
                output_dir,
                loaded=(merchants, users, policy),
                policy_resolver=repo.load_policy_at,
            )

            with (
                output_dir / "engine_tx.csv"
            ).open(
                encoding="utf-8-sig",
                newline=""
            ) as f:
                rows = list(csv.DictReader(f))

            self.assertEqual(len(rows), 2)

            july_tx, august_tx = rows

            self.assertEqual(
                july_tx["approved"], "True"
            )
            self.assertEqual(
                august_tx["approved"], "True"
            )

            # 7월 한도 소진: 캐시백 0원
            self.assertEqual(
                int(july_tx["benefit_won"]), 0
            )

            # 8월 새 정책 7% × 10,000원
            self.assertEqual(
                int(august_tx["benefit_won"]), 700
            )

            # 8월 누적 적용금액만 남아야 함
            self.assertEqual(
                state.db_month_applied, 10000
            )

            # 동백전 충전금은 월 변경으로 리셋되지 않음
            self.assertEqual(
                state.db_charge, 40000
            )


if __name__ == "__main__":
    unittest.main()
