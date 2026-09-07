"""Phase 1 — clients propres PostgreSQL pour BÉCHÉFAA-Caisse.
Aucun Wix / V1 / localStorage.
"""
import json
import time
import uuid
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import g, jsonify, request


def _clean_customer(raw):
    raw = raw if isinstance(raw, dict) else {}
    first_name = str(raw.get("first_name") or "").strip()
    last_name = str(raw.get("last_name") or "").strip()
    phone = str(raw.get("phone") or "").strip()
    email = str(raw.get("email") or "").strip().lower()
    address = str(raw.get("address") or "").strip()
    postal_code = str(raw.get("postal_code") or "").strip()
    city = str(raw.get("city") or "").strip()
    display_name = " ".join(x for x in (first_name, last_name) if x).strip()
    return {"first_name":first_name,"last_name":last_name,"display_name":display_name,"phone":phone,"email":email,"address":address,"postal_code":postal_code,"city":city}


def _has_customer(c):
    return any(c.get(k) for k in ("first_name","last_name","phone","email","address","postal_code","city"))


def _find_existing(conn, customer):
    if customer["phone"]:
        row = conn.execute("SELECT id FROM caisse_clients WHERE phone=%s ORDER BY updated_at DESC LIMIT 1", (customer["phone"],)).fetchone()
        if row: return row
    if customer["email"]:
        row = conn.execute("SELECT id FROM caisse_clients WHERE LOWER(email)=LOWER(%s) ORDER BY updated_at DESC LIMIT 1", (customer["email"],)).fetchone()
        if row: return row
    return None


def _save_customer(conn, customer):
    now = int(time.time()*1000)
    existing = _find_existing(conn, customer)
    client_id = existing["id"] if existing else "client-"+uuid.uuid4().hex
    display_name = customer["display_name"] or customer["phone"] or "Client"
    if existing:
        conn.execute("""UPDATE caisse_clients SET first_name=%s,last_name=%s,display_name=%s,phone=%s,email=%s,address=%s,postal_code=%s,city=%s,updated_at=%s WHERE id=%s""",
            (customer["first_name"],customer["last_name"],display_name,customer["phone"],customer["email"],customer["address"],customer["postal_code"],customer["city"],now,client_id))
    else:
        conn.execute("""INSERT INTO caisse_clients (id,first_name,last_name,display_name,phone,email,address,postal_code,city,notes,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'',%s,%s)""",
            (client_id,customer["first_name"],customer["last_name"],display_name,customer["phone"],customer["email"],customer["address"],customer["postal_code"],customer["city"],now,now))
    return client_id, display_name


def _upsert_and_attach(conn, order_id, customer):
    client_id, display_name = _save_customer(conn, customer)
    now=int(time.time()*1000)
    conn.execute("""UPDATE caisse_orders SET customer_id=%s,customer_name=%s,phone=%s,email=%s,address=%s,postal_code=%s,city=%s,updated_at=%s WHERE id=%s""",
        (client_id,display_name,customer["phone"],customer["email"],customer["address"],customer["postal_code"],customer["city"],now,order_id))
    return client_id, display_name


def register_customer_phase1(app, db, ensure_order_schema):
    @app.before_request
    def capture_customer_for_new_order():
        if request.path=="/api/orders" and request.method=="POST":
            payload=request.get_json(silent=True) or {}
            g.phase1_customer=_clean_customer(payload.get("customer"))

    @app.after_request
    def attach_customer_and_inject_pos(response):
        if request.path=="/api/orders" and request.method=="POST" and response.status_code==201:
            customer=getattr(g,"phase1_customer",None)
            if customer and _has_customer(customer):
                try:
                    data=response.get_json(silent=True) or {}; order_id=data.get("id")
                    if order_id:
                        with db() as conn:
                            with conn.transaction():
                                ensure_order_schema(conn); client_id,display_name=_upsert_and_attach(conn,order_id,customer)
                        data["customer_id"]=client_id; data["customer_name"]=display_name
                        response.set_data(json.dumps(data,ensure_ascii=False)); response.content_type="application/json; charset=utf-8"
                except Exception as exc:
                    try:
                        data=response.get_json(silent=True) or {}; data["customer_warning"]=str(exc)
                        response.set_data(json.dumps(data,ensure_ascii=False)); response.content_type="application/json; charset=utf-8"
                    except Exception: pass

        if request.path=="/pos" and response.status_code==200 and response.mimetype=="text/html":
            html=response.get_data(as_text=True)
            customer_html=r'''
<style>
.customer-box{position:relative;border:1px solid #d9dde3;border-radius:10px;padding:12px;margin:0 0 14px;background:#fafbfc}.customer-box h3{margin:0 0 8px}.customer-search{width:100%;padding:10px;border:2px solid #111827;border-radius:8px;font-size:14px;margin-bottom:8px}.customer-results{display:none;position:absolute;z-index:50;left:12px;right:12px;top:82px;background:#fff;border:1px solid #ccd1d8;border-radius:8px;max-height:210px;overflow:auto;box-shadow:0 5px 16px #0002}.customer-result{padding:10px;border-bottom:1px solid #eee;cursor:pointer}.customer-result:hover{background:#f0f2f5}.customer-result b{display:block}.customer-result small{color:#667085}.customer-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.customer-grid .wide{grid-column:1/-1}.customer-grid input{width:100%;padding:9px;border:1px solid #ccd1d8;border-radius:8px;font-size:13px}.customer-actions{display:flex;gap:8px;margin-top:9px}.customer-save{flex:1;border:0;border-radius:8px;padding:10px;background:#14804a;color:white;font-weight:800;cursor:pointer}.customer-clear{border:0;background:transparent;color:#b42318;cursor:pointer;font-size:12px}.customer-note{font-size:11px;color:#667085;margin-top:7px}.customer-ok{color:#14804a;font-weight:700}
</style>
<script>
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
  const side=document.querySelector('.cart');if(!side)return;const anchor=side.querySelector('.ticket-choice')||side.firstChild;
  const box=document.createElement('div');box.className='customer-box';box.innerHTML=`<h3>Client</h3><input id="cust-search" class="customer-search" autocomplete="off" placeholder="Rechercher nom ou téléphone…"><div id="cust-results" class="customer-results"></div><div class="customer-grid"><input id="cust-first" placeholder="Prénom"><input id="cust-last" placeholder="Nom"><input class="wide" id="cust-address" placeholder="Adresse"><input id="cust-postal" inputmode="numeric" maxlength="5" placeholder="Code postal"><input id="cust-city" placeholder="Ville"><input id="cust-phone" inputmode="tel" placeholder="Téléphone"><input id="cust-email" type="email" placeholder="Email"></div><div class="customer-note" id="cust-note">Recherchez un client existant ou saisissez un nouveau client.</div><div class="customer-actions"><button class="customer-save" type="button" id="cust-save">Enregistrer le client</button><button class="customer-clear" type="button" id="cust-clear">Effacer</button></div>`;
  if(anchor&&anchor.parentNode===side)side.insertBefore(box,anchor);else side.insertBefore(box,side.firstChild);
  const originalFetch=window.fetch.bind(window), ids=['first','last','address','postal','city','phone','email'];
  function values(){let o={};ids.forEach(k=>o[k]=document.getElementById('cust-'+k).value.trim());return{first_name:o.first,last_name:o.last,address:o.address,postal_code:o.postal,city:o.city,phone:o.phone,email:o.email}}
  function fill(c){document.getElementById('cust-first').value=c.first_name||'';document.getElementById('cust-last').value=c.last_name||'';document.getElementById('cust-address').value=c.address||'';document.getElementById('cust-postal').value=c.postal_code||'';document.getElementById('cust-city').value=c.city||'';document.getElementById('cust-phone').value=c.phone||'';document.getElementById('cust-email').value=c.email||'';document.getElementById('cust-search').value=c.display_name||c.phone||'';document.getElementById('cust-results').style.display='none';document.getElementById('cust-note').innerHTML='<span class="customer-ok">Client sélectionné.</span>'}
  window.fetch=function(input,init){try{const url=typeof input==='string'?input:(input&&input.url)||'';if(url==='/api/orders'&&init&&String(init.method||'GET').toUpperCase()==='POST'&&init.body){const body=JSON.parse(init.body);body.customer=values();init=Object.assign({},init,{body:JSON.stringify(body)})}}catch(e){}return originalFetch(input,init)};
  let searchTimer=null;document.getElementById('cust-search').addEventListener('input',function(){const q=this.value.trim(),res=document.getElementById('cust-results');clearTimeout(searchTimer);if(q.length<2){res.style.display='none';return}searchTimer=setTimeout(async()=>{try{let r=await originalFetch('/api/clients?q='+encodeURIComponent(q)),d=await r.json(),rows=d.clients||[];res.innerHTML=rows.length?rows.slice(0,8).map((c,i)=>`<div class="customer-result" data-i="${i}"><b>${String(c.display_name||'Client').replace(/[<>]/g,'')}</b><small>${String(c.phone||'').replace(/[<>]/g,'')}${c.city?' · '+String(c.city).replace(/[<>]/g,''):''}</small></div>`).join(''):'<div class="customer-result">Aucun client trouvé</div>';res.style.display='block';res.querySelectorAll('[data-i]').forEach(el=>el.onclick=()=>fill(rows[Number(el.dataset.i)]))}catch(e){res.style.display='none'}},220)});
  let postalTimer=null;document.getElementById('cust-postal').addEventListener('input',function(){const code=this.value.replace(/\D/g,'').slice(0,5);this.value=code;clearTimeout(postalTimer);if(code.length!==5)return;document.getElementById('cust-note').textContent='Recherche de la ville…';postalTimer=setTimeout(async()=>{try{const r=await originalFetch('/api/postal-code/'+encodeURIComponent(code)),d=await r.json();if(r.ok&&d.ok&&d.cities&&d.cities.length){document.getElementById('cust-city').value=d.cities[0];document.getElementById('cust-note').textContent='Ville renseignée automatiquement.'}else document.getElementById('cust-note').textContent='Ville non trouvée — saisissez-la.'}catch(e){document.getElementById('cust-note').textContent='Ville non trouvée — saisissez-la.'}},250)});
  document.getElementById('cust-save').onclick=async function(){const c=values();document.getElementById('cust-note').textContent='Enregistrement…';try{let r=await originalFetch('/api/clients',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Erreur');document.getElementById('cust-search').value=d.client.display_name||d.client.phone||'';document.getElementById('cust-note').innerHTML='<span class="customer-ok">Client enregistré.</span>'}catch(e){document.getElementById('cust-note').textContent='Enregistrement client impossible.'}};
  document.getElementById('cust-clear').onclick=function(){document.getElementById('cust-search').value='';ids.forEach(k=>document.getElementById('cust-'+k).value='');document.getElementById('cust-results').style.display='none';document.getElementById('cust-note').textContent='Recherchez un client existant ou saisissez un nouveau client.'};
 });
})();
</script>'''
            html=html.replace("</body>",customer_html+"</body>");response.set_data(html);response.content_length=len(response.get_data())
        return response

    @app.get("/api/postal-code/<code>")
    def postal_code_city(code):
        code="".join(ch for ch in str(code) if ch.isdigit())[:5]
        if len(code)!=5:return jsonify({"ok":False,"error":"Code postal invalide"}),400
        try:
            url="https://geo.api.gouv.fr/communes?codePostal="+quote(code)+"&fields=nom&format=json";req=Request(url,headers={"User-Agent":"BECHEFAA-Caisse/1.0"})
            with urlopen(req,timeout=4) as res: rows=json.loads(res.read().decode("utf-8"))
            cities=[]
            for row in rows if isinstance(rows,list) else []:
                name=str(row.get("nom") or "").strip() if isinstance(row,dict) else ""
                if name and name not in cities:cities.append(name)
            return jsonify({"ok":bool(cities),"postal_code":code,"cities":cities})
        except Exception as exc:return jsonify({"ok":False,"postal_code":code,"cities":[],"error":"Recherche ville indisponible","detail":str(exc)}),502

    @app.route("/api/clients",methods=["GET","POST"])
    def clients_api():
        try:
            with db() as conn:
                ensure_order_schema(conn);conn.commit()
                if request.method=="POST":
                    customer=_clean_customer(request.get_json(silent=True) or {})
                    if not _has_customer(customer):return jsonify({"ok":False,"error":"Renseignez au moins une information client"}),400
                    with conn.transaction():client_id,display_name=_save_customer(conn,customer)
                    return jsonify({"ok":True,"client":{"id":client_id,"display_name":display_name,**customer}})
                q=str(request.args.get("q") or "").strip()
                if q:
                    like="%"+q+"%";rows=conn.execute("""SELECT id,first_name,last_name,display_name,phone,email,address,postal_code,city,created_at,updated_at FROM caisse_clients WHERE display_name ILIKE %s OR phone ILIKE %s OR email ILIKE %s ORDER BY updated_at DESC LIMIT 50""",(like,like,like)).fetchall()
                else:rows=conn.execute("""SELECT id,first_name,last_name,display_name,phone,email,address,postal_code,city,created_at,updated_at FROM caisse_clients ORDER BY updated_at DESC LIMIT 100""").fetchall()
            return jsonify({"ok":True,"clients":[dict(r) for r in rows],"count":len(rows)})
        except Exception as exc:return jsonify({"ok":False,"error":"Clients indisponibles","detail":str(exc)}),500
