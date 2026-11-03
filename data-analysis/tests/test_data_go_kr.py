"""data_go_kr 공통 함수 테스트. 실행: data-analysis 폴더에서 python -m unittest discover tests"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_go_kr import (  # noqa: E402
    ApiError,
    build_params,
    check_response,
    extract_items,
    load_api_key,
    mask,
    month_range,
    period_units,
)

D1_SPEC = {
    "params": {"resultType": "json"},
    "month_params": {"stdYm": "{ym}"},
    "page_param": "pageNo",
    "size_param": "numOfRows",
    "items_path": "response.body.items.item",
    "total_path": "response.body.totalCount",
    "result_code_path": "response.header.resultCode",
    "ok_codes": ["00"],
}
D9_SPEC = {
    "params": {"returnType": "JSON"},
    "month_params": {"cond[crtr_ym::GTE]": "{ym}", "cond[crtr_ym::LTE]": "{ym}"},
    "split_param": "cond[usage_rgn_cd::EQ]",
    "page_param": "page",
    "size_param": "perPage",
    "items_path": "data",
    "total_path": "matchCount",
}


class MonthRangeTest(unittest.TestCase):
    def test_crosses_year(self) -> None:
        self.assertEqual(month_range("2025-11", "2026-02"), ["202511", "202512", "202601", "202602"])

    def test_single_month(self) -> None:
        self.assertEqual(month_range("2026-06", "2026-06"), ["202606"])

    def test_full_period_length(self) -> None:
        self.assertEqual(len(month_range("2023-01", "2026-06")), 42)

    def test_reversed_raises(self) -> None:
        with self.assertRaises(ValueError):
            month_range("2026-06", "2026-01")


class ExtractItemsTest(unittest.TestCase):
    def test_d1_list(self) -> None:
        data = {"response": {"body": {"items": {"item": [{"a": 1}, {"a": 2}]}, "totalCount": "2"}}}
        self.assertEqual(extract_items(data, D1_SPEC), ([{"a": 1}, {"a": 2}], 2))

    def test_d1_single_item_dict(self) -> None:
        data = {"response": {"body": {"items": {"item": {"a": 1}}, "totalCount": "1"}}}
        self.assertEqual(extract_items(data, D1_SPEC), ([{"a": 1}], 1))

    def test_d9_empty(self) -> None:
        self.assertEqual(extract_items({"data": [], "matchCount": 0}, D9_SPEC), ([], 0))


class BuildParamsTest(unittest.TestCase):
    def test_d9_month_and_split(self) -> None:
        params = build_params(D9_SPEC, {"ym": "202606"}, "26350", 2, 1000)
        self.assertEqual(params["cond[crtr_ym::GTE]"], "202606")
        self.assertEqual(params["cond[usage_rgn_cd::EQ]"], "26350")
        self.assertEqual((params["page"], params["perPage"]), (2, 1000))
        self.assertNotIn("serviceKey", params)


class PeriodUnitsTest(unittest.TestCase):
    def test_month_unit(self) -> None:
        self.assertEqual(period_units({"unit": "month"}, ["202605", "202606"]),
                         [("202605", {"ym": "202605"}), ("202606", {"ym": "202606"})])

    def test_period_unit(self) -> None:
        units = period_units({"unit": "period"}, ["202301", "202302", "202606"])
        self.assertEqual(units, [("202301-202606", {"start_ym": "202301", "end_ym": "202606"})])

    def test_period_params(self) -> None:
        spec = {**D9_SPEC, "month_params": {"cond[crtr_ym::GTE]": "{start_ym}", "cond[crtr_ym::LTE]": "{end_ym}"}}
        params = build_params(spec, {"start_ym": "202301", "end_ym": "202606"}, "26110", 1, 1000)
        self.assertEqual((params["cond[crtr_ym::GTE]"], params["cond[crtr_ym::LTE]"]), ("202301", "202606"))

    def test_unknown_unit_raises(self) -> None:
        with self.assertRaises(ValueError):
            period_units({"unit": "week"}, ["202301"])


class CheckResponseTest(unittest.TestCase):
    def test_gateway_error(self) -> None:
        data = {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}}
        with self.assertRaises(ApiError):
            check_response(data, 403, D1_SPEC)

    def test_d1_bad_code(self) -> None:
        with self.assertRaises(ApiError):
            check_response({"response": {"header": {"resultCode": "10"}}}, 200, D1_SPEC)

    def test_d1_ok(self) -> None:
        check_response({"response": {"header": {"resultCode": "00"}}}, 200, D1_SPEC)


class KeyTest(unittest.TestCase):
    def _env(self, text: str) -> Path:
        tmp = Path(tempfile.mkdtemp()) / ".env"
        tmp.write_text(text, encoding="utf-8")
        return tmp

    def test_strips_quotes_and_decodes(self) -> None:
        path = self._env('DATA_GO_KR_KEY="ab%2Bc%3D%3D"\n')
        self.assertEqual(load_api_key(path, "DATA_GO_KR_KEY"), "ab+c==")

    def test_empty_raises(self) -> None:
        with self.assertRaises(ApiError):
            load_api_key(self._env("DATA_GO_KR_KEY=\n"), "DATA_GO_KR_KEY")

    def test_mask(self) -> None:
        self.assertEqual(mask("url?serviceKey=SECRET&x=1", "SECRET"), "url?serviceKey=***&x=1")


if __name__ == "__main__":
    unittest.main()
