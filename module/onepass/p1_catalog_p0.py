
# onepass/p1_catalog_p0.py

"""Normalize the six selected BNK card products' benefit rows.

Input:
    CSV export of 02_혜택상세 from the team's card workbook.

This is a contract/catalog layer, NOT the P1 benefit calculator.
Unknown or complex conditions are not silently treated as supported.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path


SELECTED_PRODUCTS = {
    "P07": "딩딩 신용카드",
    "P09": "팟 신용카드",
    "P10": "SK OIL&LPG 신용카드",
    "P16": "ZipL 신용카드",
    "P19": "빵빵 체크카드",
    "P23": "어디로든 그린체크카드",
}

EXPECTED_RULE_COUNTS = {
    "P07": 10,
    "P09": 10,
    "P10": 7,
    "P16": 8,
    "P19": 6,
    "P23": 7,
}

REQUIRED_COLUMNS = {
    "product_id",
    "benefit_seq",
    "benefit_target_original",
    "benefit_target_kind",
    "benefit_type",
    "benefit_value",
}

OPTIONAL_CONDITION_COLUMNS = (
    "min_payment",
    "per_tx_cap",
    "monthly_count_cap",
    "monthly_benefit_cap",
    "perf_tier_note",
    "day_condition",
    "channel_condition",
    "perf_exclusions",
    "other_conditions",
    "source_page",
    "read_confidence",
    "note",
)


class CatalogValidationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedBenefit:
    rule_id: str
    product_id: str
    product_name: str
    benefit_seq: int
    target_original: str
    target_kind: str
    benefit_type_original: str
    benefit_value_original: str

    calculation_kind: str
    rate: Decimal | None
    fixed_won: int | None

    conditions: tuple[tuple[str, str], ...]
    supported_lanes: tuple[str, ...]
    classification: str

    def condition(self, name: str) -> str:
        return dict(self.conditions).get(name, "")


def classify_calculation(
    benefit_type: str,
    benefit_value: str,
) -> tuple[str, Decimal | None, int | None]:
    raw_type = benefit_type.strip()
    raw_value = benefit_value.strip()

    if "리터당" in raw_type or "리터당" in raw_value:
        return ("PER_LITER", None, None)

    if "포인트" in raw_type or "적립" in raw_type:
        match = re.fullmatch(
            r"(?:기본\s*)?([0-9]+(?:\.[0-9]+)?)%"
            r"\s*(?:적립)?",
            raw_value,
        )
        if match:
            return (
                "POINT_RATE",
                Decimal(match.group(1)) / 100,
                None,
            )
        return ("POINT_COMPLEX", None, None)

    match = re.fullmatch(
        r"(?:기본\s*|추가\s*)?"
        r"([0-9]+(?:\.[0-9]+)?)%"
        r"\s*(?:할인|캐시백)?",
        raw_value,
    )

    if match:
        try:
            return (
                "RATE",
                Decimal(match.group(1)) / 100,
                None,
            )
        except InvalidOperation:
            pass

    fixed = re.fullmatch(
        r"([0-9][0-9,]*)\s*원",
        raw_value,
    )

    if fixed:
        return (
            "FIXED",
            None,
            int(fixed.group(1).replace(",", "")),
        )

    return ("COMPLEX_OR_UNKNOWN", None, None)


def infer_lanes(
    target_kind: str,
    channel_condition: str,
    other_conditions: str,
) -> tuple[str, ...]:
    """Conservative lane hints, not verified payment eligibility.

    When a condition is ambiguous, leave all lanes as potential
    and mark the rule pending. A calculator must not use these
    hints as proof that a benefit is eligible.
    """
    text = (
        channel_condition + " " + other_conditions
    ).lower()

    if "간편결제" in target_kind or (
        target_kind == "결제채널"
    ):
        return ("SIMPLE_PAY",)

    if "자동납부시에만" in text or (
        "자동이체" in text
    ):
        return ("ONLINE",)

    if (
        "현장결제시에만" in text
        or "현장결제만" in text
        or "현장할인" in text
    ):
        return ("OFFLINE",)

    if (
        "공식 홈페이지" in text
        or "공식홈페이지" in text
        or "인터넷쇼핑" in text
    ):
        return ("ONLINE",)

    return ("OFFLINE", "ONLINE", "SIMPLE_PAY")


def classify_support(
    calculation_kind: str,
    conditions: dict[str, str],
    target_kind: str,
) -> str:
    """Assign review status, not actual P0 engine support."""
    if calculation_kind in {
        "PER_LITER",
        "POINT_RATE",
        "POINT_COMPLEX",
        "COMPLEX_OR_UNKNOWN",
    }:
        return "P1_COMPLEX"

    if target_kind in {
        "브랜드", "결제채널", "기타", "전가맹점"
    }:
        return "P1_CONDITIONAL"

    complex_columns = (
        "monthly_count_cap",
        "perf_tier_note",
        "channel_condition",
        "other_conditions",
        "perf_exclusions",
    )

    if any(
        conditions.get(col, "").strip()
        for col in complex_columns
    ):
        return "P1_CONDITIONAL"

    return "P0_RULE_SHAPE_CANDIDATE"


def normalize_benefit_row(row: dict) -> NormalizedBenefit:
    product_id = str(row.get("product_id") or "").strip()

    if product_id not in SELECTED_PRODUCTS:
        raise CatalogValidationError(
            "UNKNOWN_SELECTED_PRODUCT"
        )

    try:
        seq = int(str(row["benefit_seq"]).strip())
    except (ValueError, TypeError) as exc:
        raise CatalogValidationError(
            "INVALID_BENEFIT_SEQ"
        ) from exc

    if seq < 1:
        raise CatalogValidationError(
            "INVALID_BENEFIT_SEQ"
        )

    target = str(
        row.get("benefit_target_original") or ""
    ).strip()
    kind = str(
        row.get("benefit_target_kind") or ""
    ).strip()
    benefit_type = str(
        row.get("benefit_type") or ""
    ).strip()
    value = str(
        row.get("benefit_value") or ""
    ).strip()

    if not target or not kind or not value:
        raise CatalogValidationError(
            "REQUIRED_BENEFIT_CONTENT_MISSING"
        )

    conditions = {
        column: str(row.get(column) or "").strip()
        for column in OPTIONAL_CONDITION_COLUMNS
    }

    calc_kind, rate, fixed_won = classify_calculation(
        benefit_type, value
    )

    return NormalizedBenefit(
        rule_id=f"{product_id}_R{seq:02d}",
        product_id=product_id,
        product_name=SELECTED_PRODUCTS[product_id],
        benefit_seq=seq,
        target_original=target,
        target_kind=kind,
        benefit_type_original=benefit_type,
        benefit_value_original=value,
        calculation_kind=calc_kind,
        rate=rate,
        fixed_won=fixed_won,
        conditions=tuple(conditions.items()),
        supported_lanes=infer_lanes(
            kind,
            conditions["channel_condition"],
            conditions["other_conditions"],
        ),
        classification=classify_support(
            calc_kind, conditions, kind
        ),
    )


def load_benefit_catalog(
    csv_path: str | Path,
    *,
    require_complete: bool = True,
) -> list[NormalizedBenefit]:
    with Path(csv_path).open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        headers = set(reader.fieldnames or [])

        if not REQUIRED_COLUMNS.issubset(headers):
            missing = sorted(REQUIRED_COLUMNS - headers)
            raise CatalogValidationError(
                f"MISSING_COLUMNS: {missing}"
            )

        results = []
        seen = set()

        for row in reader:
            product_id = str(
                row.get("product_id") or ""
            ).strip()

            # The source workbook includes other products.
            if product_id not in SELECTED_PRODUCTS:
                continue

            benefit = normalize_benefit_row(row)

            if benefit.rule_id in seen:
                raise CatalogValidationError(
                    f"DUPLICATE_RULE: {benefit.rule_id}"
                )

            seen.add(benefit.rule_id)
            results.append(benefit)

    results.sort(
        key=lambda x: (x.product_id, x.benefit_seq)
    )

    if require_complete:
        for product_id, expected in (
            EXPECTED_RULE_COUNTS.items()
        ):
            actual = sum(
                item.product_id == product_id
                for item in results
            )

            if actual != expected:
                raise CatalogValidationError(
                    f"INCOMPLETE_PRODUCT: {product_id} "
                    f"expected={expected} actual={actual}"
                )

        if len(results) != 48:
            raise CatalogValidationError(
                "EXPECTED_48_BENEFIT_ROWS"
            )

    return results
