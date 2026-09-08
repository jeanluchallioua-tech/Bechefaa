"""Historique et modification des commandes — environnement clean PostgreSQL uniquement."""
import json
import time
from decimal import Decimal, InvalidOperation

from flask import Response, jsonify, redirect, request


def register_history_modifier(app, db, ensure_order_schema, order_payload):
    @app.get("/api/orders/<order_id>")
    def get_order(order_id):
        try:
            with db() as conn:
                ensure_order_schema(conn)
                conn.commit()
                row = conn.execute(
                    """SELECT id, num, customer_name, source, payment, status, total, created_at, updated_at
                       FROM caisse_orders WHERE id=%s""",
                    (order_id,),
                ).fetchone()
                if not row:
                    return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                return jsonify({"ok": True, "order": order_payload(conn, row)})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Lecture commande impossible", "detail": str(exc)}), 500

    @app.put("/api/orders/<order_id>")
    def update_order(order_id):
        payload = request.get_json(silent=True) or {}
        raw_items = payload.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            return jsonify({"ok": False, "error": "La commande doit contenir au moins un article"}), 400

        normalized = []
        total = Decimal("0.00")
        for position, item in enumerate(raw_items):
            if not isinstance(item, dict):
                return jsonify({"ok": False, "error": "Ligne invalide"}), 400
            name = str(item.get("name") or "").strip()
            product_id = str(item.get("product_id") or "").strip() or None
            line_id = str(item.get("line_id") or "").strip()
            try:
                qty = int(item.get("qty") or 1)
                unit_price = Decimal(str(item.get("unit_price") or 0)).quantize(Decimal("0.01"))
            except (ValueError, TypeError, InvalidOperation):
                return jsonify({"ok": False, "error": "Prix ou quantité invalide"}), 400
            if not line_id or not name or qty <= 0 or unit_price < 0:
                return jsonify({"ok": False, "error": "Ligne invalide"}), 400
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

        now = int(time.time() * 1000)
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    order = conn.execute(
                        "SELECT id, num, status FROM caisse_orders WHERE id=%s FOR UPDATE", (order_id,)
                    ).fetchone()
                    if not order:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if order["status"] == "Terminée":
                        return jsonify({"ok": False, "error": "Une commande terminée en cuisine ne peut plus être modifiée"}), 409

                    old_status = order["status"]
                    # Une modification depuis l'historique est une nouvelle instruction
                    # pour la cuisine. Toute commande non terminée repart donc dans
                    # « À préparer », y compris si son ancien statut était Enregistrée.
                    sent_to_kitchen = True
                    new_status = "À préparer"

                    conn.execute("DELETE FROM caisse_order_items WHERE order_id=%s", (order_id,))
                    for line in normalized:
                        conn.execute(
                            """INSERT INTO caisse_order_items
                               (order_id, line_id, product_id, name, qty, unit_price, options_json, options_text, prepared, position)
                               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,FALSE,%s)""",
                            (
                                order_id, line["line_id"], line["product_id"], line["name"], line["qty"],
                                line["unit_price"], json.dumps(line["options"], ensure_ascii=False),
                                line["options_text"], line["position"],
                            ),
                        )
                    summary = {
                        "reason": "Modification depuis historique",
                        "previous_status": old_status,
                        "new_status": new_status,
                        "kitchen_resend": True,
                        "item_count": len(normalized),
                    }
                    conn.execute(
                        """UPDATE caisse_orders
                           SET total=%s, status=%s, modification_flag=TRUE,
                               change_summary=%s::jsonb, updated_at=%s, modified_at=%s
                           WHERE id=%s""",
                        (total, new_status, json.dumps(summary, ensure_ascii=False), now, now, order_id),
                    )
            return jsonify({
                "ok": True,
                "id": order_id,
                "num": order["num"],
                "total": float(total),
                "status": new_status,
                "kitchen_resend": sent_to_kitchen,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Modification impossible", "detail": str(exc)}), 500

    @app.get("/historique-modification")
    def historique_modification():
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Historique</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c}.top{background:#111827;color:#fff;padding:14px 22px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}.top b{font-size:22px}.top a{color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700}.top a.active{background:#d97706}.spacer{flex:1}.wrap{max-width:1180px;margin:auto;padding:24px}.toolbar{display:flex;gap:10px;margin-bottom:16px}.toolbar input,.toolbar select{padding:12px;border:1px solid #ccd1d8;border-radius:9px;font-size:15px}.toolbar input{flex:1}.list{display:grid;gap:10px}.order{background:#fff;border-radius:12px;padding:15px;display:flex;gap:15px;align-items:center}.info{flex:1}.num{font-size:19px;font-weight:800}.meta{color:#666;font-size:13px;margin-top:3px}.items{font-size:13px;color:#444;margin-top:7px}.btn{border:1px solid #ccd1d8;background:#fff;border-radius:8px;padding:10px 13px;font-weight:700;cursor:pointer}.btn.edit{background:#111827;color:#fff;border-color:#111827}.btn.locked{background:#e5e7eb;color:#6b7280;border-color:#d1d5db;cursor:not-allowed}.empty{background:#fff;border-radius:12px;padding:30px;text-align:center;color:#777}.modal{position:fixed;inset:0;background:#0008;display:none;align-items:center;justify-content:center;padding:20px}.modal.open{display:flex}.panel{background:#fff;border-radius:14px;max-width:700px;width:100%;max-height:90vh;overflow:auto;padding:20px}.panelhead{display:flex;justify-content:space-between;align-items:center;gap:10px}.line{border-top:1px solid #eee;padding:14px 0}.linehead{display:flex;justify-content:space-between;gap:10px;font-weight:800}.opts{font-size:12px;color:#666;margin-top:4px}.qty{display:flex;align-items:center;gap:8px;margin-top:10px}.qty button{width:34px;height:34px;border:1px solid #ccc;background:#fff;border-radius:7px;font-weight:800;cursor:pointer}.remove{margin-left:auto;color:#a61b14;border:0;background:transparent;font-weight:700;cursor:pointer}.total{display:flex;justify-content:space-between;font-size:21px;font-weight:800;border-top:2px solid #111827;padding-top:14px;margin-top:10px}.save{width:100%;margin-top:14px;border:0;border-radius:9px;padding:13px;background:#14804a;color:#fff;font-weight:800;cursor:pointer}.notice{padding:10px;border-radius:8px;margin:10px 0;background:#fff5df;color:#7b4b00}.success{padding:10px;border-radius:8px;margin:10px 0;background:#e8f7ee;color:#176438}.error{padding:10px;border-radius:8px;margin:10px 0;background:#fff0ee;color:#9d261d}@media(max-width:700px){.order{align-items:flex-start;flex-direction:column}.toolbar{flex-direction:column}}
</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><a href="/pos">Caisse</a><a href="/cuisine">Cuisine</a><a class="active" href="/historique">Historique</a><span class="spacer"></span><span>PostgreSQL</span></div><div class="wrap"><h1>Historique des commandes</h1><p>Les commandes restent consultables. Une commande terminée en cuisine ne peut plus être modifiée.</p><div class="toolbar"><input id="search" placeholder="N° commande, client..."><select id="status"><option value="">Tous les statuts</option><option>Enregistrée</option><option>À préparer</option><option>En préparation</option><option>Prête</option><option>Terminée</option></select></div><div id="list" class="list"></div></div><div id="modal" class="modal"><div class="panel"><div class="panelhead"><h2 id="mtitle">Modifier</h2><button class="btn" onclick="closeModal()">Fermer</button></div><div id="mmsg"></div><div id="mlines"></div><div class="total"><span>Total</span><span id="mtotal">0,00 €</span></div><button class="save" onclick="saveEdit()">Enregistrer les modifications</button></div></div><script>
let ORDERS=[],EDIT=null;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function money(v){return Number(v||0).toFixed(2).replace('.',',')+' €'}
function render(){let q=document.getElementById('search').value.toLowerCase().trim(),st=document.getElementById('status').value;let rows=ORDERS.filter(o=>(!st||o.status===st)&&(!q||String(o.num).includes(q)||String(o.customer_name||'').toLowerCase().includes(q)));document.getElementById('list').innerHTML=rows.length?rows.map(o=>`<div class="order"><div class="info"><div class="num">#${esc(o.num)} · ${esc(o.customer_name)} </div><div class="meta">${esc(o.status)} · ${esc(o.ticket_type)} · ${money(o.total)}</div><div class="items">${esc((o.items||[]).map(i=>i.qty+'× '+i.name).join(' • '))}</div></div><button class="btn" onclick="viewOrder('${esc(o.id)}')">Voir</button>${o.status==='Terminée'?'<button class="btn locked" disabled>Terminée</button>':`<button class="btn edit" onclick="editOrder('${esc(o.id)}')">Modifier</button>`}</div>`).join(''):'<div class="empty">Aucune commande</div>'}
async function load(){let r=await fetch('/api/orders/history');let d=await r.json();if(!r.ok||!d.ok){document.getElementById('list').innerHTML='<div class="error">'+esc(d.detail||d.error||'Erreur')+'</div>';return}ORDERS=d.orders||[];render()}
function viewOrder(id){let o=ORDERS.find(x=>x.id===id);if(!o)return;alert('#'+o.num+'\n'+o.status+'\n\n'+(o.items||[]).map(i=>i.qty+'× '+i.name+(i.options_text?'\n  '+i.options_text:'')).join('\n')+'\n\nTotal '+money(o.total))}
function editOrder(id){let o=ORDERS.find(x=>x.id===id);if(!o||o.status==='Terminée')return;EDIT=JSON.parse(JSON.stringify(o));document.getElementById('mtitle').textContent='Modifier commande #'+o.num;document.getElementById('mmsg').innerHTML='<div class="notice">Après modification, cette commande sera replacée dans À préparer et renvoyée en cuisine.</div>';document.getElementById('modal').classList.add('open');renderEdit()}
function closeModal(){document.getElementById('modal').classList.remove('open');EDIT=null}
function renderEdit(){if(!EDIT)return;document.getElementById('mlines').innerHTML=(EDIT.items||[]).map((i,n)=>`<div class="line"><div class="linehead"><span>${esc(i.name)}</span><span>${money(Number(i.unit_price)*Number(i.qty))}</span></div>${i.options_text?`<div class="opts">${esc(i.options_text)}</div>`:''}<div class="qty"><button onclick="qty(${n},-1)">−</button><b>${esc(i.qty)}</b><button onclick="qty(${n},1)">+</button><button class="remove" onclick="removeLine(${n})">Retirer</button></div></div>`).join('');let t=(EDIT.items||[]).reduce((s,i)=>s+Number(i.unit_price||0)*Number(i.qty||0),0);document.getElementById('mtotal').textContent=money(t)}
function qty(n,d){if(!EDIT)return;let q=Number(EDIT.items[n].qty||1)+d;if(q<1)q=1;EDIT.items[n].qty=q;renderEdit()}
function removeLine(n){if(!EDIT)return;if(EDIT.items.length<=1){document.getElementById('mmsg').innerHTML='<div class="error">Une commande doit garder au moins un article.</div>';return}EDIT.items.splice(n,1);renderEdit()}
async function saveEdit(){if(!EDIT)return;document.getElementById('mmsg').innerHTML='<div class="notice">Enregistrement…</div>';let r=await fetch('/api/orders/'+encodeURIComponent(EDIT.id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:EDIT.items})});let d=await r.json();if(!r.ok||!d.ok){document.getElementById('mmsg').innerHTML='<div class="error">'+esc(d.detail||d.error||'Erreur')+'</div>';return}document.getElementById('mmsg').innerHTML='<div class="success">Commande #'+esc(d.num)+' modifiée. Statut : '+esc(d.status)+(d.kitchen_resend?' · renvoyée en cuisine':'')+'</div>';await load();setTimeout(closeModal,900)}
document.getElementById('search').oninput=render;document.getElementById('status').onchange=render;load();setInterval(load,8000);
</script></body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")

    @app.before_request
    def clean_history_route():
        if request.path == "/historique":
            return redirect("/historique-modification", code=302)
