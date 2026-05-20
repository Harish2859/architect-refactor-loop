import pytest
from app import _inventory, _orders, place_order, process_bulk_discounts

@pytest.fixture(autouse=True)
def reset_state():
    """Resets global mock database state between test runs."""
    _inventory.clear()
    _inventory.update({
        "PROD_001": {"name": "Wireless Mouse", "price": 25.0, "stock": 10},
        "PROD_002": {"name": "Mechanical Keyboard", "price": 90.0, "stock": 5},
        "PROD_003": {"name": "USB-C Cable", "price": 15.0, "stock": 0}
    })
    _orders.clear()

def test_place_order_success():
    """Verifies happy path deduction of inventory."""
    res = place_order("PROD_001", 2)
    assert res["success"] is True
    assert _inventory["PROD_001"]["stock"] == 8
    assert len(_orders) == 1

def test_place_order_out_of_stock():
    """Verifies out-of-stock validation protection flags false."""
    res = place_order("PROD_003", 1)
    assert res["success"] is False
    assert res["msg"] == "Insufficient stock"

def test_bulk_discount_no_duplicates():
    """
    CONTRACT TEST: Only the first qualifying order per item_id should receive
    a discount. The buggy O(N²) loop applies it to every order for that item,
    failing this assertion deterministically.
    """
    place_order("PROD_001", 5)
    place_order("PROD_001", 5)

    process_bulk_discounts()

    assert len(_orders) == 2
    assert _orders[0]["discount_applied"] is True
    # Only one discount should be issued — the second order must NOT be marked
    assert "discount_applied" not in _orders[1]
