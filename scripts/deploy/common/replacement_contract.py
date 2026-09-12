"""Pure schema shared by Gateway publication and its replacement target."""
REPLACEMENT_TOOL = {
    "name": "replace_damaged_item",
    "description": (
        "Execute a human-approved damaged-item replacement for an exact order line. "
        "Atomically create the return, reserve stock, and persist fulfillment intent. "
        "Requires an approved review; does not claim an item has shipped."
    ),
    "inputSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "customer_id": {"type": "string"},
            "order_id": {"type": "integer", "minimum": 1},
            "product_id": {"type": "integer", "minimum": 1},
            "quantity": {"type": "integer", "minimum": 1, "maximum": 100},
            "reason": {"type": "string", "enum": ["damaged"]},
            "disposition": {"type": "string", "enum": ["inspection_required"]},
            "review_id": {"type": "integer", "minimum": 1},
            "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        "required": [
            "customer_id", "order_id", "product_id", "quantity", "reason",
            "disposition", "review_id", "idempotency_key",
        ],
    },
}
