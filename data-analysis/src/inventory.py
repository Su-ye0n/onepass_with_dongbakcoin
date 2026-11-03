"""STEP 0 데이터 점검: 원본을 읽어 요약표를 outputs/tables/ 에 저장한다.

사용법 (data-analysis 폴더에서):
    python src/inventory.py d1
    python src/inventory.py d9

저장 파일 (데이터셋 이름이 앞에 붙음, 인코딩 utf-8-sig):
    00_<ds>_columns.csv          컬럼별 자료형·결측률·고유값 수
    00_<ds>_monthly.csv          월별 행 수·지역 수·금액 합계(원)
    00_<ds>_category.csv         업종별 행 수·금액 합계(원)·비중
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from profiling import days_in_month, profile_columns, to_numeric_columns
from raw_io import load_raw_json_dir
from settings import load_config, resolve_path

OUTPUT_DIR = "outputs/tables"
CSV_ENCODING = "utf-8-sig"


def load_dataset(spec: dict, reference_month: str) -> pd.DataFrame:
    """원본을 읽고 금액·건수를 숫자로 바꾼 뒤, 월 합계 금액 컬럼(month_amount_krw)을 붙인다.

    입력: 데이터셋 설정, 기준 월(YYYYMM, 이 달 이후 행은 버림)
    출력: 점검용 DataFrame (원본 파일은 바꾸지 않음)
    """
    cols = spec["columns"]
    df = load_raw_json_dir(resolve_path(spec["raw_dir"]))
    df = to_numeric_columns(df, cols["amount"] + cols["count"])
    df[cols["month"]] = df[cols["month"]].astype(str)
    df = df[df[cols["month"]] <= reference_month]
    main_amount = df[cols["amount"][0]]
    if cols.get("amount_is_daily_avg"):
        main_amount = main_amount * days_in_month(df[cols["month"]])
    df["month_amount_krw"] = main_amount
    return df


def monthly_summary(df: pd.DataFrame, cols: dict) -> pd.DataFrame:
    """월별 행 수·지역 수·업종 수·월 합계 금액(원)."""
    return (
        df.groupby(cols["month"])
        .agg(
            rows=(cols["month"], "size"),
            regions=(cols["region_code"], "nunique"),
            categories=(cols["category"], "nunique"),
            amount_krw=("month_amount_krw", "sum"),
        )
        .reset_index()
    )


def category_summary(df: pd.DataFrame, cols: dict) -> pd.DataFrame:
    """업종별 행 수·금액 합계(원)·전체 대비 비중, 금액 큰 순."""
    keys = [cols["category"]] + ([cols["category_code"]] if cols.get("category_code") else [])
    out = (
        df.groupby(keys)
        .agg(rows=(cols["category"], "size"), amount_krw=("month_amount_krw", "sum"),
             months=(cols["month"], "nunique"))
        .reset_index()
        .sort_values("amount_krw", ascending=False)
    )
    out["share"] = (out["amount_krw"] / out["amount_krw"].sum()).round(4)
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    config = load_config()
    parser = argparse.ArgumentParser(description="STEP 0 데이터 점검")
    parser.add_argument("dataset", choices=sorted(config["datasets"]))
    args = parser.parse_args()

    spec = config["datasets"][args.dataset]
    cols = spec["columns"]
    reference_month = config["reference_date"][:7].replace("-", "")
    df = load_dataset(spec, reference_month)

    out_dir = resolve_path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "columns": profile_columns(df.drop(columns="month_amount_krw")),
        "monthly": monthly_summary(df, cols),
        "category": category_summary(df, cols),
    }
    for name, table in tables.items():
        table.to_csv(out_dir / f"00_{args.dataset}_{name}.csv", index=False, encoding=CSV_ENCODING)

    print(f"{spec['title']}: {len(df):,}행, 기간 {df[cols['month']].min()}~{df[cols['month']].max()}")
    for name, table in tables.items():
        print(f"\n[{name}]\n{table.to_string(index=False)}")


if __name__ == "__main__":
    main()
