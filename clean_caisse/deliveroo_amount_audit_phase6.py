"""Read-only Deliveroo amount diagnostics; no inferred price-policy approval.

Deliveroo's line-total treatment of modifiers, fees and discounts must be
confirmed against the actual webhook contract. These are *hypotheses*, not
invoicing rules or authority to dispatch an order.
"""
from decimal import Decimal
from clean_caisse.deliveroo_order_mapping_phase6 import parse_order_new


def _eur(value):
    return str(value.quantize(Decimal("0.01")))


def audit_order_amounts(payload):
    parsed = parse_order_new(payload)
    order_total = Decimal(parsed["total_eur"])
    lines_total = Decimal("0.00")
    line_diagnostics = []
    for index, item in enumerate(parsed["items"]):
        quantity = item["quantity"]
        unit_price = Decimal(item["unit_price_eur"])
        line_total = Decimal(item["line_total_eur"])
        base_total = unit_price * quantity
        # Modifiers may be priced once per line or once per parent unit.
        # Keep both hypotheses visible until the Deliveroo schema is verified.
        modifiers_per_line = sum(
            (Decimal(m["unit_price_eur"]) * m["quantity"]
             for m in item["modifiers"]), Decimal("0.00")
        )
        with_modifiers_once = base_total + modifiers_per_line
        with_modifiers_per_parent = base_total + modifiers_per_line * quantity
        lines_total += line_total
        line_diagnostics.append({
            "index": index,
            "pos_item_id": item["pos_item_id"],
            "quantity": quantity,
            "reported_line_total_eur": _eur(line_total),
            "base_total_eur": _eur(base_total),
            "modifiers_once_eur": _eur(modifiers_per_line),
            "candidate_total_modifiers_once_eur": _eur(with_modifiers_once),
            "candidate_total_modifiers_per_parent_eur": _eur(with_modifiers_per_parent),
            "matches_base_only": line_total == base_total,
            "matches_modifiers_once": line_total == with_modifiers_once,
            "matches_modifiers_per_parent": line_total == with_modifiers_per_parent,
        })
    difference = order_total - lines_total
    return {
        "order_total_eur": _eur(order_total),
        "items_total_eur": _eur(lines_total),
        "difference_eur": _eur(difference),
        "totals_match": difference == 0,
        "line_diagnostics": line_diagnostics,
        "modifier_pricing_schema_verified": False,
        "price_policy_verified": False,
        "ready_for_dispatch": False,
        "writes": False,
    }
