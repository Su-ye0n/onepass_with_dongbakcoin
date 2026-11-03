"""STEP 1 업종 판정 근거표: D1 업종별 카드 소비 중 동백전 결제가 차지하는 비율(동백전 비중)을 계산한다.

동백전 비중 = 동백전 업종별 연간 결제액(D10 보고서 표3-6) ÷ 같은 업종 D1 연간 카드 소비액
- 비중이 아주 낮은 업종 = 동백전을 쓸 수 없는 매장이 많을 가능성이 큰 업종 (근거 중 하나일 뿐, 단정 아님)
- D1 에 동백전 카드 결제가 이미 포함됐을 수 있어 "비중"으로만 해석한다 (가정)

사용법 (data-analysis 폴더에서, clean_d1.py 실행 후): python src/industry_evidence.py
저장: outputs/tables/01_dongbaek_share_by_category.csv (utf-8-sig)
"""

from __future__ import annotations

import sys

import pandas as pd

from settings import load_config, resolve_path

OUTPUT_PATH = "outputs/tables/01_dongbaek_share_by_category.csv"
REPORT_TABLE_ID = "표3-6"
YEARS = ["2023", "2024"]
EOK = 100_000_000  # 1억 원


def load_report_by_d1_category(config: dict, years: list[str]) -> pd.DataFrame:
    """보고서 업종별 결제액(억 원)을 D1 업종으로 묶어 연도별로 합친다.

    입력: 설정, 연도 목록
    출력: d1_category × year 별 동백전 결제액(원) (불명으로 연결된 업종은 제외)
    """
    stats = pd.read_csv(resolve_path(config["ref"]["report_stats"]), encoding="utf-8-sig", dtype={"period": str})
    mapping = pd.read_csv(resolve_path(config["ref"]["report_category_map"]), encoding="utf-8-sig")
    rows = stats[(stats["table_id"] == REPORT_TABLE_ID) & stats["period"].isin(years)]
    rows = rows.merge(mapping, left_on="category", right_on="report_category", how="inner")
    rows = rows[rows["d1_category"] != "불명"]
    out = rows.groupby(["d1_category", "period"])["value"].sum().reset_index()
    out["dongbaek_amount_krw"] = out["value"] * EOK
    return out.rename(columns={"period": "year"}).drop(columns="value")


def load_d1_by_category(config: dict, years: list[str]) -> pd.DataFrame:
    """정제된 D1 에서 업종 × 연도 별 카드 소비 합계(원)를 구한다."""
    d1 = pd.read_parquet(resolve_path(config["datasets"]["d1"]["processed_path"]))
    d1["year"] = d1["ym"].str[:4]
    d1 = d1[d1["year"].isin(years)]
    out = d1.groupby(["category", "year"])["month_amount_krw"].sum().reset_index()
    return out.rename(columns={"category": "d1_category", "month_amount_krw": "card_amount_krw"})


def build_share_table(config: dict, years: list[str]) -> pd.DataFrame:
    """업종별 동백전 비중 표를 만든다. 유통과 음식료품은 보고서의 '슈퍼/마트'와 비교하려고 합친 행도 추가한다."""
    d1 = load_d1_by_category(config, years)
    merged = (
        d1.pivot(index="d1_category", columns="year", values="card_amount_krw").add_prefix("card_")
        .join(load_report_by_d1_category(config, years)
              .pivot(index="d1_category", columns="year", values="dongbaek_amount_krw").add_prefix("dongbaek_"))
    )
    combined = merged.loc[["유통", "음식료품"]].sum(min_count=1)
    combined[[f"dongbaek_{y}" for y in years]] = merged.loc["유통", [f"dongbaek_{y}" for y in years]]
    merged.loc["유통+음식료품"] = combined
    for y in years:
        merged[f"share_{y}_pct"] = (merged[f"dongbaek_{y}"] / merged[f"card_{y}"] * 100).round(2)
    merged["card_share_of_total_2024_pct"] = (
        merged["card_2024"] / d1[d1["year"] == "2024"]["card_amount_krw"].sum() * 100
    ).round(1)
    merged["source"] = "카드: D1(공공데이터포털 15164434) / 동백전: D10 부산연구원(2025) 표3-6, 업종 연결은 ref/report_category_map.csv(가정)"
    return merged.reset_index().sort_values(f"share_{years[-1]}_pct", ascending=False)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    config = load_config()
    table = build_share_table(config, YEARS)
    out = resolve_path(OUTPUT_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False, encoding="utf-8-sig")
    show = table[["d1_category", "card_2024", "dongbaek_2024", "share_2023_pct", "share_2024_pct",
                  "card_share_of_total_2024_pct"]].copy()
    show[["card_2024", "dongbaek_2024"]] = (show[["card_2024", "dongbaek_2024"]] / EOK).round(0)
    print(show.rename(columns={"card_2024": "카드2024_억", "dongbaek_2024": "동백전2024_억"}).to_string(index=False))


if __name__ == "__main__":
    main()
