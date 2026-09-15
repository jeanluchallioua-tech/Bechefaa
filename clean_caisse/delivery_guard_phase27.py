"""Phase 2.7 — verrouillage serveur des commandes Livraison provenant du SITE.

Le SITE public doit respecter les villes et minimums configurés dans
Administration -> Zones de livraison. Les commandes saisies directement sur la
Caisse restent libres : l'opérateur décide lui-même d'accepter une livraison,
même hors zone ou sous le minimum.
"""
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import jsonify, request


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Montant de commande invalide")


def _norm_city(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _ensure_delivery_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS caisse_delivery_zones (
        code TEXT PRIMARY KEY,
        minimum_order NUMERIC(12,2) NOT NULL DEFAULT 0,
        active BOOLEAN NOT NULL DEFAULT TRUE
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS caisse_delivery_cities (
        id BIGSERIAL PRIMARY KEY,
        zone_code TEXT NOT NULL REFERENCES caisse_delivery_zones(code) ON DELETE CASCADE,
        postal_code TEXT NOT NULL,
        city TEXT NOT NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        UNIQUE(postal_code, city)
    )""")
    for code in ("A", "B", "C"):
        conn.execute(
            "INSERT INTO caisse_delivery_zones(code,minimum_order,active) VALUES (%s,0,TRUE) ON CONFLICT(code) DO NOTHING",
            (code,),
        )


def _validate_delivery_payload(payload, db):
    # Règle métier : le contrôle automatique des zones/minimums ne concerne que
    # les commandes publiques du SITE. Une commande créée directement depuis la
    # caisse doit rester à la discrétion de l'opérateur.
    sales_channel = str(payload.get("sales_channel") or "").strip().upper()
    if sales_channel != "SITE":
        return None

    ticket_type = str(payload.get("ticket_type") or payload.get("source") or "").strip().lower()
    if ticket_type not in {"livraison", "delivery"}:
        return None

    customer = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
    address = str(customer.get("address") or "").strip()
    postal_code = "".join(ch for ch in str(customer.get("postal_code") or "") if ch.isdigit())[:5]
    city = str(customer.get("city") or "").strip()

    missing = []
    if not address:
        missing.append("adresse")
    if not city:
        missing.append("ville")
    if missing:
        return jsonify({
            "ok": False,
            "error": "Adresse de livraison incomplète",
            "missing": missing,
        }), 409

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return None

    total = Decimal("0.00")
    for item in items:
        if not isinstance(item, dict):
            continue
        qty = int(item.get("qty") or 1)
        if qty < 1:
            raise ValueError("Quantité invalide")
        total += _money(item.get("unit_price", 0)) * qty
    total = total.quantize(Decimal("0.01"))

    with db() as conn:
        _ensure_delivery_schema(conn)
        conn.commit()
        rows = []

        if postal_code:
            rows = conn.execute(
                """SELECT c.city,c.postal_code,z.code,z.minimum_order
                   FROM caisse_delivery_cities c
                   JOIN caisse_delivery_zones z ON z.code=c.zone_code
                   WHERE c.active=TRUE AND z.active=TRUE AND c.postal_code=%s
                   ORDER BY c.id""",
                (postal_code,),
            ).fetchall()

        if not rows:
            candidates = conn.execute(
                """SELECT c.city,c.postal_code,z.code,z.minimum_order
                   FROM caisse_delivery_cities c
                   JOIN caisse_delivery_zones z ON z.code=c.zone_code
                   WHERE c.active=TRUE AND z.active=TRUE
                   ORDER BY c.id"""
            ).fetchall()
            wanted = _norm_city(city)
            rows = [r for r in candidates if _norm_city(r["city"]) == wanted]

    if not rows:
        return jsonify({
            "ok": False,
            "error": f"{city} n'est pas dans une zone de livraison autorisée",
            "reason": "OUT_OF_ZONE",
            "city": city,
            "postal_code": postal_code,
        }), 409

    signatures = {(str(r["code"]), _money(r["minimum_order"])) for r in rows}
    if len(signatures) != 1:
        return jsonify({
            "ok": False,
            "error": "Ville ou code postal ambigu : vérifiez l'adresse",
            "reason": "AMBIGUOUS_CITY",
            "city": city,
            "postal_code": postal_code,
        }), 409

    zone_code, minimum = next(iter(signatures))
    if total < minimum:
        missing_amount = (minimum - total).quantize(Decimal("0.01"))
        return jsonify({
            "ok": False,
            "error": f"Commande refusée : minimum {minimum:.2f} € pour {city} (panier {total:.2f} €)",
            "reason": "MINIMUM_NOT_REACHED",
            "zone": zone_code,
            "minimum_order": float(minimum),
            "order_total": float(total),
            "missing_amount": float(missing_amount),
            "city": city,
            "postal_code": postal_code,
        }), 409

    return None


def register_delivery_guard_phase27(app, db):
    original = app.view_functions.get("create_order")
    if original is None:
        raise RuntimeError("Endpoint create_order introuvable pour la Phase 2.7")

    @wraps(original)
    def create_order_with_delivery_guard(*args, **kwargs):
        payload = request.get_json(silent=True) or {}
        try:
            rejection = _validate_delivery_payload(payload, db)
            if rejection is not None:
                return rejection
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Validation livraison impossible",
                "detail": str(exc),
            }), 503
        return original(*args, **kwargs)

    app.view_functions["create_order"] = create_order_with_delivery_guard

    @app.get("/api/delivery-guard-phase27/status")
    def delivery_guard_phase27_status():
        try:
            with db() as conn:
                _ensure_delivery_schema(conn)
                conn.commit()
                zones = conn.execute(
                    """SELECT z.code,z.minimum_order,z.active,c.city,c.postal_code,c.active AS city_active
                       FROM caisse_delivery_zones z
                       LEFT JOIN caisse_delivery_cities c ON c.zone_code=z.code
                       ORDER BY z.code,c.city,c.postal_code"""
                ).fetchall()
            return jsonify({
                "ok": True,
                "phase": "2.7",
                "guard": "site-only-endpoint-wrapper",
                "create_order_wrapped": app.view_functions.get("create_order") is create_order_with_delivery_guard,
                "zones": [dict(r) for r in zones],
            })
        except Exception as exc:
            return jsonify({"ok": False,"phase":"2.7","error":str(exc)}),500
