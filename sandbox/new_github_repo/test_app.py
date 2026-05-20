import pytest
import importlib
import app

# Re-import app fresh before each test to reset module-level state
@pytest.fixture(autouse=True)
def reset_state():
    app._inventory.clear()
    app._orders.clear()
    yield


# ── add_item ──────────────────────────────────────────────────────────────────

def test_add_item_success():
    item = app.add_item("SKU-1", "Widget", 9.99, 100)
    assert item["name"] == "Widget"
    assert item["price"] == 9.99
    assert item["stock"] == 100


def test_add_item_rejects_negative_price():
    with pytest.raises(ValueError):
        app.add_item("SKU-2", "Gadget", -1.0, 50)


# ── place_order ───────────────────────────────────────────────────────────────

def test_place_order_reduces_stock():
    app.add_item("SKU-3", "Doohickey", 5.00, 20)
    order = app.place_order("SKU-3", 3)
    assert order["total"] == 15.00
    assert app.get_stock("SKU-3") == 17


def test_place_order_raises_on_insufficient_stock():
    app.add_item("SKU-4", "Thingamajig", 2.50, 2)
    with pytest.raises(ValueError, match="Insufficient stock"):
        app.place_order("SKU-4", 10)


# ── apply_bulk_discount ───────────────────────────────────────────────────────

def test_apply_bulk_discount_marks_ordered_items():
    """Items that appear in the orders list should receive a discount."""
    app.add_item("SKU-5", "Alpha", 10.0, 50)
    app.add_item("SKU-6", "Beta", 20.0, 50)
    app.place_order("SKU-5", 1)

    results = app.apply_bulk_discount(["SKU-5", "SKU-6"], app._orders)

    discounted = {r["item_id"]: r["discount_applied"] for r in results}
    assert discounted["SKU-5"] is True
    assert discounted["SKU-6"] is False


def test_apply_bulk_discount_no_duplicate_entries():
    """Each item_id must appear exactly once in the result, even with multiple orders."""
    app.add_item("SKU-7", "Gamma", 5.0, 100)
    app.place_order("SKU-7", 1)
    app.place_order("SKU-7", 2)   # second order for same item

    results = app.apply_bulk_discount(["SKU-7"], app._orders)

    # Bug in original: returns one entry per matching order pair — should be exactly 1
    assert len(results) == 1


# ── cancel_order ──────────────────────────────────────────────────────────────

def test_cancel_order_restores_stock():
    app.add_item("SKU-8", "Delta", 3.0, 10)
    app.place_order("SKU-8", 4)
    result = app.cancel_order("SKU-8", 4)
    assert result["quantity_restored"] == 4
    assert app.get_stock("SKU-8") == 10


def test_cancel_order_raises_on_unknown_item():
    with pytest.raises(KeyError):
        app.cancel_order("NONEXISTENT", 1)
