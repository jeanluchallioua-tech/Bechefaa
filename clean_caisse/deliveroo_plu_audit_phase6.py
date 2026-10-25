"""Read-only Deliveroo PLU diagnostic; never guesses legacy sandbox mappings."""
from clean_caisse.deliveroo_order_mapping_phase6 import parse_order_new


def audit_order_plu(payload, catalog):
    parsed = parse_order_new(payload)
    products = catalog.get("products", []) if isinstance(catalog, dict) else []
    by_id = {
        p["id"]: p for p in products
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    }
    findings = []
    for line in parsed["items"]:
        product_id = line["pos_item_id"]
        product = by_id.get(product_id)
        if product is None:
            findings.append({"type": "unknown_product", "plu": product_id})
            continue
        groups = product.get("options") or []
        for modifier in line["modifiers"]:
            actual = modifier["pos_item_id"]
            valid = set()
            if isinstance(groups, list):
                for gi, group in enumerate(groups):
                    if not isinstance(group, dict):
                        continue
                    choices = next(
                        (group[k] for k in ("options", "values", "items", "choices")
                         if isinstance(group.get(k), list)), []
                    )
                    for ci, _ in enumerate(choices):
                        valid.add(f"opt:{product_id}:{gi}:{ci}")
            if actual not in valid:
                findings.append({
                    "type": "unmapped_modifier",
                    "product_id": product_id,
                    "received_plu": actual,
                    "expected_plu_format": f"opt:{product_id}:<group_index>:<choice_index>",
                })
    return {
        "external_order_id": parsed["external_order_id"],
        "findings": findings,
        "compatible": not findings,
        "writes": False,
        "auto_mapping": False,
    }
