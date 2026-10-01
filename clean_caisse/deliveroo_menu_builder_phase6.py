"""Phase 6 — construction du menu Deliveroo depuis le catalogue BÉCHÉFAA.

Ce module ne pousse rien chez Deliveroo. Il construit un aperçu conforme au modèle
Menu API afin de valider catégories, ITEM, CHOICE, modifiers, PLU et prix majorés
avant tout upload Sandbox.
"""
import hashlib
import json
import re
from urllib.parse import quote
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import jsonify

CENT = Decimal("0.01")


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _safe_id(prefix, raw, max_len=50):
    raw = str(raw or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_").lower()
    if not cleaned:
        cleaned = "x"
    candidate = f"{prefix}_{cleaned}"
    if len(candidate) <= max_len:
        return candidate
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    room = max_len - len(prefix) - len(digest) - 2
    return f"{prefix}_{cleaned[:max(1, room)]}_{digest}"[:max_len]


def _group_name(group, index):
    if not isinstance(group, dict):
        return "Groupe " + str(index + 1)
    return str(
        group.get("name")
        or group.get("label")
        or group.get("title")
        or ("Groupe " + str(index + 1))
    ).strip()


def _group_values(group):
    if not isinstance(group, dict):
        return []
    for key in ("options", "values", "items", "choices"):
        if isinstance(group.get(key), list):
            return group[key]
    return []


def _choice(raw, index):
    if isinstance(raw, (list, tuple)):
        name = str(raw[0] if raw else "").strip()
        price = _money(raw[1] if len(raw) > 1 else 0)
        choice_id = ""
    elif isinstance(raw, dict):
        name = str(
            raw.get("name")
            or raw.get("label")
            or raw.get("title")
            or raw.get("value")
            or raw.get("id")
            or ""
        ).strip()
        price = _money(
            raw.get("price")
            or raw.get("extraPrice")
            or raw.get("supplement")
            or 0
        )
        choice_id = str(raw.get("id") or "").strip()
    else:
        name = str(raw or "").strip()
        price = Decimal("0.00")
        choice_id = ""
    return {"name": name, "price": price, "source_id": choice_id, "index": index}


def _deliveroo_required_group(name, source_required=False):
    """Règles de composition obligatoires pour le menu Deliveroo.

    On conserve toute obligation déjà définie dans la caisse et on complète
    uniquement les groupes qui constituent clairement le produit vendu.
    Les personnalisations (retraits, suppléments, sauces, ingrédients libres)
    restent facultatives.
    """
    if source_required:
        return True
    n = str(name or "").strip().lower()
    required_exact = {
        "boisson",
        "type de tender",
        "nombre de tender",
        "oignons rings",
        "choix du poulet",
        "accompagnement",
        "type assiette de poulet",
        "choix du pain",
        "choix des viandes",
    }
    return n in required_exact


def _modifier_type(name):
    n = str(name or "").lower()
    if any(x in n for x in ("cuisson", "cooking")):
        return "cooking-instruction"
    if any(x in n for x in ("retirer", "sans ", "sans-", "garniture")):
        return "remove-ingredient"
    if any(x in n for x in ("pain", "viande", "poulet", "tender", "taille", "size")):
        return "product-variation"
    if any(x in n for x in ("boisson", "drink")):
        return "up-sell-existing-items"
    if any(x in n for x in ("sauce", "condiment")):
        return "add-separate-condiment"
    return "add-ingredient"


def _markup_percentage(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS marketplace_markup_settings(
        channel TEXT PRIMARY KEY,
        percentage NUMERIC(6,2) NOT NULL DEFAULT 15.00,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    conn.execute(
        """INSERT INTO marketplace_markup_settings(channel,percentage)
           VALUES('DELIVEROO',15.00) ON CONFLICT(channel) DO NOTHING"""
    )
    row = conn.execute(
        "SELECT percentage FROM marketplace_markup_settings WHERE channel='DELIVEROO'"
    ).fetchone()
    return _money(row["percentage"] if row else 15)


def _marked_price(value, percentage):
    base = _money(value)
    factor = Decimal("1.00") + (percentage / Decimal("100"))
    return (base * factor).quantize(CENT, rounding=ROUND_HALF_UP)


def _cents(value):
    return int((_money(value) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _catalog(conn):
    row = conn.execute(
        "SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1"
    ).fetchone()
    if not row:
        raise RuntimeError("Catalogue BÉCHÉFAA introuvable")
    data = json.loads(row["data_json"] or "{}")
    if not isinstance(data, dict):
        raise RuntimeError("Catalogue BÉCHÉFAA invalide")
    return data


def build_deliveroo_menu_preview(db):
    with db() as conn:
        data = _catalog(conn)
        markup = _markup_percentage(conn)
        conn.commit()

    raw_categories = [
        c for c in (data.get("categories") or [])
        if isinstance(c, dict) and c.get("active", True) is not False
    ]
    raw_products = [
        p for p in (data.get("products") or [])
        if isinstance(p, dict)
        and p.get("active", True) is not False
        and p.get("marketplace_visible", True) is not False
        and p.get("deliveroo_visible", True) is not False
    ]

    categories = []
    category_map = {}
    for index, cat in enumerate(raw_categories):
        name = str(cat.get("name") or "").strip()
        if not name:
            continue
        cid = _safe_id("cat", cat.get("id") or name)
        category_map[name] = cid
        categories.append({
            "id": cid,
            "name": {"fr": name},
            "description": {},
            "item_ids": [],
            "_order": index,
        })

    items = []
    modifiers = []
    mapping = {"products": {}, "choices": {}}
    warnings = []

    for product_index, product in enumerate(raw_products):
        pos_id = str(product.get("id") or "").strip()
        name = str(product.get("name") or "").strip()
        category_name = str(product.get("category") or "").strip()
        if not pos_id or not name:
            warnings.append({
                "type": "product_skipped",
                "product_index": product_index,
                "reason": "id_or_name_missing",
            })
            continue

        item_id = _safe_id("item", pos_id)
        modifier_ids = []
        mapping["products"][item_id] = {
            "pos_item_id": pos_id,
            "name": name,
            "category": category_name,
        }

        groups = product.get("options") if isinstance(product.get("options"), list) else []
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            group_name = _group_name(group, group_index)
            values = _group_values(group)
            parsed_choices = [
                _choice(raw, choice_index)
                for choice_index, raw in enumerate(values)
            ]
            parsed_choices = [x for x in parsed_choices if x["name"]]
            if not parsed_choices:
                warnings.append({
                    "type": "empty_modifier",
                    "product_id": pos_id,
                    "product": name,
                    "group": group_name,
                })
                continue

            modifier_id = _safe_id(
                "mod",
                f"{pos_id}_{group.get('id') or group_name}_{group_index}",
            )
            choice_ids = []
            for choice in parsed_choices:
                raw_choice_id = choice["source_id"] or str(choice["index"] + 1)
                choice_item_id = _safe_id(
                    "choice",
                    f"{pos_id}_{group_index}_{raw_choice_id}_{choice['name']}",
                )
                # Le PLU du CHOICE reste stable et décodable côté caisse pour les commandes entrantes.
                choice_plu = f"opt:{pos_id}:{group_index}:{choice['index']}"
                if len(choice_plu) > 50:
                    choice_plu = "opt_" + hashlib.sha1(choice_plu.encode("utf-8")).hexdigest()[:32]

                choice_price = _marked_price(choice["price"], markup) if choice["price"] > 0 else Decimal("0.00")
                items.append({
                    "id": choice_item_id,
                    "type": "CHOICE",
                    "name": {"fr": choice["name"]},
                    "description": {},
                    "operational_name": choice["name"][:120],
                    "plu": choice_plu,
                    "price_info": {
                        "price": _cents(choice_price),
                        "overrides": [],
                    },
                    "modifier_ids": [],
                    "contains_alcohol": False,
                    "tax_rate": "10.0",
                    "allergies": [],
                    "diets": [],
                    "classifications": [],
                    "external_data": json.dumps({
                        "bechefaa_product_id": pos_id,
                        "bechefaa_group_index": group_index,
                        "bechefaa_choice_index": choice["index"],
                    }, ensure_ascii=False),
                })
                choice_ids.append(choice_item_id)
                mapping["choices"][choice_item_id] = {
                    "pos_item_id": choice_plu,
                    "product_id": pos_id,
                    "group_index": group_index,
                    "group": group_name,
                    "choice_index": choice["index"],
                    "choice": choice["name"],
                    "base_extra": float(choice["price"]),
                    "deliveroo_extra": float(choice_price),
                }

            source_required = bool(group.get("required", False))
            required = _deliveroo_required_group(group_name, source_required)
            raw_max = (
                group.get("max")
                or group.get("maxChoices")
                or group.get("maximum")
                or 0
            )
            try:
                maximum = int(raw_max or 0)
            except (ValueError, TypeError):
                maximum = 0
                warnings.append({
                    "type": "invalid_max",
                    "product_id": pos_id,
                    "group": group_name,
                    "raw": raw_max,
                })
            if maximum <= 0:
                maximum = len(choice_ids)
            maximum = min(maximum, len(choice_ids))
            minimum = 1 if required else 0
            if minimum > maximum:
                minimum = maximum

            modifier_description = {
                "cuisson": "Choisissez la cuisson souhaitée.",
                "retirer garniture": "Retirez les ingrédients que vous ne souhaitez pas.",
                "suppléments": "Ajoutez les suppléments de votre choix.",
                "choix des sauces supplémentaire": "Ajoutez les sauces supplémentaires de votre choix.",
                "choix du poulet": "Choisissez votre préparation de poulet.",
                "accompagnement": "Choisissez votre accompagnement.",
                "choix du pain": "Choisissez votre pain.",
                "choix des viandes": "Choisissez votre viande.",
                "type de tender": "Choisissez le type de tender.",
                "nombre de tender": "Choisissez le nombre de tenders.",
                "oignons rings": "Choisissez votre option d'oignons rings.",
                "type assiette de poulet": "Choisissez le type d'assiette de poulet.",
                "boisson": "Choisissez votre boisson.",
            }.get(group_name.strip().lower(), "Choisissez parmi les options proposées.")

            modifiers.append({
                "id": modifier_id,
                "name": {"fr": group_name},
                "description": {"fr": modifier_description},
                "item_ids": choice_ids,
                "min_selection": minimum,
                "max_selection": maximum,
                "repeatable": False,
                "type": _modifier_type(group_name),
            })
            modifier_ids.append(modifier_id)

        base_price = _money(product.get("price", 0))
        deliveroo_price = _marked_price(base_price, markup)
        description = str(
            product.get("ingredients")
            or product.get("description")
            or product.get("desc")
            or ""
        ).strip()
        photo = str(product.get("photo") or "").strip()

        main_item = {
            "id": item_id,
            "type": "ITEM",
            "name": {"fr": name},
            "description": {"fr": description} if description else {},
            "operational_name": name[:120],
            "plu": pos_id[:50],
            "price_info": {
                "price": _cents(deliveroo_price),
                "overrides": [],
            },
            "modifier_ids": modifier_ids,
            "contains_alcohol": False,
            "tax_rate": "10.0",
            "allergies": [],
            "diets": (
                ["dairy_free", "vegetarian"] if pos_id in {"21", "23"}
                else ["dairy_free"]
            ),
            "classifications": [],
            "external_data": json.dumps({
                "bechefaa_product_id": pos_id,
                "base_price": float(base_price),
                "markup_percentage": float(markup),
            }, ensure_ascii=False),
        }
        if photo.startswith("http://") or photo.startswith("https://"):
            main_item["image"] = {"url": photo}
        elif photo:
            main_item["image"] = {
                "url": "https://caisse.bechefaa.fr/api/public/catalog/photo-marketplace/deliveroo/" + quote(pos_id, safe="")
            }
        items.append(main_item)

        category_id = category_map.get(category_name)
        if category_id:
            next(c for c in categories if c["id"] == category_id)["item_ids"].append(item_id)
        else:
            warnings.append({
                "type": "category_missing",
                "product_id": pos_id,
                "product": name,
                "category": category_name,
            })

    # Scenario Deliveroo Bundles: la Formule Falafel (POS 2) devient un vrai BUNDLE
    # composé d'ITEMs déjà présents dans le menu. Cette transformation ne modifie
    # jamais le catalogue caisse.
    by_id = {x.get("id"): x for x in items if isinstance(x, dict)}
    bundle = by_id.get("item_2")
    if bundle:
        bundle_main_mod = "bundle_2_main"
        bundle_side_mod = "bundle_2_side"
        bundle_drink_mod = "bundle_2_drink"

        bundle["type"] = "BUNDLE"
        bundle["modifier_ids"] = [bundle_main_mod, bundle_side_mod, bundle_drink_mod]

        bundle_sections = [
            {
                "id": bundle_main_mod,
                "name": {"fr": "Sandwich"},
                "description": {"fr": "Choisissez le sandwich de la formule."},
                "item_ids": ["item_42"],
                "min_selection": 1,
                "max_selection": 1,
                "repeatable": False,
                "type": "bundle-item",
            },
            {
                "id": bundle_side_mod,
                "name": {"fr": "Accompagnement"},
                "description": {"fr": "Choisissez l’accompagnement de la formule."},
                "item_ids": ["item_63"],
                "min_selection": 1,
                "max_selection": 1,
                "repeatable": False,
                "type": "bundle-item",
            },
            {
                "id": bundle_drink_mod,
                "name": {"fr": "Boisson"},
                "description": {"fr": "Choisissez la boisson de la formule."},
                "item_ids": [
                    x for x in (
                        "item_68", "item_70", "item_71", "item_72",
                        "item_73", "item_74", "item_75", "item_76"
                    ) if x in by_id
                ],
                "min_selection": 1,
                "max_selection": 1,
                "repeatable": False,
                "type": "bundle-item",
            },
        ]

        def add_bundle_zero_price(child_id, modifier_id):
            child = by_id.get(child_id)
            if not child:
                warnings.append({
                    "type": "bundle_item_missing",
                    "bundle_id": "item_2",
                    "item_id": child_id,
                })
                return
            child.setdefault("price_info", {}).setdefault("overrides", []).append({
                "type": "ITEM",
                "id": "item_2",
                "context_id": modifier_id,
                "price": 0,
            })

        add_bundle_zero_price("item_42", bundle_main_mod)
        add_bundle_zero_price("item_63", bundle_side_mod)
        for drink_id in bundle_sections[2]["item_ids"]:
            add_bundle_zero_price(drink_id, bundle_drink_mod)

        modifiers.extend(bundle_sections)

    categories = [
        {k: v for k, v in c.items() if k != "_order"}
        for c in categories if c["item_ids"]
    ]

    payload = {
        "name": "BÉCHÉFAA",
        "menu": {
            "categories": categories,
            "currency_code": "EUR",
            "is_pos_integrated": True,
            "items": items,
            "modifiers": modifiers,
            "mealtimes": [{
                "id": "all-day",
                "name": {"fr": "Toute la journée"},
                "description": {"fr": "Menu BÉCHÉFAA"},
                "image": {"url": "https://caisse.bechefaa.fr/api/public/catalog/photo-marketplace/deliveroo/1"},
                "category_ids": [cat["id"] for cat in categories],
                "schedule": [],
            }],
        },
        "site_ids": [],
    }

    return {
        "ok": True,
        "upload_performed": False,
        "source": "catalog_admin_v2",
        "markup_channel": "DELIVEROO",
        "markup_percentage": float(markup),
        "summary": {
            "categories": len(categories),
            "main_items": sum(1 for x in items if x.get("type") == "ITEM"),
            "choice_items": sum(1 for x in items if x.get("type") == "CHOICE"),
            "bundles": sum(1 for x in items if x.get("type") == "BUNDLE"),
            "modifiers": len(modifiers),
            "required_modifiers": sum(1 for x in modifiers if int(x.get("min_selection") or 0) > 0),
            "mealtimes": 1,
            "warnings": len(warnings),
        },
        "warnings": warnings,
        "mapping": mapping,
        "payload": payload,
    }


def register_deliveroo_menu_builder_phase6(app, db):
    @app.get("/api/deliveroo/menu-preview-phase6")
    def deliveroo_menu_preview_phase6():
        try:
            return jsonify(build_deliveroo_menu_preview(db))
        except Exception as exc:
            return jsonify({
                "ok": False,
                "upload_performed": False,
                "error": "Construction du menu Deliveroo impossible",
                "detail": str(exc),
            }), 500
