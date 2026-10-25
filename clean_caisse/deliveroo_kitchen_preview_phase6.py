"""Read-only Deliveroo kitchen preview. No POS, database or printer side effects."""
from clean_caisse.deliveroo_kitchen_origin_phase6 import kitchen_origin
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
from clean_caisse.deliveroo_order_reconcile_phase6 import reconcile
from clean_caisse.deliveroo_explicit_plu_map_phase6 import reconcile_with_explicit_plu_map


def preview_order(payload, catalog, approved_map=None):
    mapped = (reconcile(payload, catalog) if approved_map is None
              else reconcile_with_explicit_plu_map(payload, catalog, approved_map))
    origin = kitchen_origin("DELIVEROO", mapped.get("display_id"))
    items = []
    for item in mapped["mapped_items"]:
        qty = item["qty"]
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise DeliverooMappingError("Invalid kitchen item quantity")
        options = []
        for option in item["options"]:
            option_qty = option["quantity"]
            if not isinstance(option_qty, int) or isinstance(option_qty, bool) or option_qty < 1:
                raise DeliverooMappingError("Invalid kitchen modifier quantity")
            options.append({
                "group": option["group"],
                "name": option["name"],
                "quantity": option_qty,
            })
        items.append({"name": item["name"], "quantity": qty, "options": options})
    return {
        "origin": origin,
        "external_order_id": mapped["external_order_id"],
        "display_id": mapped["display_id"],
        "fulfillment_type": mapped["fulfillment_type"],
        "items": items,
        "instructions_verified": False,
        "ready_for_dispatch": False,
        "requires_price_policy": True,
        "writes": False,
    }
