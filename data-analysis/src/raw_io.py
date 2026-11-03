"""data/raw 에 저장된 API 원본(JSON)을 표(DataFrame)로 읽는 도구."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

LOG_FILENAME = "_download_log.json"


def load_raw_json_dir(raw_dir: Path) -> pd.DataFrame:
    """raw_dir 안의 단위별 JSON 파일을 모두 읽어 하나의 표로 합친다.

    입력: 원본 폴더 (예: data/raw/d1)
    출력: 모든 행을 합친 DataFrame. 값은 API 가 준 그대로(문자열 등) 둔다.
    예외: 폴더에 파일이 없으면 FileNotFoundError
    """
    files = sorted(p for p in raw_dir.glob("*.json") if p.name != LOG_FILENAME)
    if not files:
        raise FileNotFoundError(f"{raw_dir} 에 원본 파일이 없습니다.")
    frames = [pd.DataFrame(json.loads(p.read_text(encoding="utf-8"))) for p in files]
    return pd.concat(frames, ignore_index=True)


def load_download_log(raw_dir: Path) -> dict:
    """내려받기 기록(_download_log.json)을 읽는다. 없으면 빈 dict."""
    path = raw_dir / LOG_FILENAME
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
