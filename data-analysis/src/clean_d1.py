"""STEP 1 D1 정제: 업종 표기 통일, 기준일 이후 행 제거, 월 합계 금액 계산 후 data/processed 에 저장.

사용법 (data-analysis 폴더에서): python src/clean_d1.py
원본(data/raw/d1)은 바꾸지 않는다.

저장 컬럼:
    ym, dong_code, dong_name, category, daily_avg_amount_krw, daily_avg_count,
    days_in_month, month_amount_krw, month_count
"""

from __future__ import annotations

import sys

import pandas as pd

from profiling import days_in_month, to_numeric_columns
from raw_io import load_raw_json_dir
from settings import load_config, resolve_path


def reference_month(config: dict) -> str:
    """config 의 기준일(YYYY-MM-DD)을 'YYYYMM' 으로 바꾼다."""
    return config["reference_date"][:7].replace("-", "")


def clean_d1(raw: pd.DataFrame, spec: dict, ref_month: str) -> pd.DataFrame:
    """D1 원본 표를 분석용 표로 정리한다.

    입력: 원본 DataFrame, D1 설정(columns, category_aliases), 기준 월(YYYYMM)
    출력: 컬럼 이름을 영어로 통일하고 월 합계(원)를 붙인 DataFrame
    예외: (기준년월, 행정동, 업종) 중복이 있으면 ValueError
    """
    cols = spec["columns"]
    df = to_numeric_columns(raw, cols["amount"] + cols["count"])
    df = df.rename(columns={
        cols["month"]: "ym",
        cols["region_code"]: "dong_code",
        cols["region_name"]: "dong_name",
        cols["category"]: "category",
        cols["amount"][0]: "daily_avg_amount_krw",
        cols["count"][0]: "daily_avg_count",
    })
    df["ym"] = df["ym"].astype(str)
    df = df[df["ym"] <= ref_month].copy()
    df["category"] = df["category"].replace(spec.get("category_aliases", {}))
    if df.duplicated(["ym", "dong_code", "category"]).any():
        raise ValueError("(기준년월, 행정동, 업종) 중복 행이 있습니다.")
    df["days_in_month"] = days_in_month(df["ym"])
    df["month_amount_krw"] = df["daily_avg_amount_krw"] * df["days_in_month"]
    df["month_count"] = df["daily_avg_count"] * df["days_in_month"]
    return df[["ym", "dong_code", "dong_name", "category", "daily_avg_amount_krw",
               "daily_avg_count", "days_in_month", "month_amount_krw", "month_count"]]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    config = load_config()
    spec = config["datasets"]["d1"]
    df = clean_d1(load_raw_json_dir(resolve_path(spec["raw_dir"])), spec, reference_month(config))
    out = resolve_path(spec["processed_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"저장: {out.name} {len(df):,}행, 기간 {df.ym.min()}~{df.ym.max()}, 업종 {df.category.nunique()}개")


if __name__ == "__main__":
    main()
