"""
P0 ERD -> existing OnePass engine DTO adapter.

Reads schema_p0.sql without modifying the input database.
This adapter supports a deliberately limited subset of P0 rules.

Unsupported rules fail explicitly instead of producing incorrect benefits.
"""

from __future__ import annotations

import sqlite3
from .engine import WalletBalance
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .engine import (
    BenefitRule,
    Card,
    CardType,
    DbPolicy,
    Merchant,
    State,
)


class UnsupportedP0Rule(ValueError):
    pass


class P0Repository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

        if not self.db_path.is_file():
            raise FileNotFoundError(
                f"P0 database does not exist: {self.db_path}"
            )

    def connect(self):
        db = sqlite3.connect(
            f"file:{self.db_path.resolve().as_posix()}?mode=ro",
            uri=True,
        )
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @staticmethod
    def _active(row, day: str) -> bool:
        return (
            (row["valid_from"] is None or row["valid_from"] <= day)
            and
            (row["valid_to"] is None or day < row["valid_to"])
        )

    @staticmethod
    def _previous_month(day: str) -> str:
        first = date.fromisoformat(day).replace(day=1)
        return (first - timedelta(days=1)).strftime("%Y-%m")

    def load(
        self,
        transaction_date: str,
        policy_id: str | None = None,
    ):
        """
        Returns (merchants, users, policy).

        users = {
            user_id: (list[Card], State)
        }

        No simulation results are written to SQLite.
        """

        day = date.fromisoformat(transaction_date).isoformat()
        previous_month = self._previous_month(day)

        with self.connect() as db:
            db.execute("PRAGMA foreign_key_check")

            policies = db.execute(
                """
                SELECT *
                FROM DB_POLICY
                WHERE (valid_from IS NULL OR valid_from <= ?)
                  AND (valid_to IS NULL OR ? < valid_to)
                  AND (? IS NULL OR policy_id = ?)
                """,
                (day, day, policy_id, policy_id),
            ).fetchall()

            if len(policies) != 1:
                raise ValueError(
                    f"Expected exactly one DB policy on {day}; "
                    f"found {len(policies)}"
                )

            p = policies[0]

            if p["policy_mode"] != "HISTORICAL":
                raise UnsupportedP0Rule(
                    "FROZEN_SCENARIO requires a separate "
                    "policy-date selection contract"
                )

            if p["rounding_mode"] != "FLOOR":
                raise UnsupportedP0Rule(
                    "Only FLOOR cashback rounding is supported"
                )

            bonuses = db.execute(
                """
                SELECT *
                FROM DB_POLICY_BONUS
                WHERE policy_id = ?
                  AND (valid_from IS NULL OR valid_from <= ?)
                  AND (valid_to IS NULL OR ? < valid_to)
                """,
                (p["policy_id"], day, day),
            ).fetchall()

            if bonuses:
                raise UnsupportedP0Rule(
                    "DB_POLICY_BONUS is not supported yet"
                )

            rates = {}
            for r in db.execute(
                """
                SELECT *
                FROM DB_POLICY_RATE
                WHERE policy_id = ?
                """,
                (p["policy_id"],),
            ):
                if r["eligible_funding_bucket"] not in (
                    None, "DB_CHARGE"
                ):
                    raise UnsupportedP0Rule(
                        "Unsupported cashback funding eligibility"
                    )

                rates[r["sales_band"]] = Decimal(
                    r["cashback_rate"]
                )

            if not rates:
                raise ValueError("DB_POLICY_RATE has no rows")

            # The current engine uses a legacy band name.
            if "GT_10B_LE_30B" in rates:
                rates["LE_30B"] = rates["GT_10B_LE_30B"]

            policy = DbPolicy(
                cashback_rates=rates,
                monthly_applicable_amount_cap=(
                    p["monthly_cashback_base_cap_won"]
                ),
                assume_partial_cap=True,
                assume_cashback_eligible_charge_only=True,
            )

            # Resolve merchant categories for transaction date.
            category_map = {}
            for r in db.execute(
                "SELECT * FROM BENEFIT_CATEGORY_MAP"
            ):
                if self._active(r, day):
                    code = r["industry_code"]
                    if code in category_map:
                        raise ValueError(
                            f"Overlapping category mapping: {code}"
                        )
                    category_map[code] = r["std_category"]

            merchants = {}
            for r in db.execute("SELECT * FROM MERCHANT"):
                if r["dongbaek_status"] == "UNKNOWN":
                    # Current engine cannot safely distinguish
                    # UNKNOWN from NOT_REGISTERED.
                    continue

                if r["sales_band"] == "UNKNOWN":
                    continue

                if r["sales_band"] not in rates:
                    raise ValueError(
                        f"No cashback rate for {r['sales_band']}"
                    )

                std_category = category_map.get(
                    r["industry_code"]
                )
                if std_category is None:
                    continue

                merchants[r["merchant_id"]] = Merchant(
                    id=r["merchant_id"],
                    category=std_category,
                    db_registered=(
                        r["dongbaek_status"] == "REGISTERED"
                    ),
                    annual_sales_band=r["sales_band"],
                )

            # Validate that the current engine can evaluate all
            # active benefit rules for the users being loaded.
            def load_rules(product_id, user_card_id, perf):
                result = []

                rows = db.execute(
                    """
                    SELECT *
                    FROM BENEFIT_RULE
                    WHERE product_id = ?
                      AND (valid_from IS NULL OR valid_from <= ?)
                      AND (valid_to IS NULL OR ? < valid_to)
                    ORDER BY rule_id
                    """,
                    (product_id, day, day),
                ).fetchall()

                for r in rows:
                    rid = r["rule_id"]

                    if (
                        r["benefit_type"] != "RATE"
                        or r["reward_unit"] != "CASH"
                        or r["day_condition"] != "ALL"
                        or r["monthly_count_cap"] is not None
                        or r["shared_cap_group"] is not None
                        or r["payment_channel_required"] != "ANY"
                        or r["rounding_mode"] != "FLOOR"
                        or r["stack_rule"] != "MAX_ONLY"
                    ):
                        raise UnsupportedP0Rule(
                            f"Unsupported benefit conditions: {rid}"
                        )

                    if r["rate"] is None:
                        raise UnsupportedP0Rule(
                            f"Rate is missing: {rid}"
                        )

                    targets = db.execute(
                        """
                        SELECT target_type, target_code, apply_type
                        FROM BENEFIT_INDUSTRY
                        WHERE rule_id = ?
                        """,
                        (rid,),
                    ).fetchall()

                    
                    # P0-5: CATEGORY / MERCHANT + INCLUDE / EXCLUDE
                    supported_types = {"CATEGORY", "MERCHANT"}
                    supported_actions = {"INCLUDE", "EXCLUDE"}

                    if not targets:
                        raise UnsupportedP0Rule(
                            f"No benefit targets: {rid}"
                        )

                    for target in targets:
                        if (
                            target["target_type"] not in supported_types
                            or target["apply_type"] not in supported_actions
                        ):
                            raise UnsupportedP0Rule(
                                f"Unsupported benefit targets: {rid}"
                            )

                    included_categories = tuple(
                        t["target_code"]
                        for t in targets
                        if t["target_type"] == "CATEGORY"
                        and t["apply_type"] == "INCLUDE"
                    )

                    included_merchants = tuple(
                        t["target_code"]
                        for t in targets
                        if t["target_type"] == "MERCHANT"
                        and t["apply_type"] == "INCLUDE"
                    )

                    excluded_categories = tuple(
                        t["target_code"]
                        for t in targets
                        if t["target_type"] == "CATEGORY"
                        and t["apply_type"] == "EXCLUDE"
                    )

                    excluded_merchants = tuple(
                        t["target_code"]
                        for t in targets
                        if t["target_type"] == "MERCHANT"
                        and t["apply_type"] == "EXCLUDE"
                    )

                    if not included_categories and not included_merchants:
                        raise UnsupportedP0Rule(
                            f"Benefit has no INCLUDE target: {rid}"
                        )

                    excludes = db.execute(
                        """
                        SELECT 1
                        FROM CARD_PERF_EXCLUDE
                        WHERE product_id = ?
                          AND (rule_id IS NULL OR rule_id = ?)
                          AND (valid_from IS NULL OR valid_from <= ?)
                          AND (valid_to IS NULL OR ? < valid_to)
                        LIMIT 1
                        """,
                        (product_id, rid, day, day),
                    ).fetchone()

                    if excludes:
                        raise UnsupportedP0Rule(
                            f"Performance exclusion needs M2: {rid}"
                        )

                    tiers = db.execute(
                        """
                        SELECT 1 FROM BENEFIT_CAP_TIER
                        WHERE product_id = ?
                          AND (valid_from IS NULL OR valid_from <= ?)
                          AND (valid_to IS NULL OR ? < valid_to)
                        LIMIT 1
                        """,
                        (product_id, day, day),
                    ).fetchone()

                    if tiers:
                        raise UnsupportedP0Rule(
                            f"Benefit cap tiers need M4: {rid}"
                        )

                    close = db.execute(
                        """
                        SELECT eligible_perf_won, benefit_used_won
                        FROM CARD_PERF_MONTH_CLOSE
                        WHERE user_card_id = ?
                          AND base_month = ?
                          AND rule_id = ?
                        """,
                        (user_card_id, previous_month, rid),
                    ).fetchone()

                    threshold = r["perf_threshold_won"] or 0

                    if threshold and close is None:
                        raise ValueError(
                            f"Missing previous-month performance: "
                            f"{user_card_id}/{rid}"
                        )

                    # Current engine stores one previous-month
                    # performance number per Card, not per Rule.
                    if close is not None and (
                        perf is not None
                        and perf != close["eligible_perf_won"]
                    ):
                        raise UnsupportedP0Rule(
                            f"Rule-specific performance needs M2: "
                            f"{user_card_id}"
                        )

                    if close is not None:
                        perf = close["eligible_perf_won"]

                    result.append(
                        BenefitRule(
                            id=f"{user_card_id}:{rid}",
                            
                            categories=included_categories,
                            merchants=included_merchants,
                            excluded_categories=excluded_categories,
                            excluded_merchants=excluded_merchants,

                            rate=Decimal(r["rate"]),
                            prev_month_min=threshold,
                            min_payment=r["min_amount_won"] or 0,
                            per_tx_cap=r["per_tx_cap_won"],
                            monthly_cap=r["monthly_cap_won"],
                        )
                    )

                return result, perf or 0

            users = {}

            for u in db.execute(
                'SELECT * FROM "USER" ORDER BY user_id'
            ).fetchall():
                uid = u["user_id"]

                accounts = {
                    a["account_id"]: a["opening_balance_won"]
                    for a in db.execute(
                        "SELECT * FROM ACCOUNT WHERE user_id = ?",
                        (uid,),
                    )
                }

                wallets = db.execute(
                    "SELECT * FROM DB_WALLET WHERE user_id = ?",
                    (uid,),
                ).fetchall()

                user_cards = db.execute(
                    """
                    SELECT c.*, p.card_type
                    FROM USER_CARD c
                    JOIN CARD_PRODUCT p
                    ON p.product_id = c.product_id
                    WHERE c.user_id = ?
                    ORDER BY c.user_card_id
                    """,
                    (uid,),
                ).fetchall()

                # P0: 사용자당 활성 동백전 카드 최대 1장
                active_db_cards = [
                    c for c in user_cards
                    if c["card_type"] == "DONGBAEK_CHECK"
                    and c["card_status"] == "ACTIVE"
                ]

                if len(active_db_cards) > 1:
                    raise ValueError(
                        f"MULTIPLE_ACTIVE_DONGBAEK_CARDS: {uid}"
                    )

                # P0: 활성 동백전 카드가 사용하는 지갑은 최대 1개
                active_db_wallet_ids = {
                    c["db_wallet_id"]
                    for c in active_db_cards
                    if c["db_wallet_id"] is not None
                }

                if len(active_db_wallet_ids) > 1:
                    raise ValueError(
                        f"MULTIPLE_ACTIVE_DONGBAEK_WALLETS: {uid}"
                    )

                wallet_ids = {
                    c["db_wallet_id"]
                    for c in user_cards
                    if c["db_wallet_id"] is not None
                }


                # P0-6: 사용자별 동백전 지갑을 ID로 관리
                wallet_by_id = {
                    w["wallet_id"]: w
                    for w in wallets
                }

                # 카드가 참조하는 지갑이 반드시 카드 소유자의 지갑인지 검사
                for wid in wallet_ids:
                    if wid not in wallet_by_id:
                        raise ValueError(
                            f"WALLET_OWNERSHIP_MISMATCH: "
                            f"user={uid}, wallet={wid}"
                        )

                    w = wallet_by_id[wid]

                    if w["wallet_status"] != "ACTIVE":
                        raise UnsupportedP0Rule(
                            f"WALLET_NOT_ACTIVE: "
                            f"user={uid}, wallet={wid}"
                        )

                    for col in (
                        "charge_won",
                        "cashback_won",
                        "policy_support_won",
                    ):
                        if w[col] < 0:
                            raise ValueError(
                                f"NEGATIVE_WALLET_BALANCE: "
                                f"wallet={wid}, column={col}"
                            )


                cards = []
                credit_used = {}
                benefit_used = {}

                for c in user_cards:
                    if c["linked_account_id"] is not None:
                        if c["linked_account_id"] not in accounts:
                            raise ValueError(
                                f"Account ownership mismatch: "
                                f"{c['user_card_id']}"
                            )

                    type_map = {
                        "BANK_CREDIT": CardType.CREDIT,
                        "BANK_CHECK": CardType.DEBIT,
                        "DONGBAEK_CHECK": CardType.DONGBAEK_CHECK,
                    }

                    if c["card_type"] not in type_map:
                        raise UnsupportedP0Rule(
                            f"Unsupported card type: {c['card_type']}"
                        )

                    is_db = (
                        c["card_type"] == "DONGBAEK_CHECK"
                    )

                    if is_db and c["db_wallet_id"] is None:
                        raise ValueError(
                            f"Dongbaek wallet missing: "
                            f"{c['user_card_id']}"
                        )

                    if not is_db and c["db_wallet_id"] is not None:
                        raise ValueError(
                            f"Non-Dongbaek card has DB wallet: "
                            f"{c['user_card_id']}"
                        )

                    if c["card_type"] == "BANK_CHECK":
                        if not c["linked_account_id"]:
                            raise ValueError(
                                f"Bank check account missing: "
                                f"{c['user_card_id']}"
                            )

                    if c["card_status"] not in (
                        "ACTIVE", "LOST", "FROZEN", "EXPIRED"
                    ):
                        raise ValueError(
                            f"Unknown card status: {c['card_status']}"
                        )

                    rules, prev_perf = load_rules(
                        c["product_id"],
                        c["user_card_id"],
                        None,
                    )

                    for rule in rules:
                        prev = db.execute(
                            """
                            SELECT benefit_used_won
                            FROM CARD_PERF_MONTH_CLOSE
                            WHERE user_card_id = ?
                              AND base_month = ?
                              AND rule_id = ?
                            """,
                            (
                                c["user_card_id"],
                                day[:7],
                                rule.id.split(":", 1)[1],
                            ),
                        ).fetchone()

                        if prev and prev["benefit_used_won"]:
                            raise UnsupportedP0Rule(
                                "Current-month close cannot "
                                "initialize live benefit usage"
                            )

                    close = db.execute(
                        """
                        SELECT credit_used_won
                        FROM CARD_MONTH_CLOSE
                        WHERE user_card_id = ?
                          AND base_month = ?
                        """,
                        (c["user_card_id"], previous_month),
                    ).fetchone()

                    if close is not None:
                        credit_used[c["user_card_id"]] = (
                            close["credit_used_won"]
                        )

                    cards.append(
                        Card(
                            id=c["user_card_id"],
                            type=type_map[c["card_type"]],
                            account_id=c["linked_account_id"],
                            wallet_id=c["db_wallet_id"],
                            credit_limit=c["credit_limit_won"] or 0,
                            active=(c["card_status"] == "ACTIVE"),
                            lost=(c["card_status"] == "LOST"),
                            expired=(
                                c["card_status"] == "EXPIRED"
                            ),
                            prev_month_perf=prev_perf,
                            rules=tuple(rules),
                            
                        )
                    )

                # P0-10: USER_CATEGORY_PRIORITY 로딩
                category_priorities = {}

                active_card_ids = {
                    c.id for c in cards if c.active
                    and not c.lost and not c.expired
                }

                priority_rows = db.execute(
                    """
                    SELECT
                        user_category_code,
                        user_card_id,
                        priority_group
                    FROM USER_CATEGORY_PRIORITY
                    WHERE user_id = ?
                      AND (valid_from IS NULL OR valid_from <= ?)
                      AND (valid_to IS NULL OR ? < valid_to)
                    ORDER BY
                        user_category_code,
                        priority_group,
                        user_card_id
                    """,
                    (uid, day, day),
                ).fetchall()

                for row in priority_rows:
                    category_code = row["user_category_code"]
                    card_id = row["user_card_id"]
                    rank = row["priority_group"]

                    if card_id not in active_card_ids:
                        raise ValueError(
                            "PRIORITY_CARD_NOT_ACTIVE_OR_NOT_OWNED: "
                            f"{uid}/{card_id}"
                        )

                    category_cards = (
                        category_priorities.setdefault(
                            category_code, {}
                        )
                    )

                    if card_id in category_cards:
                        raise ValueError(
                            "DUPLICATE_ACTIVE_PRIORITY: "
                            f"{uid}/{category_code}/{card_id}"
                        )

                    category_cards[card_id] = rank

                users[uid] = (
                    cards,
                    State(
                        accounts=accounts,
                        wallets={
                            wid: WalletBalance(
                                charge=wallet_by_id[wid]["charge_won"],
                                cashback=wallet_by_id[wid]["cashback_won"],
                                grant=wallet_by_id[wid]["policy_support_won"],
                            )
                            for wid in sorted(wallet_ids)
                        },
                        credit_used=credit_used,
                        benefit_used=benefit_used,
                        category_priorities=category_priorities,
                    ),
                )

        return merchants, users, policy
