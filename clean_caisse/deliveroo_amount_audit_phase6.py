"""Read-only Deliveroo amount diagnostics; no inferred price-policy approval.

Deliveroo's line-total treatment of modifiers, fees and discounts must be
confirmed against the actual webhook contract. These are *hypotheses*, not
invoicing rules or authority to dispatch an order.
"""
from decimal import Decimal, ROUND_HALF_UP
from clean_caisse.deliveroo_order_mapping_phase6 import parse_order_new


def _eur(value):
    return str(value.quantize(Decimal("0.01")))


def audit_order_amounts(payload):
    parsed = parse_order_new(payload)
    order_total = Decimal(parsed["total_eur"])
    lines_total = Decimal("0.00")
    line_diagnostics = []
    unexplained_line_indices = []
    paid_modifiers_excluded_line_indices = []
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
        # This may be legitimate if Deliveroo charges modifiers elsewhere.
        # Never infer that policy; surface it for explicit financial review.
        paid_modifiers_excluded = modifiers_per_line > 0 and line_total == base_total
        if paid_modifiers_excluded:
            paid_modifiers_excluded_line_indices.append(index)
        if line_total not in (base_total, with_modifiers_once, with_modifiers_per_parent):
            unexplained_line_indices.append(index)
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
            "paid_modifiers_excluded_from_line_total": paid_modifiers_excluded,
            "matches_modifiers_once": line_total == with_modifiers_once,
            "matches_modifiers_per_parent": line_total == with_modifiers_per_parent,
        })
    difference = order_total - lines_total
    review_reasons = []
    if difference:
        review_reasons.append("order_total_differs_from_item_totals")
    if unexplained_line_indices:
        review_reasons.append("line_totals_match_no_candidate_model")
    if paid_modifiers_excluded_line_indices:
        review_reasons.append("paid_modifiers_excluded_from_line_totals")
    return {
        "order_total_eur": _eur(order_total),
        "items_total_eur": _eur(lines_total),
        "difference_eur": _eur(difference),
        "totals_match": difference == 0,
        "line_diagnostics": line_diagnostics,
        "unexplained_line_indices": unexplained_line_indices,
        "paid_modifiers_excluded_line_indices": paid_modifiers_excluded_line_indices,
        "requires_financial_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "modifier_pricing_schema_verified": False,
        "price_policy_verified": False,
        "ready_for_dispatch": False,
        "writes": False,
    }


def _nonnegative_decimal(value, label):
    """Parse policy inputs without accepting booleans, NaN or silent zeroes."""
    if value is None or isinstance(value, bool):
        raise ValueError("Invalid " + label)
    try:
        amount = Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        raise ValueError("Invalid " + label) from None
    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid " + label)
    return amount


def audit_catalog_base_markup(payload, catalog, *, markup_percentage):
    """Compare received ITEM unit prices to an *assumed* catalogue markup.

    The percentage must be supplied explicitly; a match is evidence for
    review, not approval of Deliveroo's pricing or modifier semantics.
    This function performs no database, network, POS or printer operation.
    """
    from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
    from clean_caisse.deliveroo_order_reconcile_phase6 import catalogue_entry_active

    parsed = parse_order_new(payload)
    if not isinstance(catalog, dict) or not isinstance(catalog.get("products"), list):
        raise DeliverooMappingError("Invalid catalogue for markup audit")
    try:
        percentage = _nonnegative_decimal(markup_percentage, "markup percentage")
    except ValueError as exc:
        raise DeliverooMappingError(str(exc)) from exc

    by_id = {}
    for product in catalog["products"]:
        if not isinstance(product, dict):
            raise DeliverooMappingError("Invalid catalogue product for markup audit")
        product_id = product.get("id")
        if (not isinstance(product_id, str) or not product_id
                or product_id != product_id.strip()
                or any(ord(char) < 32 or 127 <= ord(char) <= 159
                       for char in product_id)):
            raise DeliverooMappingError("Invalid catalogue product ID for markup audit")
        if product_id in by_id:
            raise DeliverooMappingError("Duplicate catalogue product ID for markup audit")
        by_id[product_id] = product

    diagnostics = []
    for index, item in enumerate(parsed["items"]):
        product_id = item["pos_item_id"]
        reported = Decimal(item["unit_price_eur"])
        product = by_id.get(product_id)
        status = "matches_assumed_markup"
        base_text = expected_text = difference_text = None
        if product is None:
            status = "missing_catalog_product"
        elif not catalogue_entry_active(product, "product " + product_id):
            status = "inactive_catalog_product"
        else:
            try:
                base = _nonnegative_decimal(product.get("price"), "catalogue price")
                base = base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                expected = (base * (Decimal("1") + percentage / Decimal("100"))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            except (ValueError, ArithmeticError):
                status = "invalid_catalog_price"
            else:
                base_text = _eur(base)
                expected_text = _eur(expected)
                difference_text = _eur(reported - expected)
                if reported != expected:
                    status = "unit_price_differs_from_assumed_markup"
        diagnostics.append({
            "index": index,
            "pos_item_id": product_id,
            "catalog_base_eur": base_text,
            "expected_unit_eur": expected_text,
            "reported_unit_eur": _eur(reported),
            "difference_eur": difference_text,
            "status": status,
        })
    reasons = sorted({
        line["status"] for line in diagnostics
        if line["status"] != "matches_assumed_markup"
    })
    return {
        "assumed_markup_percentage": str(percentage),
        "line_diagnostics": diagnostics,
        "review_reasons": reasons,
        "requires_financial_review": bool(reasons),
        "price_policy_verified": False,
        "ready_for_dispatch": False,
        "writes": False,
    }


def audit_catalog_modifier_markup(payload, catalog, *, markup_percentage):
    """Review received modifier unit prices against *hypothetical* menu prices.

    Canonical opt:<product>:<group>:<choice> PLUs are required. Legacy IDs
    remain unresolved, even if their names match catalogue options. This is
    read-only evidence for manual review, never approval or kitchen dispatch.
    """
    from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
    from clean_caisse.deliveroo_order_reconcile_phase6 import catalogue_entry_active

    parsed = parse_order_new(payload)
    if not isinstance(catalog, dict) or not isinstance(catalog.get("products"), list):
        raise DeliverooMappingError("Invalid catalogue for modifier markup audit")
    try:
        percentage = _nonnegative_decimal(markup_percentage, "markup percentage")
    except ValueError as exc:
        raise DeliverooMappingError(str(exc)) from exc

    by_id = {}
    for product in catalog["products"]:
        if not isinstance(product, dict):
            raise DeliverooMappingError("Invalid catalogue product for modifier markup audit")
        product_id = product.get("id")
        if (not isinstance(product_id, str) or not product_id
                or product_id != product_id.strip()
                or any(ord(char) < 32 or 127 <= ord(char) <= 159
                       for char in product_id)):
            raise DeliverooMappingError("Invalid catalogue product ID for modifier markup audit")
        if product_id in by_id:
            raise DeliverooMappingError("Duplicate catalogue product ID for modifier markup audit")
        by_id[product_id] = product

    diagnostics = []
    for item_index, item in enumerate(parsed["items"]):
        product_id = item["pos_item_id"]
        product = by_id.get(product_id)
        for modifier_index, modifier in enumerate(item["modifiers"]):
            modifier_id = modifier["pos_item_id"]
            reported = Decimal(modifier["unit_price_eur"])
            status = "matches_assumed_modifier_markup"
            base_text = expected_text = difference_text = None

            if product is None:
                status = "missing_catalog_product"
            elif not catalogue_entry_active(product, "product " + product_id):
                status = "inactive_catalog_product"
            else:
                parts = modifier_id.split(":")
                if (len(parts) != 4 or parts[:2] != ["opt", product_id]
                        or any(not p.isascii() or not p.isdecimal()
                               or len(p) > 9 or (len(p) > 1 and p.startswith("0"))
                               for p in parts[2:])):
                    status = "unmapped_modifier_plu"
                else:
                    groups = product.get("options")
                    if groups is None:
                        groups = []
                    if not isinstance(groups, list):
                        status = "invalid_catalog_modifier_groups"
                    else:
                        group_index, choice_index = int(parts[2]), int(parts[3])
                        group = groups[group_index] if group_index < len(groups) else None
                        if not isinstance(group, dict):
                            status = "unknown_catalog_modifier_group"
                        elif not catalogue_entry_active(group, "option group " + modifier_id):
                            status = "inactive_catalog_modifier_group"
                        else:
                            choices = next((
                                group[key] for key in ("options", "values", "items", "choices")
                                if isinstance(group.get(key), list)
                            ), [])
                            if choice_index >= len(choices):
                                status = "unknown_catalog_modifier_choice"
                            else:
                                choice = choices[choice_index]
                                # A null or boolean catalogue slot is not a
                                # zero-priced option. The PLU reconciliation
                                # rejects these values; the read-only price
                                # audit must not report a false match either.
                                # Match the strict PLU reconciler: an empty
                                # choice label is not a valid zero-price
                                # supplement, even if its price is numeric.
                                if isinstance(choice, dict):
                                    choice_label = str(
                                        choice.get("name") or choice.get("label")
                                        or choice.get("title") or choice.get("value")
                                        or choice.get("id") or ""
                                    ).strip()
                                elif isinstance(choice, (list, tuple)):
                                    choice_label = str(choice[0] if choice else "").strip()
                                else:
                                    choice_label = str(choice).strip()
                                if (choice is None or isinstance(choice, bool)
                                        or not choice_label):
                                    status = "invalid_catalog_modifier_choice"
                                elif (isinstance(choice, dict)
                                        and not catalogue_entry_active(
                                            choice, "option choice " + modifier_id
                                        )):
                                    status = "inactive_catalog_modifier_choice"
                                else:
                                    if isinstance(choice, dict):
                                        # A present zero-price field takes precedence
                                        # over legacy fallbacks, just like menu generation.
                                        raw_price = next((
                                            choice[key] for key in
                                            ("price", "extraPrice", "supplement")
                                            if key in choice
                                        ), 0)
                                    elif isinstance(choice, (list, tuple)):
                                        raw_price = choice[1] if len(choice) > 1 else 0
                                    else:
                                        raw_price = 0
                                    try:
                                        base = _nonnegative_decimal(
                                            raw_price, "catalogue modifier price"
                                        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                                        expected = (
                                            base * (Decimal("1") + percentage / Decimal("100"))
                                        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                                    except (ValueError, ArithmeticError):
                                        status = "invalid_catalog_modifier_price"
                                    else:
                                        base_text = _eur(base)
                                        expected_text = _eur(expected)
                                        difference_text = _eur(reported - expected)
                                        if reported != expected:
                                            status = "modifier_price_differs_from_assumed_markup"
            diagnostics.append({
                "index": item_index,
                "modifier_index": modifier_index,
                "pos_item_id": product_id,
                "modifier_pos_item_id": modifier_id,
                "catalog_base_eur": base_text,
                "expected_unit_eur": expected_text,
                "reported_unit_eur": _eur(reported),
                "difference_eur": difference_text,
                "status": status,
            })
    reasons = sorted({
        line["status"] for line in diagnostics
        if line["status"] != "matches_assumed_modifier_markup"
    })
    return {
        "assumed_markup_percentage": str(percentage),
        "modifier_diagnostics": diagnostics,
        "review_reasons": reasons,
        "requires_financial_review": bool(reasons),
        "modifier_pricing_schema_verified": False,
        "price_policy_verified": False,
        "ready_for_dispatch": False,
        "writes": False,
    }
