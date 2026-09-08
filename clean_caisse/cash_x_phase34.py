"""Phase 3.4 — X de caisse BÉCHÉFAA, lecture seule.

Le X est un état intermédiaire de la journée : il ne clôture rien et ne modifie
aucune commande. Les montants fiscaux déjà figés sur les commandes sont utilisés
quand ils existent, avec compatibilité pour les anciennes commandes.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP
from html import escape

from flask import Response, jsonify

PARIS = ZoneInfo("Europe/Paris")


def _money(value):
    try:
        return f"{Decimal(str(value or 0)):.2f}".replace(".", ",") + " €"
    except Exception:
        return "0,00 €"


def _fallback_tax(ttc):
    try:
        total = Decimal(str(ttc or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        total = Decimal("0.00")
    ht = (total / Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ht, (total - ht).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), total


def _daily_x(db, ensure_order_schema):
    now = datetime.now(PARIS)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    with db() as conn:
        ensure_order_schema(conn)
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ttc NUMERIC(12,2)")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ht NUMERIC(12,2)")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_rate NUMERIC(6,3)")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(12,2)")
        conn.commit()
        rows = conn.execute(
            """SELECT num, payment, status, total, total_ttc, total_ht, tax_amount, created_at
               FROM caisse_orders
               WHERE created_at >= %s AND created_at <= %s
               ORDER BY num""",
            (start_ms, end_ms),
        ).fetchall()

    total_ht = Decimal("0.00")
    total_tax = Decimal("0.00")
    total_ttc = Decimal("0.00")
    payments = {}
    statuses = {}
    for row in rows:
        fallback_ht, fallback_tax, fallback_ttc = _fallback_tax(row.get("total"))
        ht = Decimal(str(row.get("total_ht") if row.get("total_ht") is not None else fallback_ht))
        tax = Decimal(str(row.get("tax_amount") if row.get("tax_amount") is not None else fallback_tax))
        ttc = Decimal(str(row.get("total_ttc") if row.get("total_ttc") is not None else fallback_ttc))
        total_ht += ht
        total_tax += tax
        total_ttc += ttc
        payment = str(row.get("payment") or "À ENCAISSER")
        payments[payment] = payments.get(payment, Decimal("0.00")) + ttc
        status = str(row.get("status") or "")
        statuses[status] = statuses.get(status, 0) + 1

    return {
        "date": start.strftime("%d/%m/%Y"),
        "generated_at": now.strftime("%d/%m/%Y %H:%M:%S"),
        "count": len(rows),
        "total_ht": total_ht.quantize(Decimal("0.01")),
        "tax_amount": total_tax.quantize(Decimal("0.01")),
        "total_ttc": total_ttc.quantize(Decimal("0.01")),
        "payments": payments,
        "statuses": statuses,
    }


def register_cash_x_phase34(app, db, ensure_order_schema):
    @app.get("/api/caisse/x")
    def cash_x_api():
        try:
            x = _daily_x(db, ensure_order_schema)
            return jsonify({
                "ok": True,
                "type": "X",
                "read_only": True,
                "date": x["date"],
                "generated_at": x["generated_at"],
                "orders": x["count"],
                "total_ht": float(x["total_ht"]),
                "tax_rate": 10.0,
                "tax_amount": float(x["tax_amount"]),
                "total_ttc": float(x["total_ttc"]),
                "payments": {k: float(v) for k, v in x["payments"].items()},
                "statuses": x["statuses"],
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "X de caisse indisponible", "detail": str(exc)}), 500

    @app.get("/caisse/x")
    def cash_x_page():
        try:
            x = _daily_x(db, ensure_order_schema)
        except Exception as exc:
            return Response(f"X de caisse indisponible : {escape(str(exc))}", status=500, content_type="text/plain; charset=utf-8")

        payment_rows = "".join(
            f'<div class="row"><span>{escape(name)}</span><strong>{_money(amount)}</strong></div>'
            for name, amount in sorted(x["payments"].items())
        ) or '<div class="muted">Aucun paiement enregistré.</div>'
        status_rows = "".join(
            f'<div class="row"><span>{escape(name or "Sans statut")}</span><strong>{count}</strong></div>'
            for name, count in sorted(x["statuses"].items())
        ) or '<div class="muted">Aucune commande.</div>'

        html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>X de caisse</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f5f7;color:#17191c;font-family:Arial,sans-serif}}.top{{background:#111827;color:#fff;padding:14px 22px;display:flex;align-items:center;gap:10px}}.top b{{font-size:21px}}.top a{{margin-left:auto;color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700}}.wrap{{max-width:760px;margin:28px auto;padding:0 18px}}.card{{background:#fff;border-radius:14px;padding:22px;box-shadow:0 1px 3px #0001}}h1{{margin:0 0 4px}}.sub{{color:#666;margin-bottom:20px}}.notice{{background:#eef6ff;border:1px solid #bfdbfe;padding:11px 13px;border-radius:9px;font-weight:700;margin-bottom:18px}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.metric{{background:#f7f7f8;border-radius:10px;padding:14px}}.metric span{{display:block;color:#666;font-size:13px}}.metric strong{{font-size:24px}}h2{{font-size:17px;margin:22px 0 8px}}.row{{display:flex;justify-content:space-between;border-top:1px solid #eee;padding:9px 0}}.muted{{color:#777}}.actions{{display:flex;gap:10px;margin-top:20px}}button{{border:0;background:#111827;color:#fff;padding:11px 16px;border-radius:8px;font-weight:800;cursor:pointer}}@media(max-width:560px){{.grid{{grid-template-columns:1fr}}}}@media print{{.top,.actions,.notice{{display:none}}body{{background:#fff}}.wrap{{margin:0;max-width:none}}.card{{box-shadow:none;padding:0}}}}
</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><a href="/pos">Retour caisse</a></div><main class="wrap"><section class="card"><h1>X de caisse</h1><div class="sub">{escape(x['date'])} • généré le {escape(x['generated_at'])}</div><div class="notice">État intermédiaire en lecture seule — aucune clôture n'est effectuée.</div><div class="grid"><div class="metric"><span>Commandes</span><strong>{x['count']}</strong></div><div class="metric"><span>CA TTC</span><strong>{_money(x['total_ttc'])}</strong></div><div class="metric"><span>CA HT</span><strong>{_money(x['total_ht'])}</strong></div><div class="metric"><span>TVA 10 %</span><strong>{_money(x['tax_amount'])}</strong></div></div><h2>Répartition des paiements</h2>{payment_rows}<h2>État des commandes</h2>{status_rows}<div class="actions"><button onclick="window.print()">Imprimer le X</button></div></section></main></body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")
