"""Checklist cuisine BÉCHÉFAA — environnement clean PostgreSQL uniquement."""
import time

from flask import Response, jsonify, redirect, request


def register_kitchen_checklist(app, db, ensure_order_schema, order_payload):
    @app.post("/api/kitchen/orders/<order_id>/items/<line_id>/prepared")
    def set_kitchen_item_prepared(order_id, line_id):
        payload = request.get_json(silent=True) or {}
        prepared = bool(payload.get("prepared"))
        now = int(time.time() * 1000)
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    order = conn.execute(
                        "SELECT id, status FROM caisse_orders WHERE id=%s FOR UPDATE", (order_id,)
                    ).fetchone()
                    if not order:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if order["status"] not in ("À préparer", "En préparation"):
                        return jsonify({"ok": False, "error": "Commande hors préparation", "status": order["status"]}), 409
                    item = conn.execute(
                        "SELECT line_id FROM caisse_order_items WHERE order_id=%s AND line_id=%s",
                        (order_id, line_id),
                    ).fetchone()
                    if not item:
                        return jsonify({"ok": False, "error": "Ligne introuvable"}), 404
                    conn.execute(
                        "UPDATE caisse_order_items SET prepared=%s WHERE order_id=%s AND line_id=%s",
                        (prepared, order_id, line_id),
                    )
                    remaining = conn.execute(
                        "SELECT COUNT(*) AS n FROM caisse_order_items WHERE order_id=%s AND prepared=FALSE",
                        (order_id,),
                    ).fetchone()["n"]
                    # Dès qu'une préparation commence, la commande passe en préparation.
                    new_status = order["status"]
                    if prepared and order["status"] == "À préparer":
                        new_status = "En préparation"
                    # Si on décoche le dernier élément d'une commande encore à préparer, on garde En préparation.
                    conn.execute(
                        "UPDATE caisse_orders SET status=%s, updated_at=%s WHERE id=%s",
                        (new_status, now, order_id),
                    )
            return jsonify({"ok": True, "prepared": prepared, "remaining": int(remaining), "status": new_status})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Mise à jour cuisine impossible", "detail": str(exc)}), 500

    @app.get("/cuisine-preparation")
    def cuisine_preparation():
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Cuisine</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c}.top{background:#111827;color:#fff;padding:14px 22px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}.top b{font-size:22px}.top a{color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700}.top a.active{background:#d97706}.spacer{flex:1}.wrap{padding:20px}.head{display:flex;align-items:center;justify-content:space-between;gap:15px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:16px}.column{background:#e7e9ed;border-radius:14px;padding:14px;min-height:220px}.column h2{margin:4px 0 14px}.cards{display:grid;gap:12px}.card{background:#fff;border-radius:12px;padding:16px;border-left:6px solid #eab308}.card.preparing{border-left-color:#2563eb}.cardhead{display:flex;justify-content:space-between;gap:10px;align-items:start}.num{font-size:21px;font-weight:800}.tag{font-size:12px;background:#eef0f3;border-radius:20px;padding:5px 8px;font-weight:700}.item{display:flex;gap:12px;align-items:flex-start;padding:11px 0;border-top:1px solid #eee}.item:first-child{margin-top:10px}.item input{width:24px;height:24px;cursor:pointer;flex:0 0 auto}.itemtext{font-size:18px;font-weight:800;line-height:1.25}.opts{font-size:13px;color:#555;font-weight:400;margin-top:4px}.item.done .itemtext{text-decoration:line-through;color:#888}.item.done .opts{text-decoration:line-through;color:#999}.empty{text-align:center;color:#777;padding:50px 10px}.error{background:#fff0ee;color:#9d261d;padding:12px;border-radius:9px}.hint{font-size:13px;color:#666}.refresh{border:1px solid #ccc;background:#fff;border-radius:8px;padding:9px 12px;font-weight:700;cursor:pointer}@media(max-width:850px){.columns{grid-template-columns:1fr}}
</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><a href="/pos">Caisse</a><a class="active" href="/cuisine">Cuisine</a><a href="/historique">Historique</a><span class="spacer"></span><span id="state">PostgreSQL</span></div><div class="wrap"><div class="head"><div><h1>Écran cuisine</h1><div class="hint">Cochez un plat terminé : il reste barré et son état est mémorisé dans PostgreSQL.</div></div><button class="refresh" onclick="loadKitchen()">Actualiser</button></div><div class="columns"><section class="column"><h2>À préparer</h2><div id="todo" class="cards"></div></section><section class="column"><h2>En préparation</h2><div id="doing" class="cards"></div></section></div></div><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function card(o){let items=(o.items||[]).map(i=>`<label class="item ${i.prepared?'done':''}"><input type="checkbox" ${i.prepared?'checked':''} data-order="${esc(o.id)}" data-line="${esc(i.line_id)}"><div class="itemtext">${esc(i.qty)}× ${esc(i.name)}${i.options_text?`<div class="opts">${esc(i.options_text)}</div>`:''}</div></label>`).join('');return `<article class="card ${o.status==='En préparation'?'preparing':''}"><div class="cardhead"><div><div class="num">#${esc(o.num)} · ${esc(o.customer_name)}</div><div class="hint">${new Date(Number(o.created_at)).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}</div></div><span class="tag">${esc(o.ticket_type)}</span></div>${items||'<div class="empty">Aucun article</div>'}</article>`}
async function loadKitchen(){try{let r=await fetch('/api/kitchen/orders');let d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');let todo=d.orders.filter(o=>o.status==='À préparer'),doing=d.orders.filter(o=>o.status==='En préparation');document.getElementById('todo').innerHTML=todo.length?todo.map(card).join(''):'<div class="empty">Aucune</div>';document.getElementById('doing').innerHTML=doing.length?doing.map(card).join(''):'<div class="empty">Aucune</div>';document.getElementById('state').textContent=d.count+' commande(s) • PostgreSQL'}catch(e){document.getElementById('todo').innerHTML='<div class="error">'+esc(e.message)+'</div>';document.getElementById('state').textContent='Erreur' }}
document.addEventListener('change',async e=>{let cb=e.target.closest('input[type=checkbox][data-order]');if(!cb)return;cb.disabled=true;try{let r=await fetch('/api/kitchen/orders/'+encodeURIComponent(cb.dataset.order)+'/items/'+encodeURIComponent(cb.dataset.line)+'/prepared',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prepared:cb.checked})});let d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');await loadKitchen()}catch(err){cb.checked=!cb.checked;cb.disabled=false;alert('Mise à jour impossible : '+err.message)}});loadKitchen();setInterval(loadKitchen,5000);
</script></body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")

    @app.before_request
    def clean_kitchen_route():
        if request.path == "/cuisine":
            return redirect("/cuisine-preparation", code=302)
