"""Phase 6 — coupons promotionnels du site BÉCHÉFAA.

Gestion en administration + validation publique serveur. Les coupons ne touchent
pas aux commandes tant que le site ne transmet pas un coupon validé.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import jsonify, request, Response

def _coupon_row(conn, code):
    code=str(code or "").strip().upper().replace(" ","")
    if not code:
        return None
    return conn.execute("""SELECT * FROM site_coupons WHERE code=%s AND active=TRUE
        AND (starts_at IS NULL OR starts_at<=NOW())
        AND (ends_at IS NULL OR ends_at>=NOW()) LIMIT 1""",(code,)).fetchone()


PICKUP_COUPON_MESSAGE = "Ce code promo est valable uniquement sur bechefaa.fr, pour les commandes à emporter."


def coupon_scope_error(sales_channel, service_mode):
    channel = str(sales_channel or "").strip().upper()
    mode = str(service_mode or "").strip().upper()
    if channel != "SITE" or mode not in {"À EMPORTER", "A EMPORTER", "EMPORTER", "COMPTOIR", "TAKEAWAY", "PICKUP"}:
        return PICKUP_COUPON_MESSAGE
    return None


def quote_coupon(conn, code, subtotal, payment_method=None, *, sales_channel=None, service_mode=None):
    scope_error = coupon_scope_error(sales_channel, service_mode)
    if scope_error:
        return None, scope_error
    subtotal=Decimal(str(subtotal or 0)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
    row=_coupon_row(conn,code)
    if not row:
        return None,"Coupon invalide ou expiré"
    method=str(payment_method or "").strip().upper()
    if method.startswith("EDENRED") and not bool(row.get("allow_edenred",False)):
        return None,"Ce coupon n’est pas cumulable avec Edenred"
    minimum=Decimal(str(row["minimum_order"]))
    if subtotal < minimum:
        return None,f"Minimum de commande : {minimum:.2f} €"
    value=Decimal(str(row["discount_value"]))
    if row["discount_type"]=="PERCENT":
        discount=(subtotal*value/Decimal("100")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
    else:
        discount=min(subtotal,value)
    total=max(Decimal("0.00"),subtotal-discount)
    return {
        "code":row["code"],
        "label":row["label"],
        "discount_type":row["discount_type"],
        "discount_value":float(value),
        "allow_edenred":bool(row.get("allow_edenred",False)),
        "subtotal":float(subtotal),
        "discount":float(discount),
        "total":float(total),
    },None


def apply_coupon_to_order(db, order_id, code, payment_method=None):
    code=str(code or "").strip().upper().replace(" ","")
    if not code:
        return None
    with db() as conn:
        with conn.transaction():
            conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS coupon_code TEXT NULL")
            conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS subtotal_before_discount NUMERIC(12,2) NULL")
            row=conn.execute("SELECT total, sales_channel, source FROM caisse_orders WHERE id=%s FOR UPDATE",(order_id,)).fetchone()
            if not row:
                raise ValueError("Commande introuvable pour coupon")
            quote,error=quote_coupon(conn,code,row["total"],payment_method,sales_channel=row.get("sales_channel"),service_mode=row.get("source"))
            if error:
                raise ValueError(error)
            subtotal=Decimal(str(quote["subtotal"])).quantize(Decimal("0.01"))
            discount=Decimal(str(quote["discount"])).quantize(Decimal("0.01"))
            total=Decimal(str(quote["total"])).quantize(Decimal("0.01"))
            ht=(total/Decimal("1.10")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
            tax=(total-ht).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
            conn.execute("""UPDATE caisse_orders
                SET subtotal_before_discount=%s,discount_amount=%s,coupon_code=%s,total=%s,
                    total_ht=%s,tax_rate=10.00,tax_amount=%s,total_ttc=%s
                WHERE id=%s""",
                (subtotal,discount,quote["code"],total,ht,tax,total,order_id))
    return quote


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
            allow_edenred BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        conn.execute("ALTER TABLE site_coupons ADD COLUMN IF NOT EXISTS allow_edenred BOOLEAN NOT NULL DEFAULT FALSE")

    def serialize(r):
        return {
            "id":r["id"],"code":r["code"],"label":r["label"],
            "discount_type":r["discount_type"],"discount_value":float(r["discount_value"]),
            "minimum_order":float(r["minimum_order"]),"active":bool(r["active"]),
            "allow_edenred":bool(r.get("allow_edenred",False)),
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
        if not value.is_finite() or not minimum.is_finite() or value<=0 or minimum<0:return jsonify({"ok":False,"error":"Valeurs invalides"}),400
        if dtype=="PERCENT" and value>100:return jsonify({"ok":False,"error":"La remise en pourcentage ne peut pas dépasser 100 %"}),400
        starts_at=p.get("starts_at") or None;ends_at=p.get("ends_at") or None;active=bool(p.get("active",True));allow_edenred=bool(p.get("allow_edenred",False))
        if starts_at and ends_at and str(ends_at) <= str(starts_at):
            return jsonify({"ok":False,"error":"La date de fin doit être postérieure à la date de début"}),400
        cid=p.get("id")
        if cid is not None:
            try:
                cid=int(cid)
                if cid<=0:raise ValueError()
            except (ValueError,TypeError):
                return jsonify({"ok":False,"error":"Identifiant coupon invalide"}),400
        try:
            with db() as conn:
                with conn.transaction():
                    ensure(conn)
                    if cid:
                        updated=conn.execute("""UPDATE site_coupons SET code=%s,label=%s,discount_type=%s,discount_value=%s,
                            minimum_order=%s,starts_at=%s,ends_at=%s,active=%s,allow_edenred=%s,updated_at=NOW() WHERE id=%s RETURNING id""",
                            (code,label,dtype,value,minimum,starts_at,ends_at,active,allow_edenred,cid)).fetchone()
                        if not updated:
                            return jsonify({"ok":False,"error":"Coupon introuvable. Rechargez la liste."}),404
                    else:
                        conn.execute("""INSERT INTO site_coupons(code,label,discount_type,discount_value,minimum_order,starts_at,ends_at,active,allow_edenred)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (code,label,dtype,value,minimum,starts_at,ends_at,active,allow_edenred))
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
                quote,error=quote_coupon(conn,code,subtotal,sales_channel="SITE",service_mode=p.get("mode"))
            if error:
                return jsonify({"ok":True,"valid":False,"error":error})
            return jsonify({"ok":True,"valid":True,"coupon":{"code":quote["code"],"label":quote["label"],"discount_type":quote["discount_type"],"discount_value":quote["discount_value"],"allow_edenred":quote["allow_edenred"]},"subtotal":quote["subtotal"],"discount":quote["discount"],"total":quote["total"]})
        except Exception as exc:
            return jsonify({"ok":False,"valid":False,"error":"Validation coupon indisponible","detail":str(exc)}),500

    @app.get("/administration/coupons-site")
    def coupons_page_phase6():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Coupons site</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#14213d;font-family:Arial}.w{max-width:1100px;margin:25px auto;padding:18px}.b{background:#fff;border:1px solid #e5eaf1;border-radius:16px;padding:20px;margin-bottom:16px}.g{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}label{display:block;font-weight:800;font-size:13px;margin-bottom:5px}input,select,button{width:100%;min-height:44px;border:1px solid #ccd5e2;border-radius:9px;padding:9px;font-size:15px}button{background:#111827;color:#fff;font-weight:900;cursor:pointer}.row{display:grid;grid-template-columns:1.1fr 1.4fr .8fr .8fr .8fr .8fr;gap:8px;padding:10px 0;border-bottom:1px solid #eee;align-items:center}.del{background:#b42318}.m{color:#667085;font-size:13px}.s{font-weight:800;margin-top:10px}@media(max-width:760px){.g{grid-template-columns:1fr}.row{grid-template-columns:1fr 1fr}}</style></head><body><div class="w"><div class="b"><h1>Coupons de réduction du site</h1><p class="m">Codes valables uniquement sur bechefaa.fr pour les commandes à emporter. Période de validité et minimum de commande configurables.</p><h2 id="editor-title">Créer un coupon</h2><div class="g"><div><label>Code *</label><input id="code" placeholder="EX: RENTREE10"></div><div><label>Libellé / événement</label><input id="label" placeholder="Ex: Rentrée, Pourim, anniversaire"></div><div><label>Type</label><select id="type"><option value="PERCENT">Pourcentage</option><option value="AMOUNT">Montant €</option></select></div><div><label>Valeur *</label><input id="value" type="number" min="0" step="0.01"></div><div><label>Minimum commande €</label><input id="min" type="number" min="0" step="0.01" value="0"></div><div><label>Début</label><input id="start" type="datetime-local"></div><div><label>Fin</label><input id="end" type="datetime-local"></div><div><label>Actif</label><select id="active"><option value="1">Oui</option><option value="0">Non</option></select></div><div><label>Autoriser avec Edenred</label><select id="edenred"><option value="0">Non</option><option value="1">Oui</option></select></div></div><button id="save-coupon" style="margin-top:16px" onclick="save()">Enregistrer le coupon</button><button type="button" id="cancel-edit" hidden style="margin-top:8px;background:#667085" onclick="resetEditor()">Annuler la modification</button><div id="msg" class="s"></div></div><div class="b"><h2>Coupons existants</h2><div id="list"></div></div></div><script>
const $=x=>document.getElementById(x);let coupons=[],editingId=null,busy=false;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function euro(v){return Number(v||0).toFixed(2)+' €'}
function fmt(v){return v?new Date(v).toLocaleString('fr-FR'):'—'}
function localDate(v){if(!v)return '';const d=new Date(v);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
function isoDate(id){return $(id).value?new Date($(id).value).toISOString():null}
function resetEditor(){
 $('msg').textContent='';
 editingId=null;['code','label','value','start','end'].forEach(id=>$(id).value='');
 $('type').value='PERCENT';$('min').value='0';$('active').value='1';$('edenred').value='0';
 $('editor-title').textContent='Créer un coupon';$('save-coupon').textContent='Enregistrer le coupon';$('cancel-edit').hidden=true;
}
function edit(id){
 if(busy)return;
 const c=coupons.find(c=>Number(c.id)===Number(id));if(!c)return;
 editingId=c.id;
 for(const [field,key] of Object.entries({code:'code',label:'label',type:'discount_type',value:'discount_value',min:'minimum_order'}))$(field).value=c[key]??'';
 $('start').value=localDate(c.starts_at);$('end').value=localDate(c.ends_at);
 $('active').value=c.active?'1':'0';$('edenred').value=c.allow_edenred?'1':'0';
 $('editor-title').textContent='Modifier le coupon '+c.code;$('save-coupon').textContent='Enregistrer les modifications';$('cancel-edit').hidden=false;
 $('msg').textContent='Modification du coupon existant.';$('editor-title').scrollIntoView({behavior:'smooth',block:'start'});$('code').focus({preventScroll:true});
}
async function load(){
 const r=await fetch('/api/admin/site-coupons-phase6',{cache:'no-store'}),j=await r.json();
 if(!r.ok||!j.ok)throw Error(j.error||'Lecture impossible');
 coupons=j.coupons;
 $('list').innerHTML=coupons.length?coupons.map(c=>'<div class="row"><b>'+esc(c.code)+'</b><span>'+esc(c.label||'—')+'</span><span>'+(c.discount_type==='PERCENT'?esc(c.discount_value)+' %':euro(c.discount_value))+'</span><span>Min. '+euro(c.minimum_order)+'</span><span>'+fmt(c.starts_at)+'<br>'+fmt(c.ends_at)+'</span><span>'+(c.active?'Actif':'Inactif')+'<br><button type="button" onclick="edit('+Number(c.id)+')">Modifier</button><button type="button" class="del" onclick="del('+Number(c.id)+')">Supprimer</button></span></div>').join(''):'Aucun coupon.';
}
async function save(){
 if(busy)return;busy=true;$('save-coupon').disabled=true;$('cancel-edit').disabled=true;
 try{
  const body={code:$('code').value,label:$('label').value,discount_type:$('type').value,discount_value:$('value').value,minimum_order:$('min').value,starts_at:isoDate('start'),ends_at:isoDate('end'),active:$('active').value==='1',allow_edenred:$('edenred').value==='1'};
  if(editingId!==null)body.id=editingId;
  $('msg').textContent='Enregistrement…';
  const r=await fetch('/api/admin/site-coupons-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),j=await r.json();
  if(!r.ok||!j.ok)throw Error(j.error||'Enregistrement impossible');
  const wasEditing=editingId!==null;
  resetEditor();$('msg').textContent=wasEditing?'Coupon modifié.':'Coupon créé.';
  try{await load()}catch(e){$('msg').textContent+=' Actualisation de la liste impossible : rechargez la page.'}
 }catch(e){$('msg').textContent='Erreur : '+e.message}
 finally{busy=false;$('save-coupon').disabled=false;$('cancel-edit').disabled=false}
}
async function del(id){
 if(busy||!confirm('Supprimer ce coupon ?'))return;
 try{
  const r=await fetch('/api/admin/site-coupons-phase6/'+id,{method:'DELETE'}),j=await r.json();
  if(!r.ok||!j.ok)throw Error(j.error||'Suppression impossible');
  if(Number(editingId)===Number(id))resetEditor();await load();
 }catch(e){$('msg').textContent=e.message}
}
load().catch(e=>$('msg').textContent='Erreur : '+e.message);
</script></body></html>''',content_type="text/html; charset=utf-8")

