"""Read-only Deliveroo PLU diagnostic; never guesses legacy sandbox mappings.

The diagnostic must not report compatibility for a product or modifier that
the stricter order reconciler would reject as inactive or ambiguous.
"""
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError, parse_order_new
from clean_caisse.deliveroo_order_reconcile_phase6 import reconcile


def audit_order_plu(payload, catalog):
    parsed = parse_order_new(payload)
    products = catalog.get("products", []) if isinstance(catalog, dict) else []
    by_id = {}
    duplicates = set()
    for product in products if isinstance(products, list) else []:
        if not isinstance(product, dict):
            continue
        product_id = product.get("id")
        if not isinstance(product_id, str) or not product_id:
            continue
        if product_id in by_id:
            duplicates.add(product_id)
        else:
            by_id[product_id] = product
    findings = []
    for line in parsed["items"]:
        product_id = line["pos_item_id"]
        if product_id in duplicates:
            findings.append({"type": "duplicate_catalog_product", "plu": product_id})
            continue
        product = by_id.get(product_id)
        if product is None:
            findings.append({"type": "unknown_product", "plu": product_id})
            continue
        if product.get("active", True) is False:
            findings.append({"type": "inactive_product", "plu": product_id})
            continue
        groups = product.get("options")
        if groups is None:
            groups = []
        if not isinstance(groups, list):
            findings.append({"type": "invalid_product_options", "plu": product_id})
            continue
        valid = {}
        for gi, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            choices = next(
                (group[k] for k in ("options", "values", "items", "choices")
                 if isinstance(group.get(k), list)), []
            )
            for ci, choice in enumerate(choices):
                valid[f"opt:{product_id}:{gi}:{ci}"] = (group, choice)
        for modifier in line["modifiers"]:
            actual = modifier["pos_item_id"]
            if actual not in valid:
                findings.append({
                    "type": "unmapped_modifier",
                    "product_id": product_id,
                    "received_plu": actual,
                    "expected_plu_format": f"opt:{product_id}:<group_index>:<choice_index>",
                })
                continue
            group, choice = valid[actual]
            if group.get("active", True) is False:
                findings.append({
                    "type": "inactive_modifier_group",
                    "product_id": product_id,
                    "received_plu": actual,
                })
            if isinstance(choice, dict) and choice.get("active", True) is False:
                findings.append({
                    "type": "inactive_modifier_choice",
                    "product_id": product_id,
                    "received_plu": actual,
                })
    # The audit is advisory, but it must never claim compatibility for a
    # catalogue that the actual strict reconciler would reject. Preserve
    # specific PLU findings above and check the complete catalogue only
    # when no other incompatibility has already been reported.
    if not findings:
        try:
            reconcile(payload, catalog)
        except DeliverooMappingError as exc:
            findings.append({
                "type": "reconciler_rejected",
                "reason": str(exc),
            })
    return {
        "external_order_id": parsed["external_order_id"],
        "findings": findings,
        "compatible": not findings,
        "writes": False,
        "auto_mapping": False,
    }
