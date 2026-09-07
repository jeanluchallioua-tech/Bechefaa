"""Phase 1 — clients propres PostgreSQL pour BÉCHÉFAA-Caisse.

Aucun Wix / V1 / localStorage.
"""
import json
import time
import uuid
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import Response, g, jsonify, request


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
    return {
        "first_name": first_name,
        "last_name": last_name,
        "display_name": display_name,
        "phone": phone,
        "email": email,
        "address": address,
        "postal_code": postal_code,
        "city": city,
    }


def _has_customer(c):
    return any(c.get(k) for k in ("first_name", "last_name", "phone", "email", "address", "postal_code", "city"))


def _upsert_and_attach(conn, order_id, customer):
    now = int(time.time() * 1000)
    existing = None
    if customer["phone"]:
        existing = conn.execute(
            "SELECT id FROM caisse_clients WHERE phone=%s ORDER BY updated_at DESC LIMIT 1",
            (customer["phone"],),
        ).fetchone()
    if not existing and customer["email"]:
        existing = conn.execute(
            "SELECT id FROM caisse_clients WHERE LOWER(email)=LOWER(%s) ORDER BY updated_at DESC LIMIT 1",
            (customer["email"],),
        ).fetchone()

    client_id = existing["id"] if existing else "client-" + uuid.uuid4().hex
    display_name = customer["display_name"] or "Client"
    if existing:
        conn.execute(
            """UPDATE caisse_clients
               SET first_name=%s,last_name=%s,display_name=%s,phone=%s,email=%s,address=%s,postal_code=%s,city=%s,updated_at=%s
               WHERE id=%s""",
            (customer["first_name"], customer["last_name"], display_name, customer["phone"], customer["email"],
             customer["address"], customer["postal_code"], customer["city"], now, client_id),
        )
    else:
        conn.execute(
            """INSERT INTO caisse_clients
               (id,first_name,last_name,display_name,phone,email,address,postal_code,city,notes,created_at,updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'',%s,%s)""",
            (client_id, customer["first_name"], customer["last_name"], display_name, customer["phone"], customer["email"],
             customer["address"], customer["postal_code"], customer["city"], now, now),
        )

    conn.execute(
        """UPDATE caisse_orders
           SET customer_id=%s, customer_name=%s, phone=%s, email=%s, address=%s, postal_code=%s, city=%s, updated_at=%s
           WHERE id=%s""",
        (client_id, display_name, customer["phone"], customer["email"], customer["address"],
         customer["postal_code"], customer["city"], now, order_id),
    )
    return client_id, display_name


def register_customer_phase1(app, db, ensure_order_schema):
    @app.before_request
    def capture_customer_for_new_order():
        if request.path == "/api/orders" and request.method == "POST":
            payload = request.get_json(silent=True) or {}
            g.phase1_customer = _clean_customer(payload.get("customer"))

    @app.after_request
    def attach_customer_and_inject_pos(response):
        # Après création de commande, association client dans la même base PostgreSQL.
        if request.path == "/api/orders" and request.method == "POST" and response.status_code == 201:
            customer = getattr(g, "phase1_customer", None)
            if customer and _has_customer(customer):
                try:
                    data = response.get_json(silent=True) or {}
                    order_id = data.get("id")
                    if order_id:
                        with db() as conn:
                            with conn.transaction():
                                ensure_order_schema(conn)
                                client_id, display_name = _upsert_and_attach(conn, order_id, customer)
                        data["customer_id"] = client_id
                        data["customer_name"] = display_name
                        response.set_data(json.dumps(data, ensure_ascii=False))
                        response.content_type = "application/json; charset=utf-8"
                except Exception as exc:
                    # La commande reste enregistrée même si l'association client échoue ; le front reçoit l'info.
                    try:
                        data = response.get_json(silent=True) or {}
                        data["customer_warning"] = str(exc)
                        response.set_data(json.dumps(data, ensure_ascii=False))
                        response.content_type = "application/json; charset=utf-8"
                    except Exception:
                        pass

        # Injection isolée du formulaire client dans la page caisse existante.
        if request.path == "/pos" and response.status_code == 200 and response.mimetype == "text/html":
            html = response.get_data(as_text=True)
            customer_html = r'''
<style>
.customer-box{border:1px solid #d9dde3;border-radius:10px;padding:12px;margin:0 0 14px;background:#fafbfc}.customer-box h3{margin:0 0 10px}.customer-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.customer-grid .wide{grid-column:1/-1}.customer-grid input{width:100%;padding:9px;border:1px solid #ccd1d8;border-radius:8px;font-size:13px}.customer-note{font-size:11px;color:#667085;margin-top:7px}.customer-clear{margin-top:8px;border:0;background:transparent;color:#b42318;cursor:pointer;font-size:12px;padding:0}
</style>
<script>
(function(){
  function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
  ready(function(){
    const side=document.querySelector('.cart'); if(!side)return;
    const anchor=side.querySelector('.ticket-choice') || side.firstChild;
    const box=document.createElement('div'); box.className='customer-box';
    box.innerHTML=`<h3>Client</h3><div class="customer-grid">
      <input id="cust-first" placeholder="Prénom">
      <input id="cust-last" placeholder="Nom">
      <input class="wide" id="cust-address" placeholder="Adresse">
      <input id="cust-postal" inputmode="numeric" maxlength="5" placeholder="Code postal">
      <input id="cust-city" placeholder="Ville">
      <input id="cust-phone" inputmode="tel" placeholder="Téléphone">
      <input id="cust-email" type="email" placeholder="Email">
    </div><div class="customer-note" id="cust-note">Le code postal renseigne automatiquement la ville. La ville reste modifiable.</div><button class="customer-clear" type="button" id="cust-clear">Effacer le client</button>`;
    if(anchor && anchor.parentNode===side) side.insertBefore(box,anchor); else side.insertBefore(box,side.firstChild);

    const originalFetch=window.fetch.bind(window);
    window.fetch=function(input,init){
      try{
        const url=typeof input==='string'?input:(input&&input.url)||'';
        if(url==='/api/orders' && init && String(init.method||'GET').toUpperCase()==='POST' && init.body){
          const body=JSON.parse(init.body);
          body.customer={
            first_name:document.getElementById('cust-first').value.trim(),
            last_name:document.getElementById('cust-last').value.trim(),
            address:document.getElementById('cust-address').value.trim(),
            postal_code:document.getElementById('cust-postal').value.trim(),
            city:document.getElementById('cust-city').value.trim(),
            phone:document.getElementById('cust-phone').value.trim(),
            email:document.getElementById('cust-email').value.trim()
          };
          init=Object.assign({},init,{body:JSON.stringify(body)});
        }
      }catch(e){}
      return originalFetch(input,init);
    };

    let timer=null;
    document.getElementById('cust-postal').addEventListener('input',function(){
      const code=this.value.replace(/\D/g,'').slice(0,5); this.value=code;
      clearTimeout(timer); if(code.length!==5)return;
      document.getElementById('cust-note').textContent='Recherche de la ville…';
      timer=setTimeout(async()=>{
        try{const r=await originalFetch('/api/postal-code/'+encodeURIComponent(code)); const d=await r.json();
          if(r.ok&&d.ok&&d.cities&&d.cities.length){document.getElementById('cust-city').value=d.cities[0];document.getElementById('cust-note').textContent=d.cities.length>1?'Ville proposée automatiquement — modifiable.':'Ville renseignée automatiquement.'}
          else document.getElementById('cust-note').textContent='Ville non trouvée automatiquement — saisissez-la manuellement.';
        }catch(e){document.getElementById('cust-note').textContent='Ville non trouvée automatiquement — saisissez-la manuellement.'}
      },250);
    });
    document.getElementById('cust-clear').onclick=function(){['cust-first','cust-last','cust-address','cust-postal','cust-city','cust-phone','cust-email'].forEach(id=>document.getElementById(id).value='');document.getElementById('cust-note').textContent='Le code postal renseigne automatiquement la ville. La ville reste modifiable.'};
  });
})();
</script>
'''
            html = html.replace("</body>", customer_html + "</body>")
            response.set_data(html)
            response.content_length = len(response.get_data())
        return response

    @app.get("/api/postal-code/<code>")
    def postal_code_city(code):
        code = "".join(ch for ch in str(code) if ch.isdigit())[:5]
        if len(code) != 5:
            return jsonify({"ok": False, "error": "Code postal invalide"}), 400
        try:
            url = "https://geo.api.gouv.fr/communes?codePostal=" + quote(code) + "&fields=nom&format=json"
            req = Request(url, headers={"User-Agent": "BECHEFAA-Caisse/1.0"})
            with urlopen(req, timeout=4) as res:
                rows = json.loads(res.read().decode("utf-8"))
            cities = []
            for row in rows if isinstance(rows, list) else []:
                name = str(row.get("nom") or "").strip() if isinstance(row, dict) else ""
                if name and name not in cities:
                    cities.append(name)
            return jsonify({"ok": bool(cities), "postal_code": code, "cities": cities})
        except Exception as exc:
            return jsonify({"ok": False, "postal_code": code, "cities": [], "error": "Recherche ville indisponible", "detail": str(exc)}), 502

    @app.get("/api/clients")
    def list_clients():
        q = str(request.args.get("q") or "").strip()
        try:
            with db() as conn:
                ensure_order_schema(conn)
                conn.commit()
                if q:
                    like = "%" + q + "%"
                    rows = conn.execute(
                        """SELECT id,first_name,last_name,display_name,phone,email,address,postal_code,city,created_at,updated_at
                           FROM caisse_clients
                           WHERE display_name ILIKE %s OR phone ILIKE %s OR email ILIKE %s
                           ORDER BY updated_at DESC LIMIT 50""",
                        (like, like, like),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT id,first_name,last_name,display_name,phone,email,address,postal_code,city,created_at,updated_at
                           FROM caisse_clients ORDER BY updated_at DESC LIMIT 100"""
                    ).fetchall()
            return jsonify({"ok": True, "clients": [dict(r) for r in rows], "count": len(rows)})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Clients indisponibles", "detail": str(exc)}), 500
