
# tests/test_p1_product_ids.py

import pytest

from onepass.p1_product_ids import (
    LEGACY_TO_CANONICAL,
    SELECTED_PRODUCT_IDS,
    canonical_product_id,
    legacy_product_id,
)


@pytest.mark.parametrize(
    "old_id,new_id",
    list(LEGACY_TO_CANONICAL.items()),
)
def test_legacy_to_canonical(old_id, new_id):
    assert canonical_product_id(old_id) == new_id


@pytest.mark.parametrize(
    "new_id",
    sorted(SELECTED_PRODUCT_IDS),
)
def test_canonical_id_unchanged(new_id):
    assert canonical_product_id(new_id) == new_id


@pytest.mark.parametrize(
    "old_id,new_id",
    list(LEGACY_TO_CANONICAL.items()),
)
def test_reverse_mapping(old_id, new_id):
    assert legacy_product_id(new_id) == old_id


def test_six_products():
    assert len(LEGACY_TO_CANONICAL) == 6
    assert len(SELECTED_PRODUCT_IDS) == 6


def test_unknown_product_rejected():
    with pytest.raises(ValueError):
        canonical_product_id("UNKNOWN")


def test_dongbaek_is_separate():
    with pytest.raises(ValueError):
        canonical_product_id("PRD_DB_SYN")
