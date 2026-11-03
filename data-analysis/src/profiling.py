"""데이터 점검(STEP 0)용 공통 요약 함수."""

from __future__ import annotations

import pandas as pd


def profile_columns(df: pd.DataFrame) -> pd.DataFrame:
    """컬럼별 자료형·결측률·고유값 수·예시 값을 한 표로 만든다.

    입력: 점검할 DataFrame
    출력: 컬럼마다 한 행인 요약표 (column, dtype, missing_rate, n_unique, example)
    """
    return pd.DataFrame(
        {
            "column": df.columns,
            "dtype": [str(t) for t in df.dtypes],
            "missing_rate": df.isna().mean().round(4).values,
            "n_unique": df.nunique().values,
            "example": [df[c].dropna().iloc[0] if df[c].notna().any() else None for c in df.columns],
        }
    )


def to_numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """지정한 컬럼을 숫자로 바꾼 사본을 돌려준다. 숫자가 아닌 값은 결측(NaN)이 된다."""
    out = df.copy()
    for col in columns:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def days_in_month(ym: pd.Series) -> pd.Series:
    """'YYYYMM' 문자열마다 그 달의 일수를 돌려준다. (월 합계 = 일평균 × 일수 계산용)"""
    return pd.to_datetime(ym, format="%Y%m").dt.days_in_month


def to_markdown_table(df: pd.DataFrame) -> str:
    """DataFrame 을 마크다운 표 문자열로 바꾼다 (tabulate 없이)."""
    header = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |" for row in df.values]
    return "\n".join([header, sep, *rows])
