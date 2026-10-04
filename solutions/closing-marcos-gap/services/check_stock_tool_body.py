# Paste inside check_stock(product_query: str) in
# pellier/backend/services/agent_tools.py, replacing the stub return block.

    if not _db_service:
        return _DB_NOT_READY
    try:
        return _reply(store_tools.check_stock(_run_sql, product_query=product_query))
    except Exception as e:
        return json.dumps({"error": str(e)})
