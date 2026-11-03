"""공공데이터포털(data.go.kr) Open API 공통 내려받기 도구.

데이터셋마다 다른 부분(주소, 파라미터 이름, 응답 구조)은 config.yaml 의 datasets 항목으로 정하고,
이 모듈은 키 읽기·요청·페이지 넘기기·오류 처리·저장만 맡는다.
API 키는 화면·파일·오류 메시지에 절대 남기지 않는다.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

GATEWAY_ERROR_KEY = "OpenAPI_ServiceResponse"


class ApiError(RuntimeError):
    """API 호출 실패. 메시지에는 키가 들어가지 않는다."""


def load_api_key(env_path: Path, key_name: str) -> str:
    """.env 파일에서 API 키를 읽는다.

    입력: .env 파일 경로, 키 이름(예: DATA_GO_KR_KEY)
    출력: 인증키 문자열. 따옴표는 벗기고, Encoding 키(% 포함)는 Decoding 형태로 바꾼다.
    예외: 파일이 없거나 값이 비어 있으면 ApiError (키 값은 메시지에 넣지 않음)
    """
    if not env_path.exists():
        raise ApiError(f"{env_path.name} 파일이 없습니다.")
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == key_name:
            key = value.strip().strip('"').strip("'")
            if key:
                return unquote(key) if "%" in key else key
    raise ApiError(f"{key_name} 값이 비어 있습니다.")


def mask(text: str, key: str) -> str:
    """문장 안에 키가 섞여 있으면 *** 로 가린다."""
    return text.replace(key, "***") if key else text


def month_range(start: str, end: str) -> list[str]:
    """'YYYY-MM' 두 개 사이의 월 목록을 'YYYYMM' 형태로 만든다 (양 끝 포함).

    예: month_range("2025-11", "2026-02") → ["202511", "202512", "202601", "202602"]
    예외: start 가 end 보다 늦으면 ValueError
    """
    y, m = map(int, start.split("-"))
    end_y, end_m = map(int, end.split("-"))
    if (y, m) > (end_y, end_m):
        raise ValueError(f"시작 월 {start} 이 끝 월 {end} 보다 늦습니다.")
    months = []
    while (y, m) <= (end_y, end_m):
        months.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def get_path(data: Any, dotted: str, default: Any = None) -> Any:
    """'a.b.c' 처럼 점으로 적힌 위치의 값을 JSON(dict)에서 꺼낸다. 없으면 default."""
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return default
        data = data[part]
    return data


def extract_items(data: dict, spec: dict) -> tuple[list[dict], int]:
    """응답 JSON 에서 행 목록과 전체 건수를 꺼낸다.

    입력: 응답 JSON, 데이터셋 설정(items_path, total_path)
    출력: (행 목록, 전체 건수). 행이 1건이면 dict 로 오는 API 도 있어 list 로 맞춘다.
    """
    items = get_path(data, spec["items_path"]) or []
    if isinstance(items, dict):
        items = [items]
    total = int(get_path(data, spec["total_path"]) or 0)
    return items, total


def check_response(data: dict, status: int, spec: dict) -> None:
    """응답이 오류인지 확인하고, 오류면 ApiError 를 낸다.

    공공데이터포털 게이트웨이 오류(키 미등록 등)와 데이터셋별 결과코드를 모두 확인한다.
    """
    gateway = get_path(data, f"{GATEWAY_ERROR_KEY}.cmmMsgHeader")
    if gateway:
        raise ApiError(
            f"API 거부 (HTTP {status}): {gateway.get('errMsg')} / {gateway.get('returnAuthMsg')}"
        )
    code_path = spec.get("result_code_path")
    if code_path:
        code = str(get_path(data, code_path, ""))
        if code not in spec.get("ok_codes", []):
            raise ApiError(f"API 오류 코드 {code} (HTTP {status})")
    elif status != 200:
        raise ApiError(f"API 오류 (HTTP {status}): {json.dumps(data, ensure_ascii=False)[:300]}")


def period_units(spec: dict, months: list[str]) -> list[tuple[str, dict[str, str]]]:
    """기간을 내려받기 단위로 나눈다.

    입력: 데이터셋 설정(unit: month 또는 period), 'YYYYMM' 월 목록
    출력: (단위 이름, 기간 파라미터에 넣을 값) 목록
      - month : [("202301", {"ym": "202301"}), ...]
      - period: [("202301-202606", {"start_ym": "202301", "end_ym": "202606"})]
    예외: unit 값이 month·period 가 아니면 ValueError
    """
    unit = spec.get("unit", "month")
    if unit == "month":
        return [(ym, {"ym": ym}) for ym in months]
    if unit == "period":
        return [(f"{months[0]}-{months[-1]}", {"start_ym": months[0], "end_ym": months[-1]})]
    raise ValueError(f"알 수 없는 unit: {unit}")


def build_params(
    spec: dict, period_vars: dict[str, str], split_value: str | None, page: int, size: int
) -> dict:
    """한 번의 요청에 보낼 파라미터를 만든다 (키 제외)."""
    params = dict(spec.get("params", {}))
    params.update({k: v.format(**period_vars) for k, v in spec.get("month_params", {}).items()})
    if split_value is not None:
        params[spec["split_param"]] = split_value
    params[spec["page_param"]] = page
    params[spec["size_param"]] = size
    return params


def fetch_page(key: str, spec: dict, api: dict, params: dict) -> dict:
    """API 한 페이지를 요청해 응답 JSON 을 돌려준다.

    입력: 인증키, 데이터셋 설정, 공통 API 설정(timeout_sec), 요청 파라미터
    출력: 응답 JSON(dict)
    예외: 통신 실패·JSON 아님·오류 응답이면 ApiError (키는 가림)
    """
    resp = None
    for attempt in range(1, api.get("max_retries", 1) + 1):
        try:
            resp = requests.get(
                spec["url"], params={"serviceKey": key, **params}, timeout=api["timeout_sec"]
            )
            break
        except requests.RequestException as exc:
            if attempt == api.get("max_retries", 1):
                raise ApiError(mask(f"통신 실패 ({attempt}회 시도): {exc}", key)) from None
            time.sleep(api.get("retry_wait_sec", 0))
    try:
        data = resp.json()
    except ValueError:
        raise ApiError(
            mask(f"JSON 응답이 아님 (HTTP {resp.status_code}): {resp.text[:300]}", key)
        ) from None
    check_response(data, resp.status_code, spec)
    return data


def download_unit(
    key: str, spec: dict, api: dict, period_vars: dict[str, str], split_value: str | None
) -> list[dict]:
    """한 단위(기간 단위 하나 × 나눔값 하나)의 모든 행을 페이지를 넘기며 받는다."""
    rows: list[dict] = []
    page = 1
    while True:
        params = build_params(spec, period_vars, split_value, page, spec["page_size"])
        items, total = extract_items(fetch_page(key, spec, api, params), spec)
        rows.extend(items)
        if not items or len(rows) >= total:
            return rows
        page += 1
        time.sleep(api["pause_sec"])


def split_values(spec: dict, config: dict) -> list[str | None]:
    """데이터셋을 나눠 받을 값 목록. 나누지 않으면 [None]."""
    source = spec.get("split_values_from")
    return list(config[source].keys()) if source else [None]


def unit_filename(label: str, split_value: str | None) -> str:
    """저장 파일 이름: 단위이름.json 또는 단위이름_나눔값.json"""
    return f"{label}.json" if split_value is None else f"{label}_{split_value}.json"


def probe(
    key: str, spec: dict, api: dict, period_vars: dict[str, str], split_value: str | None
) -> tuple[list[dict], int]:
    """시험 호출: 몇 건만 받아 (행 목록, 전체 건수)를 돌려준다. 저장하지 않는다."""
    params = build_params(spec, period_vars, split_value, 1, api["probe_rows"])
    return extract_items(fetch_page(key, spec, api, params), spec)


def download_dataset(
    key: str, spec: dict, api: dict, config: dict, raw_dir: Path, months: list[str]
) -> dict:
    """데이터셋 전체를 단위별로 받아 raw_dir 에 저장하고, 받은 기록을 남긴다.

    이미 받은 파일은 다시 받지 않는다(원본 고정 원칙).
    출력: 기록 dict (raw_dir/_download_log.json 에도 저장)
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_path = raw_dir / "_download_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {
        "title": spec["title"], "source": spec["source"], "units": {}
    }
    for label, period_vars in period_units(spec, months):
        for split_value in split_values(spec, config):
            name = unit_filename(label, split_value)
            out_path = raw_dir / name
            if out_path.exists():
                continue
            rows = download_unit(key, spec, api, period_vars, split_value)
            out_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            log["units"][name] = {"rows": len(rows), "downloaded_on": str(date.today())}
            log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{name}: {len(rows)}건 저장")
            time.sleep(api["pause_sec"])
    log["last_run"] = datetime.now().isoformat(timespec="seconds")
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return log
