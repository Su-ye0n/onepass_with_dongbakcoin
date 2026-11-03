"""config.yaml 에 등록된 데이터셋을 내려받는 실행 파일.

사용법 (data-analysis 폴더에서):
    python src/download.py d1 --probe     # 시험 호출 (5건, 저장 안 함)
    python src/download.py d1             # config 의 period 기간 전체 내려받기
    python src/download.py d9 --probe
"""

from __future__ import annotations

import argparse
import json
import sys

from data_go_kr import (
    ApiError,
    download_dataset,
    load_api_key,
    month_range,
    period_units,
    probe,
    split_values,
)
from settings import load_config, resolve_path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    config = load_config()
    parser = argparse.ArgumentParser(description="공공데이터 원본 내려받기")
    parser.add_argument("dataset", choices=sorted(config["datasets"]))
    parser.add_argument("--probe", action="store_true", help="몇 건만 시험 호출")
    args = parser.parse_args()

    spec = config["datasets"][args.dataset]
    api = config["api"]
    months = month_range(config["period"]["start"], config["period"]["end"])
    try:
        key = load_api_key(resolve_path(api["env_file"]), api["key_name"])
        if args.probe:
            label, period_vars = period_units(spec, months)[-1]
            split_value = split_values(spec, config)[0]
            items, total = probe(key, spec, api, period_vars, split_value)
            target = label if split_value is None else f"{label} / {split_value}"
            print(f"성공: {spec['title']} ({target}) 전체 {total}건 중 {len(items)}건 미리보기")
            for item in items:
                print(json.dumps(item, ensure_ascii=False))
        else:
            download_dataset(key, spec, api, config, resolve_path(spec["raw_dir"]), months)
    except ApiError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
