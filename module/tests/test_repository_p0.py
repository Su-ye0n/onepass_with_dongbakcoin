import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from onepass.engine import CardType
from onepass.repository_p0 import (
    P0Repository,
    UnsupportedP0Rule,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema_p0.sql"


@pytest.fixture
def sample_db(tmp_path):
    path = tmp_path / "p0_test.sqlite"

    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(SCHEMA.read_text(encoding="utf-8"))

        db.execute(
            """
            INSERT INTO "USER" (user_id)
            VALUES ('SYN_U001')
            """
        )

        db.execute(
            """
            INSERT INTO ACCOUNT
                (account_id, user_id, account_role,
                 opening_balance_won)
            VALUES ('A001', 'SYN_U001',
                    'CHECK_PAYMENT', 100000)
            """
        )

        db.execute(
            """
            INSERT INTO DB_WALLET
                (wallet_id, user_id, charge_won,
                 cashback_won, policy_support_won)
            VALUES ('W001', 'SYN_U001',
                    30000, 2000, 0)
            """
        )

        db.executemany(
            """
            INSERT INTO CARD_PRODUCT
                (product_id, product_name, issuer, card_type)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    "P_DB", "Demo Dongbaek",
                    "DONGBAEKJEON", "DONGBAEK_CHECK",
                ),
                (
                    "P_BANK", "Demo Bank",
                    "BNK_BUSAN", "BANK_CHECK",
                ),
            ],
        )

        db.executemany(
            """
            INSERT INTO USER_CARD
                (user_card_id, user_id, product_id,
                 db_wallet_id, linked_account_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "UC_DB", "SYN_U001", "P_DB",
                    "W001", "A001",
                ),
                (
                    "UC_BANK", "SYN_U001", "P_BANK",
                    None, "A001",
                ),
            ],
        )

        db.execute(
            """
            INSERT INTO BENEFIT_CATEGORY_MAP
                (industry_code, std_category,
                 screen_group_code, valid_from)
            VALUES ('CAFE_SOURCE', 'CAFE',
                    'CAFE', '2026-01-01')
            """
        )

        db.execute(
            """
            INSERT INTO MERCHANT
                (merchant_id, industry_code,
                 dongbaek_status, sales_band)
            VALUES ('M001', 'CAFE_SOURCE',
                    'REGISTERED', 'LE_10B')
            """
        )

        db.execute(
            """
            INSERT INTO DB_POLICY
                (policy_id, policy_name, policy_mode,
                 monthly_cashback_base_cap_won,
                 valid_from, valid_to)
            VALUES ('POL001', 'Demo Policy',
                    'HISTORICAL', 500000,
                    '2026-01-01', '2027-01-01')
            """
        )

        db.execute(
            """
            INSERT INTO DB_POLICY_RATE
                (policy_id, sales_band, cashback_rate)
            VALUES ('POL001', 'LE_10B', '0.10')
            """
        )

        db.execute(
            """
            INSERT INTO BENEFIT_RULE
                (rule_id, product_id, benefit_name,
                 benefit_type, rate, valid_from, valid_to)
            VALUES ('R_CAFE', 'P_BANK', 'Cafe 5%',
                    'RATE', '0.05',
                    '2026-01-01', '2027-01-01')
            """
        )

        db.execute(
            """
            INSERT INTO BENEFIT_INDUSTRY
                (rule_id, target_type,
                 target_code, apply_type)
            VALUES ('R_CAFE', 'CATEGORY',
                    'CAFE', 'INCLUDE')
            """
        )

        db.commit()

    return path


def test_load_users_cards_wallet(sample_db):
    repo = P0Repository(sample_db)

    merchants, users, policy = repo.load("2026-06-15")

    assert "SYN_U001" in users

    cards, state = users["SYN_U001"]

    assert len(cards) == 2
    assert state.accounts["A001"] == 100000
    
    # 신규 ERD의 DB_WALLET에 대응하는 상태 검증
    assert "W001" in state.wallets

    wallet = state.wallets["W001"]

    assert wallet.charge == 30000
    assert wallet.cashback == 2000
    assert wallet.grant == 0
    assert wallet.month_applied == 0

    # 기존 단일 지갑 필드는 호환용이며
    # 신규 ERD 로더의 잔액 기준으로 사용하지 않음
    assert state.db_charge == 0
    assert state.db_cashback == 0
    assert state.db_grant == 0


    assert policy.cashback_rates["LE_10B"] == Decimal("0.10")
    assert merchants["M001"].category == "CAFE"


def test_card_product_mapping(sample_db):
    repo = P0Repository(sample_db)
    _, users, _ = repo.load("2026-06-15")

    cards, _ = users["SYN_U001"]
   
    # 동백전 카드가 올바른 지갑을 참조하는지 확인
    by_id = {card.id: card for card in cards}

    assert by_id["UC_DB"].wallet_id == "W001"
    assert by_id["UC_BANK"].wallet_id is None

    # 두 카드가 동일한 은행 계좌를 참조하는지 확인
    assert by_id["UC_DB"].account_id == "A001"
    assert by_id["UC_BANK"].account_id == "A001"


def test_benefit_rule_mapping(sample_db):
    repo = P0Repository(sample_db)
    _, users, _ = repo.load("2026-06-15")

    cards, _ = users["SYN_U001"]
    bank_card = next(c for c in cards if c.id == "UC_BANK")

    assert len(bank_card.rules) == 1

    rule = bank_card.rules[0]
    assert rule.id == "UC_BANK:R_CAFE"
    assert rule.categories == ("CAFE",)
    assert rule.rate == Decimal("0.05")


def test_unsupported_fixed_benefit_is_rejected(sample_db):
    with sqlite3.connect(sample_db) as db:
        db.execute(
            """
            UPDATE BENEFIT_RULE
            SET benefit_type = 'FIXED',
                fixed_amount_won = 1000
            WHERE rule_id = 'R_CAFE'
            """
        )
        db.commit()

    with pytest.raises(
        UnsupportedP0Rule,
        match="Unsupported benefit conditions",
    ):
        P0Repository(sample_db).load("2026-06-15")


def test_read_only_database(sample_db):
    repo = P0Repository(sample_db)

    with repo.connect() as db:
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                'INSERT INTO "USER" (user_id) VALUES (?)',
                ("SHOULD_NOT_WRITE",),
            )


def test_policy_valid_to_is_exclusive(sample_db):
    repo = P0Repository(sample_db)

    with pytest.raises(ValueError, match="Expected exactly one"):
        repo.load("2027-01-01")


def test_repository_merchant_exclusion(sample_db):
    from onepass.engine import Request, decide

    with sqlite3.connect(sample_db) as db:
        # M001: 일반 카페, M002: 같은 업종의 할인 제외 매장
        db.execute(
            """
            INSERT INTO MERCHANT
                (merchant_id, industry_code,
                 dongbaek_status, sales_band)
            VALUES ('M002', 'CAFE_SOURCE',
                    'NOT_REGISTERED', 'LE_10B')
            """
        )

        db.execute(
            """
            INSERT INTO BENEFIT_INDUSTRY
                (rule_id, target_type,
                 target_code, apply_type)
            VALUES ('R_CAFE', 'MERCHANT',
                    'M002', 'EXCLUDE')
            """
        )
        db.commit()

    merchants, users, policy = P0Repository(
        sample_db
    ).load("2026-06-15")

    cards, state = users["SYN_U001"]

    # 일반 카페는 5% 할인
    normal = decide(
        Request(
            "R1", "M001", 10000,
            payment_path="DIRECT",
            direct_card_id="UC_BANK",
        ),
        merchants["M001"],
        cards,
        state,
        policy,
    )

    # 제외 매장은 결제 가능하지만 할인 0원
    excluded = decide(
        Request(
            "R2", "M002", 10000,
            payment_path="DIRECT",
            direct_card_id="UC_BANK",
        ),
        merchants["M002"],
        cards,
        state,
        policy,
    )

    assert normal.approved
    assert normal.benefit_won == 500

    assert excluded.approved
    assert excluded.benefit_won == 0

    # 미리보기 호출이므로 상태는 불변
    assert state.accounts["A001"] == 100000
    assert state.ledger == []

def test_repository_loads_multiple_wallets(sample_db):
    """P0에서는 사용자당 활성 동백전 카드 2장을 허용하지 않는다."""
    with sqlite3.connect(sample_db) as db:
        db.execute(
            """
            INSERT INTO DB_WALLET
                (wallet_id, user_id, charge_won,
                 cashback_won, policy_support_won)
            VALUES ('W002', 'SYN_U001', 50000, 1000, 0)
            """
        )

        db.execute(
            """
            INSERT INTO USER_CARD
                (user_card_id, user_id, product_id,
                 db_wallet_id, linked_account_id)
            VALUES (
                'UC_DB2', 'SYN_U001',
                'P_DB', 'W002', 'A001'
            )
            """
        )
        db.commit()

    with pytest.raises(
        ValueError,
        match="MULTIPLE_ACTIVE_DONGBAEK_CARDS",
    ):
        P0Repository(sample_db).load("2026-06-15")

def test_multiple_wallets_payment_isolation(sample_db):
    """동백전 1장과 일반 체크카드 2장의 상태 공유 검증."""
    from onepass.engine import Request, process

    with sqlite3.connect(sample_db) as db:
        db.execute(
            """
            INSERT INTO USER_CARD
                (user_card_id, user_id, product_id,
                 linked_account_id)
            VALUES (
                'UC_BANK2', 'SYN_U001',
                'P_BANK', 'A001'
            )
            """
        )
        db.commit()

    merchants, users, policy = P0Repository(
        sample_db
    ).load("2026-06-15")

    cards, state = users["SYN_U001"]

    by_id = {card.id: card for card in cards}

    assert len(cards) == 3

    # 동백전 카드 한 장
    assert sum(
        card.type.value == "DONGBAEK_CHECK"
        for card in cards
    ) == 1

    # 일반 체크카드 두 장
    assert by_id["UC_BANK"].account_id == "A001"
    assert by_id["UC_BANK2"].account_id == "A001"

    first = process(
        Request(
            "R_BANK1",
            "M001",
            10000,
            payment_path="DIRECT",
            direct_card_id="UC_BANK",
        ),
        merchants["M001"],
        cards,
        state,
        policy,
    )

    assert first.approved
    assert state.accounts["A001"] == 90000

    second = process(
        Request(
            "R_BANK2",
            "M001",
            10000,
            payment_path="DIRECT",
            direct_card_id="UC_BANK2",
        ),
        merchants["M001"],
        cards,
        state,
        policy,
    )

    assert second.approved
    assert state.accounts["A001"] == 80000

    # 일반 카드 결제는 동백전 지갑에 영향 없음
    assert state.wallets["W001"].charge == 30000
    assert state.wallets["W001"].cashback == 2000

    # 동백전 결제
    third = process(
        Request(
            "R_DB",
            "M001",
            10000,
            payment_path="DIRECT",
            direct_card_id="UC_DB",
        ),
        merchants["M001"],
        cards,
        state,
        policy,
    )

    assert third.approved

    # 동백전은 지갑에서 결제하므로 은행 계좌 불변
    assert state.accounts["A001"] == 80000

    assert state.wallets["W001"].charge == 22000
    assert state.wallets["W001"].cashback == 800

def test_blocked_wallet_cannot_load_as_active(sample_db):
    """차단 지갑을 활성 결제 지갑으로 로딩하지 않는다."""
    with sqlite3.connect(sample_db) as db:
        db.execute(
            """
            UPDATE DB_WALLET
            SET wallet_status = 'BLOCKED'
            WHERE wallet_id = 'W001'
            """
        )
        db.commit()

    with pytest.raises(
        UnsupportedP0Rule,
        match="WALLET_NOT_ACTIVE",
    ):
        P0Repository(sample_db).load("2026-06-15")

def test_repository_loads_category_priorities(sample_db):
    from onepass.engine import Request, decide

    with sqlite3.connect(sample_db) as db:
        db.execute(
            """
            INSERT INTO USER_CATEGORY
                (user_id, user_category_code, label)
            VALUES ('SYN_U001', 'CAFE', '카페')
            """
        )

        db.executemany(
            """
            INSERT INTO USER_CATEGORY_PRIORITY
                (priority_id, user_id, user_category_code,
                 user_card_id, priority_group)
            VALUES (?, 'SYN_U001', 'CAFE', ?, ?)
            """,
            [
                ("PRI1", "UC_BANK", 1),
                ("PRI2", "UC_DB", 2),
            ],
        )
        db.commit()

    merchants, users, policy = P0Repository(
        sample_db
    ).load("2026-06-15")

    cards, state = users["SYN_U001"]

    assert state.category_priorities["CAFE"] == {
        "UC_BANK": 1,
        "UC_DB": 2,
    }

    # 실제 혜택이 더 큰 동백전 카드가 선택되어야 함
    result = decide(
        Request("R1", "M001", 10000),
        merchants["M001"],
        cards,
        state,
        policy,
    )

    assert result.approved
    assert result.selected_card_id == "UC_DB"

    # 충전금 사용액 8,000원 × 캐시백률 10%
    assert result.benefit_won == 800

