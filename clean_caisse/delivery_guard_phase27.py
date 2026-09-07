"""Phase 2.7 — validation serveur des commandes Livraison.

Aucun frais de livraison. Le contrôle s'applique uniquement à POST /api/orders
pour une commande Livraison et vérifie la ville configurée ainsi que le minimum
de commande de sa zone.

Le code postal n'est plus obligatoire pour accepter une livraison : la ville est
la référence métier. S'il est présent, il sert à départager d'éventuels doublons.
"""
from decimal import Decimal, InvalidOperation

from flask import jsonify, request


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Montant de commande invalide")


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


def register_delivery_guard_phase27(app, db):
    @app.before_request
    def delivery_guard_phase27():
        if request.method != "POST" or request.path != "/api/orders":
            return None

        payload = request.get_json(silent=True) or {}
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

        try:
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
                rows = conn.execute(
                    """SELECT c.city,c.postal_code,z.code,z.minimum_order
                       FROM caisse_delivery_cities c
                       JOIN caisse_delivery_zones z ON z.code=c.zone_code
                       WHERE c.active=TRUE AND z.active=TRUE
                         AND LOWER(TRIM(c.city))=LOWER(TRIM(%s))
                       ORDER BY c.id""",
                    (city,),
                ).fetchall()

            if not rows:
                return jsonify({
                    "ok": False,
                    "error": "Ville hors zone de livraison",
                    "reason": "OUT_OF_ZONE",
                    "postal_code": postal_code,
                    "city": city,
                }), 409

            # Si plusieurs entrées portent le même nom de ville, le code postal
            # permet de sélectionner la bonne. Sans code postal, on n'accepte
            # que si toutes les entrées correspondent à la même zone/minimum.
            if postal_code:
                postal_rows = [r for r in rows if str(r["postal_code"]) == postal_code]
                if postal_rows:
                    rows = postal_rows

            signatures = {(str(r["code"]), _money(r["minimum_order"])) for r in rows}
            if len(signatures) != 1:
                return jsonify({
                    "ok": False,
                    "error": "Ville ambiguë : précisez le code postal",
                    "reason": "AMBIGUOUS_CITY",
                    "city": city,
                }), 409

            zone_code, minimum = next(iter(signatures))
            if total < minimum:
                return jsonify({
                    "ok": False,
                    "error": f"Minimum de commande non atteint : {minimum:.2f} € minimum pour {city}",
                    "reason": "MINIMUM_NOT_REACHED",
                    "zone": zone_code,
                    "minimum_order": float(minimum),
                    "order_total": float(total),
                    "missing_amount": float((minimum - total).quantize(Decimal("0.01"))),
                    "city": city,
                }), 409

        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Validation livraison impossible",
                "detail": str(exc),
            }), 503

        return None
