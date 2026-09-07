"""Phase 2.7 — validation serveur des commandes Livraison.

Portée volontairement limitée à POST /api/orders avec ticket_type=Livraison.
Aucun frais de livraison n'est ajouté. Le serveur vérifie seulement :
- adresse + code postal + ville présents ;
- ville/code postal dans une zone active ;
- minimum de commande de la zone atteint.

Le module est enregistré après le verrouillage des prix Phase 2.6 : le total utilisé ici
est donc composé de lignes dont le prix unitaire a déjà été validé côté serveur.
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
        ticket_type = str(payload.get("ticket_type") or "").strip().lower()
        if ticket_type != "livraison":
            return None

        customer = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
        address = str(customer.get("address") or "").strip()
        postal_code = "".join(ch for ch in str(customer.get("postal_code") or "") if ch.isdigit())[:5]
        city = str(customer.get("city") or "").strip()

        missing = []
        if not address:
            missing.append("adresse")
        if len(postal_code) != 5:
            missing.append("code postal")
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
            return None  # create_order conserve sa validation historique.

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
                row = conn.execute(
                    """SELECT c.city,c.postal_code,z.code,z.minimum_order
                       FROM caisse_delivery_cities c
                       JOIN caisse_delivery_zones z ON z.code=c.zone_code
                       WHERE c.active=TRUE AND z.active=TRUE
                         AND c.postal_code=%s
                         AND LOWER(c.city)=LOWER(%s)
                       LIMIT 2""",
                    (postal_code, city),
                ).fetchall()

            if len(row) != 1:
                return jsonify({
                    "ok": False,
                    "error": "Adresse hors zone de livraison",
                    "reason": "OUT_OF_ZONE",
                    "postal_code": postal_code,
                    "city": city,
                }), 409

            zone = row[0]
            minimum = _money(zone["minimum_order"])
            if total < minimum:
                return jsonify({
                    "ok": False,
                    "error": "Minimum de commande non atteint pour la livraison",
                    "reason": "MINIMUM_NOT_REACHED",
                    "zone": zone["code"],
                    "minimum_order": float(minimum),
                    "order_total": float(total),
                    "missing_amount": float((minimum - total).quantize(Decimal("0.01"))),
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
