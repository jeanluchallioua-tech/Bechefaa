"""Phase 6 — gestion clients isolée.

INACTIF : module non importé / non enregistré dans wsgi_caisse.py.

But strict : ajouter une page dédiée /clients pour rechercher et modifier les clients
existants, sans toucher au flux de commande, au paiement, à la cuisine, au Z ou aux
tickets. La création client existante de customer_phase1 reste l'autorité.
"""
from flask import jsonify, request


def register_clients_management_isolated_phase6(app, db, ensure_order_schema):
    @app.put("/api/clients/<client_id>")
    def update_client_phase6(client_id):
        payload = request.get_json(silent=True) or {}
        first_name = str(payload.get("first_name") or "").strip()
        last_name = str(payload.get("last_name") or "").strip()
        phone = str(payload.get("phone") or "").strip()
        email = str(payload.get("email") or "").strip().lower()
        address = str(payload.get("address") or "").strip()
        postal_code = str(payload.get("postal_code") or "").strip()
        city = str(payload.get("city") or "").strip()
        if postal_code and (len(postal_code) != 5 or not postal_code.isdigit()):
            return jsonify({"ok": False, "error": "Code postal invalide"}), 400
        display_name = " ".join(x for x in (first_name, last_name) if x).strip() or phone or "Client"
        if not any((first_name, last_name, phone, email, address, postal_code, city)):
            return jsonify({"ok": False, "error": "Renseignez au moins une information client"}), 400
        try:
            with db() as conn:
                ensure_order_schema(conn)
                row = conn.execute("SELECT id FROM caisse_clients WHERE id=%s", (client_id,)).fetchone()
                if not row:
                    return jsonify({"ok": False, "error": "Client introuvable"}), 404
                with conn.transaction():
                    conn.execute(
                        """UPDATE caisse_clients
                           SET first_name=%s,last_name=%s,display_name=%s,phone=%s,email=%s,
                               address=%s,postal_code=%s,city=%s,updated_at=(EXTRACT(EPOCH FROM NOW())*1000)::bigint
                           WHERE id=%s""",
                        (first_name,last_name,display_name,phone,email,address,postal_code,city,client_id),
                    )
            return jsonify({"ok": True, "client": {"id": client_id, "first_name": first_name,
                "last_name": last_name, "display_name": display_name, "phone": phone, "email": email,
                "address": address, "postal_code": postal_code, "city": city}})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Modification client impossible", "detail": str(exc)}), 500

    @app.get("/clients")
    def clients_management_page_phase6():
        return r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Clients — BÉCHÉFAA Caisse</title>
<style>body{font-family:Arial,sans-serif;margin:0;background:#f4f5f7;color:#111827}.wrap{max-width:1100px;margin:0 auto;padding:24px}.top{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:18px}.top a{text-decoration:none;color:#111827;font-weight:700}.card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px}.search{width:100%;box-sizing:border-box;padding:12px;border:2px solid #111827;border-radius:9px;font-size:15px;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.client{border:1px solid #e5e7eb;border-radius:10px;padding:14px;cursor:pointer;background:#fff}.client:hover{border-color:#9ca3af}.client b{display:block;font-size:16px;margin-bottom:4px}.muted{color:#6b7280;font-size:13px}.empty{padding:20px;color:#6b7280;text-align:center}.modal{display:none;position:fixed;inset:0;background:#0008;align-items:center;justify-content:center;padding:20px}.panel{background:#fff;max-width:620px;width:100%;border-radius:12px;padding:18px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fields .wide{grid-column:1/-1}.fields input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #d1d5db;border-radius:8px}.actions{display:flex;gap:10px;justify-content:flex-end;margin-top:14px}.btn{border:0;border-radius:8px;padding:10px 14px;font-weight:700;cursor:pointer}.save{background:#111827;color:white}.close{background:#e5e7eb}.ok{color:#15803d;font-size:13px;margin-top:8px}.err{color:#b91c1c;font-size:13px;margin-top:8px}</style></head><body><div class="wrap"><div class="top"><div><h1 style="margin:0">Clients</h1><div class="muted">Recherche et modification des fiches clients</div></div><a href="/pos">← Retour caisse</a></div><div class="card"><input id="q" class="search" placeholder="Rechercher par nom, téléphone ou email…"><div id="grid" class="grid"></div></div></div>
<div id="modal" class="modal"><div class="panel"><h2 style="margin-top:0">Modifier le client</h2><div class="fields"><input id="f_first" placeholder="Prénom"><input id="f_last" placeholder="Nom"><input class="wide" id="f_address" placeholder="Adresse"><input id="f_postal" maxlength="5" inputmode="numeric" placeholder="Code postal"><input id="f_city" placeholder="Ville"><input id="f_phone" placeholder="Téléphone"><input id="f_email" type="email" placeholder="Email"></div><div id="msg"></div><div class="actions"><button class="btn close" id="close">Fermer</button><button class="btn save" id="save">Enregistrer</button></div></div></div>
<script>let rows=[],current=null,t=null;const $=id=>document.getElementById(id);function esc(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}async function load(){const q=$('q').value.trim();const r=await fetch('/api/clients'+(q?'?q='+encodeURIComponent(q):''));const d=await r.json();rows=d.clients||[];$('grid').innerHTML=rows.length?rows.map((c,i)=>`<div class="client" data-i="${i}"><b>${esc(c.display_name||'Client')}</b><div class="muted">${esc(c.phone||'')}${c.email?' · '+esc(c.email):''}</div><div class="muted">${esc([c.address,c.postal_code,c.city].filter(Boolean).join(' '))}</div></div>`).join(''):'<div class="empty">Aucun client trouvé</div>';$('grid').querySelectorAll('[data-i]').forEach(x=>x.onclick=()=>openClient(rows[Number(x.dataset.i)]))}function openClient(c){current=c;$('f_first').value=c.first_name||'';$('f_last').value=c.last_name||'';$('f_address').value=c.address||'';$('f_postal').value=c.postal_code||'';$('f_city').value=c.city||'';$('f_phone').value=c.phone||'';$('f_email').value=c.email||'';$('msg').textContent='';$('modal').style.display='flex'}$('close').onclick=()=>{$('modal').style.display='none'};$('q').oninput=()=>{clearTimeout(t);t=setTimeout(load,180)};$('f_postal').oninput=async function(){this.value=this.value.replace(/\D/g,'').slice(0,5);if(this.value.length===5){try{const r=await fetch('/api/postal-code/'+this.value),d=await r.json();if(r.ok&&d.cities&&d.cities.length)$('f_city').value=d.cities[0]}catch(e){}}};$('save').onclick=async()=>{if(!current)return;const body={first_name:$('f_first').value.trim(),last_name:$('f_last').value.trim(),address:$('f_address').value.trim(),postal_code:$('f_postal').value.trim(),city:$('f_city').value.trim(),phone:$('f_phone').value.trim(),email:$('f_email').value.trim()};$('msg').className='';$('msg').textContent='Enregistrement…';try{const r=await fetch('/api/clients/'+encodeURIComponent(current.id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Erreur');$('msg').className='ok';$('msg').textContent='Client modifié.';await load();current=d.client}catch(e){$('msg').className='err';$('msg').textContent=e.message||'Modification impossible'}};load();</script></body></html>'''
