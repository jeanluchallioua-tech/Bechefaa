"""Phase 4.4 — remboursement sur ticket client uniquement.

Le ticket cuisine reste volontairement inchangé. Lecture seule du journal financier.
"""
from flask import request


def register_refund_client_ticket_phase44(app, db):
    @app.after_request
    def inject_refund_client_ticket_phase44(response):
        if not request.path.startswith("/impression/client/") or response.status_code != 200 or response.mimetype != "text/html":
            return response
        order_id = request.path[len("/impression/client/"):].strip()
        if not order_id:
            return response
        try:
            with db() as conn:
                row = conn.execute("""
                    SELECT o.payment_status,
                           COALESCE(SUM(CASE WHEN t.transaction_type='PAYMENT' AND t.status='SUCCEEDED' THEN t.amount ELSE 0 END),0) AS paid,
                           COALESCE(SUM(CASE WHEN t.transaction_type='REFUND' AND t.status='SUCCEEDED' THEN t.amount ELSE 0 END),0) AS refunded,
                           COALESCE(SUM(CASE WHEN t.transaction_type='REFUND' AND t.status='PENDING_EXTERNAL' THEN t.amount ELSE 0 END),0) AS pending_refund
                    FROM caisse_orders o
                    LEFT JOIN caisse_payment_transactions t ON t.order_id=o.id
                    WHERE o.id=%s
                    GROUP BY o.id,o.payment_status
                """, (order_id,)).fetchone()
            if not row:
                return response
            refunded = float(row["refunded"] or 0)
            pending = float(row["pending_refund"] or 0)
            paid = float(row["paid"] or 0)
            if refunded <= 0 and pending <= 0:
                return response
            net = round(paid - refunded, 2)
            def money(v): return f"{float(v):.2f}".replace(".", ",") + " €"
            block = (
                '<div id="p44-refund-ticket"><div class="sep"></div>'
                '<div style="font-size:13px;font-weight:900;text-align:center;margin:4px 0">'
                + str(row["payment_status"] or "REMBOURSEMENT") + '</div>'
                '<div class="row cfiscal"><span>Payé initialement</span><span>' + money(paid) + '</span></div>'
                '<div class="row cfiscal"><span>Remboursement</span><span>-' + money(refunded) + '</span></div>'
                '<div class="row ctotal"><span>NET PAYÉ</span><span>' + money(net) + '</span></div>'
                + (('<div class="row cfiscal"><span>Remboursement en attente</span><span>' + money(pending) + '</span></div>') if pending > 0 else '')
                + '</div>'
            )
            html = response.get_data(as_text=True)
            marker = '<div class="sep"></div><div class="thanks">Merci</div>'
            if marker in html:
                html = html.replace(marker, block + marker, 1)
            else:
                html = html.replace('</div><div class="actions">', block + '</div><div class="actions">', 1)
            response.set_data(html)
            response.content_length = len(response.get_data())
        except Exception:
            # L'impression client existante doit rester disponible même si le complément échoue.
            pass
        return response
