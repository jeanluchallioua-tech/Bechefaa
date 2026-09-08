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
                    order = conn.execute("SELECT id, status FROM caisse_orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
                    if not order:return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if order["status"] not in ("À préparer", "En préparation"):return jsonify({"ok": False, "error": "Commande hors préparation", "status": order["status"]}), 409
                    item = conn.execute("SELECT line_id FROM caisse_order_items WHERE order_id=%s AND line_id=%s",(order_id, line_id)).fetchone()
                    if not item:return jsonify({"ok": False, "error": "Ligne introuvable"}), 404
                    conn.execute("UPDATE caisse_order_items SET prepared=%s WHERE order_id=%s AND line_id=%s",(prepared, order_id, line_id))
                    remaining = conn.execute("SELECT COUNT(*) AS n FROM caisse_order_items WHERE order_id=%s AND prepared=FALSE",(order_id,)).fetchone()["n"]
                    new_status = order["status"]
                    if prepared and order["status"] == "À préparer":new_status = "En préparation"
                    conn.execute("UPDATE caisse_orders SET status=%s, updated_at=%s WHERE id=%s",(new_status, now, order_id))
            return jsonify({"ok": True, "prepared": prepared, "remaining": int(remaining), "status": new_status})
        except Exception as exc:return jsonify({"ok": False, "error": "Mise à jour cuisine impossible", "detail": str(exc)}), 500

    @app.post("/api/kitchen/orders/<order_id>/finish")
    def finish_kitchen_order(order_id):
        now = int(time.time() * 1000)
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    order = conn.execute("SELECT id, num, status FROM caisse_orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
                    if not order:return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if order["status"] == "Terminée":return jsonify({"ok": True, "id": order_id, "num": order["num"], "status": "Terminée"}), 200
                    if order["status"] not in ("À préparer", "En préparation"):return jsonify({"ok": False, "error": "Cette commande ne peut pas être terminée", "status": order["status"]}), 409
                    remaining = conn.execute("SELECT COUNT(*) AS n FROM caisse_order_items WHERE order_id=%s AND prepared=FALSE",(order_id,)).fetchone()["n"]
                    if int(remaining) > 0:return jsonify({"ok": False, "error": "Tous les plats doivent être cochés avant de terminer", "remaining": int(remaining)}), 409
                    conn.execute("UPDATE caisse_orders SET status='Terminée', updated_at=%s WHERE id=%s",(now, order_id))
            return jsonify({"ok": True, "id": order_id, "num": order["num"], "status": "Terminée"}), 200
        except Exception as exc:return jsonify({"ok": False, "error": "Finalisation cuisine impossible", "detail": str(exc)}), 500

    @app.get("/cuisine-preparation")
    def cuisine_preparation():
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Cuisine</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c}.top{background:#111827;color:#fff;padding:14px 22px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}.top b{font-size:22px}.top a{color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700}.top a.active{background:#d97706}.spacer{flex:1}.wrap{padding:20px}.head{display:flex;align-items:center;justify-content:space-between;gap:15px}.columns{display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px;margin-top:16px}.column{background:#e7e9ed;border-radius:14px;padding:14px;min-height:220px}.column h2{margin:4px 0 14px}.cards{display:grid;gap:12px}.card{background:#fff;border-radius:12px;padding:16px;border-left:6px solid #eab308}.card.preparing{border-left-color:#2563eb}.card.finished{border-left-color:#16a34a}.cardhead{display:flex;justify-content:space-between;gap:10px;align-items:start}.num{font-size:21px;font-weight:800}.badges{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.tag{font-size:12px;border-radius:7px;padding:6px 9px;font-weight:900;color:#fff;white-space:nowrap}.mode-salle{background:#2563eb}.mode-emporter{background:#d97706}.mode-livraison{background:#7c3aed}.channel-caisse{background:#475569}.channel-site{background:#16a34a}.channel-uber{background:#111827}.channel-deliveroo{background:#0d9488}.item{display:flex;gap:12px;align-items:flex-start;padding:11px 0;border-top:1px solid #eee}.item:first-child{margin-top:10px}.item input{width:24px;height:24px;cursor:pointer;flex:0 0 auto}.itemtext{font-size:18px;font-weight:800;line-height:1.25}.qty{font-size:20px;font-weight:900}.opts{font-size:14px;color:#30343a;font-weight:600;margin-top:6px;display:grid;gap:3px}.optrow{line-height:1.25}.optgroup{color:#dc2626;font-weight:900}.item.done .itemtext{text-decoration:line-through;color:#888}.item.done .opts{text-decoration:line-through;color:#999}.item.done .optgroup{color:#999}.empty{text-align:center;color:#777;padding:50px 10px}.error{background:#fff0ee;color:#9d261d;padding:12px;border-radius:9px}.hint{font-size:13px;color:#666}.refresh,.finish{border:1px solid #ccc;background:#fff;border-radius:8px;padding:9px 12px;font-weight:700;cursor:pointer}.finish{width:100%;margin-top:12px;background:#16a34a;color:#fff;border-color:#16a34a}.finish:disabled{opacity:.45;cursor:not-allowed}.finished .item input{pointer-events:none}.finished .item{opacity:.8}@media(max-width:1100px){.columns{grid-template-columns:1fr 1fr}}@media(max-width:750px){.columns{grid-template-columns:1fr}}
</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><a href="/pos">Caisse</a><a class="active" href="/cuisine">Cuisine</a><a href="/historique">Historique</a><span class="spacer"></span><span id="state">PostgreSQL</span></div><div class="wrap"><div class="head"><div><h1>Écran cuisine</h1><div class="hint">Cochez les plats préparés. Quand tout est coché, utilisez « Terminer ». La commande reste dans l’historique.</div></div><button class="refresh" onclick="loadKitchen()">Actualiser</button></div><div class="columns"><section class="column"><h2>À préparer</h2><div id="todo" class="cards"></div></section><section class="column"><h2>En préparation</h2><div id="doing" class="cards"></div></section><section class="column"><h2>Terminée</h2><div id="done" class="cards"></div></section></div></div><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]));
function modeBadge(v){let s=String(v||'').toLowerCase();if(s.includes('livraison'))return '<span class="tag mode-livraison">LIVRAISON</span>';if(s.includes('emporter'))return '<span class="tag mode-emporter">EMPORTER</span>';return '<span class="tag mode-salle">SALLE</span>'}
function channelBadge(v){let s=String(v||'').toUpperCase();if(s.includes('UBER'))return '<span class="tag channel-uber">UBER EATS</span>';if(s.includes('DELIVEROO'))return '<span class="tag channel-deliveroo">DELIVEROO</span>';if(s.includes('WIX')||s.includes('SITE')||s.includes('WEB'))return '<span class="tag channel-site">SITE INTERNET</span>';return '<span class="tag channel-caisse">CAISSE</span>'}
function optionRows(i){let opts=Array.isArray(i.options)?i.options:[];let lastGroup='';let rows=opts.map(o=>{if(o&&typeof o==='object'){let g=String(o.group||'').trim(),n=String(o.name||o.label||'').trim();if(!n)return '';let showGroup=g&&g!==lastGroup;if(g)lastGroup=g;return `<div class="optrow">${showGroup?`<span class="optgroup">${esc(g)} :</span> `:''}${esc(n)}</div>`}return o!=null?`<div class="optrow">${esc(o)}</div>`:''}).filter(Boolean);if(rows.length)return `<div class="opts">${rows.join('')}</div>`;return i.options_text?`<div class="opts"><div class="optrow">${esc(i.options_text)}</div></div>`:''}
function card(o){let finished=o.status==='Terminée';let items=(o.items||[]).map(i=>`<label class="item ${i.prepared?'done':''}"><input type="checkbox" ${i.prepared?'checked':''} ${finished?'disabled':''} data-order="${esc(o.id)}" data-line="${esc(i.line_id)}"><div class="itemtext"><span class="qty">${esc(i.qty)}×</span> ${esc(i.name)}${optionRows(i)}</div></label>`).join('');let allDone=(o.items||[]).length>0&&(o.items||[]).every(i=>i.prepared);let button=!finished?`<button class="finish" data-finish="${esc(o.id)}" ${allDone?'':'disabled'}>Terminer</button>`:'';return `<article class="card ${o.status==='En préparation'?'preparing':''} ${finished?'finished':''}"><div class="cardhead"><div><div class="num">#${esc(o.num)} · ${esc(o.customer_name)}</div><div class="hint">${new Date(Number(o.created_at)).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}</div></div><div class="badges">${channelBadge(o.source)}${modeBadge(o.ticket_type)}</div></div>${items||'<div class="empty">Aucun article</div>'}${button}</article>`}
async function loadKitchen(){try{let r=await fetch('/api/kitchen/orders');let d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');let todo=d.orders.filter(o=>o.status==='À préparer'),doing=d.orders.filter(o=>o.status==='En préparation'),done=d.orders.filter(o=>o.status==='Terminée');document.getElementById('todo').innerHTML=todo.length?todo.map(card).join(''):'<div class="empty">Aucune</div>';document.getElementById('doing').innerHTML=doing.length?doing.map(card).join(''):'<div class="empty">Aucune</div>';document.getElementById('done').innerHTML=done.length?done.map(card).join(''):'<div class="empty">Aucune</div>';document.getElementById('state').textContent=d.count+' commande(s) • PostgreSQL'}catch(e){document.getElementById('todo').innerHTML='<div class="error">'+esc(e.message)+'</div>';document.getElementById('state').textContent='Erreur' }}
document.addEventListener('change',async e=>{let cb=e.target.closest('input[type=checkbox][data-order]');if(!cb)return;cb.disabled=true;try{let r=await fetch('/api/kitchen/orders/'+encodeURIComponent(cb.dataset.order)+'/items/'+encodeURIComponent(cb.dataset.line)+'/prepared',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prepared:cb.checked})});let d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');await loadKitchen()}catch(err){cb.checked=!cb.checked;cb.disabled=false;alert('Mise à jour impossible : '+err.message)}});
document.addEventListener('click',async e=>{let btn=e.target.closest('[data-finish]');if(!btn)return;btn.disabled=true;try{let r=await fetch('/api/kitchen/orders/'+encodeURIComponent(btn.dataset.finish)+'/finish',{method:'POST'});let d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');await loadKitchen()}catch(err){btn.disabled=false;alert('Impossible de terminer : '+err.message)}});
loadKitchen();setInterval(loadKitchen,5000);
</script></body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")

    @app.before_request
    def clean_kitchen_route():
        if request.path == "/cuisine":return redirect("/cuisine-preparation", code=302)
