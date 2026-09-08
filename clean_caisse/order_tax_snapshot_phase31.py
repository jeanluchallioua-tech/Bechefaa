"""Phase 3.1 — mémorisation fiscale HT / TVA / TTC des commandes.

Règle validée : les prix catalogue restent TTC. Pour chaque nouvelle commande ou
modification, le serveur mémorise un snapshot fiscal avec TVA à 10 %.

Aucune modification du catalogue. Aucune suppression de données historiques.
"""
from decimal import Decimal, ROUND_HALF_UP

from flask import jsonify, request

TAX_RATE = Decimal("10.00")
VAT_DIVISOR = Decimal("1.10")
CENT = Decimal("0.01")


def _fiscal_from_ttc(value):
    ttc = Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    ht = (ttc / VAT_DIVISOR).quantize(CENT, rounding=ROUND_HALF_UP)
    tax = (ttc - ht).quantize(CENT, rounding=ROUND_HALF_UP)
    return ht, tax, ttc


def _is_order_write():
    if request.method == "POST" and request.path == "/api/orders":
        return True
    if request.method == "PUT" and request.path.startswith("/api/orders/"):
        suffix = request.path[len("/api/orders/"):].strip("/")
        return bool(suffix) and "/" not in suffix
    return False


def _ensure_tax_columns(conn):
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ht NUMERIC(12,2) NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_rate NUMERIC(5,2) NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(12,2) NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ttc NUMERIC(12,2) NULL")


def register_order_tax_snapshot_phase31(app, db):
    # Prépare les colonnes avant l'écriture de commande, sans toucher au catalogue.
    @app.before_request
    def order_tax_schema_phase31():
        if not _is_order_write() and request.path != "/api/tax-phase31/status":
            return None
        try:
            with db() as conn:
                _ensure_tax_columns(conn)
                conn.commit()
        except Exception:
            # L'API métier garde la responsabilité de sa propre erreur DB.
            # Ce garde ne doit jamais transformer une panne transitoire en panne de caisse.
            return None
        return None

    # Après une écriture réussie, calcule le snapshot depuis le total serveur en base.
    @app.after_request
    def order_tax_snapshot_phase31(response):
        if not _is_order_write() or response.status_code >= 400:
            return response
        try:
            payload = response.get_json(silent=True) or {}
            order_id = str(payload.get("id") or "").strip()
            if not order_id:
                suffix = request.path[len("/api/orders/"):].strip("/") if request.method == "PUT" else ""
                order_id = suffix
            if not order_id:
                return response

            with db() as conn:
                _ensure_tax_columns(conn)
                row = conn.execute(
                    "SELECT total FROM caisse_orders WHERE id=%s FOR UPDATE",
                    (order_id,),
                ).fetchone()
                if not row:
                    return response
                ht, tax, ttc = _fiscal_from_ttc(row["total"])
                conn.execute(
                    """UPDATE caisse_orders
                       SET total_ht=%s, tax_rate=%s, tax_amount=%s, total_ttc=%s
                       WHERE id=%s""",
                    (ht, TAX_RATE, tax, ttc, order_id),
                )
                conn.commit()
        except Exception:
            # La commande reste valide même si le snapshot fiscal doit être diagnostiqué.
            pass
        return response

    @app.get("/api/tax-phase31/status")
    def order_tax_status_phase31():
        try:
            with db() as conn:
                _ensure_tax_columns(conn)
                conn.commit()
                row = conn.execute(
                    """SELECT id, num, total, total_ht, tax_rate, tax_amount, total_ttc
                       FROM caisse_orders
                       ORDER BY created_at DESC
                       LIMIT 1"""
                ).fetchone()
            latest = None
            if row:
                latest = {
                    "id": row["id"],
                    "num": row["num"],
                    "total": float(row["total"]),
                    "total_ht": None if row["total_ht"] is None else float(row["total_ht"]),
                    "tax_rate": None if row["tax_rate"] is None else float(row["tax_rate"]),
                    "tax_amount": None if row["tax_amount"] is None else float(row["tax_amount"]),
                    "total_ttc": None if row["total_ttc"] is None else float(row["total_ttc"]),
                }
            return jsonify({
                "ok": True,
                "phase": "3.1",
                "taxRate": 10.0,
                "catalogPricesRemainTTC": True,
                "latestOrder": latest,
            })
        except Exception as exc:
            return jsonify({"ok": False, "phase": "3.1", "error": str(exc)}), 500
