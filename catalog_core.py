"""BÉCHÉFAA catalogue domain model.

This module is deliberately side-effect free: importing it never rewrites static files,
never touches Flask routes and never mutates the database.  It is the future single
source of truth used by POS and site adapters.
"""
from copy import deepcopy
import re
import unicodedata

PRICE_EXTRA = "extra"
PRICE_ABSOLUTE = "absolute"


def norm(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _choice(raw):
    if isinstance(raw, (list, tuple)):
        name = str(raw[0] if raw else "Option")
        price = float(raw[1] if len(raw) > 1 and raw[1] not in (None, "") else 0)
        return [name, price]
    if isinstance(raw, dict):
        name = str(raw.get("name") or raw.get("label") or "Option")
        price = float(raw.get("price") or raw.get("extra") or 0)
        return [name, price]
    return [str(raw or "Option"), 0.0]


def normalize_group(group):
    g = dict(group or {})
    title = str(g.get("title") or g.get("name") or g.get("key") or "Options").strip()
    mode = g.get("priceMode")
    if mode not in (PRICE_EXTRA, PRICE_ABSOLUTE):
        mode = PRICE_EXTRA
    return {
        "key": str(g.get("key") or "").strip(),
        "title": title,
        "required": bool(g.get("required", False)),
        "max": max(0, int(g.get("max", 1) or 0)),
        "priceMode": mode,
        "choices": [_choice(x) for x in (g.get("choices") or [])],
    }


def normalize_product(product):
    p = dict(product or {})
    availability = str(p.get("availability") or ("available" if p.get("active", True) else "disabled")).strip().lower()
    if availability not in {"available", "soldout", "disabled"}:
        availability = "available"
    active = availability != "disabled"
    channels = dict(p.get("channels") or {"caisse": True, "site": True, "ubereats": False, "deliveroo": False})
    raw_soldout = dict(p.get("channelSoldout") or {})
    channel_soldout = {key: bool(raw_soldout.get(key, False)) for key in ("caisse", "site", "ubereats", "deliveroo")}
    return {
        "id": str(p.get("id") or "").strip(),
        "category": str(p.get("category") or p.get("cat") or "").strip(),
        "name": str(p.get("name") or "Produit").strip(),
        "price": float(p.get("price") or 0),
        "photo": str(p.get("photo") or p.get("image") or ""),
        "ingredients": str(p.get("ingredients") or p.get("desc") or ""),
        "active": active,
        "availability": availability,
        "channels": channels,
        "channelSoldout": channel_soldout,
        "options": [normalize_group(g) for g in (p.get("options") or [])],
        "optionSelections": deepcopy(p.get("optionSelections") or {}),
    }


def normalize_catalogue(data):
    src = dict(data or {})
    categories = []
    seen = set()
    for index, raw in enumerate(src.get("categories") or []):
        if isinstance(raw, str):
            c = {"id": f"cat-{index}", "name": raw, "active": True, "order": index}
        else:
            c = dict(raw or {})
            c = {
                "id": str(c.get("id") or f"cat-{index}"),
                "name": str(c.get("name") or "").strip(),
                "active": bool(c.get("active", True)),
                "order": int(c.get("order", index) or 0),
            }
        if not c["name"] or norm(c["name"]) in seen:
            continue
        seen.add(norm(c["name"]))
        categories.append(c)

    out = {
        "categories": categories,
        "products": [normalize_product(p) for p in (src.get("products") or [])],
        "optionLists": deepcopy(src.get("optionLists") or {}),
        "optionListDefs": deepcopy(src.get("optionListDefs") or {}),
        "schemaVersion": 1,
    }
    for key, value in src.items():
        if key not in out:
            out[key] = deepcopy(value)
    return out


def validate_catalogue(data):
    cat = normalize_catalogue(data)
    errors = []
    category_names = {c["name"] for c in cat["categories"] if c["active"]}
    ids = set()
    for p in cat["products"]:
        if not p["id"]:
            errors.append(f"Produit sans identifiant: {p['name']}")
        elif p["id"] in ids:
            errors.append(f"Identifiant produit en double: {p['id']}")
        ids.add(p["id"])
        if not p["name"]:
            errors.append(f"Produit {p['id']} sans nom")
        if p["category"] and p["category"] not in category_names:
            errors.append(f"Catégorie inconnue pour {p['name']}: {p['category']}")
        for group in p["options"]:
            if group["priceMode"] == PRICE_ABSOLUTE and group["max"] != 1:
                errors.append(f"{p['name']} / {group['title']}: un prix total doit être un choix unique")
    return errors


def product_unit_price(product, selections, channel="CAISSE"):
    """Return final unit price from structured selections.

    `absolute` groups replace the base price (ex: 5 pièces=8 €, 10 pièces=15 €).
    `extra` groups are then added. Uber Eats / Deliveroo get the configured 15% POS markup.
    """
    p = normalize_product(product)
    groups = {g["key"]: g for g in p["options"]}
    base = p["price"]
    extra = 0.0
    for key, values in (selections or {}).items():
        group = groups.get(key)
        if not group:
            continue
        chosen = values if isinstance(values, list) else [values]
        prices = []
        for item in chosen:
            if isinstance(item, dict):
                prices.append(float(item.get("price") or 0))
            elif isinstance(item, (list, tuple)) and len(item) > 1:
                prices.append(float(item[1] or 0))
        if group["priceMode"] == PRICE_ABSOLUTE and prices:
            base = prices[0]
        else:
            extra += sum(prices)
    total = base + extra
    if str(channel).upper() in {"UBER EATS", "DELIVEROO"}:
        total *= 1.15
    return round(total + 1e-9, 2)
