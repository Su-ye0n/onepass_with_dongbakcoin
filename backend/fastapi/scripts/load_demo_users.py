import argparse
import csv
import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "demo_users.csv"
CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "demo_user_cards.csv"
PAYMENTS_FILE = Path(__file__).resolve().parents[1] / "data" / "demo_payments.csv"


def _date_value(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _demo_card_values(card: dict[str, str], source_ref: str) -> dict:
    return {
        "user_card_id": card["user_card_id"],
        "user_id": card["user_id"],
        "product_id": card["product_id"],
        "card_status": card["card_status"],
        "credit_limit_won": (
            int(card["credit_limit_won"]) if card["credit_limit_won"] else None
        ),
        "default_preference_rank": int(card["default_preference_rank"]),
        "expires_at": card["expires_at"] or None,
        "active_from": card["active_from"] or None,
        "registered_ref": source_ref,
    }


def load_demo_users(apply: bool, allow_remote: bool = False) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set.")

    parsed_url = make_url(database_url)
    is_local = (
        parsed_url.get_backend_name() == "sqlite"
        or parsed_url.host in {"localhost", "127.0.0.1", "::1"}
    )
    if not is_local and not allow_remote:
        raise RuntimeError("Demo seed loading is restricted to a local database.")
    if not apply:
        raise RuntimeError("Pass --apply to import the synthetic demo CSV.")

    with DATA_FILE.open(encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))
    if not rows:
        raise RuntimeError("The demo CSV contains no users.")
    with CARDS_FILE.open(encoding="utf-8-sig", newline="") as csv_file:
        card_rows = list(csv.DictReader(csv_file))
    if not card_rows:
        raise RuntimeError("The demo card CSV contains no cards.")
    with PAYMENTS_FILE.open(encoding="utf-8-sig", newline="") as csv_file:
        payment_rows = list(csv.DictReader(csv_file))

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            for row in rows:
                connection.execute(
                    text(
                        """
                        INSERT INTO "user" (
                            user_id, user_type, origin_type, user_status
                        ) VALUES (
                            :user_id, :user_type, :origin_type, :user_status
                        )
                        ON CONFLICT (user_id) DO NOTHING
                        """
                    ),
                    {
                        "user_id": row["user_id"],
                        "user_type": row["user_type"],
                        "origin_type": row["origin_type"],
                        "user_status": row["user_status"],
                    },
                )
                existing_user = connection.execute(
                    text(
                        """
                        SELECT user_type, origin_type
                        FROM "user"
                        WHERE user_id = :user_id
                        """
                    ),
                    {"user_id": row["user_id"]},
                ).one_or_none()
                if (
                    existing_user is None
                    or existing_user.user_type != "SYNTHETIC"
                    or existing_user.origin_type != "SYNTHETIC"
                ):
                    raise RuntimeError(
                        "Demo user ID conflicts with a non-synthetic user."
                    )

                connection.execute(
                    text(
                        """
                        INSERT INTO db_wallet (
                            wallet_id, user_id, charge_won, cashback_won,
                            policy_support_won, wallet_status, origin_type
                        ) VALUES (
                            :wallet_id, :user_id, :charge_won, :cashback_won,
                            :policy_support_won, 'ACTIVE', 'SYNTHETIC'
                        )
                        ON CONFLICT (wallet_id) DO NOTHING
                        """
                    ),
                    {
                        **row,
                        "charge_won": int(row["charge_won"]),
                        "cashback_won": int(row["cashback_won"]),
                        "policy_support_won": int(row["policy_support_won"]),
                    },
                )
                wallet_owner = connection.execute(
                    text(
                        """
                        SELECT user_id
                        FROM db_wallet
                        WHERE wallet_id = :wallet_id
                        """
                    ),
                    {"wallet_id": row["wallet_id"]},
                ).scalar_one_or_none()
                if wallet_owner != row["user_id"]:
                    raise RuntimeError(
                        "Demo wallet ID is already assigned to another user."
                    )

                connection.execute(
                    text(
                        """
                        INSERT INTO user_profile (
                            user_id, display_name, student_card_id, phone_number,
                            address, university, department, source_mode
                        ) VALUES (
                            :user_id, :display_name, :student_card_id, :phone_number,
                            :address, :university, :department, 'SYNTHETIC'
                        )
                        ON CONFLICT (user_id) DO NOTHING
                        """
                    ),
                    row,
                )
                for card in card_rows:
                    if card["user_id"] != row["user_id"]:
                        continue

                    source_user = connection.execute(
                        text(
                            """
                            SELECT user_type, origin_type
                            FROM "user"
                            WHERE user_id = :source_user_id
                            """
                        ),
                        {"source_user_id": card["source_user_id"]},
                    ).one_or_none()
                    if (
                        source_user is None
                        or source_user.user_type != "SYNTHETIC"
                        or source_user.origin_type != "SYNTHETIC"
                    ):
                        raise RuntimeError(
                            "Demo card source must be an existing synthetic user."
                        )

                    source_card = connection.execute(
                        text(
                            """
                            SELECT product_id, card_status, credit_limit_won,
                                   default_preference_rank, expires_at, active_from
                            FROM user_card
                            WHERE user_card_id = :source_user_card_id
                              AND user_id = :source_user_id
                            """
                        ),
                        {
                            "source_user_card_id": card["source_user_card_id"],
                            "source_user_id": card["source_user_id"],
                        },
                    ).one_or_none()
                    expected_source_card = (
                        card["product_id"],
                        card["card_status"],
                        int(card["credit_limit_won"])
                        if card["credit_limit_won"]
                        else None,
                        int(card["default_preference_rank"]),
                        card["expires_at"] or None,
                        card["active_from"] or None,
                    )
                    actual_source_card = (
                        source_card.product_id,
                        source_card.card_status,
                        source_card.credit_limit_won,
                        source_card.default_preference_rank,
                        _date_value(source_card.expires_at),
                        _date_value(source_card.active_from),
                    ) if source_card is not None else None
                    if actual_source_card != expected_source_card:
                        raise RuntimeError(
                            "Demo card snapshot no longer matches its source card."
                        )

                    product_exists = connection.execute(
                        text(
                            """
                            SELECT product_id
                            FROM card_product
                            WHERE product_id = :product_id
                            """
                        ),
                        {"product_id": card["product_id"]},
                    ).scalar_one_or_none()
                    if product_exists is None:
                        raise RuntimeError(
                            "Demo card product ID is not present in the database."
                        )

                    source_ref = (
                        f"SYNTHETIC_DEMO_FROM_{card['source_user_id']}:"
                        f"{card['source_user_card_id']}"
                    )
                    connection.execute(
                        text(
                            """
                            INSERT INTO user_card (
                                user_card_id, user_id, product_id, card_status,
                                credit_limit_won, default_preference_rank,
                                expires_at, active_from, registered_ref
                            ) VALUES (
                                :user_card_id, :user_id, :product_id, :card_status,
                                :credit_limit_won, :default_preference_rank,
                                :expires_at, :active_from, :registered_ref
                            )
                            ON CONFLICT (user_card_id) DO NOTHING
                            """
                        ),
                        {
                            "user_card_id": card["user_card_id"],
                            "user_id": card["user_id"],
                            "product_id": card["product_id"],
                            "card_status": card["card_status"],
                            "credit_limit_won": (
                                int(card["credit_limit_won"])
                                if card["credit_limit_won"]
                                else None
                            ),
                            "default_preference_rank": int(
                                card["default_preference_rank"]
                            ),
                            "expires_at": card["expires_at"] or None,
                            "active_from": card["active_from"] or None,
                            "registered_ref": source_ref,
                        },
                    )
                    existing_card = connection.execute(
                        text(
                            """
                            SELECT user_id, product_id, card_status,
                                   credit_limit_won, default_preference_rank,
                                   expires_at, active_from, registered_ref
                            FROM user_card
                            WHERE user_card_id = :user_card_id
                            """
                        ),
                        {"user_card_id": card["user_card_id"]},
                    ).one_or_none()
                    expected_demo_card = (
                        card["user_id"],
                        card["product_id"],
                        card["card_status"],
                        int(card["credit_limit_won"])
                        if card["credit_limit_won"]
                        else None,
                        int(card["default_preference_rank"]),
                        card["expires_at"] or None,
                        card["active_from"] or None,
                        source_ref,
                    )
                    actual_demo_card = (
                        (
                            existing_card.user_id,
                            existing_card.product_id,
                            existing_card.card_status,
                            existing_card.credit_limit_won,
                            existing_card.default_preference_rank,
                            _date_value(existing_card.expires_at),
                            _date_value(existing_card.active_from),
                            existing_card.registered_ref,
                        )
                        if existing_card is not None
                        else None
                    )
                    if actual_demo_card != expected_demo_card:
                        if (
                            existing_card is None
                            or existing_card.user_id != card["user_id"]
                            or existing_card.registered_ref not in {
                                "SYNTHETIC_DEMO",
                                source_ref,
                            }
                        ):
                            raise RuntimeError(
                                "Demo card ID conflicts with non-demo card data."
                            )
                        connection.execute(
                            text(
                                """
                                UPDATE user_card
                                SET product_id = :product_id,
                                    card_status = :card_status,
                                    credit_limit_won = :credit_limit_won,
                                    default_preference_rank = :default_preference_rank,
                                    expires_at = :expires_at,
                                    active_from = :active_from,
                                    registered_ref = :registered_ref
                                WHERE user_card_id = :user_card_id
                                  AND user_id = :user_id
                                  AND registered_ref IN ('SYNTHETIC_DEMO', :registered_ref)
                                """
                            ),
                            _demo_card_values(card, source_ref),
                        )

                demo_card_ids = {
                    card["user_card_id"]
                    for card in card_rows
                    if card["user_id"] == row["user_id"]
                }
                for payment in payment_rows:
                    if payment["user_id"] != row["user_id"]:
                        continue
                    if payment["user_card_id"] not in demo_card_ids:
                        raise RuntimeError(
                            "Demo payment refers to a card not assigned to its user."
                        )

                    merchant_exists = connection.execute(
                        text(
                            """
                            SELECT merchant_id
                            FROM merchant
                            WHERE merchant_id = :merchant_id
                            """
                        ),
                        {"merchant_id": payment["merchant_id"]},
                    ).scalar_one_or_none()
                    if merchant_exists is None:
                        raise RuntimeError(
                            "Demo payment merchant ID is not present in the database."
                        )

                    amount = int(payment["amount_won"])
                    existing_payment = connection.execute(
                        text(
                            """
                            SELECT user_id, user_card_id, merchant_id,
                                   gross_purchase_won
                            FROM ledger
                            WHERE request_id = :request_id
                              AND event_type = 'PAYMENT'
                            """
                        ),
                        {"request_id": payment["request_id"]},
                    ).one_or_none()
                    expected_payment = (
                        payment["user_id"],
                        payment["user_card_id"],
                        payment["merchant_id"],
                        amount,
                    )
                    if existing_payment is not None:
                        if tuple(existing_payment) != expected_payment:
                            raise RuntimeError(
                                "Demo payment request ID conflicts with existing data."
                            )
                        continue

                    connection.execute(
                        text(
                            """
                            INSERT INTO ledger (
                                tx_id, request_id, user_id, user_card_id,
                                merchant_id, event_at, event_seq, event_type,
                                bucket_type, delta_won, gross_purchase_won,
                                awarded_benefit_won, approval_status,
                                source_mode, event_note
                            ) VALUES (
                                :tx_id, :request_id, :user_id, :user_card_id,
                                :merchant_id, :event_at, 1, 'PAYMENT', 'NONE',
                                :delta_won, :gross_purchase_won, 0,
                                'APPROVED', 'MOCK',
                                'Synthetic demo payment; no real payment was processed.'
                            )
                            """
                        ),
                        {
                            "tx_id": f"DEMO_TX_{payment['request_id']}",
                            "request_id": payment["request_id"],
                            "user_id": payment["user_id"],
                            "user_card_id": payment["user_card_id"],
                            "merchant_id": payment["merchant_id"],
                            "event_at": datetime.now()
                            - timedelta(days=int(payment["days_ago"])),
                            "delta_won": -amount,
                            "gross_purchase_won": amount,
                        },
                    )
    finally:
        engine.dispose()

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load only synthetic demo users into a local database."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the CSV to the configured database.",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Explicitly allow the synthetic seed to be applied to a remote database.",
    )
    args = parser.parse_args()
    count = load_demo_users(args.apply, args.allow_remote)
    print(f"Loaded {count} synthetic demo user(s).")


if __name__ == "__main__":
    main()
