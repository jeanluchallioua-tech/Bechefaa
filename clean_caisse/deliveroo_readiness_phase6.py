"""Pure readiness assessment for the isolated Deliveroo kitchen preview.

This is a diagnostic only. It never dispatches or changes a POS order.
"""


def assess_kitchen_readiness(preview, *, plu_approved=False,
                             price_policy_approved=False,
                             instruction_schema_verified=False):
    blockers = []
    if not isinstance(preview, dict) or preview.get("writes") is not False:
        blockers.append("invalid_read_only_preview")
    if not plu_approved:
        blockers.append("plu_mapping_not_approved")
    if not price_policy_approved:
        blockers.append("price_policy_not_approved")
    if not instruction_schema_verified:
        blockers.append("instruction_schema_not_verified")
    if isinstance(preview, dict):
        if not isinstance(preview.get("items"), list) or not preview["items"]:
            blockers.append("missing_kitchen_items")
        if preview.get("ready_for_dispatch") is not False:
            blockers.append("preview_dispatch_guard_missing")
        if preview.get("requires_price_policy") is not True:
            blockers.append("price_policy_guard_missing")
        audit = preview.get("instruction_field_audit")
        if not isinstance(audit, dict) or audit.get("writes") is not False:
            blockers.append("instruction_audit_missing")
        if instruction_schema_verified and (
            preview.get("instructions_verified") is not True
            or not isinstance(audit, dict)
            or audit.get("schema_verified") is not True
        ):
            blockers.append("instruction_evidence_missing")
        if price_policy_approved and preview.get("requires_price_policy") is True:
            blockers.append("price_policy_evidence_missing")
    return {
        "checks_passed": not blockers,
        "blockers": blockers,
        "dispatch_performed": False,
        "writes": False,
    }
