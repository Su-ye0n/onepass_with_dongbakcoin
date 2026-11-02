
# check_p1_db_eligibility.py

from types import SimpleNamespace

from onepass.p1_eligibility_repository import (
    P1EligibilityRepository,
)


def payment(lane, provider=None, sales_channel=None):
    return SimpleNamespace(
        lane=lane,
        provider=provider,
        sales_channel=sales_channel or (
            "OFFLINE" if lane == "OFFLINE"
            else "ONLINE"
        ),
    )


def main():
    repo = P1EligibilityRepository()

    cases = [
        (
            "카페 일반 결제",
            "BR_P07_CAFE",
            "M00336",
            payment("OFFLINE"),
        ),
        (
            "카페 온라인 결제",
            "BR_P07_CAFE",
            "M00336",
            payment("ONLINE"),
        ),
        (
            "특정 가맹점 네이버페이",
            "BR_P09_CAFE",
            "M01388",
            payment("SIMPLE_PAY", "NAVERPAY"),
        ),
        (
            "특정 가맹점 카카오페이",
            "BR_P09_CAFE",
            "M01388",
            payment("SIMPLE_PAY", "KAKAOPAY"),
        ),
    ]

    for name, rule_id, merchant_id, pay in cases:
        r = repo.evaluate(
            rule_id=rule_id,
            merchant_id=merchant_id,
            payment=pay,
            as_of="2026-10-27",
        )

        print(f"\n[{name}]")
        print("rule:", r.rule_id)
        print("merchant:", r.merchant_id)
        print("status:", r.status)
        print("reason:", r.reason)
        print("target:", r.target_status)
        print("channel:", r.channel_status)
        print("source:", r.source_status)
        print("category:", r.std_category)


if __name__ == "__main__":
    main()
