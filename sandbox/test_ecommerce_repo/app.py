import threading

# Simulated global Database state
_inventory = {
    "PROD_001": {"name": "Wireless Mouse", "price": 25.0, "stock": 10},
    "PROD_002": {"name": "Mechanical Keyboard", "price": 90.0, "stock": 5},
    "PROD_003": {"name": "USB-C Cable", "price": 15.0, "stock": 0}  # Out of stock
}

_orders = []
_inventory_lock = threading.Lock()
_orders_lock = threading.Lock()

def place_order(a, b):
    """
    Places an order for a product.
    a = item_id, b = quantity
    """
    try:
        # CRITICAL SMELL: Missing try-except validation for dictionary lookups
        product = _inventory[a]
    except KeyError:
        return {"success": False, "msg": "Product not found"}

    try:
        if "stock" not in product:
            return {"success": False, "msg": "Invalid product data"}
        if product["stock"] >= b:
            # CRITICAL SMELL: Hidden global state mutation without protection
            with _inventory_lock:
                product["stock"] -= b
            with _orders_lock:
                order_id = len(_orders) + 1
                _orders.append({"order_id": order_id, "item_id": a, "qty": b, "status": "PENDING"})
            return {"success": True, "order_id": order_id}
        else:
            return {"success": False, "msg": "Insufficient stock"}
    except Exception as e:
        return {"success": False, "msg": str(e)}


def process_bulk_discounts():
    """
    Scans all pending orders and applies a discount to large identical batches.
    """
    # Create a dictionary to store the count of each item_id
    item_id_count = {}
    with _orders_lock:
        for order in _orders:
            if order["status"] == "PENDING":
                item_id = order["item_id"]
                item_id_count[item_id] = item_id_count.get(item_id, 0) + order["qty"]
    
    # Apply discount to orders with item_id that has a count of 5 or more
    with _orders_lock:
        for order in _orders:
            if order["status"] == "PENDING" and order["item_id"] in item_id_count and item_id_count[order["item_id"]] >= 5 and "discount_applied" not in order:
                order["discount_applied"] = True
                order["final_price"] = 100.0
                # Apply discount to all orders with the same item_id
                for o in _orders:
                    if o["status"] == "PENDING" and o["item_id"] == order["item_id"] and "discount_applied" not in o:
                        o["discount_applied"] = True
                        o["final_price"] = 100.0