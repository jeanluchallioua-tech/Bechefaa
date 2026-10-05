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
from clean_caisse.payment_topup_mixed_isolated_phase5 import _ledger_net, _payment_methods


def register_payment_navigation_phase6(app, db, ensure_order_schema):
    def page(order, error=""):
        total=float(order.get("total") or 0)
        paid=float(order.get("ledger_paid") if order.get("ledger_paid") is not None else order.get("paid_amount") or 0)
        remaining=max(0.0,total-paid)
        err=f'<div class="err">{error}</div>' if error else ''
        return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Encaisser</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f5f7;font-family:Arial,sans-serif;color:#111827;padding:18px}}
.card{{max-width:560px;margin:12px auto;background:#fff;border-radius:18px;padding:22px;box-shadow:0 8px 30px #0002}}
h1{{margin:0 0 5px;font-size:27px}}.meta{{color:#667085;font-weight:700;margin-bottom:16px}}
.summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px}}
.sum{{background:#f8fafc;border:1px solid #e5e7eb;border-radius:11px;padding:10px;text-align:center}}
.sum small{{display:block;color:#667085;font-weight:700;margin-bottom:4px}}.sum b{{font-size:19px}}
label{{display:block;font-weight:900;margin:13px 0 6px}}
input{{width:100%;padding:13px;border:1px solid #cfd4dc;border-radius:10px;font-size:21px;font-weight:800}}
.methods{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:9px;margin-top:14px}}
.method{{min-height:72px;border:2px solid #d0d5dd;border-radius:12px;background:#fff;color:#111827;font-size:15px;font-weight:900;cursor:pointer;padding:8px}}
.method:active{{background:#111827;color:#fff;border-color:#111827}}
.cash{{display:none;margin-top:12px;padding:12px;background:#fafafa;border:1px solid #e5e7eb;border-radius:11px}}
.cash.show{{display:block}}.err{{background:#fee2e2;color:#991b1b;padding:10px;border-radius:9px;margin:12px 0;font-weight:700}}
.back{{display:block;width:100%;padding:13px;border-radius:10px;font-weight:900;text-align:center;text-decoration:none;margin-top:14px;background:#e5e7eb;color:#111827}}
.note{{font-size:12px;color:#667085;margin-top:8px;line-height:1.4}}
@media(max-width:520px){{.methods{{grid-template-columns:1fr}}.summary{{grid-template-columns:1fr 1fr 1fr}}}}
</style></head><body><div class="card">
<h1>Encaisser</h1>
<div class="meta">Commande #{order.get("num")} · {order.get("table_label") or order.get("customer_name") or ""}</div>
<div class="summary">
 <div class="sum"><small>Total</small><b>{total:.2f} €</b></div>
 <div class="sum"><small>Déjà encaissé</small><b>{paid:.2f} €</b></div>
 <div class="sum"><small>Reste</small><b>{remaining:.2f} €</b></div>
</div>
{err}
<form id="payform" method="post" action="/encaisser-phase6/{order.get("id")}">
<input type="hidden" name="method" id="method" value="">
<label>Montant à encaisser</label>
<input id="amount" name="amount" inputmode="decimal" value="{remaining:.2f}" required>
<div class="methods">
 <button type="button" class="method" data-method="ESPÈCES">💶<br>Espèces</button>
 <button type="button" class="method" data-method="CB">💳<br>Carte bancaire</button>
 <button type="button" class="method" data-method="TITRE RESTAURANT">🍽️<br>Titre restaurant</button>
</div>
<div id="cash" class="cash">
 <label>Montant reçu en espèces</label>
 <input id="received" name="received" inputmode="decimal" value="{remaining:.2f}">
 <div class="note">La monnaie à rendre sera calculée sur le montant encaissé maintenant.</div>
</div>
<div class="note">Vous pouvez saisir seulement une partie du reste à payer. Après validation, le solde restera disponible à l’encaissement avec un autre moyen de paiement.</div>
</form>
<a class="back" href="/historique-modification">Retour historique</a>
</div>
<script>
(function(){{
 const form=document.getElementById('payform'),method=document.getElementById('method'),
       amount=document.getElementById('amount'),cash=document.getElementById('cash'),
       received=document.getElementById('received');
 document.querySelectorAll('.method').forEach(function(btn){{
   btn.addEventListener('click',function(){{
     method.value=btn.dataset.method;
     if(method.value==='ESPÈCES'){{
       cash.classList.add('show');
       if(!received.value)received.value=amount.value;
     }}else cash.classList.remove('show');
     if(!amount.value||Number(String(amount.value).replace(',','.'))<=0){{alert('Indiquez le montant à encaisser.');return;}}
     form.submit();
   }});
 }});
}})();
</script></body></html>"""

    def read_order(order_id):
        with db() as conn:
            _ensure_payment_schema(conn, ensure_order_schema)
            conn.commit()
            row=conn.execute("""
                SELECT id,num,total,customer_name,table_label,payment_status,
                       payment_method,paid_amount,z_closure_id
                FROM caisse_orders WHERE id=%s
            """,(order_id,)).fetchone()
            if row:
                row=dict(row)
                row["ledger_paid"]=float(_ledger_net(conn, order_id))
            return row

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
            try: row=read_order(order_id)
            except Exception: row=None
            return Response(page(row or {"id":order_id},"Choisissez Espèces, Carte bancaire ou Titre restaurant."),status=400,content_type="text/html; charset=utf-8")
        try:
            with db() as conn:
                with conn.transaction():
                    _ensure_payment_schema(conn, ensure_order_schema)
                    row=conn.execute("""
                        SELECT id,num,total,customer_name,table_label,payment_status,
                               paid_amount,cash_received,change_due,z_closure_id,
                               fiscal_ticket_number
                        FROM caisse_orders WHERE id=%s FOR UPDATE
                    """,(order_id,)).fetchone()
                    if not row:
                        return Response("Commande introuvable",status=404)
                    if row.get("z_closure_id") is not None:
                        return Response(page(dict(row),"Commande clôturée par le Z : encaissement interdit"),status=409,content_type="text/html; charset=utf-8")
                    if "REMBOURS" in str(row.get("payment_status") or "").upper():
                        return Response(page(dict(row),"Commande remboursée : encaissement interdit"),status=409,content_type="text/html; charset=utf-8")

                    total=_money(row["total"])
                    net=_ledger_net(conn,order_id)
                    if net>=total:
                        return redirect("/historique-modification",code=303)
                    remaining=(total-net).quantize(Decimal("0.01"))
                    amount=_money(request.form.get("amount"))
                    if amount<=0:
                        data=dict(row);data["ledger_paid"]=float(net)
                        return Response(page(data,"Le montant doit être supérieur à 0."),status=400,content_type="text/html; charset=utf-8")
                    if amount>remaining:
                        data=dict(row);data["ledger_paid"]=float(net)
                        return Response(page(data,"Le montant dépasse le reste à payer."),status=400,content_type="text/html; charset=utf-8")

                    cash_received=None
                    change_due=Decimal("0.00")
                    if method=="ESPÈCES":
                        cash_received=_money(request.form.get("received"))
                        if cash_received<amount:
                            data=dict(row);data["ledger_paid"]=float(net)
                            return Response(page(data,"Montant reçu insuffisant."),status=400,content_type="text/html; charset=utf-8")
                        change_due=(cash_received-amount).quantize(Decimal("0.01"))

                    previous_methods=_payment_methods(conn,order_id)
                    paid_at=int(time.time()*1000)
                    record_payment_transaction(conn,order_id,method,amount,provider="LOCAL")
                    new_net=(net+amount).quantize(Decimal("0.01"))
                    is_full=new_net>=total
                    all_methods=sorted(set(previous_methods+[method]))
                    stored_method=method if len(all_methods)==1 else "MIXTE"
                    status="PAYÉE" if is_full else "PARTIELLEMENT PAYÉE"

                    old_cash=_money(row.get("cash_received")) if row.get("cash_received") is not None else Decimal("0.00")
                    old_change=_money(row.get("change_due"))
                    new_cash=(old_cash+cash_received).quantize(Decimal("0.01")) if method=="ESPÈCES" else row.get("cash_received")
                    new_change=(old_change+change_due).quantize(Decimal("0.01")) if method=="ESPÈCES" else old_change

                    fiscal=row.get("fiscal_ticket_number")
                    if is_full and not fiscal:
                        fiscal=allocate_fiscal_ticket_number(conn,ensure_order_schema,order_id,paid_at)

                    conn.execute("""
                        UPDATE caisse_orders
                        SET payment=%s,payment_status=%s,payment_method=%s,
                            paid_amount=%s,cash_received=%s,change_due=%s,
                            paid_at=%s,updated_at=%s
                        WHERE id=%s
                    """,(stored_method,status,stored_method,new_net,new_cash,new_change,paid_at,paid_at,order_id))

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
