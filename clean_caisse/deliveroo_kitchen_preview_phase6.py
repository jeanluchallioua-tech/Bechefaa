"""Read-only Deliveroo kitchen preview. No POS, database or printer side effects."""
from copy import deepcopy
from clean_caisse.deliveroo_kitchen_origin_phase6 import kitchen_origin
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
from clean_caisse.deliveroo_order_reconcile_phase6 import reconcile
from clean_caisse.deliveroo_explicit_plu_map_phase6 import reconcile_with_explicit_plu_map
from clean_caisse.deliveroo_instruction_audit_phase6 import audit_instruction_fields
from clean_caisse.deliveroo_amount_audit_phase6 import (
    audit_order_amounts, audit_catalog_base_markup, audit_catalog_modifier_markup,
)


def _pricing_payload_after_approved_plu_mapping(payload, approved_map):
    """Use validated legacy mappings for *diagnostic* modifier price comparisons.

    Called only after reconcile_with_explicit_plu_map has validated every
    mapping and the original order. Never mutates the webhook payload.
    """
    if approved_map is None:
        return payload, []
    translated = deepcopy(payload)
    translations = []
    for item_index, item in enumerate(translated["body"]["order"]["items"]):
        for modifier_index, modifier in enumerate(item.get("modifiers") or []):
            original_plu = modifier["pos_item_id"]
            if original_plu.startswith("opt:"):
                continue
            target_plu = approved_map[(item["pos_item_id"], original_plu)]
            modifier["pos_item_id"] = target_plu
            translations.append({
                "item_index": item_index,
                "modifier_index": modifier_index,
                "received_plu": original_plu,
                "approved_canonical_plu": target_plu,
            })
    return translated, translations


def preview_order(payload, catalog, approved_map=None, *, assumed_markup_percentage=None):
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
    preview = {
        "origin": origin,
        "external_order_id": mapped["external_order_id"],
        "display_id": mapped["display_id"],
        "fulfillment_type": mapped["fulfillment_type"],
        "items": items,
        "instruction_field_audit": audit_instruction_fields(payload),
        "amount_audit": audit_order_amounts(payload),
        "instructions_verified": False,
        "ready_for_dispatch": False,
        "requires_price_policy": True,
        "writes": False,
    }
    if assumed_markup_percentage is not None:
        preview["catalog_markup_audit"] = audit_catalog_base_markup(
            payload, catalog, markup_percentage=assumed_markup_percentage
        )
        pricing_payload, translations = _pricing_payload_after_approved_plu_mapping(
            payload, approved_map
        )
        preview["catalog_modifier_markup_audit"] = audit_catalog_modifier_markup(
            pricing_payload, catalog, markup_percentage=assumed_markup_percentage
        )
        # Keep the exact received PLUs visible for human review. This is not
        # evidence that the financial policy or webhook schema is approved.
        preview["catalog_modifier_markup_audit"]["approved_legacy_plu_translations"] = translations
    return preview
