"""Read-only BIS Deliveroo 20% preflight: evidence, never dispatch approval.

No SQL, network, order creation, menu upload, printer or kitchen side effects.
The 20% rate is the *requested Deliveroo audit assumption*, not a change to
persisted marketplace settings (especially not Uber Eats).
"""
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
from clean_caisse.deliveroo_order_reconcile_phase6 import reconcile
from clean_caisse.deliveroo_explicit_plu_map_phase6 import audit_modifier_plu_sources
from clean_caisse.deliveroo_amount_audit_phase6 import (
    audit_order_amounts, audit_catalog_base_markup, audit_catalog_modifier_markup,
)
from clean_caisse.deliveroo_instruction_audit_phase6 import audit_instruction_fields

DELIVEROO_AUDIT_MARKUP = "20"


def audit_deliveroo_20pct_preflight(payload, catalog):
    """Collect independent PLU, amount, markup and instruction diagnostics.

    Unknown/legacy PLUs and mismatched prices remain blockers; this report
    cannot be used as authorization to import, print or accept an order.
    """
    reasons = []
    # A valid canonical PLU can still refer to a different catalogue choice
    # after an option reorder. Compare labels for review, never auto-remap.
    # Only indices and PLUs are returned; no customer notes or raw labels.
    label_drift = []
    label_unverifiable = []
    label_check_complete = False
    plu = audit_modifier_plu_sources(payload)
    if plu["requires_explicit_mapping_review"]:
        reasons.append("modifier_plu_review_required")
    try:
        reconciled = reconcile(payload, catalog)
    except DeliverooMappingError:
        reasons.append("catalogue_reconciliation_failed")
    else:
        label_check_complete = True
        for line_index, (received, mapped) in enumerate(
                zip(reconciled["items"], reconciled["mapped_items"])):
            product_id = received["pos_item_id"]
            received_label = " ".join(received["name"].split()).casefold()
            catalog_label = " ".join(mapped["name"].split()).casefold()
            if not received_label or not catalog_label:
                label_unverifiable.append({
                    "kind": "product", "line_index": line_index,
                    "pos_item_id": product_id,
                })
            elif received_label != catalog_label:
                label_drift.append({
                    "kind": "product", "line_index": line_index,
                    "pos_item_id": product_id,
                })
            for modifier_index, (incoming_option, catalog_option) in enumerate(
                    zip(received["modifiers"], mapped["options"])
            ):
                received_label = " ".join(incoming_option["name"].split()).casefold()
                catalog_label = " ".join(catalog_option["name"].split()).casefold()
                entry = {
                    "kind": "modifier", "line_index": line_index,
                    "modifier_index": modifier_index,
                    "pos_item_id": incoming_option["pos_item_id"],
                }
                if not received_label or not catalog_label:
                    label_unverifiable.append(entry)
                elif received_label != catalog_label:
                    label_drift.append(entry)
        if label_drift:
            reasons.append("catalogue_labels_differ_from_webhook")
        if label_unverifiable:
            reasons.append("catalogue_labels_unverifiable")

    amounts = audit_order_amounts(payload)
    if amounts["requires_financial_review"]:
        reasons.append("order_amounts_require_review")

    base = audit_catalog_base_markup(
        payload, catalog, markup_percentage=DELIVEROO_AUDIT_MARKUP
    )
    if base["requires_financial_review"]:
        reasons.append("base_prices_differ_from_20pct_policy")

    modifiers = audit_catalog_modifier_markup(
        payload, catalog, markup_percentage=DELIVEROO_AUDIT_MARKUP
    )
    if modifiers["requires_financial_review"]:
        reasons.append("modifier_prices_differ_from_20pct_policy")

    notes = audit_instruction_fields(payload)
    if notes["scan_complete"] is not True:
        reasons.append("instruction_scan_incomplete")
    if notes["candidate_paths"]:
        reasons.append("customer_instructions_need_mapping")

    return {
        "deliveroo_markup_assumption_percent": DELIVEROO_AUDIT_MARKUP,
        "blockers": reasons,
        "plu_inventory": plu,
        "catalogue_label_check_complete": label_check_complete,
        "catalogue_label_drift": label_drift,
        "catalogue_label_unverifiable": label_unverifiable,
        "order_amount_audit": amounts,
        "base_price_audit": base,
        "modifier_price_audit": modifiers,
        # Do not expose customer instruction values in this summary.
        "instruction_candidate_paths": notes["candidate_paths"],
        "instruction_scan_complete": notes["scan_complete"],
        "requires_explicit_dispatch_approval": True,
        "ready_for_dispatch": False,
        "writes": False,
    }
