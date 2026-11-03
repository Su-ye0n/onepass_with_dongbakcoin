"""clean_d1 테스트. 실행: data-analysis 폴더에서 python -m unittest discover tests"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from clean_d1 import clean_d1  # noqa: E402

SPEC = {
    "columns": {"month": "stdYm", "region_code": "hcode", "region_name": "hname",
                "category": "ryLNm", "amount": ["avgAmt"], "count": ["avgCnt"]},
    "category_aliases": {"음식료픔": "음식료품"},
}


def raw(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["stdYm", "hcode", "hname", "ryLNm", "avgAmt", "avgCnt"])


class CleanD1Test(unittest.TestCase):
    def test_month_total_uses_days_in_month(self) -> None:
        df = clean_d1(raw([("202402", "1", "가동", "유통", "100", "2")]), SPEC, "202606")
        self.assertEqual(df.loc[0, "days_in_month"], 29)  # 2024년 윤년
        self.assertEqual(df.loc[0, "month_amount_krw"], 2900)
        self.assertEqual(df.loc[0, "month_count"], 58)

    def test_alias_fixes_typo(self) -> None:
        df = clean_d1(raw([("202601", "1", "가동", "음식료픔", "1", "1")]), SPEC, "202606")
        self.assertEqual(df.loc[0, "category"], "음식료품")

    def test_drops_rows_after_reference_month(self) -> None:
        df = clean_d1(raw([("202606", "1", "가동", "유통", "1", "1"),
                           ("202607", "1", "가동", "유통", "1", "1")]), SPEC, "202606")
        self.assertEqual(df["ym"].tolist(), ["202606"])

    def test_duplicate_raises(self) -> None:
        rows = [("202606", "1", "가동", "유통", "1", "1")] * 2
        with self.assertRaises(ValueError):
            clean_d1(raw(rows), SPEC, "202606")


if __name__ == "__main__":
    unittest.main()
