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
    if isinstance(preview, dict) and not preview.get("items"):
        blockers.append("missing_kitchen_items")
    return {
        "checks_passed": not blockers,
        "blockers": blockers,
        "dispatch_performed": False,
        "writes": False,
    }
