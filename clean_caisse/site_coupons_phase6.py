"""Phase 6 — coupons promotionnels du site BÉCHÉFAA.

Gestion en administration + validation publique serveur. Les coupons ne touchent
pas aux commandes tant que le site ne transmet pas un coupon validé.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import jsonify, request, Response

def register_site_coupons_phase6(app, db):
    def ensure(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS site_coupons(
            id BIGSERIAL PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL DEFAULT '',
            discount_type TEXT NOT NULL CHECK(discount_type IN ('PERCENT','AMOUNT')),
            discount_value NUMERIC(10,2) NOT NULL,
            minimum_order NUMERIC(10,2) NOT NULL DEFAULT 0,
            starts_at TIMESTAMPTZ NULL,
            ends_at TIMESTAMPTZ NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")

    def serialize(r):
        return {
            "id":r["id"],"code":r["code"],"label":r["label"],
            "discount_type":r["discount_type"],"discount_value":float(r["discount_value"]),
            "minimum_order":float(r["minimum_order"]),"active":bool(r["active"]),
            "starts_at":r["starts_at"].isoformat() if r.get("starts_at") else None,
            "ends_at":r["ends_at"].isoformat() if r.get("ends_at") else None,
        }

    @app.get("/api/admin/site-coupons-phase6")
    def coupons_list_phase6():
        try:
            with db() as conn:
                ensure(conn);conn.commit()
                rows=conn.execute("SELECT * FROM site_coupons ORDER BY active DESC, id DESC").fetchall()
            return jsonify({"ok":True,"coupons":[serialize(r) for r in rows]})
        except Exception as exc:
            return jsonify({"ok":False,"error":"Coupons indisponibles","detail":str(exc)}),500

    @app.post("/api/admin/site-coupons-phase6")
    def coupons_save_phase6():
        p=request.get_json(silent=True) or {}
        code=str(p.get("code") or "").strip().upper().replace(" ","")[:40]
        label=str(p.get("label") or "").strip()[:120]
        dtype=str(p.get("discount_type") or "PERCENT").strip().upper()
        if not code:return jsonify({"ok":False,"error":"Code coupon obligatoire"}),400
        if dtype not in {"PERCENT","AMOUNT"}:return jsonify({"ok":False,"error":"Type de remise invalide"}),400
        try:
            value=Decimal(str(p.get("discount_value"))).quantize(Decimal("0.01"))
            minimum=Decimal(str(p.get("minimum_order") or 0)).quantize(Decimal("0.01"))
        except (InvalidOperation,ValueError,TypeError):
            return jsonify({"ok":False,"error":"Montant ou pourcentage invalide"}),400
        if value<=0 or minimum<0:return jsonify({"ok":False,"error":"Valeurs invalides"}),400
        if dtype=="PERCENT" and value>100:return jsonify({"ok":False,"error":"La remise en pourcentage ne peut pas dépasser 100 %"}),400
        starts_at=p.get("starts_at") or None;ends_at=p.get("ends_at") or None;active=bool(p.get("active",True))
        if starts_at and ends_at and str(ends_at) <= str(starts_at):
            return jsonify({"ok":False,"error":"La date de fin doit être postérieure à la date de début"}),400
        cid=p.get("id")
        try:
            with db() as conn:
                with conn.transaction():
                    ensure(conn)
                    if cid:
                        conn.execute("""UPDATE site_coupons SET code=%s,label=%s,discount_type=%s,discount_value=%s,
                            minimum_order=%s,starts_at=%s,ends_at=%s,active=%s,updated_at=NOW() WHERE id=%s""",
                            (code,label,dtype,value,minimum,starts_at,ends_at,active,int(cid)))
                    else:
                        conn.execute("""INSERT INTO site_coupons(code,label,discount_type,discount_value,minimum_order,starts_at,ends_at,active)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (code,label,dtype,value,minimum,starts_at,ends_at,active))
                    row=conn.execute("SELECT * FROM site_coupons WHERE code=%s",(code,)).fetchone()
            return jsonify({"ok":True,"coupon":serialize(row)})
        except Exception as exc:
            detail=str(exc)
            if "unique" in detail.lower() or "duplicate" in detail.lower():
                return jsonify({"ok":False,"error":"Ce code coupon existe déjà"}),409
            return jsonify({"ok":False,"error":"Enregistrement impossible","detail":detail}),500

    @app.delete("/api/admin/site-coupons-phase6/<int:coupon_id>")
    def coupons_delete_phase6(coupon_id):
        try:
            with db() as conn:
                with conn.transaction():
                    ensure(conn);conn.execute("DELETE FROM site_coupons WHERE id=%s",(coupon_id,))
            return jsonify({"ok":True})
        except Exception as exc:
            return jsonify({"ok":False,"error":"Suppression impossible","detail":str(exc)}),500

    @app.post("/api/public/site-coupons/validate-phase6")
    def coupons_validate_phase6():
        p=request.get_json(silent=True) or {}
        code=str(p.get("code") or "").strip().upper().replace(" ","")
        try:subtotal=Decimal(str(p.get("subtotal") or 0)).quantize(Decimal("0.01"))
        except (InvalidOperation,ValueError,TypeError):return jsonify({"ok":False,"valid":False,"error":"Montant invalide"}),400
        if subtotal<0:return jsonify({"ok":False,"valid":False,"error":"Montant invalide"}),400
        try:
            with db() as conn:
                ensure(conn);conn.commit()
                row=conn.execute("""SELECT * FROM site_coupons WHERE code=%s AND active=TRUE
                    AND (starts_at IS NULL OR starts_at<=NOW())
                    AND (ends_at IS NULL OR ends_at>=NOW()) LIMIT 1""",(code,)).fetchone()
            if not row:return jsonify({"ok":True,"valid":False,"error":"Coupon invalide ou expiré"})
            minimum=Decimal(str(row["minimum_order"]))
            if subtotal<minimum:return jsonify({"ok":True,"valid":False,"error":f"Minimum de commande : {minimum:.2f} €"})
            value=Decimal(str(row["discount_value"]))
            if row["discount_type"]=="PERCENT":
                discount=(subtotal*value/Decimal("100")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
            else:
                discount=min(subtotal,value)
            total=max(Decimal("0.00"),subtotal-discount)
            return jsonify({"ok":True,"valid":True,"coupon":{"code":row["code"],"label":row["label"],"discount_type":row["discount_type"],"discount_value":float(value)},"subtotal":float(subtotal),"discount":float(discount),"total":float(total)})
        except Exception as exc:
            return jsonify({"ok":False,"valid":False,"error":"Validation coupon indisponible","detail":str(exc)}),500

    @app.get("/administration/coupons-site")
    def coupons_page_phase6():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Coupons site</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#14213d;font-family:Arial}.w{max-width:1100px;margin:25px auto;padding:18px}.b{background:#fff;border:1px solid #e5eaf1;border-radius:16px;padding:20px;margin-bottom:16px}.g{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}label{display:block;font-weight:800;font-size:13px;margin-bottom:5px}input,select,button{width:100%;min-height:44px;border:1px solid #ccd5e2;border-radius:9px;padding:9px;font-size:15px}button{background:#111827;color:#fff;font-weight:900;cursor:pointer}.row{display:grid;grid-template-columns:1.1fr 1.4fr .8fr .8fr .8fr .8fr;gap:8px;padding:10px 0;border-bottom:1px solid #eee;align-items:center}.del{background:#b42318}.m{color:#667085;font-size:13px}.s{font-weight:800;margin-top:10px}@media(max-width:760px){.g{grid-template-columns:1fr}.row{grid-template-columns:1fr 1fr}}</style></head><body><div class="w"><div class="b"><h1>Coupons de réduction du site</h1><p class="m">Crée un code promotionnel avec période de validité et minimum de commande.</p><div class="g"><div><label>Code *</label><input id="code" placeholder="EX: RENTREE10"></div><div><label>Libellé / événement</label><input id="label" placeholder="Ex: Rentrée, Pourim, anniversaire"></div><div><label>Type</label><select id="type"><option value="PERCENT">Pourcentage</option><option value="AMOUNT">Montant €</option></select></div><div><label>Valeur *</label><input id="value" type="number" min="0" step="0.01"></div><div><label>Minimum commande €</label><input id="min" type="number" min="0" step="0.01" value="0"></div><div><label>Début</label><input id="start" type="datetime-local"></div><div><label>Fin</label><input id="end" type="datetime-local"></div><div><label>Actif</label><select id="active"><option value="1">Oui</option><option value="0">Non</option></select></div></div><button style="margin-top:16px" onclick="save()">Enregistrer le coupon</button><div id="msg" class="s"></div></div><div class="b"><h2>Coupons existants</h2><div id="list"></div></div></div><script>
const $=x=>document.getElementById(x);let coupons=[];function euro(v){return Number(v||0).toFixed(2)+' €'}function fmt(v){if(!v)return '—';return new Date(v).toLocaleString('fr-FR')}
async function load(){let r=await fetch('/api/admin/site-coupons-phase6',{cache:'no-store'}),j=await r.json();if(!r.ok||!j.ok){$('msg').textContent='Erreur : '+(j.error||'lecture impossible');return}coupons=j.coupons;$('list').innerHTML=coupons.length?coupons.map(c=>'<div class="row"><b>'+c.code+'</b><span>'+((c.label||'')||'—')+'</span><span>'+(c.discount_type==='PERCENT'?c.discount_value+' %':euro(c.discount_value))+'</span><span>Min. '+euro(c.minimum_order)+'</span><span>'+fmt(c.starts_at)+'<br>'+fmt(c.ends_at)+'</span><span>'+(c.active?'Actif':'Inactif')+'<br><button class="del" onclick="del('+c.id+')">Supprimer</button></span></div>').join(''):'Aucun coupon.'}
async function save(){let body={code:$('code').value,label:$('label').value,discount_type:$('type').value,discount_value:$('value').value,minimum_order:$('min').value,starts_at:$('start').value||null,ends_at:$('end').value||null,active:$('active').value==='1'};$('msg').textContent='Enregistrement…';let r=await fetch('/api/admin/site-coupons-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),j=await r.json();if(!r.ok||!j.ok){$('msg').textContent='Erreur : '+(j.error||'impossible');return}$('msg').textContent='Coupon enregistré.';$('code').value='';$('label').value='';$('value').value='';await load()}
async function del(id){if(!confirm('Supprimer ce coupon ?'))return;let r=await fetch('/api/admin/site-coupons-phase6/'+id,{method:'DELETE'}),j=await r.json();if(r.ok&&j.ok)await load();else $('msg').textContent='Suppression impossible.'}load();
</script></body></html>''',content_type="text/html; charset=utf-8")
