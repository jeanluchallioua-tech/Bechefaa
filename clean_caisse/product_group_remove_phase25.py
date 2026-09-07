"""Phase 2.5 — retrait ciblé d'un groupe d'options d'un seul produit.
Ne supprime jamais le groupe central, optionLists, optionListDefs, ni l'historique.
"""
import json
import time
from flask import Response, jsonify, request


def register_product_group_remove_phase25(app, db):
    @app.post('/api/admin/product-group-remove-phase25')
    def product_group_remove_phase25_api():
        payload=request.get_json(silent=True) or {}
        product_id=str(payload.get('product_id') or '').strip()
        group_key=str(payload.get('group_key') or '').strip()
        if not product_id or not group_key:
            return jsonify({'ok':False,'error':'Produit ou groupe manquant'}),400
        try:
            with db() as conn:
                with conn.transaction():
                    row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
                    if not row:return jsonify({'ok':False,'error':'Catalogue introuvable'}),404
                    data=json.loads(row['data_json'] or '{}')
                    product=next((p for p in data.get('products') or [] if isinstance(p,dict) and str(p.get('id') or '')==product_id),None)
                    if not product:return jsonify({'ok':False,'error':'Produit introuvable'}),404
                    direct=product.get('options') if isinstance(product.get('options'),list) else []
                    matches=[(i,g) for i,g in enumerate(direct) if isinstance(g,dict) and str(g.get('key') or g.get('name') or '').strip()==group_key]
                    if len(matches)!=1:
                        return jsonify({'ok':False,'error':'Groupe introuvable ou ambigu sur ce produit','matches':len(matches)}),409
                    idx,g=matches[0]
                    title=str(g.get('title') or g.get('label') or g.get('name') or group_key).strip()
                    # Retrait de la référence selection seulement si ce groupe est la copie central_<key>.
                    selection_removed=False
                    if group_key.startswith('central_'):
                        source_key=group_key[len('central_'):]
                        selections=product.get('optionSelections')
                        if isinstance(selections,dict) and source_key in selections:
                            selections.pop(source_key,None);selection_removed=True
                    direct.pop(idx)
                    product['options']=direct
                    conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb,updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
            return jsonify({'ok':True,'product':product.get('name') or product_id,'removedGroup':title,'groupKey':group_key,'selectionReferenceRemoved':selection_removed,'centralListsUntouched':True,'orderHistoryUntouched':True})
        except Exception as exc:
            return jsonify({'ok':False,'error':'Retrait impossible','detail':str(exc)}),500

    @app.get('/administration/suppression-groupe-produit-test')
    def product_group_remove_phase25_page():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Retrait groupe produit</title><style>body{font-family:Arial;background:#f4f5f7;margin:0}.wrap{max-width:850px;margin:auto;padding:24px}.card{background:#fff;border-radius:14px;padding:18px;margin:14px 0}select,button{width:100%;padding:12px;margin-top:8px}button{background:#b42318;color:#fff;border:0;border-radius:8px;font-weight:700}.hint{color:#667085}.ok{background:#e8f7ee;padding:12px}.bad{background:#fff0ee;color:#9d261d;padding:12px}</style></head><body><div class="wrap"><h1>Retrait ciblé d'un groupe</h1><p class="hint">Un seul produit est modifié. Les groupes centraux et l'historique restent intacts.</p><div class="card"><label>Produit</label><select id="p"></select><label>Groupe présent sur ce produit</label><select id="g"></select><button id="remove">Retirer ce groupe uniquement de ce produit</button></div><div id="msg"></div></div><script>const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function J(u){let r=await fetch(u+(u.includes('?')?'&':'?')+'t='+Date.now(),{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');return d}async function products(){let d=await J('/api/admin/options-products-list');p.innerHTML=d.products.map(x=>'<option value="'+E(x.id)+'">'+E(x.name)+'</option>').join('');let f=d.products.find(x=>/enfant/i.test(x.name));if(f)p.value=f.id;p.onchange=groups;groups()}async function groups(){let d=await J('/api/admin/product-groups-diagnostic/'+encodeURIComponent(p.value));g.innerHTML=d.groups.filter(x=>x.source==='direct').map(x=>'<option value="'+E(x.key)+'">'+E(x.title)+' — '+E(x.key)+'</option>').join('')}remove.onclick=async()=>{let pn=p.options[p.selectedIndex]?.text||'',gn=g.options[g.selectedIndex]?.text||'';if(!confirm('Retirer « '+gn+' » uniquement de « '+pn+' » ?'))return;try{let r=await fetch('/api/admin/product-group-remove-phase25',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_id:p.value,group_key:g.value})}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');msg.innerHTML='<div class="ok">Groupe « '+E(d.removedGroup)+' » retiré uniquement de « '+E(d.product)+' ». Groupes centraux et historique inchangés.</div>';groups()}catch(e){msg.innerHTML='<div class="bad">'+E(e.message)+'</div>'}};products();</script></body></html>''',content_type='text/html; charset=utf-8')
