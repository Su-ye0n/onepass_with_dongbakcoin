"""data-analysis 공통 설정(config.yaml) 읽기."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """config.yaml 을 읽어 dict 로 돌려준다.

    입력: 설정 파일 경로 (기본: data-analysis/config.yaml)
    출력: 설정 dict
    예외: 파일이 없으면 FileNotFoundError
    """
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_path(relative: str) -> Path:
    """config 에 적힌 상대 경로를 data-analysis/ 기준 절대 경로로 바꾼다."""
    return BASE_DIR / relative
