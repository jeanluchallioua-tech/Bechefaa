"""Encaissement serveur de secours Phase 6.

Contourne les appels fetch() de l'Historique sur les navigateurs/tablettes
qui renvoient "Failed to fetch", tout en réutilisant les mêmes règles
comptables PostgreSQL que payment_core_phase41.
"""
import time
from decimal import Decimal

from flask import Response, redirect, request
from clean_caisse.payment_core_phase41 import _ensure_payment_schema, _money, ALLOWED_METHODS
from clean_caisse.payment_transactions_phase44 import record_payment_transaction
from clean_caisse.fiscal_ticket_phase44 import allocate_fiscal_ticket_number


def register_payment_navigation_phase6(app, db, ensure_order_schema):
    def page(order, error=""):
        total=float(order.get("total") or 0)
        remaining=max(0.0,total-float(order.get("paid_amount") or 0))
        err=f'<div class="err">{error}</div>' if error else ''
        return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Encaisser</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f5f7;font-family:Arial,sans-serif;color:#111827;padding:20px}}
.card{{max-width:520px;margin:20px auto;background:#fff;border-radius:16px;padding:22px;box-shadow:0 8px 30px #0002}}
h1{{margin:0 0 8px}}.meta{{color:#667085;margin-bottom:18px}}label{{display:block;font-weight:800;margin:14px 0 6px}}
input,select{{width:100%;padding:13px;border:1px solid #cfd4dc;border-radius:9px;font-size:18px}}
button,a{{display:block;width:100%;padding:14px;border:0;border-radius:10px;font-weight:900;font-size:16px;text-align:center;text-decoration:none;margin-top:14px}}
button{{background:#16a34a;color:#fff}}a{{background:#e5e7eb;color:#111827}}.err{{background:#fee2e2;color:#991b1b;padding:10px;border-radius:9px;margin:12px 0}}
.total{{font-size:28px;font-weight:900;text-align:center;background:#f8fafc;padding:14px;border-radius:12px}}
.note{{font-size:12px;color:#667085;margin-top:8px}}
</style></head><body><div class="card"><h1>Encaisser</h1>
<div class="meta">Commande #{order.get("num")} · {order.get("table_label") or order.get("customer_name") or ""}</div>
<div class="total">{remaining:.2f} € à régler</div>{err}
<form method="post" action="/encaisser-phase6/{order.get("id")}">
<label>Moyen de paiement</label>
<select name="method" required>
<option value="CB">Carte bancaire</option>
<option value="ESPÈCES">Espèces</option>
<option value="TITRE RESTAURANT">Titre restaurant</option>
</select>
<label>Montant à encaisser</label>
<input name="amount" inputmode="decimal" value="{remaining:.2f}" required>
<label>Montant reçu en espèces</label>
<input name="received" inputmode="decimal" value="{remaining:.2f}">
<div class="note">Le montant reçu est utilisé uniquement pour un paiement en espèces.</div>
<button type="submit">VALIDER L’ENCAISSEMENT</button>
</form>
<a href="/historique-modification">Annuler / retour historique</a>
</div></body></html>"""

    def read_order(order_id):
        with db() as conn:
            _ensure_payment_schema(conn, ensure_order_schema)
            conn.commit()
            return conn.execute("""
                SELECT id,num,total,customer_name,table_label,payment_status,
                       payment_method,paid_amount,z_closure_id
                FROM caisse_orders WHERE id=%s
            """,(order_id,)).fetchone()

    @app.get("/encaisser-phase6/<order_id>")
    def payment_navigation_get_phase6(order_id):
        try:
            row=read_order(order_id)
            if not row:
                return Response("Commande introuvable",status=404)
            if row.get("z_closure_id") is not None:
                return Response("Commande clôturée par le Z : encaissement interdit",status=409)
            if str(row.get("payment_status") or "")=="PAYÉE":
                return redirect("/historique-modification",code=303)
            return Response(page(row),content_type="text/html; charset=utf-8")
        except Exception as exc:
            return Response("Encaissement indisponible : "+str(exc),status=500)

    @app.post("/encaisser-phase6/<order_id>")
    def payment_navigation_post_phase6(order_id):
        method=str(request.form.get("method") or "").strip().upper()
        if method=="ESPECES":
            method="ESPÈCES"
        if method not in ALLOWED_METHODS:
            try:
                row=read_order(order_id)
            except Exception:
                row=None
            return Response(page(row or {"id":order_id}, "Moyen de paiement invalide"),status=400,content_type="text/html; charset=utf-8")
        try:
            with db() as conn:
                with conn.transaction():
                    _ensure_payment_schema(conn, ensure_order_schema)
                    row=conn.execute("""
                        SELECT id,num,total,customer_name,table_label,payment_status,
                               paid_amount,z_closure_id
                        FROM caisse_orders WHERE id=%s FOR UPDATE
                    """,(order_id,)).fetchone()
                    if not row:
                        return Response("Commande introuvable",status=404)
                    if row.get("z_closure_id") is not None:
                        return Response(page(row,"Commande clôturée par le Z : encaissement interdit"),status=409,content_type="text/html; charset=utf-8")
                    if row.get("payment_status")=="PAYÉE":
                        return redirect("/historique-modification",code=303)

                    total=_money(row["total"])
                    already=_money(row.get("paid_amount") or 0)
                    remaining=(total-already).quantize(Decimal("0.01"))
                    amount=_money(request.form.get("amount"))
                    if amount<=0 or amount>remaining:
                        return Response(page(row,"Montant invalide ou supérieur au reste à payer"),status=400,content_type="text/html; charset=utf-8")

                    cash_received=None
                    change_due=Decimal("0.00")
                    if method=="ESPÈCES":
                        cash_received=_money(request.form.get("received"))
                        if cash_received<amount:
                            return Response(page(row,"Montant reçu insuffisant"),status=400,content_type="text/html; charset=utf-8")
                        change_due=(cash_received-amount).quantize(Decimal("0.01"))

                    new_paid=(already+amount).quantize(Decimal("0.01"))
                    is_full=new_paid>=total
                    status="PAYÉE" if is_full else "PARTIELLEMENT PAYÉE"
                    paid_at=int(time.time()*1000)
                    fiscal=None
                    if is_full:
                        fiscal=allocate_fiscal_ticket_number(conn,ensure_order_schema,order_id,paid_at)

                    conn.execute("""
                        UPDATE caisse_orders
                        SET payment=%s,payment_status=%s,payment_method=%s,
                            paid_amount=%s,cash_received=%s,change_due=%s,
                            paid_at=%s,updated_at=%s
                        WHERE id=%s
                    """,(method,status,method,new_paid,cash_received,change_due,paid_at,paid_at,order_id))
                    record_payment_transaction(conn,order_id,method,amount,provider="LOCAL")
            return redirect("/historique-modification?payment=ok",code=303)
        except ValueError as exc:
            try: row=read_order(order_id)
            except Exception: row={"id":order_id}
            return Response(page(row,str(exc)),status=400,content_type="text/html; charset=utf-8")
        except Exception as exc:
            try: row=read_order(order_id)
            except Exception: row={"id":order_id}
            return Response(page(row,"Encaissement impossible : "+str(exc)),status=500,content_type="text/html; charset=utf-8")

    @app.after_request
    def inject_payment_navigation_phase6(response):
        if request.path!="/historique-modification" or response.status_code!=200 or response.mimetype!="text/html":
            return response
        html=response.get_data(as_text=True)
        if "bechefaa-payment-navigation-phase6" in html:
            return response
        addon=r"""
<script id="bechefaa-payment-navigation-phase6">
(function(){
 function orderId(card){
   for(const b of card.querySelectorAll('button')){
     const s=b.getAttribute('onclick')||'';
     let m=s.match(/editOrder\('([^']+)'\)/);
     if(!m)m=s.match(/viewOrder\('([^']+)'\)/);
     if(m)return m[1];
   }
   return '';
 }
 document.addEventListener('click',function(e){
   const b=e.target.closest('.p41-pay-btn');
   if(!b)return;
   const card=b.closest('.order'),id=card?orderId(card):'';
   if(!id)return;
   e.preventDefault();e.stopImmediatePropagation();
   window.location.href='/encaisser-phase6/'+encodeURIComponent(id);
 },true);
})();
</script>
"""
        html=html.replace("</body>",addon+"</body>")
        response.set_data(html);response.content_length=len(response.get_data())
        return response
