"""동백원패스 1차 규칙 기반 시뮬레이터. 외부 결제 승인 기능 없음."""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Optional

class CardType(str, Enum):
    CREDIT = 'CREDIT'
    DEBIT = 'DEBIT'
    DONGBAEK_CHECK = 'DONGBAEK_CHECK'


@dataclass(frozen=True)
class Request:
    id: str
    merchant_id: str
    amount: int
    onecard_active: bool = True
    payment_path: str = "ONECARD"
    direct_card_id: Optional[str] = None

@dataclass(frozen=True)
class BenefitRule:
    id: str
    categories: tuple[str, ...]
    rate: Decimal
    prev_month_min: int = 0
    min_payment: int = 0
    per_tx_cap: Optional[int] = None
    monthly_cap: Optional[int] = None

    # P0-5: 가맹점 단위 포함·제외 조건
    merchants: tuple[str, ...] = ()
    excluded_categories: tuple[str, ...] = ()
    excluded_merchants: tuple[str, ...] = ()

@dataclass(frozen=True)
class Card:
    id: str
    type: CardType
    account_id: Optional[str] = None
    credit_limit: int = 0
    active: bool = True
    lost: bool = False
    expired: bool = False
    prev_month_perf: int = 0
    rules: tuple[BenefitRule, ...] = ()

    # P0-4: 확정 ERD의 USER_CARD.db_wallet_id
    wallet_id: Optional[str] = None

@dataclass(frozen=True)
class Merchant:
    id: str
    category: str
    db_registered: bool
    annual_sales_band: str = "LE_10B"

@dataclass(frozen=True)
class DbPolicy:
    cashback_rates: dict[str, Decimal] = field(default_factory=lambda: {
        'LE_10B': Decimal('0.10'), 'LE_30B': Decimal('0.08'), 'GT_30B': Decimal('0')
    })
    monthly_applicable_amount_cap: int = 500_000
    # Below are explicit SIMULATION ASSUMPTIONS (not a verified policy claim).
    assume_partial_cap: bool = True
    assume_cashback_eligible_charge_only: bool = True

@dataclass
class WalletBalance:
    charge: int = 0
    cashback: int = 0
    grant: int = 0
    month_applied: int = 0


@dataclass
class State:
    accounts: dict[str, int]

    # P0-4: wallet_id별 동백전 잔액
    wallets: dict[str, WalletBalance] = field(default_factory=dict)

    credit_used: dict[str, int] = field(default_factory=dict)

    # 기존 단일 지갑 필드: 구형 코드 호환용
    db_charge: int = 0
    db_cashback: int = 0
    db_grant: int = 0
    db_month_applied: int = 0

    benefit_used: dict[str, int] = field(default_factory=dict)
    ledger: list[dict] = field(default_factory=list)
    processed_requests: set[str] = field(default_factory=set)
    
    # 업종별 카드 우선순위: 숫자가 작을수록 우선
    # 예: {"CAFE": {"UC_BANK": 1, "UC_DB": 2}}
    category_priorities: dict[str, dict[str, int]] = field(
        default_factory=dict
    )

@dataclass(frozen=True)
class Candidate:
    card_id: str
    eligible: bool
    reason: str
    expected_benefit: int = 0
    funding_mode: str = ''
    rule_id: str = ''
    db_applied: int = 0

@dataclass(frozen=True)
class Decision:
    request_id: str
    approved: bool
    selected_card_id: Optional[str]
    benefit_won: int
    reason: str
    candidates: tuple[Candidate, ...]

def won(amount: Decimal) -> int:
    return int(amount.quantize(Decimal('1'), rounding=ROUND_DOWN))


def _wallet_values(
    state: State,
    card: Card,
) -> tuple[int, int, int, int]:
    """
    Return (grant, cashback, charge, month_applied).

    New cards use wallet_id.
    Legacy cards use the original db_* fields.
    """
    if card.wallet_id is not None:
        if card.wallet_id not in state.wallets:
            raise ValueError(
                f"WALLET_NOT_FOUND: {card.wallet_id}"
            )

        w = state.wallets[card.wallet_id]

        return (
            w.grant,
            w.cashback,
            w.charge,
            w.month_applied,
        )

    if state.wallets:
        raise ValueError(
            f"WALLET_ID_REQUIRED: {card.id}"
        )

    return (
        state.db_grant,
        state.db_cashback,
        state.db_charge,
        state.db_month_applied,
    )


def _apply_wallet_purchase(
    state: State,
    card: Card,
    amount: int,
    cashback_earned: int,
    applied: int,
) -> None:
    """
    Spend order (simulation assumption):
    GRANT -> CASHBACK -> CHARGE.

    The cashback earned is added after payment.
    """

    # Legacy single-wallet mode
    if card.wallet_id is None:
        remaining = amount

        for bucket in (
            "db_grant",
            "db_cashback",
            "db_charge",
        ):
            deduct = min(
                remaining,
                getattr(state, bucket),
            )

            setattr(
                state,
                bucket,
                getattr(state, bucket) - deduct,
            )

            remaining -= deduct

        if remaining:
            raise ValueError(
                "not enough dongbaek funding"
            )

        state.db_month_applied += applied
        state.db_cashback += cashback_earned
        return

    # New multi-wallet mode
    w = state.wallets[card.wallet_id]
    remaining = amount

    for bucket in ("grant", "cashback", "charge"):
        deduct = min(
            remaining,
            getattr(w, bucket),
        )

        setattr(
            w,
            bucket,
            getattr(w, bucket) - deduct,
        )

        remaining -= deduct

    if remaining:
        raise ValueError(
            "not enough dongbaek funding"
        )

    w.month_applied += applied
    w.cashback += cashback_earned


def db_funding(
    amount: int,
    state: State,
    card: Card,
) -> tuple[bool, str]:

    grant, cashback, charge, _ = _wallet_values(
        state, card
    )

    total_balance = grant + cashback + charge

    # 동백전 지갑으로 전액 결제 가능
    if total_balance >= amount:
        return True, "DB_BALANCE"

    # 지갑 부족 시 연결 계좌에서 전액 결제
    if (
        card.account_id
        and state.accounts.get(card.account_id, 0) >= amount
    ):
        return True, "ACCOUNT_FALLBACK"

    return False, "INSUFFICIENT_DB_AND_ACCOUNT"

def matches_benefit_target(
    rule: BenefitRule,
    merchant: Merchant,
) -> bool:
    """
    P0-5 benefit target matching.

    INCLUDE:
      category match OR merchant match

    EXCLUDE:
      category or merchant match vetoes the rule.

    An empty INCLUDE set does not mean all merchants.
    """
    if merchant.category in rule.excluded_categories:
        return False

    if merchant.id in rule.excluded_merchants:
        return False

    category_match = merchant.category in rule.categories
    merchant_match = merchant.id in rule.merchants

    return category_match or merchant_match

def evaluate(card: Card, merchant: Merchant, amount: int, state: State, policy: DbPolicy) -> Candidate:
    if not card.active: return Candidate(card.id, False, 'INACTIVE')
    if card.lost: return Candidate(card.id, False, 'LOST')
    if card.expired: return Candidate(card.id, False, 'EXPIRED')
    if card.type == CardType.CREDIT:
        if card.credit_limit - state.credit_used.get(card.id, 0) < amount:
            return Candidate(card.id, False, 'CREDIT_LIMIT')
    elif card.type == CardType.DEBIT:
        if not card.account_id or state.accounts.get(card.account_id, 0) < amount:
            return Candidate(card.id, False, 'ACCOUNT_BALANCE')
    elif card.type == CardType.DONGBAEK_CHECK:
        if not merchant.db_registered:
            return Candidate(card.id, False, 'NOT_DB_MERCHANT')
        ok, funding = db_funding(amount, state, card)
        if not ok: return Candidate(card.id, False, funding)
        if funding == 'ACCOUNT_FALLBACK':
            return Candidate(card.id, True, 'ELIGIBLE_ZERO_CASHBACK', 0, funding)
        # Charge money assumed eligible, other buckets assumed ineligible.
        
        grant, cashback, charge, month_applied = (_wallet_values(state, card))

        charge_spent = min(charge,max(0, amount - grant - cashback), )

        charge_eligible = charge_spent if policy.assume_cashback_eligible_charge_only else amount
        remaining = max(0,policy.monthly_applicable_amount_cap- month_applied)

        applied = min(charge_eligible, remaining) if policy.assume_partial_cap else (charge_eligible if charge_eligible <= remaining else 0)
        rate = policy.cashback_rates.get(merchant.annual_sales_band, Decimal(0))
        return Candidate(card.id, True, 'ELIGIBLE', won(Decimal(applied) * rate), funding, db_applied=applied)
    else:
        return Candidate(card.id, False, 'UNKNOWN_CARD_TYPE')

    best = (0, "")

    for rule in card.rules:
        if not matches_benefit_target(rule, merchant):
            continue

        if amount < rule.min_payment:
            continue

        if card.prev_month_perf < rule.prev_month_min:
            continue

        value = won(Decimal(amount) * rule.rate)
        if rule.per_tx_cap is not None: value = min(value, rule.per_tx_cap)
        if rule.monthly_cap is not None: value = min(value, max(0, rule.monthly_cap - state.benefit_used.get(rule.id, 0)))
        if (value, rule.id) > best: best = (value, rule.id)
    return Candidate(card.id, True, 'ELIGIBLE', best[0], 'CREDIT' if card.type == CardType.CREDIT else 'ACCOUNT', best[1])



def decide(
    request: Request,
    merchant: Merchant,
    cards: list[Card],
    state: State,
    policy: DbPolicy
) -> Decision:

    # 1. 공통 요청 검사
    if request.id in state.processed_requests:
        return Decision(
            request.id, False, None, 0,
            "DUPLICATE_REQUEST", ()
        )

    if request.amount <= 0:
        return Decision(
            request.id, False, None, 0,
            "INVALID_AMOUNT", ()
        )

    if request.payment_path not in ("ONECARD", "DIRECT"):
        return Decision(
            request.id, False, None, 0,
            "INVALID_PAYMENT_PATH", ()
        )

    # 2. 원카드 자동 결제인 경우에만 원카드 상태 검사
    if request.payment_path == "ONECARD":
        if not request.onecard_active:
            return Decision(
                request.id, False, None, 0,
                "ONECARD_BLOCKED", ()
            )

    # 3. 모든 하위 카드의 이용 가능 여부와 혜택 계산
    candidates = tuple(
        evaluate(
            card, merchant, request.amount, state, policy
        )
        for card in cards
    )

    # 4. 실물카드 직접 결제
    if request.payment_path == "DIRECT":

        if not request.direct_card_id:
            return Decision(
                request.id, False, None, 0,
                "DIRECT_CARD_REQUIRED", candidates
            )

        selected = next(
            (
                c for c in candidates
                if c.card_id == request.direct_card_id
            ),
            None
        )

        if selected is None:
            return Decision(
                request.id, False, None, 0,
                "DIRECT_CARD_NOT_REGISTERED", candidates
            )

        if not selected.eligible:
            return Decision(
                request.id, False, None, 0,
                "DIRECT_" + selected.reason, candidates
            )

        return Decision(
            request.id,
            True,
            selected.card_id,
            selected.expected_benefit,
            "DIRECT_CARD",
            candidates
        )

    # 5. 원카드 자동 배정: 최대 혜택 선택
    eligible = [
        c for c in candidates if c.eligible
    ]

    if not eligible:
        return Decision(
            request.id, False, None, 0,
            "NO_ELIGIBLE_CARD", candidates
        )
    
    # M5: 해당 업종에 설정된 사용자 카드 우선순위
    category_ranks = state.category_priorities.get(
        merchant.category, {}
    )

    selected = min(
        eligible,
        key=lambda c: (
            -c.expected_benefit,
            category_ranks.get(c.card_id, float("inf")),
            c.funding_mode == "ACCOUNT_FALLBACK",
            c.card_id,
        ),
    )

    return Decision(
        request.id,
        True,
        selected.card_id,
        selected.expected_benefit,
        "MAX_BENEFIT",
        candidates
    )

def apply(decision: Decision, request: Request, cards: list[Card], state: State) -> None:
    if request.id in state.processed_requests: raise ValueError('duplicate request')
    if not decision.approved or decision.selected_card_id is None: return
    card = next(c for c in cards if c.id == decision.selected_card_id)
    candidate = next(c for c in decision.candidates if c.card_id == card.id)
    amount = request.amount
    if card.type == CardType.CREDIT:
        state.credit_used[card.id] = state.credit_used.get(card.id, 0) + amount
    elif card.type == CardType.DEBIT:
        assert card.account_id is not None
        state.accounts[card.account_id] -= amount
    else:
        if candidate.funding_mode == 'ACCOUNT_FALLBACK':
            assert card.account_id is not None
            state.accounts[card.account_id] -= amount
        
        else:
            _apply_wallet_purchase(
                state, card,amount,candidate.expected_benefit,candidate.db_applied,  )

    if candidate.rule_id:
        state.benefit_used[candidate.rule_id] = state.benefit_used.get(candidate.rule_id, 0) + candidate.expected_benefit
    state.processed_requests.add(request.id)
    state.ledger.append({'request_id': request.id, 'card_id': card.id, 'amount': amount,
                         'benefit_won': candidate.expected_benefit, 'funding': candidate.funding_mode})


def process(request: Request, merchant: Merchant, cards: list[Card], state: State, policy: DbPolicy) -> Decision:
    result = decide(request, merchant, cards, state, policy)
    if result.approved: apply(result, request, cards, state)
    return result
