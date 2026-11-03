
# check_p1_card_lanes.py

"""Inspect P1 payment-lane decisions using NeonDB card data."""

from collections import Counter

from onepass.p1_card_repository import P1CardRepository
from onepass.p1_lane_evaluator import evaluate_card_lanes
from onepass.p1_payment_p0 import PaymentContext


def main():
    repo = P1CardRepository()

    card = repo.get_card("P09")

    if card is None:
        raise RuntimeError("P09_CARD_NOT_FOUND")

    scenarios = {
        "OFFLINE": PaymentContext(
            "OFFLINE",
            "OFFLINE",
        ),
        "ONLINE": PaymentContext(
            "ONLINE",
            "ONLINE",
        ),
        "NAVERPAY_ONLINE": PaymentContext(
            "SIMPLE_PAY",
            "ONLINE",
            "NAVERPAY",
        ),
        "KAKAOPAY_OFFLINE": PaymentContext(
            "SIMPLE_PAY",
            "OFFLINE",
            "KAKAOPAY",
        ),
    }

    print("Card:", card["product_name"])
    print("Benefit rows:", len(card["benefits"]))

    for name, payment in scenarios.items():
        results = evaluate_card_lanes(
            card, payment
        )

        counts = Counter(
            result.decision for result in results
        )

        print(f"\n[{name}]")
        print("Decisions:", dict(counts))

        first = next(
            x for x in results
            if x.rule_id == "P09_R01"
        )

        print("P09_R01:", first.decision)
        print("Reason:", first.reason)


if __name__ == "__main__":
    main()
