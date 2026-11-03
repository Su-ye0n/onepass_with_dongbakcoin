
import csv
import tempfile
import unittest
from pathlib import Path

from onepass.compare import run_comparison
from onepass.batch import run_batch

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "data" / "sample_config.json"
REQUESTS = ROOT / "data" / "tx_requests.csv"


def load_csv(path):
    with Path(path).open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        return list(csv.DictReader(file))


class ComparisonTests(unittest.TestCase):

    def test_onepass_matches_batch(self):
        """B 전략과 기존 배치 엔진의 결과가 같아야 한다."""

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            batch_dir = tmp / "batch"
            compare_dir = tmp / "compare"
            batch_dir.mkdir()

            run_batch(CONFIG, REQUESTS, batch_dir)
            run_comparison(
                CONFIG, REQUESTS, compare_dir
            )

            batch_rows = load_csv(
                batch_dir / "engine_tx.csv"
            )
            compare_rows = load_csv(
                compare_dir / "strategy_tx.csv"
            )

            b_rows = [
                row for row in compare_rows
                if row["strategy"] == "B"
            ]

            self.assertEqual(
                len(batch_rows), len(b_rows)
            )

            for original, b in zip(batch_rows, b_rows):
                self.assertEqual(
                    original["request_id"],
                    b["request_id"]
                )
                self.assertEqual(
                    original["selected_card_id"],
                    b["selected_card_id"]
                )
                self.assertEqual(
                    original["approved"],
                    b["approved"]
                )
                self.assertEqual(
                    original["benefit_won"],
                    b["benefit_won"]
                )

    def test_direct_payment_updates_balance(self):
        """직접 결제도 잔액을 소진해 다음 거래에 반영해야 한다."""

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            requests_path = tmp / "direct.csv"

            requests_path.write_text(
                "request_id,user_id,requested_at,"
                "merchant_id,amount_won,onecard_active,"
                "payment_path,direct_card_id\n"
                "D001,U001,2026-07-01T09:00:00,"
                "M2,90000,false,DIRECT,U1_CK\n"
                "D002,U001,2026-07-01T10:00:00,"
                "M2,90000,false,DIRECT,U1_CK\n",
                encoding="utf-8"
            )

            result = run_comparison(
                CONFIG,
                requests_path,
                tmp / "output"
            )

            self.assertEqual(
                result["requests_per_strategy"], 2
            )

            rows = load_csv(
                tmp / "output" / "strategy_tx.csv"
            )

            for strategy in ("A1", "A2", "A3", "B"):
                selected = [
                    row for row in rows
                    if row["strategy"] == strategy
                ]

                self.assertEqual(len(selected), 2)

                # 초기 계좌 100,000원
                # 첫 결제 60,000원 승인
                self.assertEqual(
                    selected[0]["approved"], "True"
                )
                self.assertEqual(
                    selected[0]["selected_card_id"],
                    "U1_CK"
                )

                # 남은 40,000원으로는
                # 다음 60,000원 결제 불가
                self.assertEqual(
                    selected[1]["approved"], "False"
                )
                self.assertEqual(
                    selected[1]["selected_card_id"], ""
                )

    def test_comparison_difference_is_correct(self):
        """혜택 증가액은 B 혜택 - A 혜택이어야 한다."""

        with tempfile.TemporaryDirectory() as tmp:
            run_comparison(
                CONFIG, REQUESTS, tmp
            )

            rows = load_csv(
                Path(tmp) / "strategy_comparison.csv"
            )

            self.assertEqual(len(rows), 6)

            for row in rows:
                baseline = int(
                    row["baseline_benefit_won"]
                )
                onepass = int(
                    row["onepass_benefit_won"]
                )
                difference = int(
                    row["difference_won"]
                )

                self.assertEqual(
                    difference,
                    onepass - baseline
                )

    def test_strategy_state_is_independent(self):
        """전략별 실행이 다른 전략의 상태를 바꾸지 않아야 한다."""

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            run_comparison(
                CONFIG, REQUESTS, tmp / "run1",
                seed=42
            )
            run_comparison(
                CONFIG, REQUESTS, tmp / "run2",
                seed=42
            )

            files = (
                "strategy_tx.csv",
                "strategy_monthly.csv",
                "strategy_comparison.csv",
            )

            for filename in files:
                first = load_csv(tmp / "run1" / filename)
                second = load_csv(tmp / "run2" / filename)

                self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
