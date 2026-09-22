"""Phase 6 — gestion clients isolée.

INACTIF : module non importé / non enregistré dans wsgi_caisse.py.

But strict : ajouter une page dédiée /clients pour rechercher et modifier les clients
existants, sans toucher au flux de commande, au paiement, à la cuisine, au Z ou aux
tickets. La création client existante de customer_phase1 reste l'autorité.
"""
import csv
import io
import re
import time
import uuid

from flask import jsonify, request
from openpyxl import load_workbook


def _normalize_import_header(value):
    text = str(value or "").strip().lower()
    repl = {
        "é":"e","è":"e","ê":"e","ë":"e","à":"a","â":"a","ä":"a",
        "î":"i","ï":"i","ô":"o","ö":"o","ù":"u","û":"u","ü":"u","ç":"c",
        "’":"'","–":"-","—":"-",
    }
    for a,b in repl.items():
        text = text.replace(a,b)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    aliases = {
        "telephone":"phone","tel":"phone","mobile":"phone",
        "nom_raison_sociale":"display_name","nom_raison_social":"display_name",
        "nom_prenom":"display_name","client":"display_name","nom_complet":"display_name",
        "prenom":"first_name","nom":"last_name",
        "adresse":"address","code_postal":"postal_code","cp":"postal_code",
        "ville":"city","email":"email","e_mail":"email","mail":"email",
        "code_porte_interphone":"door_intercom","code_porte":"door_intercom",
        "interphone":"door_intercom","porte_interphone":"door_intercom",
        "notes":"notes","a_verifier":"notes",
    }
    return aliases.get(text, text)


def _clean_import_phone(value):
    raw = str(value or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    if digits.startswith("33") and not digits.startswith("+33"):
        digits = "+" + digits
    return digits


def _import_client_rows(conn, rows):
    now = int(time.time() * 1000)
    imported = 0
    updated = 0
    created = 0
    skipped = 0

    for raw in rows:
        if not isinstance(raw, dict):
            skipped += 1
            continue

        first_name = str(raw.get("first_name") or "").strip()
        last_name = str(raw.get("last_name") or "").strip()
        display_name = str(raw.get("display_name") or "").strip()
        phone = _clean_import_phone(raw.get("phone"))
        email = str(raw.get("email") or "").strip().lower()
        address = str(raw.get("address") or "").strip()
        postal_code = str(raw.get("postal_code") or "").strip()
        city = str(raw.get("city") or "").strip()
        door_intercom = str(raw.get("door_intercom") or "").strip()
        notes = str(raw.get("notes") or "").strip()

        if display_name and not first_name and not last_name:
            last_name = display_name
        display_name = " ".join(x for x in (first_name, last_name) if x).strip() or display_name or phone or email

        if not any((display_name, phone, email, address, postal_code, city, door_intercom)):
            skipped += 1
            continue

        existing = None
        if phone:
            existing = conn.execute(
                "SELECT * FROM caisse_clients WHERE phone=%s ORDER BY updated_at DESC LIMIT 1",
                (phone,),
            ).fetchone()
        if not existing and email:
            existing = conn.execute(
                "SELECT * FROM caisse_clients WHERE LOWER(email)=LOWER(%s) ORDER BY updated_at DESC LIMIT 1",
                (email,),
            ).fetchone()

        if existing:
            def keep(new_value, old_key):
                return new_value if str(new_value or "").strip() else str(existing.get(old_key) or "").strip()

            first_name2 = keep(first_name, "first_name")
            last_name2 = keep(last_name, "last_name")
            display_name2 = " ".join(x for x in (first_name2, last_name2) if x).strip() or keep(display_name, "display_name")
            conn.execute(
                """UPDATE caisse_clients
                   SET first_name=%s,last_name=%s,display_name=%s,phone=%s,email=%s,
                       address=%s,postal_code=%s,city=%s,door_intercom=%s,notes=%s,updated_at=%s
                   WHERE id=%s""",
                (
                    first_name2,last_name2,display_name2,
                    keep(phone,"phone"),keep(email,"email"),keep(address,"address"),
                    keep(postal_code,"postal_code"),keep(city,"city"),
                    keep(door_intercom,"door_intercom"),keep(notes,"notes"),
                    now,existing["id"],
                ),
            )
            updated += 1
        else:
            client_id = "client-" + uuid.uuid4().hex
            conn.execute(
                """INSERT INTO caisse_clients
                   (id,first_name,last_name,display_name,phone,email,address,postal_code,city,
                    door_intercom,notes,created_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    client_id,first_name,last_name,display_name,phone,email,address,
                    postal_code,city,door_intercom,notes,now,now,
                ),
            )
            created += 1
        imported += 1

    return {"imported": imported, "created": created, "updated": updated, "skipped": skipped}


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
        door_intercom = str(payload.get("door_intercom") or "").strip()
        if postal_code and (len(postal_code) != 5 or not postal_code.isdigit()):
            return jsonify({"ok": False, "error": "Code postal invalide"}), 400
        display_name = " ".join(x for x in (first_name, last_name) if x).strip() or phone or "Client"
        if not any((first_name, last_name, phone, email, address, postal_code, city, door_intercom)):
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
                               address=%s,postal_code=%s,city=%s,door_intercom=%s,updated_at=(EXTRACT(EPOCH FROM NOW())*1000)::bigint
                           WHERE id=%s""",
                        (first_name,last_name,display_name,phone,email,address,postal_code,city,door_intercom,client_id),
                    )
            return jsonify({"ok": True, "client": {"id": client_id, "first_name": first_name,
                "last_name": last_name, "display_name": display_name, "phone": phone, "email": email,
                "address": address, "postal_code": postal_code, "city": city, "door_intercom": door_intercom}})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Modification client impossible", "detail": str(exc)}), 500



    @app.post("/api/clients/import-phase6")
    def import_clients_phase6():
        upload = request.files.get("file")
        if not upload or not upload.filename:
            return jsonify({"ok": False, "error": "Aucun fichier sélectionné"}), 400

        name = upload.filename.lower()
        if not (name.endswith(".xlsx") or name.endswith(".csv")):
            return jsonify({"ok": False, "error": "Format accepté : .xlsx ou .csv"}), 400

        data = upload.read()
        if len(data) > 5 * 1024 * 1024:
            return jsonify({"ok": False, "error": "Fichier trop volumineux (5 Mo maximum)"}), 413

        try:
            rows = []
            if name.endswith(".xlsx"):
                wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
                preferred = "Clients à importer"
                ws = wb[preferred] if preferred in wb.sheetnames else wb[wb.sheetnames[0]]
                iterator = ws.iter_rows(values_only=True)
                headers_raw = next(iterator, None)
                if not headers_raw:
                    return jsonify({"ok": False, "error": "Fichier Excel vide"}), 400
                headers = [_normalize_import_header(x) for x in headers_raw]
                for values in iterator:
                    if not any(v is not None and str(v).strip() for v in values):
                        continue
                    rows.append({headers[i]: values[i] if i < len(values) else "" for i in range(len(headers))})
            else:
                text = data.decode("utf-8-sig")
                sample = text[:4096]
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
                except Exception:
                    dialect = csv.excel
                reader = csv.DictReader(io.StringIO(text), dialect=dialect)
                for raw in reader:
                    rows.append({_normalize_import_header(k): v for k,v in (raw or {}).items()})

            if not rows:
                return jsonify({"ok": False, "error": "Aucun client trouvé dans le fichier"}), 400
            if len(rows) > 5000:
                return jsonify({"ok": False, "error": "Import limité à 5000 clients"}), 400

            with db() as conn:
                ensure_order_schema(conn)
                conn.commit()
                with conn.transaction():
                    result = _import_client_rows(conn, rows)

            return jsonify({"ok": True, **result})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Import clients impossible", "detail": str(exc)}), 500

    @app.delete("/api/clients/<client_id>")
    def delete_client_phase6(client_id):
        try:
            with db() as conn:
                ensure_order_schema(conn)
                row = conn.execute(
                    "SELECT id,display_name FROM caisse_clients WHERE id=%s",
                    (client_id,),
                ).fetchone()
                if not row:
                    return jsonify({"ok": False, "error": "Client introuvable"}), 404

                with conn.transaction():
                    linked = conn.execute(
                        "SELECT COUNT(*) AS n FROM caisse_orders WHERE customer_id=%s",
                        (client_id,),
                    ).fetchone()
                    linked_count = int((linked or {}).get("n") or 0)

                    if linked_count:
                        conn.execute(
                            """UPDATE caisse_orders
                               SET customer_id=NULL
                               WHERE customer_id=%s""",
                            (client_id,),
                        )

                    conn.execute(
                        "DELETE FROM caisse_clients WHERE id=%s",
                        (client_id,),
                    )

            return jsonify({
                "ok": True,
                "deleted": True,
                "client_id": client_id,
                "detached_orders": linked_count,
            })
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Suppression client impossible",
                "detail": str(exc),
            }), 500

    @app.get("/clients")
    def clients_management_page_phase6():
        return r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Clients — BÉCHÉFAA Caisse</title>
<style>body{font-family:Arial,sans-serif;margin:0;background:#f4f5f7;color:#111827}.wrap{max-width:1100px;margin:0 auto;padding:24px}.top{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:18px}.top a{text-decoration:none;color:#111827;font-weight:700}.card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px}.search{width:100%;box-sizing:border-box;padding:12px;border:2px solid #111827;border-radius:9px;font-size:15px;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.client{border:1px solid #e5e7eb;border-radius:10px;padding:14px;cursor:pointer;background:#fff}.client:hover{border-color:#9ca3af}.client b{display:block;font-size:16px;margin-bottom:4px}.muted{color:#6b7280;font-size:13px}.empty{padding:20px;color:#6b7280;text-align:center}.modal{display:none;position:fixed;inset:0;background:#0008;align-items:center;justify-content:center;padding:20px}.panel{background:#fff;max-width:620px;width:100%;border-radius:12px;padding:18px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fields .wide{grid-column:1/-1}.fields input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #d1d5db;border-radius:8px}.actions{display:flex;gap:10px;justify-content:flex-end;margin-top:14px}.btn{border:0;border-radius:8px;padding:10px 14px;font-weight:700;cursor:pointer}.save{background:#111827;color:white}.close{background:#e5e7eb}.ok{color:#15803d;font-size:13px;margin-top:8px}.err{color:#b91c1c;font-size:13px;margin-top:8px}</style></head><body><div class="wrap"><div class="top"><div><h1 style="margin:0">Clients</h1><div class="muted">Recherche et modification des fiches clients</div></div><div style="display:flex;gap:8px;align-items:center"><button class="btn save" id="import-btn" type="button">Importer des clients</button><input id="import-file" type="file" accept=".xlsx,.csv" style="display:none"><a href="/pos">← Retour caisse</a></div></div><div class="card"><input id="q" class="search" placeholder="Rechercher par nom, téléphone ou email…"><div id="grid" class="grid"></div></div></div>
<div id="modal" class="modal"><div class="panel"><h2 style="margin-top:0">Modifier le client</h2><div class="fields"><input id="f_first" placeholder="Prénom"><input id="f_last" placeholder="Nom"><input class="wide" id="f_address" placeholder="Adresse"><input id="f_postal" maxlength="5" inputmode="numeric" placeholder="Code postal"><input id="f_city" placeholder="Ville"><input class="wide" id="f_intercom" placeholder="Code porte / Interphone"><input id="f_phone" placeholder="Téléphone"><input id="f_email" type="email" placeholder="Email"></div><div id="msg"></div><div class="actions"><button class="btn" id="delete" style="background:#fee2e2;color:#991b1b;margin-right:auto">Supprimer</button><button class="btn close" id="close">Fermer</button><button class="btn save" id="save">Enregistrer</button></div></div></div>
<script>let rows=[],current=null,t=null;const $=id=>document.getElementById(id);function esc(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}async function load(){const q=$('q').value.trim();const r=await fetch('/api/clients'+(q?'?q='+encodeURIComponent(q):''));const d=await r.json();rows=d.clients||[];$('grid').innerHTML=rows.length?rows.map((c,i)=>`<div class="client" data-i="${i}"><b>${esc(c.display_name||'Client')}</b><div class="muted">${esc(c.phone||'')}${c.email?' · '+esc(c.email):''}</div><div class="muted">${esc([c.address,c.postal_code,c.city].filter(Boolean).join(' '))}</div>${c.door_intercom?'<div class="muted">Code porte / Interphone : '+esc(c.door_intercom)+'</div>':''}</div>`).join(''):'<div class="empty">Aucun client trouvé</div>';$('grid').querySelectorAll('[data-i]').forEach(x=>x.onclick=()=>openClient(rows[Number(x.dataset.i)]))}function openClient(c){current=c;$('f_first').value=c.first_name||'';$('f_last').value=c.last_name||'';$('f_address').value=c.address||'';$('f_postal').value=c.postal_code||'';$('f_city').value=c.city||'';$('f_intercom').value=c.door_intercom||'';$('f_phone').value=c.phone||'';$('f_email').value=c.email||'';$('msg').textContent='';$('modal').style.display='flex'}$('import-btn').onclick=()=>{$('import-file').click()};$('import-file').onchange=async function(){const file=this.files&&this.files[0];if(!file)return;if(!confirm('Importer les clients du fichier '+file.name+' ?')){this.value='';return}const fd=new FormData();fd.append('file',file);const btn=$('import-btn'),old=btn.textContent;btn.disabled=true;btn.textContent='Import en cours…';try{const r=await fetch('/api/clients/import-phase6',{method:'POST',body:fd}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Import impossible');alert('Import terminé : '+d.imported+' ligne(s), '+d.created+' créé(s), '+d.updated+' mis à jour, '+d.skipped+' ignoré(s).');await load()}catch(e){alert(e.message||'Import impossible')}finally{btn.disabled=false;btn.textContent=old;this.value=''}};$('close').onclick=()=>{$('modal').style.display='none'};$('delete').onclick=async()=>{if(!current)return;const name=current.display_name||current.phone||'ce client';if(!confirm('Supprimer définitivement '+name+' ?'))return;$('msg').className='';$('msg').textContent='Suppression…';try{const r=await fetch('/api/clients/'+encodeURIComponent(current.id),{method:'DELETE'}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Erreur');$('modal').style.display='none';current=null;await load()}catch(e){$('msg').className='err';$('msg').textContent=e.message||'Suppression impossible'}};$('q').oninput=()=>{clearTimeout(t);t=setTimeout(load,180)};$('f_postal').oninput=async function(){this.value=this.value.replace(/\D/g,'').slice(0,5);if(this.value.length===5){try{const r=await fetch('/api/postal-code/'+this.value),d=await r.json();if(r.ok&&d.cities&&d.cities.length)$('f_city').value=d.cities[0]}catch(e){}}};$('save').onclick=async()=>{if(!current)return;const body={first_name:$('f_first').value.trim(),last_name:$('f_last').value.trim(),address:$('f_address').value.trim(),postal_code:$('f_postal').value.trim(),city:$('f_city').value.trim(),door_intercom:$('f_intercom').value.trim(),phone:$('f_phone').value.trim(),email:$('f_email').value.trim()};$('msg').className='';$('msg').textContent='Enregistrement…';try{const r=await fetch('/api/clients/'+encodeURIComponent(current.id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Erreur');$('msg').className='ok';$('msg').textContent='Client modifié.';await load();current=d.client}catch(e){$('msg').className='err';$('msg').textContent=e.message||'Modification impossible'}};load();</script></body></html>'''
