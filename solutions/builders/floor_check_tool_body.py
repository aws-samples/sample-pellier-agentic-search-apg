# Paste inside floor_check() in pellier/backend/services/agent_tools.py
# (replace the WORKSHOP_EXERCISE_STUB return block).

    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        from services.business_logic import BusinessLogic

        logic = BusinessLogic(_db_service)
        result = _run_async(logic.floor_check())
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
