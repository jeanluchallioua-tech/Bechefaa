"""Pure Deliveroo order.new parser; no database writes or POS dispatch.

This module is intentionally not registered in production. It validates the
Sandbox event shape before an order bridge can be enabled.
"""
from decimal import Decimal, InvalidOperation


class DeliverooMappingError(ValueError):
    pass


def _money(value):
    if not isinstance(value, dict) or value.get("currency_code") != "EUR":
        raise DeliverooMappingError("Expected EUR money object")
    try:
        cents = int(value["fractional"])
    except (KeyError, TypeError, ValueError):
        raise DeliverooMappingError("Invalid monetary amount")
    if cents < 0:
        raise DeliverooMappingError("Negative monetary amount")
    return str((Decimal(cents) / Decimal(100)).quantize(Decimal("0.01")))


def parse_order_new(payload):
    """Return a lossless, read-only summary for mapping review.

    Do not use this as an /api/orders payload: Deliveroo POS IDs have not yet
    been reconciled with the BÉCHÉFAA catalogue, and delivery details may be
    absent from a Deliveroo-managed delivery.
    """
    if not isinstance(payload, dict) or payload.get("event") != "order.new":
        raise DeliverooMappingError("Not an order.new event")
    body = payload.get("body")
    order = body.get("order") if isinstance(body, dict) else None
    if not isinstance(order, dict):
        raise DeliverooMappingError("Missing body.order")
    order_id = str(order.get("id") or "").strip()
    if not order_id:
        raise DeliverooMappingError("Missing Deliveroo order ID")
    raw_items = order.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise DeliverooMappingError("Missing items")
    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise DeliverooMappingError("Invalid item")
        pos_id = str(item.get("pos_item_id") or "").strip()
        if not pos_id:
            raise DeliverooMappingError("Missing POS item ID")
        try:
            qty = int(item.get("quantity"))
        except (TypeError, ValueError):
            raise DeliverooMappingError("Invalid quantity")
        if qty < 1:
            raise DeliverooMappingError("Invalid quantity")
        modifiers = []
        for modifier in item.get("modifiers") or []:
            if not isinstance(modifier, dict) or not modifier.get("pos_item_id"):
                raise DeliverooMappingError("Invalid modifier")
            modifiers.append({
                "pos_item_id": str(modifier["pos_item_id"]),
                "name": str(modifier.get("name") or ""),
                "quantity": int(modifier.get("quantity") or 1),
                "unit_price_eur": _money(modifier.get("unit_price")),
            })
        items.append({
            "pos_item_id": pos_id,
            "name": str(item.get("name") or ""),
            "quantity": qty,
            "unit_price_eur": _money(item.get("unit_price")),
            "line_total_eur": _money(item.get("total_price")),
            "modifiers": modifiers,
        })
    return {
        "external_order_id": order_id,
        "display_id": str(order.get("display_id") or ""),
        "location_id": str(order.get("location_id") or ""),
        "brand_id": str(order.get("brand_id") or ""),
        "status": str(order.get("status") or ""),
        "fulfillment_type": str(order.get("fulfillment_type") or ""),
        "total_eur": _money(order.get("total_price")),
        "items": items,
        "requires_catalog_mapping": True,
        "writes": False,
    }
