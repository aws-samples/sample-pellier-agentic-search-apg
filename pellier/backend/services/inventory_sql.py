"""The bounded SQL contract used by Stock Keeper's inventory tool."""


def warehouse_inventory_query(product_id: str) -> tuple[str, tuple[str]]:
    """Return a parameterized query and its arguments for one product.

    Join warehouse_inventory (wi) to warehouses (w).
    Return warehouse_id, warehouse_name, city, ship_window_min,
    ship_window_max, and quantity. Keep warehouses with zero stock.
    Bind product_id as a value; never insert it into the SQL string.
    """
    # === WORKSHOP: warehouse inventory SQL: START ===
    query = """
        SELECT w.id AS warehouse_id,
               w.display_name AS warehouse_name,
               w.city,
               w.ship_window_min,
               w.ship_window_max,
               wi.quantity
        FROM pellier.warehouse_inventory wi
        JOIN pellier.warehouses w ON w.id = wi.warehouse_id
        WHERE wi.product_id = %s
        ORDER BY wi.quantity DESC, w.id ASC
    """
    return query, (product_id,)
    # === WORKSHOP: warehouse inventory SQL: END ===
