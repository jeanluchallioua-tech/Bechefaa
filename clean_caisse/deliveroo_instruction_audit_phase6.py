"""Read-only inventory of possible Deliveroo kitchen instruction fields.

Candidate field names are diagnostic only: their semantics have not yet been
confirmed against the actual Deliveroo order webhook contract.
"""
def _unsafe_controls(value):
    """Reject printer/control bytes; allow ordinary multiline customer notes."""
    return any((ord(char) < 32 and char not in "\t\n\r") or 127 <= ord(char) <= 159
               for char in value)


# Deliveroo Order Events webhook examples document these at body.order level.
# Source: https://api-docs.deliveroo.com/docs/fulfillment-types
# Documented fields are not verified BÉCHÉFAA runtime payload semantics.
DOCUMENTED_ORDER_NOTE_KEYS = frozenset({"order_notes", "cutlery_notes"})

CANDIDATE_KEYS = frozenset({
    "notes", "note", "instructions", "special_instructions",
    "customer_note", "customer_notes", "cooking_instructions",
    "delivery_instructions", "delivery_notes", "dropoff_instructions",
    "customer_instructions", "special_requests", "allergy_information",
    "specialInstructions", "deliveryInstructions", "customerInstructions",
    "orderNotes", "cutleryNotes", "allergyNotes",
}) | DOCUMENTED_ORDER_NOTE_KEYS

# Webhook field casing/separators may vary across producers. Recognize known
# instruction concepts even when a producer changes only their spelling form.
# Keep the original path/value for diagnostics; never interpret or print notes.
def _instruction_key(key):
    return "".join(char for char in key.casefold() if "a" <= char <= "z" or "0" <= char <= "9")


NORMALIZED_CANDIDATE_KEYS = frozenset(_instruction_key(key) for key in CANDIDATE_KEYS)


def audit_instruction_fields(payload):
    """Inventory candidate notes anywhere inside body.order, without writes.

    A bounded traversal prevents pathological payloads from exhausting the
    webhook worker. An incomplete scan is a hard stop for the opt-in bridge,
    never an implicit approval to drop potentially uninspected instructions.
    """
    body = payload.get("body") if isinstance(payload, dict) else None
    order = body.get("order") if isinstance(body, dict) else None
    paths = []
    values = []
    scan_complete = True
    if isinstance(order, dict):
        pending = [("body.order", order, 0)]
        # Count every inspected field/list entry, not only container nodes:
        # a single huge flat object/list must not bypass the traversal budget.
        inspected = 0
        while pending:
            path, node, depth = pending.pop()
            inspected += 1
            if inspected > 5000 or depth > 16:
                scan_complete = False
                break
            if isinstance(node, dict):
                for key, value in node.items():
                    inspected += 1
                    if inspected > 5000:
                        scan_complete = False
                        break
                    if not isinstance(key, str):
                        scan_complete = False
                        continue
                    child_path = path + "." + key
                    if _instruction_key(key) in NORMALIZED_CANDIDATE_KEYS and value is not None:
                        paths.append(child_path)
                        values.append({"path": child_path, "value": value})
                    if isinstance(value, (dict, list)):
                        pending.append((child_path, value, depth + 1))
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    inspected += 1
                    if inspected > 5000:
                        scan_complete = False
                        break
                    if isinstance(value, (dict, list)):
                        pending.append((f"{path}[{index}]", value, depth + 1))
            if not scan_complete:
                break
    return {
        "candidate_paths": sorted(paths),
        "documented_order_note_paths": sorted(
            "body.order." + key for key in DOCUMENTED_ORDER_NOTE_KEYS
            if isinstance(order, dict) and key in order and order[key] is not None
        ),
        "candidate_values": sorted(values, key=lambda x: x["path"]),
        "non_text_candidate_paths": sorted(
            entry["path"] for entry in values if not isinstance(entry["value"], str)
        ),
        "blank_candidate_paths": sorted(
            entry["path"] for entry in values
            if isinstance(entry["value"], str) and not entry["value"].strip()
        ),
        "unsafe_control_candidate_paths": sorted(
            entry["path"] for entry in values
            if isinstance(entry["value"], str) and _unsafe_controls(entry["value"])
        ),
        "scan_complete": scan_complete,
        "schema_verified": False,
        "writes": False,
    }
