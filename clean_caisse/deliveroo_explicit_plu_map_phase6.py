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
    # Two distinct legacy IDs must not silently collapse onto one kitchen
    # option for the same parent product. Review such aliases explicitly.
    seen_targets = {}
    for key, target in approved_map.items():
        if (not isinstance(key, tuple) or len(key) != 2
                or any(not isinstance(part, str) or not part.strip() for part in key)
                or not isinstance(target, str)
                or not target.startswith("opt:" + key[0] + ":")):
            raise DeliverooMappingError("Invalid approved legacy PLU mapping entry")
        if (key[0] != key[0].strip() or key[1] != key[1].strip()
                or key[1].startswith("opt:")):
            raise DeliverooMappingError("Invalid approved legacy PLU mapping source")
        target_key = (key[0], target)
        previous_source = seen_targets.get(target_key)
        if previous_source is not None and previous_source != key[1]:
            raise DeliverooMappingError("Ambiguous approved legacy PLU target")
        seen_targets[target_key] = key[1]
        parts = target.split(":")
        if (len(parts) != 4 or any(
                not part.isascii() or not part.isdecimal()
                or str(int(part)) != part for part in parts[2:]
        )):
            raise DeliverooMappingError("Non-canonical approved modifier PLU target")
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


def audit_modifier_plu_sources(payload):
    """Inventory legacy modifier IDs for human reconciliation (read-only).

    This is not a mapping, does not guess targets by label, and never grants
    approval to send an order to the kitchen. Repeated occurrences are grouped
    by their exact parent product and modifier PLU.
    """
    parsed = parse_order_new(payload)
    sources = {}
    malformed_prefixed = {}
    canonical_occurrences = 0
    for item in parsed["items"]:
        parent_id = item["pos_item_id"]
        for modifier in item["modifiers"]:
            source_id = modifier["pos_item_id"]
            if source_id.startswith("opt:"):
                parts = source_id.split(":")
                # A prefix alone is not evidence of a canonical parent-scoped
                # PLU. Malformed prefixed IDs cannot be legacy-map approved.
                canonical = (
                    len(parts) == 4 and parts[1] == parent_id
                    and all(
                        part.isascii() and part.isdecimal()
                        and (part == "0" or not part.startswith("0"))
                        for part in parts[2:]
                    )
                )
                if canonical:
                    canonical_occurrences += 1
                else:
                    key = (parent_id, source_id)
                    malformed_prefixed[key] = malformed_prefixed.get(key, 0) + 1
                continue
            key = (parent_id, source_id)
            entry = sources.setdefault(key, {
                "parent_pos_item_id": parent_id,
                "legacy_modifier_pos_item_id": source_id,
                "source_labels": [],
                "occurrences": 0,
            })
            entry["occurrences"] += 1
            label = modifier["name"]
            if label not in entry["source_labels"]:
                entry["source_labels"].append(label)
    inventory = []
    conflicts = []
    missing_labels = []
    for key in sorted(sources):
        entry = sources[key]
        entry["source_labels"].sort()
        normalized = {label.strip().casefold() for label in entry["source_labels"]}
        entry["conflicting_labels"] = len(normalized) > 1
        entry["missing_label"] = "" in normalized
        if entry["conflicting_labels"]:
            conflicts.append(list(key))
        if entry["missing_label"]:
            missing_labels.append(list(key))
        inventory.append(entry)
    return {
        "legacy_sources": inventory,
        "legacy_source_count": len(inventory),
        "canonical_modifier_occurrences_unverified": canonical_occurrences,
        "malformed_prefixed_sources": [
            {"parent_pos_item_id": parent_id,
             "received_modifier_pos_item_id": source_id,
             "occurrences": malformed_prefixed[(parent_id, source_id)]}
            for parent_id, source_id in sorted(malformed_prefixed)
        ],
        "conflicting_label_sources": conflicts,
        "missing_label_sources": missing_labels,
        "requires_explicit_mapping_review": bool(inventory or malformed_prefixed),
        "mapping_approved": False,
        "ready_for_dispatch": False,
        "writes": False,
    }
