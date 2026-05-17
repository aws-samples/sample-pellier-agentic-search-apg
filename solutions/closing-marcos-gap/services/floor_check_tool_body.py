# Paste inside floor_check(product_query: str = "") in
# pellier/backend/services/agent_tools.py, replacing the stub return block.

    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        from services.business_logic import BusinessLogic

        logic = BusinessLogic(_db_service)
        query = (product_query or "").strip() or None
        result = _run_async(logic.floor_check(product_query=query))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
