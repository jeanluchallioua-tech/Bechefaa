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
        for item in preview.get("items", []) if isinstance(preview.get("items"), list) else []:
            if not isinstance(item, dict):
                blockers.append("invalid_kitchen_item")
                continue
            if not isinstance(item.get("name"), str) or not item["name"].strip():
                blockers.append("invalid_kitchen_item")
            # Validate quantities and modifiers even when the label is invalid.
            # A malformed line must not hide additional kitchen blockers.
            qty = item.get("quantity")
            if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
                blockers.append("invalid_kitchen_quantity")
            options = item.get("options")
            if not isinstance(options, list):
                blockers.append("invalid_kitchen_options")
                continue
            for option in options:
                if not isinstance(option, dict) or any(
                    not isinstance(option.get(key), str) or not option[key].strip()
                    for key in ("group", "name")
                ):
                    blockers.append("invalid_kitchen_modifier")
                    continue
                option_qty = option.get("quantity")
                if isinstance(option_qty, bool) or not isinstance(option_qty, int) or option_qty < 1:
                    blockers.append("invalid_kitchen_modifier_quantity")
        if preview.get("ready_for_dispatch") is not False:
            blockers.append("preview_dispatch_guard_missing")
        if preview.get("requires_price_policy") is not True:
            blockers.append("price_policy_guard_missing")
        audit = preview.get("instruction_field_audit")
        if not isinstance(audit, dict) or audit.get("writes") is not False:
            blockers.append("instruction_audit_missing")
        if isinstance(audit, dict):
            for key, blocker in (
                ("non_text_candidate_paths", "non_text_instruction_candidates"),
                ("blank_candidate_paths", "blank_instruction_candidates"),
            ):
                flagged = audit.get(key)
                if not isinstance(flagged, list):
                    blockers.append("instruction_candidate_diagnostics_missing")
                elif flagged:
                    blockers.append(blocker)
        if instruction_schema_verified and (
            preview.get("instructions_verified") is not True
            or not isinstance(audit, dict)
            or audit.get("schema_verified") is not True
        ):
            blockers.append("instruction_evidence_missing")
        amount_audit = preview.get("amount_audit")
        if not isinstance(amount_audit, dict) or amount_audit.get("writes") is not False:
            blockers.append("amount_audit_missing")
        else:
            if amount_audit.get("requires_financial_review") is True:
                blockers.append("amount_requires_financial_review")
            if amount_audit.get("ready_for_dispatch") is not False:
                blockers.append("amount_audit_dispatch_guard_missing")
            if amount_audit.get("price_policy_verified") is not False:
                blockers.append("amount_audit_price_guard_missing")
            if amount_audit.get("modifier_pricing_schema_verified") is not False:
                blockers.append("modifier_pricing_guard_missing")
            line_diagnostics = amount_audit.get("line_diagnostics")
            if (not isinstance(line_diagnostics, list)
                    or not isinstance(preview.get("items"), list)
                    or len(line_diagnostics) != len(preview["items"])
                    or any(not isinstance(line, dict) for line in line_diagnostics)):
                blockers.append("amount_line_diagnostics_missing")
        if price_policy_approved and preview.get("requires_price_policy") is True:
            blockers.append("price_policy_evidence_missing")
    return {
        "checks_passed": not blockers,
        "blockers": blockers,
        "dispatch_performed": False,
        "writes": False,
    }
