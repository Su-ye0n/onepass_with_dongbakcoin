
# check_p1_three_lanes.py

from collections import Counter

from onepass.p1_payment_p0 import (
    PaymentContext,
    PaymentLane,
    SalesChannel,
    PaymentProvider,
)
from onepass.p1_eligibility_repository import (
    P1EligibilityRepository,
)
from onepass.p1_monthly_db_repository import connect_db


def get_rules():
    """현재 DB의 카드 6종에 속하는 혜택 규칙 조회."""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                """
                SELECT br.rule_id, br.product_id,
                       br.source_status
                FROM public.benefit_rule br
                WHERE br.product_id IN (
                    'BNK_CR_P07', 'BNK_CR_P09',
                    'BNK_CR_P10', 'BNK_CR_P16',
                    'BNK_CK_P19', 'BNK_CK_P23'
                )
                ORDER BY br.product_id, br.rule_id
                """
            )
            return cur.fetchall()


def main():
    repo = P1EligibilityRepository()
    rules = get_rules()

    cases = [
        (
            "OFFLINE",
            PaymentContext(
                lane=PaymentLane.OFFLINE,
                sales_channel=SalesChannel.OFFLINE,
            ),
        ),
        (
            "ONLINE",
            PaymentContext(
                lane=PaymentLane.ONLINE,
                sales_channel=SalesChannel.ONLINE,
            ),
        ),
        (
            "SIMPLE_PAY / NAVERPAY",
            PaymentContext(
                lane=PaymentLane.SIMPLE_PAY,
                sales_channel=SalesChannel.ONLINE,
                payment_provider=PaymentProvider.NAVERPAY,
            ),
        ),
        (
            "SIMPLE_PAY / KAKAOPAY",
            PaymentContext(
                lane=PaymentLane.SIMPLE_PAY,
                sales_channel=SalesChannel.ONLINE,
                payment_provider=PaymentProvider.KAKAOPAY,
            ),
        ),
        (
            "SIMPLE_PAY / SAMSUNGPAY",
            PaymentContext(
                lane=PaymentLane.SIMPLE_PAY,
                sales_channel=SalesChannel.OFFLINE,
                payment_provider=PaymentProvider.SAMSUNGPAY,
            ),
        ),
    ]

    merchant_id = "M00336"
    as_of = "2026-10-29"

    print("DB RULE COUNT:", len(rules))
    print("MERCHANT:", merchant_id)

    for lane_name, payment in cases:
        print(f"\n=== {lane_name} ===")
        counts = Counter()

        for rule_id, product_id, source_status in rules:
            result = repo.evaluate(
                rule_id=rule_id,
                merchant_id=merchant_id,
                payment=payment,
                as_of=as_of,
            )

            counts[result.status] += 1

            if result.status == "ELIGIBLE":
                print(
                    product_id,
                    rule_id,
                    result.status,
                    f"source={source_status}",
                )

        print("SUMMARY:", dict(counts))
        print(
            "NOTE: ELIGIBLE means target/channel match, "
            "not approved cash benefit."
        )


if __name__ == "__main__":
    main()
