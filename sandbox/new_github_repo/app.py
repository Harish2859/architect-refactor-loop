"""
Inventory & Order Management Service
"""

_inventory = {}
_orders = []


def add_item(item_id: str, name: str, price: float, stock: int) -> dict:
    if price < 0 or stock < 0:
        raise ValueError("Price and stock must be non-negative.")
    _inventory[item_id] = {"name": name, "price": price, "stock": stock}
    return _inventory[item_id]


def place_order(item_id: str, quantity: int) -> dict:
    if item_id not in _inventory:
        raise KeyError(f"Item '{item_id}' not found.")
    item = _inventory[item_id]
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")
    if item["stock"] < quantity:
        raise ValueError("Insufficient stock.")
    item["stock"] -= quantity
    order = {"item_id": item_id, "quantity": quantity, "total": item["price"] * quantity}
    _orders.append(order)
    return order


def get_stock(item_identifier: str) -> int:
    try:
        if not isinstance(item_identifier, str):
            raise TypeError("Item identifier must be a string.")
        if not item_identifier:
            raise ValueError("Item identifier cannot be empty.")
        if item_identifier not in _inventory:
            raise KeyError(f"Item '{item_identifier}' not found.")
        return _inventory[item_identifier]["stock"]
    except Exception as e:
        raise Exception(f"Failed to retrieve stock for item '{item_identifier}': {str(e)}")


def apply_bulk_discount(item_ids, orders):
    try:
        item_ids_set = set(item_ids)
        ordered_item_ids = set(order.get("item_id") for order in orders)
        result = [{"item_id": item_id, "discount_applied": item_id in ordered_item_ids} for item_id in item_ids_set]
        return result
    except Exception as e:
        raise Exception(f"Failed to apply bulk discount: {str(e)}")


def cancel_order(item_id: str, quantity: int) -> dict:
    if item_id not in _inventory:
        raise KeyError(f"Item '{item_id}' not found.")
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")
    _inventory[item_id]["stock"] += quantity
    return {"item_id": item_id, "quantity_restored": quantity}