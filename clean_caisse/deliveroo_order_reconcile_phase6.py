"""Read-only Deliveroo PLU reconciliation. No order writes or POS dispatch."""
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError, parse_order_new


def reconcile(payload, catalog):
    parsed = parse_order_new(payload)
    products = catalog.get("products", []) if isinstance(catalog, dict) else []
    if not isinstance(products, list):
        raise DeliverooMappingError("Invalid catalogue products list")
    by_id = {}
    for product in products:
        if not isinstance(product, dict):
            continue
        raw_product_id = product.get("id")
        if not isinstance(raw_product_id, str):
            raise DeliverooMappingError("Invalid catalogue product ID")
        product_id = raw_product_id.strip()
        if not product_id:
            raise DeliverooMappingError("Missing catalogue product ID")
        if product_id in by_id:
            raise DeliverooMappingError("Duplicate catalogue product ID")
        by_id[product_id] = product

    mapped = []
    for line in parsed["items"]:
        product_id = line["pos_item_id"]
        product = by_id.get(product_id)
        if not product or product.get("active", True) is False:
            raise DeliverooMappingError("Unknown or inactive POS product: " + product_id)
        groups = product.get("options")
        if groups is None:
            groups = []
        if not isinstance(groups, list):
            raise DeliverooMappingError("Invalid catalogue option groups: " + product_id)
        selections = []
        for modifier in line["modifiers"]:
            plu = modifier["pos_item_id"]
            parts = plu.split(":")
            if len(parts) != 4 or parts[0] != "opt" or parts[1] != product_id:
                raise DeliverooMappingError("Unmapped modifier PLU: " + plu)
            try:
                # PLU indices are zero-based and must never use Python's
                # negative indexing or accept non-canonical representations.
                if any(not part.isascii() or not part.isdecimal() or
                       str(int(part)) != part for part in parts[2:]):
                    raise ValueError("Non-canonical modifier index")
                group_index, choice_index = int(parts[2]), int(parts[3])
                group = groups[group_index]
                if not isinstance(group, dict):
                    raise DeliverooMappingError("Invalid catalogue option group")
                choices = next(
                    group[key] for key in ("options", "values", "items", "choices")
                    if isinstance(group.get(key), list)
                )
                choice = choices[choice_index]
            except (ValueError, IndexError, KeyError, TypeError, StopIteration):
                raise DeliverooMappingError("Invalid modifier PLU: " + plu)
            if group.get("active", True) is False:
                raise DeliverooMappingError("Inactive catalogue option group: " + plu)
            if isinstance(choice, dict) and choice.get("active", True) is False:
                raise DeliverooMappingError("Inactive catalogue option choice: " + plu)
            group_name = str(group.get("name") or group.get("label") or group.get("title") or "Groupe " + str(group_index + 1))
            if isinstance(choice, dict):
                choice_name = str(choice.get("name") or choice.get("label") or choice.get("title") or choice.get("value") or choice.get("id") or "")
            elif isinstance(choice, (list, tuple)):
                choice_name = str(choice[0] if choice else "")
            else:
                choice_name = str(choice)
            if not choice_name:
                raise DeliverooMappingError("Empty choice for modifier PLU")
            selections.append({"group": group_name, "name": choice_name,
                               "quantity": modifier["quantity"]})
        mapped.append({
            "product_id": product_id,
            "name": str(product.get("name") or ""),
            "qty": line["quantity"],
            "options": selections,
            "deliveroo_unit_eur": line["unit_price_eur"],
            "deliveroo_line_eur": line["line_total_eur"],
        })
    parsed["mapped_items"] = mapped
    parsed["requires_price_policy"] = True
    parsed["writes"] = False
    return parsed
