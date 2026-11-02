from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema_p0.sql"

EXPECTED_TABLES = {
    "CARD_PRODUCT",
    "BENEFIT_RULE",
    "BENEFIT_INDUSTRY",
    "CARD_PERF_EXCLUDE",
    "BENEFIT_CAP_TIER",
    "DB_POLICY",
    "DB_POLICY_RATE",
    "DB_POLICY_BONUS",
    "MERCHANT",
    "BENEFIT_CATEGORY_MAP",
    "USER",
    "ONECARD",
    "USER_CATEGORY",
    "USER_CATEGORY_PRIORITY",
    "ACCOUNT",
    "DB_WALLET",
    "USER_CARD",
    "LEDGER",
    "CARD_MONTH_CLOSE",
    "CARD_PERF_MONTH_CLOSE",
}


def create_db():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA.read_text(encoding="utf-8"))
    return db


def test_create_20_tables():
    with create_db() as db:
        actual = {
            row[0]
            for row in db.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            )
        }

    assert actual == EXPECTED_TABLES


def test_foreign_keys_enabled():
    with create_db() as db:
        assert db.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0] == 1


def test_wallet_is_separate_from_account():
    with create_db() as db:
        wallet_columns = {
            row[1]
            for row in db.execute("PRAGMA table_info(DB_WALLET)")
        }

        account_columns = {
            row[1]
            for row in db.execute("PRAGMA table_info(ACCOUNT)")
        }

    assert "charge_won" in wallet_columns
    assert "cashback_won" in wallet_columns
    assert "policy_support_won" in wallet_columns

    assert "opening_balance_won" in account_columns
    assert "charge_won" not in account_columns


def test_user_card_references_wallet_and_account():
    with create_db() as db:
        columns = {
            row[1]
            for row in db.execute("PRAGMA table_info(USER_CARD)")
        }

    assert "db_wallet_id" in columns
    assert "linked_account_id" in columns
    assert "registered_ref" in columns


def test_foreign_key_integrity():
    with create_db() as db:
        db.execute(
            """
            INSERT INTO CARD_PRODUCT
                (product_id, product_name, issuer, card_type)
            VALUES (?, ?, ?, ?)
            """,
            ("P1", "Demo Card", "BNK_BUSAN", "BANK_CHECK"),
        )

        db.execute(
            """
            INSERT INTO "USER" (user_id)
            VALUES (?)
            """,
            ("SYN_U001",),
        )

        db.execute(
            """
            INSERT INTO USER_CARD
                (user_card_id, user_id, product_id)
            VALUES (?, ?, ?)
            """,
            ("UC1", "SYN_U001", "P1"),
        )

        errors = db.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    assert errors == []
