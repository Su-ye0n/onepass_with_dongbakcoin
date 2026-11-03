# 4개 시나리오 실행 결과 (v3.4)

직원 대시보드 API(`/api/v1/admin/...`)가 읽는 시뮬레이션 결과입니다. DB에 쓰지 않습니다.

| 파일 | 내용 | 만든 곳 |
|---|---|---|
| `users.csv` | 사용자 240명 × 시나리오 S00·S10·S01·S11 혜택 | `compare_four_scenarios.py` |
| `transactions.csv` | 거래 7,540건 × 시나리오별 선택 카드·혜택 | `compare_four_scenarios.py` |
| `summary.json` | 시나리오 합계, Shapley 분해, 실행 조건 | `compare_four_scenarios.py` |
| `dashboard_constants.json` | 동백전 배제 사유 건수, S02 자동충전 민감도 9칸 | MVP 대시보드 값을 옮김 (원천 파일 교체 필요) |

- 평가월 2026-06, 합성 데이터 v3.4. 실제 고객·실거래 아님
- 혜택 = 동백전 캐시백 + BNK 현금성 혜택. **카드 포인트는 0원으로 계산** (`summary.json` → `methodology.point_rate`)
- 다른 실행 결과를 쓰려면 `.env`에 `SIMULATION_RESULTS_DIR=<폴더 경로>`를 지정
