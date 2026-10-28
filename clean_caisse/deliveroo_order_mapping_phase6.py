"""Pure Deliveroo order.new parser; no database writes or POS dispatch.

This module is intentionally not registered in production. It validates the
Sandbox event shape before an order bridge can be enabled.
"""
from decimal import Decimal, InvalidOperation


class DeliverooMappingError(ValueError):
    pass


def _canonical_id(value, label):
    """Reject silent PLU/order-ID normalization and control characters."""
    if (not isinstance(value, str) or not value or value != value.strip()
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
        raise DeliverooMappingError("Invalid or non-canonical " + label)
    return value


def _webhook_label(value, label):
    """Preserve customer-facing labels without converting JSON scalars to text.

    A boolean or object must never become a printable product/option name.
    Empty strings remain available for the separate missing-label diagnostic.
    """
    if not isinstance(value, str):
        raise DeliverooMappingError("Invalid Deliveroo " + label)
    return value


def _money(value):
    if not isinstance(value, dict) or value.get("currency_code") != "EUR":
        raise DeliverooMappingError("Expected EUR money object")
    try:
        raw_cents = value["fractional"]
        if isinstance(raw_cents, bool) or not isinstance(raw_cents, int):
            raise DeliverooMappingError("Invalid monetary amount")
        cents = raw_cents
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
    order_id = _canonical_id(order.get("id"), "Deliveroo order ID")
    raw_items = order.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise DeliverooMappingError("Missing items")
    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise DeliverooMappingError("Invalid item")
        pos_id = _canonical_id(item.get("pos_item_id"), "POS item ID")
        raw_qty = item.get("quantity")
        if isinstance(raw_qty, bool) or not isinstance(raw_qty, int):
            raise DeliverooMappingError("Invalid quantity")
        qty = raw_qty
        if qty < 1:
            raise DeliverooMappingError("Invalid quantity")
        raw_modifiers = item.get("modifiers")
        if raw_modifiers is None:
            raw_modifiers = []
        if not isinstance(raw_modifiers, list):
            raise DeliverooMappingError("Invalid modifiers list")
        modifiers = []
        for modifier in raw_modifiers:
            if not isinstance(modifier, dict):
                raise DeliverooMappingError("Invalid modifier")
            modifier_pos_id = _canonical_id(
                modifier.get("pos_item_id"), "modifier POS item ID"
            )
            modifier_qty = modifier.get("quantity", 1)
            if isinstance(modifier_qty, bool) or not isinstance(modifier_qty, int) or modifier_qty < 1:
                raise DeliverooMappingError("Invalid modifier quantity")
            modifiers.append({
                "pos_item_id": modifier_pos_id,
                "name": _webhook_label(modifier.get("name"), "modifier name"),
                "quantity": modifier_qty,
                "unit_price_eur": _money(modifier.get("unit_price")),
            })
        items.append({
            "pos_item_id": pos_id,
            "name": _webhook_label(item.get("name"), "item name"),
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
