"""Phase 4.4 — prévisualisation isolée du fond de caisse BÉCHÉFAA.

Lecture seule. Ne modifie ni le X, ni le Z, ni les paiements. Cette page montre
le calcul prévu : fond initial + ventes espèces réussies = tiroir théorique.
"""
from datetime import datetime
from decimal import Decimal
from html import escape
from zoneinfo import ZoneInfo

from flask import Response

PARIS = ZoneInfo("Europe/Paris")
PREVIEW_FLOAT = Decimal("40.00")


def _eur(value):
    return f"{Decimal(str(value or 0)):.2f} €".replace(".", ",")


def register_cash_float_test_phase44(app, db):
    @app.get("/maintenance/phase44/cash-float-test")
    def cash_float_test_phase44():
        now = datetime.now(PARIS)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)
        try:
            with db() as conn:
                row = conn.execute("""
                    SELECT COALESCE(SUM(t.amount),0) AS cash_sales,
                           COUNT(*) AS cash_payments
                    FROM caisse_payment_transactions t
                    JOIN caisse_orders o ON o.id=t.order_id
                    WHERE t.transaction_type='PAYMENT'
                      AND t.status='SUCCEEDED'
                      AND UPPER(t.method) IN ('ESPÈCES','ESPECES')
                      AND t.created_at >= %s AND t.created_at <= %s
                """, (start_ms, end_ms)).fetchone()
            cash_sales = Decimal(str(row["cash_sales"] or 0))
            theoretical = PREVIEW_FLOAT + cash_sales
            html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fond de caisse Phase 4.4</title><style>
body{{font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c;padding:22px}}.box{{max-width:720px;margin:auto;background:#fff;border-radius:15px;padding:24px}}.note{{background:#eef6ff;border:1px solid #bfdbfe;border-radius:9px;padding:12px;margin:15px 0}}.row{{display:flex;justify-content:space-between;border-top:1px solid #eee;padding:13px 0}}.total{{font-size:21px;font-weight:800}}.muted{{color:#64748b}}
</style></head><body><div class="box"><h1>Fond de caisse — prévisualisation</h1><p class="muted">{escape(now.strftime("%d/%m/%Y %H:%M"))} · lecture seule</p><div class="note">Aucun montant n'est enregistré par cette page. Le fond de 40,00 € sert uniquement à vérifier le futur calcul.</div>
<div class="row"><span>Fond initial simulé</span><strong>{_eur(PREVIEW_FLOAT)}</strong></div>
<div class="row"><span>Ventes espèces du jour ({int(row['cash_payments'])} paiement(s))</span><strong>+ {_eur(cash_sales)}</strong></div>
<div class="row total"><span>Espèces théoriques dans le tiroir</span><strong>{_eur(theoretical)}</strong></div>
<p class="muted">Les remboursements électroniques, CB, SumUp et Stripe n'affectent pas ce calcul.</p></div></body></html>'''
            return Response(html, mimetype="text/html")
        except Exception as exc:
            return Response("Prévisualisation fond de caisse indisponible : " + escape(str(exc)), status=500, mimetype="text/plain")
