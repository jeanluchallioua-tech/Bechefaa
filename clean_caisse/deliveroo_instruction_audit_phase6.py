"""Read-only inventory of possible Deliveroo kitchen instruction fields.

Candidate field names are diagnostic only: their semantics have not yet been
confirmed against the actual Deliveroo order webhook contract.
"""
CANDIDATE_KEYS = frozenset({
    "notes", "note", "instructions", "special_instructions",
    "customer_note", "customer_notes", "cooking_instructions",
})


def audit_instruction_fields(payload):
    body = payload.get("body") if isinstance(payload, dict) else None
    order = body.get("order") if isinstance(body, dict) else None
    if not isinstance(order, dict):
        return {"candidate_paths": [], "schema_verified": False, "writes": False}
    paths = []
    for key in CANDIDATE_KEYS:
        if key in order and order[key] is not None:
            paths.append("body.order." + key)
    items = order.get("items")
    if isinstance(items, list):
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            for key in CANDIDATE_KEYS:
                if key in item and item[key] is not None:
                    paths.append(f"body.order.items[{index}].{key}")
    return {
        "candidate_paths": sorted(paths),
        "schema_verified": False,
        "writes": False,
    }
