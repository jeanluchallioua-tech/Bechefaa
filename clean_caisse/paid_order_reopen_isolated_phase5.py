"""Phase 5 — réouverture contrôlée d'une commande payée, terminée en cuisine.

Module isolé et INACTIF : non importé / non enregistré dans wsgi_caisse.py.

But :
- autoriser la modification d'une commande déjà terminée/payée tant qu'elle n'est pas clôturée par le Z ;
- renvoyer la commande modifiée en cuisine avec statut « À préparer » ;
- conserver le règlement déjà journalisé ;
- interdire une baisse du nouveau total sous le net déjà payé (le remboursement reste le flux dédié) ;
- laisser le comportement historique inchangé pour les autres commandes.
"""
import json
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import jsonify, request

from clean_caisse.payment_transactions_phase44 import ensure_payment_transaction_schema

CENT = Decimal("0.01")


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


def _normalize_items(raw_items):
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("La commande doit contenir au moins un article")

    normalized = []
    total = Decimal("0.00")
    for position, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise ValueError("Ligne invalide")
        name = str(item.get("name") or "").strip()
        product_id = str(item.get("product_id") or "").strip() or None
        line_id = str(item.get("line_id") or "").strip()
        try:
            qty = int(item.get("qty") or 1)
            unit_price = Decimal(str(item.get("unit_price") or 0)).quantize(CENT)
        except (ValueError, TypeError, InvalidOperation):
            raise ValueError("Prix ou quantité invalide")
        if not line_id or not name or qty <= 0 or unit_price < 0:
            raise ValueError("Ligne invalide")

        options = item.get("options") if isinstance(item.get("options"), list) else []
        options_text = str(item.get("options_text") or "").strip()
        if not options_text:
            labels = []
            for option in options:
                if isinstance(option, dict):
                    label = str(option.get("name") or option.get("label") or "").strip()
                    group = str(option.get("group") or "").strip()
                    if label:
                        labels.append((group + ": " if group else "") + label)
                elif option is not None:
                    labels.append(str(option))
            options_text = " • ".join(labels)

        normalized.append({
            "line_id": line_id,
            "product_id": product_id,
            "name": name,
            "qty": qty,
            "unit_price": unit_price,
            "options": options,
            "options_text": options_text,
            "position": position,
        })
        total += unit_price * qty

    return normalized, total.quantize(CENT)


def register_paid_order_reopen_isolated_phase5(app, db, ensure_order_schema):
    original_update = app.view_functions.get("update_order")
    if original_update is None:
        raise RuntimeError("Route update_order introuvable")

    def update_order_paid_reopen_phase5(order_id, *args, **kwargs):
        payload = request.get_json(silent=True) or {}

        # Prélecture : les commandes non terminées restent intégralement gérées
        # par le flux historique déjà validé.
        try:
            with db() as conn:
                ensure_order_schema(conn)
                order = conn.execute(
                    "SELECT id,status,z_closure_id FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                if not order:
                    return jsonify({"ok": False, "error": "Commande introuvable"}), 404
            if str(order["status"] or "") != "Terminée":
                return original_update(order_id, *args, **kwargs)
        except Exception as exc:
            return jsonify({"ok": False, "error": "Contrôle réouverture impossible", "detail": str(exc)}), 500

        try:
            normalized, new_total = _normalize_items(payload.get("items"))
            now = int(time.time() * 1000)

            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    ensure_payment_transaction_schema(conn)
                    order = conn.execute("""
                        SELECT id,num,status,total,payment_status,paid_amount,z_closure_id
                        FROM caisse_orders
                        WHERE id=%s
                        FOR UPDATE
                    """, (order_id,)).fetchone()
                    if not order:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if order["z_closure_id"] is not None:
                        return jsonify({
                            "ok": False,
                            "error": "Commande clôturée par le Z : modification interdite",
                            "code": "ORDER_Z_LOCKED",
                        }), 409
                    if str(order["status"] or "") != "Terminée":
                        return jsonify({"ok": False, "error": "La commande a changé d'état. Rechargez l'historique."}), 409

                    paid_net = _ledger_net(conn, order_id)
                    if paid_net <= Decimal("0.00"):
                        return jsonify({"ok": False, "error": "Aucun règlement journalisé : utilisez le flux de modification normal."}), 409
                    if new_total < paid_net:
                        return jsonify({
                            "ok": False,
                            "error": "Le nouveau total ne peut pas être inférieur au montant déjà payé. Utilisez d'abord le remboursement.",
                            "paid_amount": float(paid_net),
                            "new_total": float(new_total),
                        }), 409

                    conn.execute("DELETE FROM caisse_order_items WHERE order_id=%s", (order_id,))
                    for line in normalized:
                        conn.execute("""
                            INSERT INTO caisse_order_items
                            (order_id,line_id,product_id,name,qty,unit_price,options_json,options_text,prepared,position)
                            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,FALSE,%s)
                        """, (
                            order_id, line["line_id"], line["product_id"], line["name"], line["qty"],
                            line["unit_price"], json.dumps(line["options"], ensure_ascii=False),
                            line["options_text"], line["position"],
                        ))

                    summary = {
                        "reason": "Réouverture après paiement",
                        "previous_status": "Terminée",
                        "new_status": "À préparer",
                        "kitchen_resend": True,
                        "paid_before_edit": float(paid_net),
                        "new_total": float(new_total),
                        "topup_required": bool(new_total > paid_net),
                    }
                    conn.execute("""
                        UPDATE caisse_orders
                        SET total=%s,status='À préparer',modification_flag=TRUE,
                            change_summary=%s::jsonb,updated_at=%s,modified_at=%s
                        WHERE id=%s
                    """, (new_total, json.dumps(summary, ensure_ascii=False), now, now, order_id))

            return jsonify({
                "ok": True,
                "id": order_id,
                "num": order["num"],
                "total": float(new_total),
                "paid_amount": float(paid_net),
                "remaining_amount": float((new_total - paid_net).quantize(CENT)),
                "payment_status": "PAYÉE" if new_total == paid_net else "PARTIELLEMENT PAYÉE",
                "status": "À préparer",
                "kitchen_resend": True,
                "reopened_after_payment": True,
            })
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Modification impossible", "detail": str(exc)}), 500

    update_order_paid_reopen_phase5.__name__ = "update_order_paid_reopen_phase5"
    app.view_functions["update_order"] = update_order_paid_reopen_phase5

    @app.after_request
    def paid_order_reopen_ui_phase5(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<script id="phase5-paid-reopen-ui-isolated">
(function(){
  function patch(){
    if(typeof window.render!=='function' || typeof window.editOrder!=='function')return;
    const originalRender=window.render;
    window.render=function(){
      originalRender();
      const rows=(window.ORDERS||[]);
      const cards=[...document.querySelectorAll('#list .order')];
      cards.forEach(card=>{
        const num=(card.querySelector('.num')?.textContent||'').match(/#([^ ·]+)/)?.[1];
        const order=rows.find(o=>String(o.num)===String(num));
        if(!order || order.status!=='Terminée')return;
        const locked=card.querySelector('.btn.locked');
        if(locked){
          locked.disabled=false;
          locked.classList.remove('locked');
          locked.classList.add('edit');
          locked.textContent='Modifier';
          locked.onclick=function(){window.editOrder(order.id)};
        }
      });
    };
    const originalEdit=window.editOrder;
    window.editOrder=function(id){
      const o=(window.ORDERS||[]).find(x=>x.id===id);
      if(o && o.status==='Terminée'){
        window.EDIT=JSON.parse(JSON.stringify(o));
        document.getElementById('mtitle').textContent='Modifier commande #'+o.num;
        document.getElementById('mmsg').innerHTML='<div class="notice">Commande déjà payée : toute modification sera renvoyée en cuisine. Si le total augmente, seul le complément restera à encaisser. Une commande clôturée par le Z reste verrouillée.</div>';
        document.getElementById('modal').classList.add('open');
        if(typeof window.renderEdit==='function')window.renderEdit();
        return;
      }
      return originalEdit(id);
    };
    window.render();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(patch,0));else setTimeout(patch,0);
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
