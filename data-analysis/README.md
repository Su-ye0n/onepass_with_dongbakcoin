# data-analysis — 동백 ONE 데이터 분석

동백전을 쓸 수 없는 곳의 소비 규모와 동백전 적립 추정액을 **공공데이터 기반 추정·시뮬레이션**으로 분석합니다.
작업 지시서는 [`docs/brief.md`](docs/brief.md), 데이터 점검 결과는 [`docs/data_inventory.md`](docs/data_inventory.md)에 있습니다.

## 1. 준비 (처음 한 번)

**① 파이썬 라이브러리 설치** (Python 3.12에서 확인)

```bash
cd data-analysis
pip install -r requirements.txt
```

**② 공공데이터포털 API 활용신청** — [data.go.kr](https://www.data.go.kr)에서 로그인 후 아래 두 개를 "활용신청" (자동 승인, 반영까지 1~2시간 걸릴 수 있음)

| 이름 | 번호 |
|---|---|
| 부산광역시_일별 행정동 소비매출 월별 일평균(업종)_카드데이터 | [15164434](https://www.data.go.kr/data/15164434/openapi.do) |
| 한국조폐공사_지역사랑상품권_가맹점_업종별_결제정보 | [15149767](https://www.data.go.kr/data/15149767/openapi.do) |

**③ API 키 넣기** — `data-analysis/.env` 파일을 만들고 마이페이지의 **일반 인증키**를 한 줄로 넣습니다.

```
DATA_GO_KR_KEY=여기에_인증키
```

> ⚠️ `.env`는 git에 올라가지 않습니다(`.gitignore`). 키를 코드·채팅·메신저에 붙여 넣지 마세요.

## 2. 실행 순서

모든 명령은 `data-analysis` 폴더에서 실행합니다.

| 순서 | 명령 | 하는 일 | 결과 |
|---|---|---|---|
| 1 | `python src/download.py d1 --probe` | 키가 작동하는지 5건만 시험 (저장 안 함) | 화면 출력 |
| 2 | `python src/download.py d1` | D1 원본 내려받기 (약 2분) | `data/raw/d1/` |
| 3 | `python src/download.py d9` | D9 원본 내려받기 (응답이 느려 약 30분) | `data/raw/d9/` |
| 4 | `python src/inventory.py d1` (d9도 같음) | STEP 0 점검 요약표 | `outputs/tables/00_*.csv` |
| 5 | `python src/clean_d1.py` | D1 정제 (오타 통일, 기준일 이후 제거, 월 합계) | `data/processed/d1_clean.parquet` |
| 6 | `python src/industry_evidence.py` | 업종별 동백전 비중 근거표 | `outputs/tables/01_dongbaek_share_by_category.csv` |

- **원본만 없는 경우:** 정제본(`data/processed/d1_clean.parquet`)은 저장소에 있으니, 5번까지 다시 할 필요 없이 **6번부터 바로** 실행할 수 있습니다.
- **다시 받기 방지:** 이미 받은 원본은 다시 받지 않습니다. 원본은 2026-10-19 한 번 받아 고정하는 원칙이에요.

**테스트**

```bash
python -m unittest discover tests
```

## 3. 폴더 구조

```
data-analysis/
├─ config.yaml        # 기간·기준일·API 주소·경로·컬럼 이름 (값은 여기서만 바꿈)
├─ src/
│  ├─ data_go_kr.py   # 공공데이터포털 공통 도구 (키 읽기·요청·페이지·저장)
│  ├─ download.py     # 내려받기 실행
│  ├─ inventory.py    # STEP 0 점검
│  ├─ clean_d1.py     # STEP 1 D1 정제
│  ├─ industry_evidence.py  # STEP 1 업종 판정 근거
│  └─ settings.py · raw_io.py · profiling.py  # 설정·원본 읽기·요약 함수
├─ ref/               # 사람이 입력·검토하는 표 (출처 열 포함)
│  ├─ industry_map.csv          # D1 업종 ↔ 동백전 사용 가능 여부 (초안, 검토 중)
│  ├─ report_category_map.csv   # 보고서 업종 → D1 업종 연결 (초안)
│  ├─ dongbaek_stats_bdi2025.csv  # 부산연구원(2025) 보고서 표 옮김
│  └─ policy.csv                # 동백전 캐시백·한도 이력
├─ data/raw/          # API 원본 (git 제외)
├─ data/processed/    # 정제본
├─ outputs/tables/    # 결과표
├─ docs/              # 지시서·점검 결과
└─ tests/
```

## 4. 새 공공데이터 API 추가하는 법

`config.yaml`의 `datasets:` 아래에 항목을 하나 추가하면, `python src/download.py <이름>`으로 같은 코드를 그대로 쓸 수 있습니다. `d1`, `d9` 항목을 참고하세요.

| 설정 | 뜻 |
|---|---|
| `url` | API 주소 |
| `params` | 매번 같은 값으로 보내는 파라미터 |
| `month_params` | 기간 파라미터 |
| `unit` | `month`(한 달씩) / `period`(기간 전체를 한 번에) |
| `page_param` · `size_param` | 페이지 번호·페이지당 행 수 파라미터 이름 |
| `items_path` · `total_path` | 응답 안에서 행 목록·전체 건수가 있는 위치 |

## 5. 지켜야 할 것

- **다른 폴더는 건드리지 않습니다.** 이 폴더 밖 파일은 수정하지 않아요.
- **값은 코드에 쓰지 않습니다.** 정책값·경로는 `config.yaml`이나 `ref/`에 둡니다.
- **결과는 추정으로 표현합니다.** "실제 효과"가 아니라 "공공데이터 기반 추정·시뮬레이션"이라고 쓰고, 숫자마다 출처 또는 "가정"을 표시해요.
- **기준 시점은 2026-06-30입니다.** 이후 자료는 쓰지 않아요.
