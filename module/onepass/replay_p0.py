"""P0 S2: 동일 거래의 전략별 독립 재생.

- DB 입력 데이터 수정 없음
- 전략별 State 깊은 복사
- 같은 월, 같은 거래 목록 사용
- 시간순 처리
- 월 경계 및 중복 요청 차단
- M6 전략별 카드 선택 로직은 다음 단계에서 연결
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from .engine import (
    Card,
    DbPolicy,
    Decision,
    Merchant,
    Request,
    State,
    process,
)


@dataclass(frozen=True)
class ReplayItem:
    """하나의 원본 소비 거래와 전략별 결제 요청."""

    event_at: str
    event_seq: int
    request: Request


@dataclass
class ReplayResult:
    strategy_id: str
    decisions: list[Decision]
    final_state: State


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        raise ValueError(
            "event_at must include a timezone offset: "
            f"{value}"
        )

    if parsed.utcoffset() is None:
        raise ValueError(
            f"Invalid timezone in event_at: {value}"
        )

    return parsed


def _validate_items(
    strategy_items: Mapping[str, Sequence[ReplayItem]],
) -> None:
    if not strategy_items:
        raise ValueError("No strategies provided")

    reference_signature = None

    for strategy_id, items in strategy_items.items():
        if not items:
            raise ValueError(
                f"No transactions: {strategy_id}"
            )

        seen = set()
        signature = []
        previous_key = None
        months = set()

        for item in items:
            req = item.request
            event_time = _parse_time(item.event_at)

            if req.amount <= 0:
                raise ValueError(
                    f"Invalid amount: {req.id}"
                )

            if item.event_seq < 0:
                raise ValueError(
                    f"Invalid event_seq: {req.id}"
                )

            if req.id in seen:
                raise ValueError(
                    f"Duplicate request_id in {strategy_id}: "
                    f"{req.id}"
                )
            seen.add(req.id)

            # 입력은 거래시각·순번 오름차순이어야 함
            key = (event_time, item.event_seq)

            if previous_key is not None and key < previous_key:
                raise ValueError(
                    f"Transactions are not ordered: "
                    f"{strategy_id}"
                )

            previous_key = key
            months.add(event_time.strftime("%Y-%m"))

            # 결제 방식만 달라질 수 있고 원본 소비는 동일해야 함
            signature.append(
                (
                    req.id,
                    req.merchant_id,
                    req.amount,
                    event_time,
                    item.event_seq,
                )
            )

        if len(months) != 1:
            raise ValueError(
                f"Mixed months not supported: {strategy_id}"
            )

        if reference_signature is None:
            reference_signature = signature
        elif signature != reference_signature:
            raise ValueError(
                "Strategies must use identical transactions "
                "in identical order"
            )


def replay_strategies(
    *,
    strategy_items: Mapping[str, Sequence[ReplayItem]],
    merchants: Mapping[str, Merchant],
    cards: Sequence[Card],
    initial_state: State,
    policy: DbPolicy,
) -> dict[str, ReplayResult]:
    """전략별 거래를 독립 상태에서 실행한다.

    주의:
    - 거래 목록의 원본 소비 조건은 모두 동일해야 한다.
    - strategy마다 Request.payment_path와
      Request.direct_card_id는 달라질 수 있다.
    - 이 함수는 월간 상태를 자동 초기화하지 않는다.
      한 번에 한 달만 실행한다.
    """
    _validate_items(strategy_items)

    results = {}

    for strategy_id, items in strategy_items.items():
        # 핵심: 전략별 원본 상태의 독립 복사
        state = deepcopy(initial_state)
        strategy_cards = deepcopy(list(cards))
        decisions = []

        for item in items:
            req = item.request

            if req.merchant_id not in merchants:
                raise ValueError(
                    f"Unknown merchant: {req.merchant_id}"
                )

            decision = process(
                req,
                merchants[req.merchant_id],
                strategy_cards,
                state,
                policy,
            )
            decisions.append(decision)

        results[strategy_id] = ReplayResult(
            strategy_id=strategy_id,
            decisions=decisions,
            final_state=state,
        )

    return results
