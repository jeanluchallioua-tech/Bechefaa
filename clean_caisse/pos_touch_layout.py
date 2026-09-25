"""Ergonomie tactile isolée pour la caisse BÉCHÉFAA.

- La fiche client existante devient une fenêtre modale.
- Trois modes de commande : Salle, Emporter, Livraison.
- Salle n'utilise pas de coordonnées client.
- Le client courant est effacé après envoi réussi en cuisine.
- Accès immédiat aux commandes récentes et à leurs tickets depuis la caisse.
- Aucun Wix / V1 / localStorage.
"""
import importlib
import json

from flask import g, jsonify, request


def register_pos_touch_layout(app, db):
    core = importlib.import_module("clean_caisse.app")

    def clean_ticket_type(source):
        value = str(source or "").upper()
        if value == "SALLE":
            return "Salle"
        if value in {"EMPORTER", "TAKEAWAY"}:
            return "Emporter"
        if value in {"LIVRAISON", "DELIVERY"}:
            return "Livraison"
        return "Comptoir"

    core.ticket_type = clean_ticket_type

    @app.get("/api/pos/recent-orders")
    def pos_recent_orders():
        try:
            with db() as conn:
                rows = conn.execute("""
                    SELECT id, customer_name, source, status, total,
                           COALESCE(payment_status, 'À ENCAISSER') AS payment_status,
                           table_number, table_label, created_at
                    FROM caisse_orders
                    WHERE COALESCE(cancellation_hidden, FALSE) = FALSE
                      AND UPPER(COALESCE(status, '')) <> 'ANNULÉE'
                      AND (to_timestamp(created_at / 1000.0) AT TIME ZONE 'Europe/Paris')::date
                          = (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Paris')::date
                    ORDER BY created_at DESC
                    LIMIT 30
                """).fetchall()
            return jsonify({
                "ok": True,
                "orders": [{
                    "id": r["id"],
                    "customer_name": r.get("customer_name") or "",
                    "ticket_type": clean_ticket_type(r.get("source")),
                    "table_number": r.get("table_number"),
                    "table_label": r.get("table_label") or "",
                    "status": r.get("status") or "",
                    "total": float(r.get("total") or 0),
                    "payment_status": r.get("payment_status") or "À ENCAISSER",
                    "created_at": r.get("created_at"),
                } for r in rows],
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Commandes récentes indisponibles", "detail": str(exc)}), 500

    @app.before_request
    def capture_order_mode():
        if request.path == "/api/orders" and request.method == "POST":
            payload = request.get_json(silent=True) or {}
            raw = str(payload.get("service_mode") or payload.get("ticket_type") or "").strip().upper()
            if raw in {"LIVRAISON", "DELIVERY"}:
                g.pos_order_mode = "LIVRAISON"
            elif raw in {"EMPORTER", "TAKEAWAY", "COMPTOIR"}:
                g.pos_order_mode = "EMPORTER"
            elif raw in {"SALLE", "SUR PLACE", "SUR_PLACE"}:
                g.pos_order_mode = "SALLE"
            else:
                g.pos_order_mode = None
            try:
                g.pos_table_number = int(payload.get("table_number")) if g.pos_order_mode == "SALLE" else None
            except (TypeError, ValueError):
                g.pos_table_number = None
            if g.pos_order_mode == "SALLE":
                if not g.pos_table_number or g.pos_table_number < 1 or g.pos_table_number > 9:
                    return jsonify({"ok": False, "error": "Sur place : choisissez une table de 1 à 9."}), 400

    @app.after_request
    def apply_order_mode_and_touch_layout(response):
        if request.path == "/api/orders" and request.method == "POST" and response.status_code == 201:
            mode = getattr(g, "pos_order_mode", None)
            table_number = getattr(g, "pos_table_number", None)
            try:
                data = response.get_json(silent=True) or {}
                order_id = data.get("id")
                if order_id and mode in {"SALLE", "EMPORTER", "LIVRAISON"}:
                    with db() as conn:
                        with conn.transaction():
                            conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_number INTEGER NULL")
                            conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_label TEXT NULL")
                            if mode == "SALLE" and table_number:
                                conn.execute(
                                    "UPDATE caisse_orders SET source=%s, table_number=%s, table_label=%s WHERE id=%s",
                                    (mode, table_number, f"Table {table_number}", order_id),
                                )
                            else:
                                conn.execute(
                                    "UPDATE caisse_orders SET source=%s, table_number=NULL, table_label=NULL WHERE id=%s",
                                    (mode, order_id),
                                )
                    data["ticket_type"] = clean_ticket_type(mode)
                    if mode == "SALLE" and table_number:
                        data["service_mode"] = "Salle"
                        data["table_number"] = table_number
                        data["table_label"] = f"Table {table_number}"
                response.set_data(json.dumps(data, ensure_ascii=False))
                response.content_type = "application/json; charset=utf-8"
            except Exception:
                pass
            return response

        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style>
@media(min-width:901px){
  .cart{position:relative;height:calc(100vh - 64px);overflow-y:auto;overscroll-behavior:contain}
  .main,.cats{overscroll-behavior:contain;-webkit-overflow-scrolling:touch}
}
.ticket-choice{position:sticky;top:0;z-index:15;background:#fff;padding:4px 0 8px;margin:0;gap:7px}
.ticket-choice button{min-height:52px;font-size:14px;touch-action:manipulation;padding:8px 5px}
.touch-client-summary{background:#f7f8fa;border:1px solid #d9dde3;border-radius:10px;padding:10px 12px;margin:8px 0 12px;display:flex;align-items:center;gap:10px;cursor:pointer;min-height:54px;touch-action:manipulation}
.touch-client-summary.hidden{display:none!important}.touch-client-summary .tc-main{flex:1;min-width:0}.touch-client-summary b{display:block;font-size:18px;color:#111827;font-weight:900}.touch-client-summary span{display:block;font-size:15px;color:#4b5563;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}.touch-client-summary .tc-edit{font-weight:900;font-size:14px;background:#111827;color:#fff;padding:10px 12px;border-radius:8px}
.customer-box.touch-modal{display:none!important;position:fixed!important;z-index:10000;inset:0!important;margin:0!important;border:0!important;border-radius:0!important;background:#0008!important;padding:20px!important;overflow:auto!important}
.customer-box.touch-modal.open{display:flex!important;align-items:flex-start;justify-content:center}
.customer-box.touch-modal .touch-client-panel{width:min(620px,96vw);background:#fff;border-radius:16px;padding:18px;margin-top:max(12px,5vh);box-shadow:0 18px 55px #0005;position:relative}
.touch-client-close{position:absolute;right:12px;top:10px;border:0;background:#eef0f3;border-radius:9px;width:42px;height:42px;font-size:24px;font-weight:800;cursor:pointer;touch-action:manipulation}
.customer-box.touch-modal h3{font-size:22px;padding-right:50px;margin-bottom:14px}.customer-box.touch-modal input{font-size:17px;min-height:48px;color:#111827;background:#fff}.customer-box.touch-modal button{min-height:44px}.customer-box.touch-modal .customer-results{background:#fff!important}.customer-box.touch-modal .customer-result{color:#111827!important;font-size:16px!important;padding:13px 12px!important}.customer-box.touch-modal .customer-result b{font-size:18px!important;color:#111827!important;font-weight:900!important}.customer-box.touch-modal .customer-result small{font-size:15px!important;color:#4b5563!important;margin-top:3px!important;display:block!important}.order-box{scroll-margin-top:70px}
.pos-settings-link{display:flex;align-items:center;gap:9px;width:100%;padding:13px 10px;margin:0 0 10px;border:0;border-radius:8px;background:#111827;color:#fff!important;text-decoration:none;text-align:left;font-weight:900;font-size:14px;cursor:pointer;touch-action:manipulation;position:sticky;top:0;z-index:20;box-shadow:0 2px 8px #0002}
.pos-settings-link:hover{background:#263244}.pos-settings-link .gear{font-size:19px;line-height:1}
.pos-recent-orders-btn{width:100%;min-height:48px;margin:0 0 10px;border:1px solid #d1d5db;border-radius:10px;background:#fff;color:#111827;font-size:14px;font-weight:900;cursor:pointer;touch-action:manipulation;display:flex;align-items:center;justify-content:center;gap:8px}
.pos-recent-orders-btn:hover{background:#f3f4f6}
.pos-recent-backdrop{display:none;position:fixed;inset:0;z-index:10020;background:rgba(15,23,42,.62);padding:18px;align-items:flex-start;justify-content:center;overflow:auto}
.pos-recent-backdrop.open{display:flex}
.pos-recent-panel{width:min(760px,98vw);background:#fff;border-radius:16px;margin-top:max(10px,3vh);box-shadow:0 20px 60px #0005;overflow:hidden}
.pos-recent-head{display:flex;align-items:center;gap:10px;padding:16px 18px;border-bottom:1px solid #e5e7eb}.pos-recent-head h2{margin:0;font-size:21px;flex:1}.pos-recent-close{border:0;background:#eef0f3;border-radius:9px;width:42px;height:42px;font-size:24px;font-weight:900;cursor:pointer}
.pos-recent-list{padding:10px;max-height:72vh;overflow:auto}.pos-recent-empty{padding:28px;text-align:center;color:#6b7280}.pos-recent-error{padding:14px;background:#fff1f2;color:#9f1239;border-radius:10px}
.pos-recent-row{border:1px solid #e5e7eb;border-radius:12px;padding:12px;margin-bottom:9px}.pos-recent-main{display:flex;gap:10px;align-items:flex-start}.pos-recent-info{flex:1;min-width:0}.pos-recent-title{font-size:16px;font-weight:900}.pos-recent-meta{font-size:12px;color:#667085;margin-top:4px}.pos-recent-actions{display:flex;gap:7px;margin-top:10px}.pos-recent-actions a{flex:1;text-align:center;text-decoration:none;border-radius:9px;padding:10px 8px;font-weight:900;font-size:13px}.pos-recent-client{background:#2563eb;color:#fff}.pos-recent-kitchen{background:#d97706;color:#fff}
@media(max-width:600px){.pos-recent-main{display:block}.pos-recent-actions a{padding:12px 8px}.pos-recent-list{max-height:78vh}}
</style>
<script>
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const box=document.querySelector('.customer-box'),cart=document.querySelector('.cart'),ticket=document.querySelector('.ticket-choice');
   if(!box||!cart||!ticket)return;

   function ensureSettingsLink(){
     const cats=document.querySelector('.cats');
     if(!cats)return;
     let link=cats.querySelector('.pos-settings-link');
     if(!link){link=document.createElement('a');link.className='pos-settings-link';link.href='/administration';link.innerHTML='<span class="gear">⚙</span><span>Paramètres</span>';cats.insertBefore(link,cats.firstChild)}
     else if(cats.firstChild!==link){cats.insertBefore(link,cats.firstChild)}
   }
   ensureSettingsLink();
   const cats=document.querySelector('.cats');
   if(cats){let restoring=false;new MutationObserver(function(){if(restoring)return;if(!cats.querySelector('.pos-settings-link')||cats.firstElementChild?.classList.contains('pos-settings-link')===false){restoring=true;ensureSettingsLink();restoring=false}}).observe(cats,{childList:true})}

   if(ticket.parentNode===cart)cart.insertBefore(ticket,cart.firstChild);
   ticket.innerHTML='<button data-ticket="Salle">Salle</button><button data-ticket="Emporter">Emporter</button><button data-ticket="Livraison">Livraison</button>';

   const recentBtn=document.createElement('button');recentBtn.type='button';recentBtn.className='pos-recent-orders-btn';recentBtn.innerHTML='<span>🧾</span><span>Commandes récentes</span>';ticket.insertAdjacentElement('afterend',recentBtn);
   const recent=document.createElement('div');recent.className='pos-recent-backdrop';recent.innerHTML='<div class="pos-recent-panel"><div class="pos-recent-head"><h2>Commandes récentes</h2><button type="button" class="pos-recent-close" aria-label="Fermer">×</button></div><div class="pos-recent-list"><div class="pos-recent-empty">Chargement…</div></div></div>';document.body.appendChild(recent);
   const recentList=recent.querySelector('.pos-recent-list'),recentClose=recent.querySelector('.pos-recent-close');
   const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
   const euro=v=>Number(v||0).toFixed(2).replace('.',',')+' €';
   function recentTitle(o){
     if(o.table_number)return esc(o.table_label||('Table '+o.table_number));
     const name=o.customer_name&&o.customer_name!=='Client comptoir'&&o.customer_name!=='Client livraison'&&o.customer_name!=='Client emporter'?' — '+esc(o.customer_name):'';
     if(String(o.ticket_type||'').toLowerCase()==='livraison')return 'Livraison'+name;
     if(String(o.ticket_type||'').toLowerCase()==='emporter')return 'À emporter'+name;
     return esc(o.ticket_type||'Commande')+name;
   }
   async function loadRecent(){
     recentList.innerHTML='<div class="pos-recent-empty">Chargement…</div>';
     try{
       const r=await fetch('/api/pos/recent-orders',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');
       const rows=d.orders||[];if(!rows.length){recentList.innerHTML='<div class="pos-recent-empty">Aucune commande aujourd’hui.</div>';return}
       recentList.innerHTML=rows.map(o=>'<div class="pos-recent-row"><div class="pos-recent-main"><div class="pos-recent-info"><div class="pos-recent-title">'+recentTitle(o)+' · '+euro(o.total)+'</div><div class="pos-recent-meta">'+esc(o.status)+' · '+esc(o.payment_status)+'</div></div></div><div class="pos-recent-actions"><a class="pos-recent-client" target="_blank" rel="noopener" href="/impression/client/'+encodeURIComponent(o.id)+'">🧾 Ticket client</a><a class="pos-recent-kitchen" target="_blank" rel="noopener" href="/impression/cuisine/'+encodeURIComponent(o.id)+'">🍳 Ticket cuisine</a></div></div>').join('');
     }catch(e){recentList.innerHTML='<div class="pos-recent-error">'+esc(e.message||'Commandes récentes indisponibles')+'</div>'}
   }
   function openRecent(){recent.classList.add('open');loadRecent()}function closeRecent(){recent.classList.remove('open')}
   recentBtn.addEventListener('click',openRecent);recentClose.addEventListener('click',closeRecent);recent.addEventListener('click',e=>{if(e.target===recent)closeRecent()});

   const summary=document.createElement('div');summary.className='touch-client-summary hidden';summary.innerHTML='<div class="tc-main"><b id="tc-name">Client</b><span id="tc-detail">Toucher pour rechercher ou enregistrer un client</span></div><div class="tc-edit">Client</div>';recentBtn.insertAdjacentElement('afterend',summary);
   const panel=document.createElement('div');panel.className='touch-client-panel';while(box.firstChild)panel.appendChild(box.firstChild);const close=document.createElement('button');close.type='button';close.className='touch-client-close';close.setAttribute('aria-label','Fermer');close.textContent='×';panel.insertBefore(close,panel.firstChild);box.appendChild(panel);box.classList.add('touch-modal');document.body.appendChild(box);

   function updateSummary(){const first=document.getElementById('cust-first')?.value.trim()||'',last=document.getElementById('cust-last')?.value.trim()||'',phone=document.getElementById('cust-phone')?.value.trim()||'',city=document.getElementById('cust-city')?.value.trim()||'';const name=(first+' '+last).trim();document.getElementById('tc-name').textContent=name||'Client';document.getElementById('tc-detail').textContent=[phone,city].filter(Boolean).join(' • ')||'Toucher pour rechercher ou enregistrer un client'}
   function clearCustomer(){document.getElementById('cust-clear')?.click();updateSummary()}function open(){box.classList.add('open');setTimeout(()=>document.getElementById('cust-search')?.focus(),80)}function shut(){box.classList.remove('open');updateSummary()}
   function applyMode(mode){summary.classList.toggle('hidden',mode==='Salle');if(mode==='Salle'){shut();clearCustomer()}else document.getElementById('tc-name').textContent=(mode==='Livraison'?'Client livraison':'Client emporter')}
   summary.onclick=open;close.onclick=shut;box.addEventListener('click',e=>{if(e.target===box)shut()});document.addEventListener('keydown',e=>{if(e.key==='Escape'){shut();closeRecent()}});panel.addEventListener('input',updateSummary);
   panel.addEventListener('click',e=>{if(e.target.closest('#cust-clear'))setTimeout(updateSummary,100);if(e.target.closest('.customer-result[data-i]'))setTimeout(()=>{updateSummary();shut()},120);if(e.target.closest('#cust-save'))setTimeout(updateSummary,100)});
   const note=document.getElementById('cust-note');if(note){new MutationObserver(()=>{const text=(note.textContent||'').toLowerCase();if(text.includes('client enregistré'))setTimeout(()=>{updateSummary();shut()},120)}).observe(note,{childList:true,subtree:true,characterData:true})}
   ticket.addEventListener('click',e=>{const b=e.target.closest('[data-ticket]');if(!b)return;setTimeout(()=>applyMode(b.dataset.ticket),0)});document.querySelectorAll('.main,.cats,.cart').forEach(el=>{el.style.webkitOverflowScrolling='touch'});
   function resetCurrentOrder(){
     try{if(typeof ORDER!=='undefined'&&Array.isArray(ORDER)){ORDER.length=0;if(typeof renderOrder==='function')renderOrder()}}catch(e){}
     try{if(typeof LAST_SAVED_ORDER!=='undefined')LAST_SAVED_ORDER=null}catch(e){}
     if(msg)msg.innerHTML='';
     clearCustomer();shut();
     summary.classList.add('hidden');
   }
   const msg=document.getElementById('order-message');
   if(msg){const observer=new MutationObserver(function(){const text=(msg.textContent||'').toLowerCase();if(text.includes('envoyée en cuisine'))setTimeout(()=>document.dispatchEvent(new CustomEvent('bechefaa:new-order')),450)});observer.observe(msg,{childList:true,subtree:true,characterData:true})}
   document.addEventListener('bechefaa:new-order',resetCurrentOrder);
   document.addEventListener('click',function(e){const a=e.target.closest('a.pos-v3-nav[href="/pos"]');if(!a||!String(a.textContent||'').toLowerCase().includes('nouvelle commande'))return;e.preventDefault();document.dispatchEvent(new CustomEvent('bechefaa:new-order'))},true);
   updateSummary();
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response