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
        return {"candidate_paths": [], "candidate_values": [],
                "non_text_candidate_paths": [], "blank_candidate_paths": [],
                "schema_verified": False, "writes": False}
    paths = []
    values = []
    for key in sorted(CANDIDATE_KEYS):
        if key in order and order[key] is not None:
            path = "body.order." + key
            paths.append(path)
            values.append({"path": path, "value": order[key]})
    items = order.get("items")
    if isinstance(items, list):
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            for key in sorted(CANDIDATE_KEYS):
                if key in item and item[key] is not None:
                    path = f"body.order.items[{index}].{key}"
                    paths.append(path)
                    values.append({"path": path, "value": item[key]})
            modifiers = item.get("modifiers")
            if isinstance(modifiers, list):
                for modifier_index, modifier in enumerate(modifiers):
                    if not isinstance(modifier, dict):
                        continue
                    for key in sorted(CANDIDATE_KEYS):
                        if key in modifier and modifier[key] is not None:
                            path = (
                                f"body.order.items[{index}].modifiers"
                                f"[{modifier_index}].{key}"
                            )
                            paths.append(path)
                            values.append({"path": path, "value": modifier[key]})
    return {
        "candidate_paths": sorted(paths),
        "candidate_values": sorted(values, key=lambda x: x["path"]),
        # Candidate field names are not a verified webhook schema. Do not
        # convert structured or empty values into printable kitchen notes.
        "non_text_candidate_paths": sorted(
            entry["path"] for entry in values if not isinstance(entry["value"], str)
        ),
        "blank_candidate_paths": sorted(
            entry["path"] for entry in values
            if isinstance(entry["value"], str) and not entry["value"].strip()
        ),
        "schema_verified": False,
        "writes": False,
    }
