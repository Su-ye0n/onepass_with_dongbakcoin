"""P0 M6: A2/A3/B 결제 전략 실행.

A2: 고정 기본 카드, 실패 시 재시도 없음
A3: 동백전 우선, 불가능하면 기본 카드
B : 기존 OnePass 자동 선택

거래는 동일하게 유지하고 전략별 상태만 독립 복제한다.
A1 통계형은 데이터팀 행동 확률이 준비되면 추가한다.
"""

from __future__ import annotations
from copy import deepcopy
from typing import Mapping, Sequence
from .engine import ( Card,CardType, DbPolicy, Merchant, Request, State, decide, process,)
from .replay_p0 import ( ReplayItem,ReplayResult,_validate_items,)

from .a1_p0 import select_a1_card, validate_a1_weights

def _direct_request(
    original: Request,
    card_id: str,
) -> Request:
    """소비 거래 정보는 유지하고 결제 카드만 지정."""
    return Request(
        id=original.id,
        merchant_id=original.merchant_id,
        amount=original.amount,
        onecard_active=original.onecard_active,
        payment_path="DIRECT",
        direct_card_id=card_id,
    )

def _onecard_request(original: Request) -> Request:
    """동일 소비 거래를 OnePass 자동 결제 요청으로 변경."""
    return Request(
        id=original.id,
        merchant_id=original.merchant_id,
        amount=original.amount,
        onecard_active=original.onecard_active,
        payment_path="ONECARD",
    )


def _select_dongbaek_first(
    original: Request,
    merchant: Merchant,
    cards: list[Card],
    state: State,
    policy: DbPolicy,
    default_card_id: str,
    a1_weights: Mapping[str, object] | None = None,
    a1_seed: int = 2026,
) -> dict[str, ReplayResult]:

    """
    동백전 우선형의 현재 거래 카드 결정.

    동백전 카드가 여러 장이면 카드 ID 오름차순으로
    최초 결제 가능한 카드를 사용한다.

    동백전 카드가 하나도 결제 가능하지 않으면
    기본 카드를 선택한다.

    동백전 계좌대체 결제도 '결제 가능'으로 간주한다.
    """

    dongbaek_cards = sorted(
        (
            card
            for card in cards
            if card.type == CardType.DONGBAEK_CHECK
        ),
        key=lambda card: card.id,
    )

    for card in dongbaek_cards:
        candidate_request = _direct_request(
            original,
            card.id,
        )

        # decide는 상태를 변경하지 않는다.
        quoted = decide(
            candidate_request,
            merchant,
            cards,
            state,
            policy,
        )

        if quoted.approved:
            return card.id

    return default_card_id



def run_m6_p0(
    *,
    items: Sequence[ReplayItem],
    merchants: Mapping[str, Merchant],
    cards: Sequence[Card],
    initial_state: State,
    policy: DbPolicy,
    default_card_id: str,
    a1_weights: Mapping[str, object] | None = None,
    a1_seed: int = 2026,
) -> dict[str, ReplayResult]:

    """
    동일 소비 거래에 대해 A2, A3, B를 실행한다.

    각 전략은 완전히 독립된 State로 시작한다.
    A3는 매 거래마다 현재 상태로 동백전 가능 여부를 판단한다.

    Returns:
        {
          "A2": ReplayResult,
          "A3": ReplayResult,
          "B": ReplayResult,
        }
    """

    # 기존 S2의 입력 정렬, 중복 요청, 월 경계 검증 재사용
    _validate_items({"BASE": items})

    if not any(
        card.id == default_card_id for card in cards
    ):
        raise ValueError(
            f"DEFAULT_CARD_NOT_FOUND: {default_card_id}"
        )

    # P0 카드 보유 제약: 동백전 체크카드는 최대 1장
    dongbaek_cards = [
        card for card in cards
        if card.type == CardType.DONGBAEK_CHECK
    ]

    if len(dongbaek_cards) > 1:
        raise ValueError(
            "MULTIPLE_DONGBAEK_CARDS_NOT_ALLOWED: "
            f"{len(dongbaek_cards)} cards"
        )

    for item in items:
        if item.request.merchant_id not in merchants:
            raise ValueError(
                f"UNKNOWN_MERCHANT: "
                f"{item.request.merchant_id}"
            )

    results = {}
    
    if a1_weights is not None:
        validate_a1_weights(cards, a1_weights)

    strategies = (
        ("A1", "A2", "A3", "B")
        if a1_weights is not None
        else ("A2", "A3", "B")
    )

    results = {}

    for strategy_id in strategies:

        state = deepcopy(initial_state)
        strategy_cards = deepcopy(list(cards))
        decisions = []

        for item in items:
            original = item.request
            merchant = merchants[original.merchant_id]

            
            if strategy_id == "A1":
                selected_card_id = select_a1_card(
                    request_id=original.id,
                    cards=strategy_cards,
                    weights=a1_weights,
                    seed=a1_seed,
                )
                request = _direct_request(
                    original,
                    selected_card_id,
                )

            elif strategy_id == "A2":
                request = _direct_request(
                    original,
                    default_card_id,
                )

            elif strategy_id == "A3":
                selected_card_id = _select_dongbaek_first(
                    original=original,
                    merchant=merchant,
                    cards=strategy_cards,
                    state=state,
                    policy=policy,
                    default_card_id=default_card_id,
                )
                request = _direct_request(
                    original,
                    selected_card_id,
                )

            else:
                request = _onecard_request(original)

            decision = process(
                request,
                merchant,
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
