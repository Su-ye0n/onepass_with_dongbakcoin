LEGACY_TO_CANONICAL = {
    "P07": "BNK_CR_P07",
    "P09": "BNK_CR_P09",
    "P10": "BNK_CR_P10",
    "P16": "BNK_CR_P16",
    "P19": "BNK_CK_P19",
    "P23": "BNK_CK_P23",
}

CANONICAL_TO_LEGACY = {
    new: old
    for old, new in LEGACY_TO_CANONICAL.items()
}

SELECTED_PRODUCT_IDS = frozenset(
    LEGACY_TO_CANONICAL.values()
)


def canonical_product_id(product_id: str) -> str:
    """기존 상품 ID를 표준 상품 ID로 변환함."""
    if product_id in LEGACY_TO_CANONICAL:
        return LEGACY_TO_CANONICAL[product_id]

    if product_id in SELECTED_PRODUCT_IDS:
        return product_id

    raise ValueError(
        f"UNSUPPORTED_PRODUCT_ID: {product_id}"
    )


def legacy_product_id(product_id: str) -> str:
    """표준 상품 ID를 기존 원문 자료 ID로 변환함."""
    canonical = canonical_product_id(product_id)
    return CANONICAL_TO_LEGACY[canonical]
