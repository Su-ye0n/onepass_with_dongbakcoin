"""규칙 엔진 처리시간 측정 (DB 없이 메모리에서만).

실행: python scripts/benchmark_engine.py
- 카드 수·카드당 규칙 수를 바꿔 가며 결제 1건(process)의 처리시간을 잰다.
- 같은 사용자의 결제를 연달아 처리하는 배치 시간도 잰다.
"""
import statistics
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "module"))
from onepass.engine import (  # noqa: E402
    BenefitRule, Card, CardType, DbPolicy, Merchant, Request, State, process,
)


def build_cards(n_cards: int, n_rules: int):
    cards = [Card("DB01", CardType.DONGBAEK_CHECK, account_id="ACC01")]
    for i in range(n_cards - 1):
        rules = tuple(
            BenefitRule(f"R{i}_{j}", ("FOOD",), Decimal("0.03"), 0, 0, 3000, 10**9)
            for j in range(n_rules)
        )
        cards.append(Card(
            f"C{i}", CardType.CREDIT if i % 2 else CardType.DEBIT,
            account_id="ACC01", credit_limit=10**9, prev_month_perf=10**6, rules=rules,
        ))
    return cards


def one_request_us(n_cards: int, n_rules: int, reps: int = 5000) -> float:
    cards, merchant, policy = build_cards(n_cards, n_rules), Merchant("M1", "FOOD", True), DbPolicy()
    times = []
    for k in range(reps):
        state = State(accounts={"ACC01": 10**12}, db_charge=10**12)
        t0 = time.perf_counter()
        process(Request(f"T{k}", "M1", 20000), merchant, cards, state, policy)
        times.append(time.perf_counter() - t0)
    return statistics.median(times) * 1e6


if __name__ == "__main__":
    print("[결제 1건] 카드 수 늘리기 (카드당 규칙 3개)")
    for c in (2, 4, 8, 16, 32, 64):
        print(f"  카드 {c:>2}장: 중앙값 {one_request_us(c, 3):7.1f} µs")
    print("[결제 1건] 카드당 규칙 수 늘리기 (카드 8장)")
    for r in (1, 3, 6, 12, 24):
        print(f"  규칙 {r:>2}개: 중앙값 {one_request_us(8, r):7.1f} µs")
    print("[연속 처리] 한 사용자, 카드 4장 x 규칙 3개")
    cards, merchant, policy = build_cards(4, 3), Merchant("M1", "FOOD", True), DbPolicy()
    for n in (1000, 7540, 30000):
        state = State(accounts={"ACC01": 10**12}, db_charge=10**9)
        t0 = time.perf_counter()
        for k in range(n):
            process(Request(f"B{n}_{k}", "M1", 20000), merchant, cards, state, policy)
        dt = time.perf_counter() - t0
        print(f"  {n:>6}건: 총 {dt:6.3f}초 (건당 {dt / n * 1e6:5.1f} µs)")
