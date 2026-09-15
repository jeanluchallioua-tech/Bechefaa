"""Paiements partiels et mixtes BÉCHÉFAA.

Couche isolée au-dessus du socle d'encaissement :
- moyens autorisés : Espèces, CB, Titre restaurant ;
- premier règlement partiel possible ;
- compléments avec un moyen différent ;
- une transaction PAYMENT distincte par règlement ;
- ticket fiscal attribué uniquement lorsque la commande est intégralement payée ;
- le Z conserve sa source de vérité dans le journal des transactions.
"""
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import jsonify, request

from clean_caisse.payment_transactions_phase44 import (
    ensure_payment_transaction_schema,
    record_payment_transaction,
)
from clean_caisse.fiscal_ticket_phase44 import allocate_fiscal_ticket_number
from clean_caisse.payment_core_phase41 import _ensure_payment_schema

CENT = Decimal("0.01")
ALLOWED_METHODS = {"ESPÈCES", "CB", "TITRE RESTAURANT"}


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Montant invalide")


def _ledger_net(conn, order_id):
    ensure_payment_transaction_schema(conn)
    row = conn.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS paid,
          COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunded
        FROM caisse_payment_transactions
        WHERE order_id=%s
    """, (order_id,)).fetchone()
    return (_money(row["paid"]) - _money(row["refunded"])).quantize(CENT)


def _payment_methods(conn, order_id):
    rows = conn.execute("""
        SELECT DISTINCT UPPER(method) AS method
        FROM caisse_payment_transactions
        WHERE order_id=%s
          AND transaction_type='PAYMENT'
          AND status='SUCCEEDED'
          AND method IS NOT NULL
        ORDER BY UPPER(method)
    """, (order_id,)).fetchall()
    return [str(r["method"] or "").strip().upper() for r in rows if str(r["method"] or "").strip()]


def register_payment_topup_mixed_isolated_phase5(app, db, ensure_order_schema):
    original_meta = app.view_functions.get("history_meta_phase44")
    original_get = app.view_functions.get("get_order_payment_phase41")
    if original_meta is None or original_get is None:
        raise RuntimeError("Routes encaissement/historique introuvables")

    def history_meta_topup_mixed_phase5(*args, **kwargs):
        response = app.make_response(original_meta(*args, **kwargs))
        if not 200 <= response.status_code < 300:
            return response
        payload = response.get_json(silent=True) or {}
        orders = payload.get("orders") or {}
        if not orders:
            return response
        try:
            ids = list(orders.keys())
            with db() as conn:
                ensure_order_schema(conn)
                ensure_payment_transaction_schema(conn)
                rows = conn.execute("""
                    SELECT order_id,
                      COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS paid,
                      COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunded
                    FROM caisse_payment_transactions
                    WHERE order_id = ANY(%s)
                    GROUP BY order_id
                """, (ids,)).fetchall()
            net_by_id = {
                str(r["order_id"]): (_money(r["paid"]) - _money(r["refunded"])).quantize(CENT)
                for r in rows
            }
            for order_id, info in orders.items():
                total = _money(info.get("total"))
                net = net_by_id.get(str(order_id), Decimal("0.00"))
                if Decimal("0.00") < net < total:
                    info["payment_status"] = "PARTIELLEMENT PAYÉE"
                    info["paid_amount"] = float(net)
                    info["remaining_amount"] = float((total - net).quantize(CENT))
                    info["topup_required"] = True
            return jsonify(payload)
        except Exception:
            return response

    def get_order_payment_topup_mixed_phase5(order_id, *args, **kwargs):
        response = app.make_response(original_get(order_id, *args, **kwargs))
        if not 200 <= response.status_code < 300:
            return response
        payload = response.get_json(silent=True) or {}
        info = payload.get("order") or {}
        try:
            with db() as conn:
                _ensure_payment_schema(conn, ensure_order_schema)
                order = conn.execute("SELECT total FROM caisse_orders WHERE id=%s", (order_id,)).fetchone()
                if not order:
                    return response
                total = _money(order["total"])
                net = _ledger_net(conn, order_id)
                methods = _payment_methods(conn, order_id)
            remaining = max(Decimal("0.00"), (total - net).quantize(CENT))
            info["order_total"] = float(total)
            info["paid_amount"] = float(max(Decimal("0.00"), net))
            info["remaining_amount"] = float(remaining)
            info["previous_payment_methods"] = methods
            info["mixed_payment_allowed"] = True
            if Decimal("0.00") < net < total:
                info["total"] = float(remaining)
                info["payment_status"] = "PARTIELLEMENT PAYÉE"
                info["topup_required"] = True
            return jsonify(payload)
        except Exception:
            return response

    def set_order_payment_topup_mixed_phase5(order_id, *args, **kwargs):
        payload = request.get_json(silent=True) or {}
        method = str(payload.get("method") or "").strip().upper()
        if method == "ESPECES":
            method = "ESPÈCES"
        if method not in ALLOWED_METHODS:
            return jsonify({"ok": False, "error": "Moyen de paiement invalide"}), 400

        try:
            with db() as conn:
                with conn.transaction():
                    _ensure_payment_schema(conn, ensure_order_schema)
                    order = conn.execute("""
                        SELECT id,num,total,payment_method,payment,cash_received,change_due,
                               paid_at,z_closure_id,fiscal_ticket_number
                        FROM caisse_orders
                        WHERE id=%s
                        FOR UPDATE
                    """, (order_id,)).fetchone()
                    if not order:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if order["z_closure_id"] is not None:
                        return jsonify({"ok": False, "error": "Commande clôturée par le Z : encaissement interdit", "code": "ORDER_Z_LOCKED"}), 409

                    total = _money(order["total"])
                    net = _ledger_net(conn, order_id)
                    remaining = (total - net).quantize(CENT)
                    if remaining <= 0:
                        return jsonify({"ok": False, "error": "Commande déjà encaissée", "code": "ORDER_ALREADY_PAID"}), 409

                    amount_raw = payload.get("amount")
                    requested = remaining if amount_raw in (None, "") else _money(amount_raw)
                    if requested <= 0:
                        return jsonify({"ok": False, "error": "Montant du règlement invalide"}), 400
                    if requested > remaining:
                        return jsonify({
                            "ok": False,
                            "error": "Montant supérieur au reste à payer",
                            "remaining_amount": float(remaining),
                        }), 400

                    cash_received = None
                    change_due = Decimal("0.00")
                    if method == "ESPÈCES":
                        received_raw = payload.get("received")
                        cash_received = requested if received_raw in (None, "") else _money(received_raw)
                        if cash_received < requested:
                            return jsonify({"ok": False, "error": "Montant reçu insuffisant"}), 400
                        change_due = (cash_received - requested).quantize(CENT)

                    now = int(time.time() * 1000)
                    transaction_id = record_payment_transaction(conn, order_id, method, requested, provider="LOCAL")
                    net_after = (net + requested).quantize(CENT)

                    previous_methods = _payment_methods(conn, order_id)
                    all_methods = sorted(set(previous_methods + [method]))
                    stored_method = method if len(all_methods) == 1 else "MIXTE"

                    old_cash = _money(order["cash_received"]) if order["cash_received"] is not None else Decimal("0.00")
                    old_change = _money(order["change_due"])
                    new_cash = (old_cash + cash_received).quantize(CENT) if method == "ESPÈCES" else order["cash_received"]
                    new_change = (old_change + change_due).quantize(CENT) if method == "ESPÈCES" else old_change

                    fully_paid = net_after >= total
                    fiscal_ticket_number = order["fiscal_ticket_number"]
                    paid_at = order["paid_at"]
                    if fully_paid:
                        paid_at = now
                        if not fiscal_ticket_number:
                            fiscal_ticket_number = allocate_fiscal_ticket_number(conn, ensure_order_schema, order_id, now)

                    conn.execute("""
                        UPDATE caisse_orders
                        SET payment=%s,
                            payment_status=%s,
                            payment_method=%s,
                            paid_amount=%s,
                            cash_received=%s,
                            change_due=%s,
                            paid_at=%s,
                            updated_at=%s
                        WHERE id=%s
                    """, (
                        stored_method,
                        "PAYÉE" if fully_paid else "PARTIELLEMENT PAYÉE",
                        stored_method,
                        total if fully_paid else net_after,
                        new_cash,
                        new_change,
                        paid_at,
                        now,
                        order_id,
                    ))

            return jsonify({
                "ok": True,
                "id": order_id,
                "num": order["num"],
                "fiscal_ticket_number": fiscal_ticket_number,
                "payment_status": "PAYÉE" if fully_paid else "PARTIELLEMENT PAYÉE",
                "payment_method": stored_method,
                "payment_methods": all_methods,
                "paid_amount": float(total if fully_paid else net_after),
                "payment_amount": float(requested),
                "remaining_amount": float(max(Decimal("0.00"), total - net_after)),
                "order_total": float(total),
                "cash_received": None if cash_received is None else float(cash_received),
                "change_due": float(change_due),
                "paid_at": paid_at,
                "transaction_id": transaction_id,
                "partial": not fully_paid,
                "mixed_payment": len(all_methods) > 1,
            })
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Encaissement impossible", "detail": str(exc)}), 500

    @app.after_request
    def inject_partial_mixed_ui_phase5(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response
        html = response.get_data(as_text=True)
        if "phase5-mixed-payment-ui" in html:
            return response
        addon = r'''
<style id="phase5-mixed-payment-ui">
.p5-amount-box{margin:0 0 14px;padding:12px;border:1px solid #e4e7ec;border-radius:12px;background:#fafafa}
.p5-amount-box label{display:block;font-weight:900;margin-bottom:7px}
.p5-amount-box input{width:100%;box-sizing:border-box;min-height:50px;border:1px solid #cfd4dc;border-radius:9px;padding:10px;font-size:20px;font-weight:900}
.p5-paid-summary{margin-top:7px;color:#667085;font-size:13px;font-weight:800}
.p5-partial-badge{display:block;margin-top:7px;color:#92400e;background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:7px 9px;font-size:12px;font-weight:900}
</style>
<script id="phase5-mixed-payment-script">
(function(){
 function euro(v){return Number(v||0).toFixed(2).replace('.',',')+' €'}
 function orderId(card){
   const buttons=[...card.querySelectorAll('button')];
   for(const b of buttons){const oc=b.getAttribute('onclick')||'';let m=oc.match(/editOrder\('([^']+)'\)/);if(!m)m=oc.match(/viewOrder\('([^']+)'\)/);if(m)return m[1]}
   const a=card.querySelector('a[href*="/impression/client/"]');if(a){const m=a.getAttribute('href').match(/\/impression\/client\/([^/?#]+)/);if(m)return decodeURIComponent(m[1])}
   return null;
 }
 function install(){
   const modal=document.querySelector('.p43-modal'),methods=document.querySelector('.p43-methods');
   if(!modal||!methods||document.getElementById('p5-payment-amount'))return;
   const box=document.createElement('div');box.className='p5-amount-box';box.innerHTML='<label for="p5-payment-amount">Montant de ce règlement</label><input id="p5-payment-amount" inputmode="decimal" autocomplete="off"><div id="p5-paid-summary" class="p5-paid-summary"></div>';
   methods.parentNode.insertBefore(box,methods);
   const oldConfirm=document.getElementById('p43-confirm');
   if(!oldConfirm)return;
   const confirm=oldConfirm.cloneNode(true);oldConfirm.replaceWith(confirm);
   let currentId=null,currentState=null;
   const amount=document.getElementById('p5-payment-amount'),summary=document.getElementById('p5-paid-summary'),received=document.getElementById('p43-received'),error=document.getElementById('p43-error');
   async function loadState(id){
     try{const r=await fetch('/api/orders/'+encodeURIComponent(id)+'/payment-phase41',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Lecture impossible');currentState=d.order;const remaining=Number(d.order.remaining_amount ?? d.order.total ?? 0);amount.value=remaining.toFixed(2);summary.textContent=Number(d.order.paid_amount||0)>0?'Déjà réglé : '+euro(d.order.paid_amount)+' · Reste : '+euro(remaining):'Vous pouvez régler tout ou partie du montant.';}catch(e){currentState=null;error.textContent=e.message||'Lecture impossible'}}
   document.addEventListener('click',function(e){const btn=e.target.closest&&e.target.closest('.p41-pay-btn');if(!btn)return;const card=btn.closest('.order');currentId=card?orderId(card):null;if(currentId)setTimeout(()=>loadState(currentId),40)},true);
   document.querySelectorAll('.p43-method').forEach(btn=>btn.addEventListener('click',()=>{if(btn.dataset.method==='ESPÈCES'&&amount.value)setTimeout(()=>{received.value=amount.value;received.dispatchEvent(new Event('input',{bubbles:true}))},0)}));
   amount.addEventListener('input',()=>{const active=document.querySelector('.p43-method.active');if(active&&active.dataset.method==='ESPÈCES'){received.value=amount.value;received.dispatchEvent(new Event('input',{bubbles:true}))}});
   confirm.addEventListener('click',async()=>{
     if(!currentId||!currentState){error.textContent='Commande introuvable.';return}
     const active=document.querySelector('.p43-method.active');if(!active){error.textContent='Choisissez un moyen de paiement.';return}
     const method=active.dataset.method;const value=Number(String(amount.value||'').replace(',','.'));const remaining=Number(currentState.remaining_amount ?? currentState.total ?? 0);
     if(!Number.isFinite(value)||value<=0){error.textContent='Montant du règlement invalide.';return}
     if(value>remaining+.001){error.textContent='Le montant dépasse le reste à payer ('+euro(remaining)+').';return}
     const body={method,amount:value};
     if(method==='ESPÈCES'){const rec=Number(String(received.value||'').replace(',','.'));if(!Number.isFinite(rec)||rec<value){error.textContent='Montant reçu insuffisant.';return}body.received=rec}
     error.textContent='';confirm.disabled=true;
     try{const r=await fetch('/api/orders/'+encodeURIComponent(currentId)+'/payment-phase41',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Encaissement impossible');location.reload()}catch(e){error.textContent=e.message||'Encaissement impossible';confirm.disabled=false}
   });
   async function decoratePartial(){
     try{const r=await fetch('/api/orders/history-meta-phase44',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok||!d.orders)return;document.querySelectorAll('#list .order').forEach(card=>{const id=orderId(card),info=id&&d.orders[id];if(!info)return;let badge=card.querySelector('.p5-partial-badge');if(info.payment_status==='PARTIELLEMENT PAYÉE'){if(!badge){badge=document.createElement('span');badge.className='p5-partial-badge';card.appendChild(badge)}badge.textContent='Paiement partiel · réglé '+euro(info.paid_amount)+' · reste '+euro(info.remaining_amount);const b=card.querySelector('.p41-pay-btn');if(b)b.textContent='💳 Régler le reste'}else if(badge)badge.remove()})}catch(e){}
   }
   decoratePartial();const list=document.getElementById('list');if(list)new MutationObserver(()=>setTimeout(decoratePartial,60)).observe(list,{childList:true,subtree:true});
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(install,0),{once:true});else setTimeout(install,0);
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response

    history_meta_topup_mixed_phase5.__name__ = "history_meta_topup_mixed_phase5"
    get_order_payment_topup_mixed_phase5.__name__ = "get_order_payment_topup_mixed_phase5"
    set_order_payment_topup_mixed_phase5.__name__ = "set_order_payment_topup_mixed_phase5"
    app.view_functions["history_meta_phase44"] = history_meta_topup_mixed_phase5
    app.view_functions["get_order_payment_phase41"] = get_order_payment_topup_mixed_phase5
    app.view_functions["set_order_payment_phase41"] = set_order_payment_topup_mixed_phase5
