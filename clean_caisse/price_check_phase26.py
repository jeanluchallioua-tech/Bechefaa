"""Phase 2.6 — contrôle serveur des prix, lecture seule.
Calcule le prix canonique d'un produit + options depuis catalog_admin_v2.
N'enregistre aucune commande et ne modifie aucune donnée.
"""
from decimal import Decimal, InvalidOperation
from flask import Response, jsonify, request


def _d(v):
    try:
        return Decimal(str(v or 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Prix catalogue invalide')


def _group_name(g, i):
    if not isinstance(g, dict):
        return 'Groupe '+str(i+1)
    return str(g.get('name') or g.get('label') or g.get('title') or ('Groupe '+str(i+1))).strip()


def _vals(g):
    if not isinstance(g, dict): return []
    for k in ('options','values','items','choices'):
        if isinstance(g.get(k), list): return g[k]
    return []


def _opt(v):
    if isinstance(v, (list, tuple)):
        return str(v[0] if v else '').strip(), _d(v[1] if len(v)>1 else 0)
    if isinstance(v, dict):
        return str(v.get('name') or v.get('label') or v.get('title') or v.get('value') or v.get('id') or '').strip(), _d(v.get('price') or v.get('extraPrice') or v.get('supplement') or 0)
    return str(v or '').strip(), Decimal('0.00')


def register_price_check_phase26(app, db):
    @app.post('/api/admin/price-check-phase26')
    def price_check_phase26_api():
        b=request.get_json(silent=True) or {}
        pid=str(b.get('productId') or '').strip()
        selected=b.get('options') if isinstance(b.get('options'), list) else []
        if not pid: return jsonify({'ok':False,'error':'Produit obligatoire'}),400
        try:
            with db() as conn:
                row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1").fetchone()
            if not row: return jsonify({'ok':False,'error':'Catalogue introuvable'}),404
            import json
            data=json.loads(row['data_json'] or '{}')
            products=[p for p in (data.get('products') or []) if isinstance(p,dict) and str(p.get('id') or '')==pid]
            if len(products)!=1: return jsonify({'ok':False,'error':'Produit introuvable ou ambigu'}),409
            p=products[0]
            if p.get('active',True) is False: return jsonify({'ok':False,'error':'Produit inactif'}),409
            base=_d(p.get('price',0)); groups=p.get('options') if isinstance(p.get('options'),list) else []
            used={}; extra=Decimal('0.00'); canonical=[]
            for s in selected:
                if not isinstance(s,dict): return jsonify({'ok':False,'error':'Option sélectionnée invalide'}),400
                gn=str(s.get('group') or '').strip(); on=str(s.get('name') or s.get('label') or '').strip()
                gm=[(i,g) for i,g in enumerate(groups) if _group_name(g,i)==gn]
                if len(gm)!=1: return jsonify({'ok':False,'error':f'Groupe option introuvable ou ambigu : {gn}'}),409
                gi,g=gm[0]; choices=[]
                for v in _vals(g):
                    name,price=_opt(v)
                    if name==on: choices.append((name,price))
                if len(choices)!=1: return jsonify({'ok':False,'error':f'Choix introuvable ou ambigu : {gn} / {on}'}),409
                used[gi]=used.get(gi,0)+1
                price=choices[0][1]; extra+=price
                canonical.append({'group':gn,'name':on,'price':float(price)})
            for gi,g in enumerate(groups):
                if not isinstance(g,dict): continue
                count=used.get(gi,0); req=bool(g.get('required',False)); mx=int(g.get('max') or g.get('maxChoices') or g.get('maximum') or 0)
                if req and count<1: return jsonify({'ok':False,'error':f'Option obligatoire manquante : {_group_name(g,gi)}'}),409
                if mx>0 and count>mx: return jsonify({'ok':False,'error':f'Trop de choix pour : {_group_name(g,gi)}'}),409
            total=(base+extra).quantize(Decimal('0.01'))
            return jsonify({'ok':True,'readOnly':True,'product':{'id':p.get('id'),'name':p.get('name')},'basePrice':float(base),'extraPrice':float(extra),'unitPrice':float(total),'options':canonical})
        except ValueError as e:
            return jsonify({'ok':False,'error':str(e)}),409
        except Exception as e:
            return jsonify({'ok':False,'error':'Contrôle impossible','detail':str(e)}),500

    @app.get('/administration/controle-prix')
    def price_check_phase26_page():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Contrôle prix</title><style>body{font-family:Arial;background:#f4f5f7;margin:0;color:#17191c}.wrap{max-width:820px;margin:auto;padding:24px}.card{background:#fff;padding:18px;border-radius:14px;margin:12px 0}select{width:100%;padding:11px}.g{border-top:1px solid #eee;padding-top:12px;margin-top:12px}.v{display:block;width:100%;text-align:left;padding:9px;margin:5px 0;border:1px solid #ddd;background:#fff;border-radius:8px}.v.sel{background:#111827;color:#fff}.ok{background:#e8f7ee;padding:12px}.err{background:#fff0ee;color:#9d261d;padding:12px}</style></head><body><div class="wrap"><h1>Contrôle serveur des prix</h1><p>Lecture seule : aucune commande n'est enregistrée.</p><div class="card"><select id="p" onchange="loadP()"></select></div><div id="opts"></div><div id="out"></div></div><script>let prod=null,groups=[],sel={};const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function oi(v){if(Array.isArray(v))return{name:String(v[0]??''),price:Number(v[1]||0)};if(v&&typeof v==='object')return{name:String(v.name||v.label||v.title||v.value||v.id||''),price:Number(v.price||v.extraPrice||v.supplement||0)};return{name:String(v??''),price:0}}function gi(g,i){let vals=g&&(g.options||g.values||g.items||g.choices)||[];return{name:String(g&&(g.name||g.label||g.title)||('Groupe '+(i+1))),vals:Array.isArray(vals)?vals:[],max:Number(g&&(g.max??g.maxChoices??g.maximum)||0)||0,required:!!(g&&g.required)}}function draw(){opts.innerHTML='<div class="card"><b>'+E(prod.name)+'</b> — '+Number(prod.price||0).toFixed(2).replace('.',',')+' €</div>'+groups.map((g,i)=>{let x=gi(g,i);return '<div class="card g"><b>'+E(x.name)+(x.required?' *':'')+'</b>'+x.vals.map((v,j)=>{let o=oi(v),k=i+':'+j;return '<button class="v '+(sel[k]?'sel':'')+'" onclick="tog('+i+','+j+')">'+E(o.name)+(o.price?' (+'+o.price.toFixed(2).replace('.',',')+' €)':'')+'</button>'}).join('')+'</div>'}).join('')+'<div class="card"><button onclick="check()" style="width:100%;padding:12px">Contrôler le prix côté serveur</button></div>'}function tog(i,j){let x=gi(groups[i],i),k=i+':'+j;if(sel[k])delete sel[k];else{if(x.max===1)Object.keys(sel).filter(a=>a.startsWith(i+':')).forEach(a=>delete sel[a]);else if(x.max>1&&Object.keys(sel).filter(a=>a.startsWith(i+':')&&sel[a]).length>=x.max)return;sel[k]=1}draw()}async function load(){let r=await fetch('/api/catalog/summary?t='+Date.now()),d=await r.json();p.innerHTML=(d.items||[]).map(x=>'<option value="'+E(x.id)+'">'+E(x.name)+'</option>').join('');loadP()}async function loadP(){sel={};let r=await fetch('/api/catalog/product/'+encodeURIComponent(p.value)+'/options?t='+Date.now()),d=await r.json();prod=d.product;groups=d.groups||[];out.innerHTML='';draw()}async function check(){let options=[];groups.forEach((g,i)=>{let x=gi(g,i);x.vals.forEach((v,j)=>{if(sel[i+':'+j]){let o=oi(v);options.push({group:x.name,name:o.name,price:o.price})}})});let r=await fetch('/api/admin/price-check-phase26',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({productId:p.value,options})}),d=await r.json();out.innerHTML='<div class="'+(r.ok&&d.ok?'ok':'err')+'">'+(r.ok&&d.ok?('Prix serveur : <b>'+Number(d.unitPrice).toFixed(2).replace('.',',')+' €</b> (base '+Number(d.basePrice).toFixed(2).replace('.',',')+' € + options '+Number(d.extraPrice).toFixed(2).replace('.',',')+' €)'):E(d.error||d.detail||'Erreur'))+'</div>'}load();</script></body></html>''',content_type='text/html; charset=utf-8')
