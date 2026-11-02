# check_p1_db_rules.py

from onepass.p1_rule_repository import (
    P1RuleRepository,
    SELECTED_PRODUCTS,
)


def main():
    repo = P1RuleRepository()
    total = 0

    print("=== P1 Normalized Rules ===")

    for product_id in sorted(SELECTED_PRODUCTS):
        rules = repo.load(
            product_id=product_id,
            as_of="2026-10-26",
        )

        total += len(rules)
        ready = sum(
            result.status == "READY"
            for result in rules
        )

        print(
            f"{product_id}: "
            f"{len(rules)} rules, "
            f"{ready} mapping-ready"
        )

        for item in rules:
            if item.status != "READY":
                print(
                    " ",
                    item.rule.rule_id,
                    item.status,
                    ",".join(item.reasons),
                )

    print("Total normalized rules:", total)


if __name__ == "__main__":
    main()
