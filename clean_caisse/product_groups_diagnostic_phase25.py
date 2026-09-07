"""Phase 2.5 — diagnostic lecture seule des groupes d'options d'un produit.
Aucune écriture PostgreSQL. Sert à repérer les groupes doublons avant toute modification.
"""
import json
from flask import Response, jsonify


def register_product_groups_diagnostic_phase25(app, db):
    @app.get('/api/admin/product-groups-diagnostic/<product_id>')
    def product_groups_diagnostic_phase25_api(product_id):
        try:
            with db() as conn:
                row = conn.execute("SELECT data_json::text AS data_json, updated_at FROM catalog_admin_v2 WHERE id=1").fetchone()
            if not row:
                return jsonify({'ok':False,'error':'Catalogue introuvable'}),404
            data=json.loads(row['data_json'] or '{}')
            product=next((p for p in data.get('products') or [] if isinstance(p,dict) and str(p.get('id') or '')==str(product_id)),None)
            if not product:
                return jsonify({'ok':False,'error':'Produit introuvable'}),404
            lists=data.get('optionLists') if isinstance(data.get('optionLists'),dict) else {}
            defs=data.get('optionListDefs') if isinstance(data.get('optionListDefs'),dict) else {}
            selections=product.get('optionSelections') if isinstance(product.get('optionSelections'),dict) else {}
            direct=product.get('options') if isinstance(product.get('options'),list) else []
            groups=[]
            for pos,g in enumerate(direct):
                if not isinstance(g,dict): continue
                key=str(g.get('key') or g.get('name') or '').strip()
                title=str(g.get('title') or g.get('label') or g.get('name') or key).strip()
                choices=g.get('choices') if isinstance(g.get('choices'),list) else (g.get('options') if isinstance(g.get('options'),list) else [])
                names=[]
                for c in choices:
                    if isinstance(c,dict): n=str(c.get('name') or c.get('label') or c.get('title') or '').strip()
                    elif isinstance(c,(list,tuple)): n=str(c[0] if c else '').strip()
                    else: n=str(c or '').strip()
                    if n:names.append(n)
                groups.append({'source':'direct','position':pos,'key':key,'title':title,'required':bool(g.get('required',False)),'max':g.get('max',0) or 0,'choices':names})
            for key,indices in selections.items():
                if not isinstance(indices,list) or not indices: continue
                vals=lists.get(key) if isinstance(lists.get(key),list) else []
                meta=defs.get(key) if isinstance(defs.get(key),dict) else {}
                names=[]
                for raw in indices:
                    try:i=int(raw)
                    except (TypeError,ValueError):continue
                    if not (0<=i<len(vals)):continue
                    v=vals[i]
                    if isinstance(v,dict):n=str(v.get('name') or v.get('label') or v.get('title') or '').strip()
                    elif isinstance(v,(list,tuple)):n=str(v[0] if v else '').strip()
                    else:n=str(v or '').strip()
                    if n:names.append(n)
                groups.append({'source':'selection','position':None,'key':str(key),'title':str(meta.get('title') or meta.get('label') or key),'required':bool(meta.get('required',False)),'max':meta.get('max',0) or 0,'choices':names})
            # Compare les ensembles de choix, sans déclarer automatiquement qu'un groupe est supprimable.
            for i,g in enumerate(groups):
                sig=tuple(sorted(x.casefold() for x in g['choices']))
                g['sameChoicesAs']=[j for j,h in enumerate(groups) if j!=i and sig and sig==tuple(sorted(x.casefold() for x in h['choices']))]
            return jsonify({'ok':True,'readOnly':True,'source':'catalog_admin_v2','product':{'id':product.get('id'),'name':product.get('name')},'groups':groups,'count':len(groups),'updatedAt':row['updated_at']})
        except Exception as exc:
            return jsonify({'ok':False,'error':'Diagnostic impossible','detail':str(exc)}),500

    @app.get('/administration/groupes-produit-diagnostic')
    def product_groups_diagnostic_phase25_page():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Diagnostic groupes produit</title><style>*{box-sizing:border-box}body{font-family:Arial;margin:0;background:#f4f5f7;color:#17191c}.wrap{max-width:950px;margin:auto;padding:25px}.card{background:white;border-radius:13px;padding:16px;margin:12px 0}select{width:100%;padding:11px}.tag{font-size:12px;background:#eef2f6;padding:3px 7px;border-radius:6px}.warn{background:#fff3cd;padding:9px;border-radius:7px}.hint{color:#667085}</style></head><body><div class="wrap"><h1>Diagnostic des groupes d'options</h1><p class="hint">Lecture seule — aucune donnée n'est modifiée.</p><div class="card"><b>Produit</b><select id="p"></select></div><div id="out"></div></div><script>const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function J(u){let r=await fetch(u+'?t='+Date.now(),{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');return d}async function load(){try{let d=await J('/api/admin/options-products-list');p.innerHTML=d.products.map(x=>'<option value="'+E(x.id)+'">'+E(x.name)+'</option>').join('');let f=d.products.find(x=>/enfant/i.test(x.name));if(f)p.value=f.id;p.onchange=show;show()}catch(e){out.textContent=e.message}}async function show(){try{let d=await J('/api/admin/product-groups-diagnostic/'+encodeURIComponent(p.value));out.innerHTML='<div class="card"><b>'+E(d.product.name)+'</b> — '+d.count+' groupe(s)</div>'+d.groups.map((g,i)=>'<div class="card"><h3>'+E(g.title)+' <span class="tag">'+E(g.source)+' / '+E(g.key)+'</span></h3><div>Obligatoire : '+(g.required?'oui':'non')+' • Maximum : '+E(g.max)+'</div><p>'+g.choices.map(E).join(' • ')+'</p>'+(g.sameChoicesAs.length?'<div class="warn">Même liste de choix que le(s) groupe(s) n° '+g.sameChoicesAs.map(x=>x+1).join(', ')+'</div>':'')+'</div>').join('')}catch(e){out.textContent=e.message}}load();</script></body></html>''',content_type='text/html; charset=utf-8')
