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
    plu = audit_modifier_plu_sources(payload)
    if plu["requires_explicit_mapping_review"]:
        reasons.append("modifier_plu_review_required")
    try:
        reconcile(payload, catalog)
    except DeliverooMappingError:
        reasons.append("catalogue_reconciliation_failed")

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
