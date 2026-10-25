"""Explicit, read-only legacy Deliveroo modifier PLU translation.

No automatic matching by name or price. Mapping entries must be reviewed and
provided explicitly for each parent product. Does not write to POS or printer.
"""
from copy import deepcopy
from clean_caisse.deliveroo_order_mapping_phase6 import (
    DeliverooMappingError, parse_order_new,
)
from clean_caisse.deliveroo_order_reconcile_phase6 import reconcile


def reconcile_with_explicit_plu_map(payload, catalog, approved_map):
    if not isinstance(approved_map, dict):
        raise DeliverooMappingError("Explicit PLU mapping must be a dictionary")
    parsed = parse_order_new(payload)
    translated = deepcopy(payload)
    lines = translated["body"]["order"]["items"]
    legacy_labels = {}
    for key, target in approved_map.items():
        if (not isinstance(key, tuple) or len(key) != 2
                or any(not isinstance(part, str) or not part.strip() for part in key)
                or not isinstance(target, str)
                or not target.startswith("opt:" + key[0] + ":")):
            raise DeliverooMappingError("Invalid approved legacy PLU mapping entry")
    for line_index, item in enumerate(parsed["items"]):
        product_id = item["pos_item_id"]
        for modifier_index, modifier in enumerate(item["modifiers"]):
            old_plu = modifier["pos_item_id"]
            if old_plu.startswith("opt:"):
                continue
            key = (product_id, old_plu)
            label = modifier["name"].strip().casefold()
            if key in legacy_labels and legacy_labels[key] != label:
                raise DeliverooMappingError("Conflicting legacy modifier labels: " + old_plu)
            legacy_labels[key] = label
            target = approved_map.get(key)
            if not isinstance(target, str) or not target:
                raise DeliverooMappingError("Unapproved legacy modifier PLU: " + old_plu)
            if not target.startswith("opt:" + product_id + ":"):
                raise DeliverooMappingError("Cross-product modifier PLU mapping: " + old_plu)
            lines[line_index]["modifiers"][modifier_index]["pos_item_id"] = target
    result = reconcile(translated, catalog)
    for line_index, item in enumerate(parsed["items"]):
        for modifier_index, modifier in enumerate(item["modifiers"]):
            if modifier["pos_item_id"].startswith("opt:"):
                continue
            original_name = modifier["name"].strip()
            resolved_name = result["mapped_items"][line_index]["options"][modifier_index]["name"].strip()
            if not original_name or original_name.casefold() != resolved_name.casefold():
                raise DeliverooMappingError(
                    "Legacy modifier label mismatch: " + modifier["pos_item_id"]
                )
    result["explicit_plu_translation"] = True
    result["ready_for_dispatch"] = False
    result["writes"] = False
    return result
