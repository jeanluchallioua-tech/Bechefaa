"""Phase 4.4 — vue de contrôle isolée du journal financier.

Lecture seule : aucune écriture, aucun changement du moteur de paiement ou de
remboursement. Affiche les transactions existantes de la commande de test #65.
"""
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from flask import Response

TEST_ORDER_ID = "caisse-1c123f071e8c4500bc798b6ec5913df3"
PARIS = ZoneInfo("Europe/Paris")


def _money(value):
    return f"{float(value or 0):.2f} €".replace(".", ",")


def _when(ms):
    if not ms:
        return "—"
    return datetime.fromtimestamp(int(ms) / 1000, tz=PARIS).strftime("%d/%m/%Y %H:%M:%S")


def _origin(provider):
    value = str(provider or "").strip().upper()
    if value == "LOCAL":
        return "Caisse"
    if value == "SUMUP":
        return "SumUp"
    if value == "STRIPE":
        return "Stripe"
    return value or "—"


def register_transaction_journal_test_phase44(app, db):
    @app.get("/maintenance/phase44/transaction-journal-test")
    def transaction_journal_test_phase44():
        try:
            with db() as conn:
                order = conn.execute(
                    "SELECT id,num,total,payment_status FROM caisse_orders WHERE id=%s LIMIT 1",
                    (TEST_ORDER_ID,),
                ).fetchone()
                if not order:
                    return Response("Commande #65 introuvable", status=404, mimetype="text/plain")
                rows = conn.execute("""
                    SELECT id,transaction_type,provider,method,amount,status,
                           external_reference,parent_transaction_id,reason,created_by,created_at
                    FROM caisse_payment_transactions
                    WHERE order_id=%s
                    ORDER BY created_at,id
                """, (TEST_ORDER_ID,)).fetchall()

            paid = sum(float(r["amount"] or 0) for r in rows if r["transaction_type"] == "PAYMENT" and r["status"] == "SUCCEEDED")
            refunded = sum(float(r["amount"] or 0) for r in rows if r["transaction_type"] == "REFUND" and r["status"] == "SUCCEEDED")
            pending = sum(float(r["amount"] or 0) for r in rows if r["transaction_type"] == "REFUND" and r["status"] == "PENDING_EXTERNAL")

            items = []
            for r in rows:
                kind = "PAIEMENT" if r["transaction_type"] == "PAYMENT" else "REMBOURSEMENT"
                sign = "+" if r["transaction_type"] == "PAYMENT" else "−"
                items.append(f'''<tr>
<td>{escape(_when(r["created_at"]))}</td><td><strong>{kind}</strong></td>
<td>{escape(_origin(r["provider"]))}</td><td>{escape(str(r["method"] or "—"))}</td>
<td><strong>{sign}{_money(r["amount"])}</strong></td><td>{escape(str(r["status"] or "—"))}</td>
<td>{escape(str(r["created_by"] or "—"))}</td><td>{escape(str(r["reason"] or "—"))}</td>
</tr>''')

            html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Journal financier Phase 4.4</title><style>
body{{font-family:Arial,sans-serif;background:#f8fafc;color:#0f172a;padding:22px}}.box{{max-width:1100px;margin:auto;background:#fff;border:1px solid #cbd5e1;border-radius:16px;padding:22px}}
.cards{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}}.card{{background:#f1f5f9;border-radius:10px;padding:12px 16px;min-width:150px}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #e2e8f0}}th{{background:#f8fafc}}.note{{color:#475569}}
</style></head><body><div class="box"><h2>Journal financier — commande #{order["num"]}</h2>
<p class="note">Vue de contrôle Phase 4.4 — lecture seule.</p>
<div class="cards"><div class="card">Statut<br><strong>{escape(str(order["payment_status"]))}</strong></div><div class="card">Payé<br><strong>{_money(paid)}</strong></div><div class="card">Remboursé<br><strong>{_money(refunded)}</strong></div><div class="card">Net payé<br><strong>{_money(paid-refunded)}</strong></div><div class="card">En attente<br><strong>{_money(pending)}</strong></div></div>
<table><thead><tr><th>Date / heure</th><th>Opération</th><th>Origine</th><th>Moyen</th><th>Montant</th><th>Statut</th><th>Opérateur</th><th>Motif</th></tr></thead><tbody>{''.join(items)}</tbody></table>
</div></body></html>'''
            return Response(html, mimetype="text/html")
        except Exception as exc:
            return Response("Journal indisponible : " + str(exc), status=500, mimetype="text/plain")
