
import csv
import tempfile
import unittest
from pathlib import Path

from onepass.batch import (
    run_batch,
    read_requests,
    load_configuration
)

ROOT = Path(__file__).resolve().parent.parent


class BatchTests(unittest.TestCase):

    def test_sample_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats = run_batch(
                ROOT / "data/sample_config.json",
                ROOT / "data/tx_requests.csv",
                Path(tmp)
            )

            self.assertEqual(stats["requests"], 6)
            self.assertEqual(stats["approved"], 6)
            self.assertEqual(stats["users"], 2)

            with (Path(tmp) / "engine_tx.csv").open(
                encoding="utf-8-sig",
                newline=""
            ) as file:
                tx = list(csv.DictReader(file))

            self.assertEqual(
                tx[0]["selected_card_id"],
                "U1_DB"
            )
            self.assertEqual(
                tx[-1]["reason"],
                "DIRECT_CARD"
            )

            with (Path(tmp) / "engine_ledger.csv").open(
                encoding="utf-8-sig",
                newline=""
            ) as file:
                ledger = list(csv.DictReader(file))

            self.assertEqual(len(ledger), 6)

            with (Path(tmp) / "user_summary.csv").open(
                encoding="utf-8-sig",
                newline=""
            ) as file:
                summary = {
                    row["user_id"]: row
                    for row in csv.DictReader(file)
                }

            self.assertEqual(
                summary["U001"]["request_count"],
                "4"
            )
            self.assertEqual(
                summary["U002"]["request_count"],
                "2"
            )

    def test_time_order_even_if_input_unsorted(self):
        merchants, users, _ = load_configuration(
            ROOT / "data/sample_config.json"
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unsorted.csv"
            path.write_text(
                "request_id,user_id,requested_at,"
                "merchant_id,amount_won,onecard_active\n"
                "Z,U001,2026-07-08T09:00:00,M1,1000,true\n"
                "A,U001,2026-07-01T09:00:00,M1,2000,true\n",
                encoding="utf-8"
            )

            records = read_requests(
                path, merchants, users
            )

            self.assertEqual(
                [row[-1].id for row in records],
                ["A", "Z"]
            )

    def test_unknown_user_fails_explicitly(self):
        merchants, users, _ = load_configuration(
            ROOT / "data/sample_config.json"
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unknown.csv"
            path.write_text(
                "request_id,user_id,requested_at,"
                "merchant_id,amount_won,onecard_active\n"
                "X,NOT_USER,2026-07-01T09:00:00,"
                "M1,1000,true\n",
                encoding="utf-8"
            )

            with self.assertRaisesRegex(
                ValueError, "unknown user_id"
            ):
                read_requests(
                    path, merchants, users
                )


if __name__ == "__main__":
    unittest.main()
