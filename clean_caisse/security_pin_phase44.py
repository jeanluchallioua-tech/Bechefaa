"""Phase 4.4 — sécurité PIN et accès interne aux identifiants de commande.

- Deux profils : Administrateur et Utilisateur Caisse.
- Les deux profils ont les mêmes droits opérationnels.
- Les PIN sont stockés uniquement sous forme de hash Werkzeug.
- L'accès interne utilise un jeton aléatoire HttpOnly à durée limitée.
- L'annulation d'une commande est bloquée côté serveur sans session PIN valide.
- Aucun lien vers cette zone n'est ajouté à la caisse, la cuisine ou l'historique.
"""
import secrets
import time

from flask import Response, jsonify, make_response, request
from werkzeug.security import check_password_hash, generate_password_hash

COOKIE_NAME = "bechefaa_security_phase44"
SESSION_SECONDS = 30 * 60
PROFILES = {
    "ADMIN": "Administrateur",
    "CAISSE": "Utilisateur Caisse",
}


def register_security_pin_phase44(app, db, ensure_order_schema):
    def ensure_security_schema(conn):
        ensure_order_schema(conn)
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_number INTEGER NULL")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_label TEXT NULL")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS cancellation_hidden BOOLEAN NOT NULL DEFAULT FALSE")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'À ENCAISSER'")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(12,2) NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS z_closure_id BIGINT NULL")
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_security_users (
            user_key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            pin_hash TEXT NULL,
            updated_at BIGINT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_security_sessions (
            token TEXT PRIMARY KEY,
            user_key TEXT NOT NULL REFERENCES caisse_security_users(user_key) ON DELETE CASCADE,
            created_at BIGINT NOT NULL,
            expires_at BIGINT NOT NULL
        )""")
        now = int(time.time() * 1000)
        for key, label in PROFILES.items():
            conn.execute("""INSERT INTO caisse_security_users(user_key,label,pin_hash,updated_at)
                            VALUES (%s,%s,NULL,%s)
                            ON CONFLICT (user_key) DO UPDATE SET label=EXCLUDED.label""",
                         (key, label, now))
        conn.execute("DELETE FROM caisse_security_sessions WHERE expires_at < %s", (now,))

    def valid_pin(pin):
        return isinstance(pin, str) and pin.isdigit() and 4 <= len(pin) <= 8

    def current_user(conn):
        token = request.cookies.get(COOKIE_NAME, "")
        if not token:
            return None
        now = int(time.time() * 1000)
        return conn.execute("""SELECT s.token,s.user_key,u.label,s.expires_at
                               FROM caisse_security_sessions s
                               JOIN caisse_security_users u ON u.user_key=s.user_key
                               WHERE s.token=%s AND s.expires_at>%s""", (token, now)).fetchone()

    @app.before_request
    def protect_sensitive_cancellation_phase44():
        path = request.path
        if request.method != "POST" or not (path.startswith("/api/orders/") and path.endswith("/cancel-phase44")):
            return None
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_security_schema(conn)
                    user = current_user(conn)
            if user:
                return None
            return jsonify({"ok": False, "error": "Code PIN requis pour cette opération", "code": "PIN_REQUIRED"}), 403
        except Exception as exc:
            return jsonify({"ok": False, "error": "Sécurité PIN indisponible", "detail": str(exc)}), 503

    @app.get("/api/security/status-phase44")
    def security_status_phase44():
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_security_schema(conn)
                    rows = conn.execute("SELECT user_key,label,pin_hash FROM caisse_security_users ORDER BY user_key").fetchall()
                    user = current_user(conn)
            return jsonify({
                "ok": True,
                "configured": all(bool(r["pin_hash"]) for r in rows),
                "profiles": [{"key": r["user_key"], "label": r["label"], "configured": bool(r["pin_hash"])} for r in rows],
                "authenticated": bool(user),
                "user": ({"key": user["user_key"], "label": user["label"]} if user else None),
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Sécurité indisponible", "detail": str(exc)}), 500

    @app.post("/api/security/bootstrap-phase44")
    def security_bootstrap_phase44():
        payload = request.get_json(silent=True) or {}
        admin_pin = str(payload.get("admin_pin") or "")
        caisse_pin = str(payload.get("caisse_pin") or "")
        if not valid_pin(admin_pin) or not valid_pin(caisse_pin):
            return jsonify({"ok": False, "error": "Chaque PIN doit contenir 4 à 8 chiffres"}), 400
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_security_schema(conn)
                    row = conn.execute("SELECT COUNT(*) AS n FROM caisse_security_users WHERE pin_hash IS NOT NULL AND pin_hash<>''").fetchone()
                    if int(row["n"] or 0) > 0:
                        return jsonify({"ok": False, "error": "Initialisation déjà effectuée"}), 409
                    now = int(time.time() * 1000)
                    conn.execute("UPDATE caisse_security_users SET pin_hash=%s,updated_at=%s WHERE user_key='ADMIN'",
                                 (generate_password_hash(admin_pin), now))
                    conn.execute("UPDATE caisse_security_users SET pin_hash=%s,updated_at=%s WHERE user_key='CAISSE'",
                                 (generate_password_hash(caisse_pin), now))
            return jsonify({"ok": True, "configured": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Initialisation PIN impossible", "detail": str(exc)}), 500

    @app.post("/api/security/login-phase44")
    def security_login_phase44():
        payload = request.get_json(silent=True) or {}
        user_key = str(payload.get("profile") or "").upper()
        pin = str(payload.get("pin") or "")
        if user_key not in PROFILES or not valid_pin(pin):
            return jsonify({"ok": False, "error": "Profil ou PIN invalide"}), 400
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_security_schema(conn)
                    row = conn.execute("SELECT user_key,label,pin_hash FROM caisse_security_users WHERE user_key=%s", (user_key,)).fetchone()
                    if not row or not row["pin_hash"]:
                        return jsonify({"ok": False, "error": "PIN non configuré"}), 409
                    if not check_password_hash(row["pin_hash"], pin):
                        return jsonify({"ok": False, "error": "PIN incorrect"}), 403
                    now = int(time.time() * 1000)
                    token = secrets.token_urlsafe(32)
                    expires_at = now + SESSION_SECONDS * 1000
                    conn.execute("INSERT INTO caisse_security_sessions(token,user_key,created_at,expires_at) VALUES (%s,%s,%s,%s)",
                                 (token, user_key, now, expires_at))
            response = make_response(jsonify({"ok": True, "user": {"key": user_key, "label": PROFILES[user_key]}, "expires_in": SESSION_SECONDS}))
            response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True, secure=request.is_secure, samesite="Strict", path="/")
            return response
        except Exception as exc:
            return jsonify({"ok": False, "error": "Connexion PIN impossible", "detail": str(exc)}), 500

    @app.post("/api/security/logout-phase44")
    def security_logout_phase44():
        token = request.cookies.get(COOKIE_NAME, "")
        try:
            if token:
                with db() as conn:
                    with conn.transaction():
                        ensure_security_schema(conn)
                        conn.execute("DELETE FROM caisse_security_sessions WHERE token=%s", (token,))
        except Exception:
            pass
        response = make_response(jsonify({"ok": True}))
        response.delete_cookie(COOKIE_NAME, path="/")
        return response

    @app.get("/api/security/orders-phase44")
    def security_orders_phase44():
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_security_schema(conn)
                    user = current_user(conn)
                    if not user:
                        return jsonify({"ok": False, "error": "Authentification PIN requise"}), 403
                    rows = conn.execute("""SELECT id,customer_name,source,status,total,table_number,table_label,
                                                  payment_status,paid_amount,z_closure_id,created_at
                                           FROM caisse_orders
                                           WHERE COALESCE(cancellation_hidden,FALSE)=FALSE
                                             AND UPPER(COALESCE(status,''))<>'ANNULÉE'
                                           ORDER BY created_at DESC
                                           LIMIT 100""").fetchall()
            orders = []
            for r in rows:
                source = str(r["source"] or "").upper()
                customer = str(r["customer_name"] or "").strip()
                if r.get("table_label"):
                    label = str(r["table_label"]).upper()
                elif source in ("LIVRAISON", "DELIVERY"):
                    label = "LIVRAISON" + ((" — " + customer) if customer and customer.lower() != "client livraison" else "")
                else:
                    label = "À EMPORTER" + ((" — " + customer) if customer and customer.lower() != "client comptoir" else "")
                ps = str(r.get("payment_status") or "À ENCAISSER").upper()
                unpaid = float(r.get("paid_amount") or 0) <= 0 and ps in {"À ENCAISSER", "A ENCAISSER", "NON PAYÉE", "NON PAYEE"} and r.get("z_closure_id") is None
                orders.append({
                    "id": r["id"], "label": label, "status": r["status"], "total": float(r["total"] or 0),
                    "payment_status": r.get("payment_status"), "unpaid_cancellable": unpaid,
                })
            return jsonify({"ok": True, "user": {"key": user["user_key"], "label": user["label"]}, "orders": orders})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Lecture interne impossible", "detail": str(exc)}), 500

    @app.get("/securite")
    def security_page_phase44():
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Sécurité</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#111827}.wrap{max-width:850px;margin:40px auto;padding:20px}.box{background:#fff;border-radius:16px;padding:22px;box-shadow:0 5px 20px #0001;margin-bottom:16px}h1,h2{margin-top:0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}input,select,button{width:100%;min-height:48px;border-radius:9px;border:1px solid #cfd4dc;padding:10px;font-size:16px}button{background:#111827;color:#fff;font-weight:900;cursor:pointer}.danger{background:#b42318;border-color:#b42318}.muted{color:#667085;font-size:13px}.msg{margin-top:10px;font-weight:800}.order{border-top:1px solid #e5e7eb;padding:14px 0}.order:first-child{border-top:0}.id{font-family:monospace;font-size:12px;background:#f3f4f6;padding:7px;border-radius:7px;word-break:break-all;margin:6px 0}.row{display:flex;gap:10px;align-items:center}.row>div{flex:1}.row button{width:auto;padding:8px 13px;min-height:40px}.hidden{display:none}@media(max-width:650px){.grid{grid-template-columns:1fr}.row{align-items:flex-start;flex-direction:column}.row button{width:100%}}
</style></head><body><div class="wrap"><div class="box"><h1>Zone sécurité BÉCHÉFAA</h1><p class="muted">Zone interne non affichée dans la caisse, la cuisine ou l’historique. Les identifiants techniques ne sont accessibles qu’après authentification PIN.</p><div id="setup" class="hidden"><h2>Première configuration</h2><div class="grid"><input id="admin-pin" type="password" inputmode="numeric" placeholder="PIN Administrateur (4 à 8 chiffres)"><input id="caisse-pin" type="password" inputmode="numeric" placeholder="PIN Utilisateur Caisse (4 à 8 chiffres)"></div><button onclick="bootstrap()" style="margin-top:10px">Enregistrer les deux PIN</button></div><div id="login" class="hidden"><h2>Identification</h2><div class="grid"><select id="profile"><option value="ADMIN">Administrateur</option><option value="CAISSE">Utilisateur Caisse</option></select><input id="pin" type="password" inputmode="numeric" placeholder="Code PIN"></div><button onclick="login()" style="margin-top:10px">Ouvrir la zone interne</button></div><div id="connected" class="hidden"><div class="row"><div><b id="who"></b><div class="muted">Session sécurisée limitée à 30 minutes.</div></div><button onclick="logout()">Fermer la session</button></div></div><div id="msg" class="msg"></div></div><div id="orders-box" class="box hidden"><h2>Commandes — accès interne</h2><p class="muted">L’ID technique apparaît uniquement dans cette zone protégée. L’annulation n’est proposée que pour les commandes non payées et non clôturées.</p><div id="orders"></div></div></div><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const msg=t=>document.getElementById('msg').textContent=t||'';
async function status(){let r=await fetch('/api/security/status-phase44',{cache:'no-store'}),d=await r.json();document.getElementById('setup').classList.toggle('hidden',!!d.configured);document.getElementById('login').classList.toggle('hidden',!d.configured||!!d.authenticated);document.getElementById('connected').classList.toggle('hidden',!d.authenticated);document.getElementById('orders-box').classList.toggle('hidden',!d.authenticated);if(d.authenticated){document.getElementById('who').textContent=d.user.label;await loadOrders()}}
async function bootstrap(){msg('Enregistrement…');let r=await fetch('/api/security/bootstrap-phase44',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({admin_pin:document.getElementById('admin-pin').value,caisse_pin:document.getElementById('caisse-pin').value})}),d=await r.json();msg(d.ok?'PIN enregistrés. Identifiez-vous.':(d.error||'Erreur'));if(d.ok)status()}
async function login(){msg('Vérification…');let r=await fetch('/api/security/login-phase44',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile:document.getElementById('profile').value,pin:document.getElementById('pin').value})}),d=await r.json();msg(d.ok?'Accès autorisé.':(d.error||'Erreur'));if(d.ok)status()}
async function logout(){await fetch('/api/security/logout-phase44',{method:'POST'});msg('Session fermée.');document.getElementById('orders').innerHTML='';status()}
async function loadOrders(){let r=await fetch('/api/security/orders-phase44',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok){msg(d.error||'Lecture impossible');return}document.getElementById('orders').innerHTML=d.orders.length?d.orders.map(o=>`<div class="order"><div class="row"><div><b>${esc(o.label)}</b><div class="muted">${esc(o.status)} · ${Number(o.total||0).toFixed(2).replace('.',',')} € · ${esc(o.payment_status||'')}</div><div class="id">ID technique : ${esc(o.id)}</div></div>${o.unpaid_cancellable?`<button class="danger" onclick="cancelOrder('${esc(o.id)}','${esc(o.label)}')">Annuler</button>`:''}</div></div>`).join(''):'<div class="muted">Aucune commande.</div>'}
async function cancelOrder(id,label){if(!confirm('Annuler '+label+' ? Cette action concerne uniquement une commande non payée.'))return;let r=await fetch('/api/orders/'+encodeURIComponent(id)+'/cancel-phase44',{method:'POST'}),d=await r.json();if(!r.ok||!d.ok){alert(d.error||'Annulation impossible');return}await loadOrders()}
status();
</script></body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")
