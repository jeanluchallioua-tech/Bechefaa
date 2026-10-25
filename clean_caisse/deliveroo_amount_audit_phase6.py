"""Read-only monetary consistency diagnostic for Deliveroo order.new.

A mismatch is diagnostic, not a price-policy approval: delivery fees,
discounts and other adjustments may legitimately affect order totals.
"""
from decimal import Decimal
from clean_caisse.deliveroo_order_mapping_phase6 import parse_order_new


def audit_order_amounts(payload):
    parsed = parse_order_new(payload)
    order_total = Decimal(parsed["total_eur"])
    lines_total = sum(
        (Decimal(item["line_total_eur"]) for item in parsed["items"]),
        Decimal("0.00"),
    )
    difference = order_total - lines_total
    return {
        "order_total_eur": str(order_total),
        "items_total_eur": str(lines_total),
        "difference_eur": str(difference),
        "totals_match": difference == 0,
        "price_policy_verified": False,
        "ready_for_dispatch": False,
        "writes": False,
    }
