"""Phase 2.3 — test isolé des règles d'un groupe d'options sur un produit.
Écrit uniquement required/max sur un groupe direct central_* déjà existant.
Ne modifie ni optionLists, ni indices, ni commandes historiques.
"""
import json
import time
from html import escape
from flask import Response, request


def register_option_rules_test_phase23(app, db):
    def load_catalog():
        with db() as conn:
            row = conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1").fetchone()
        if not row:
            raise RuntimeError('Catalogue catalog_admin_v2 introuvable')
        data = json.loads(row['data_json'] or '{}')
        return data if isinstance(data, dict) else {}

    @app.route('/administration/options-regles-test', methods=['GET','POST'], endpoint='phase23_option_rules_test_page')
    def page():
        message=''; error=''
        try:
            if request.method == 'POST':
                product_id=str(request.form.get('product_id') or '').strip()
                group_key=str(request.form.get('group_key') or '').strip()
                required=str(request.form.get('required') or '0') == '1'
                try: max_choices=int(str(request.form.get('max') or '0'))
                except ValueError: raise ValueError('Nombre maximum invalide')
                if max_choices < 0 or max_choices > 99: raise ValueError('Nombre maximum invalide')
                with db() as conn:
                    with conn.transaction():
                        row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
                        if not row: raise RuntimeError('Catalogue catalog_admin_v2 introuvable')
                        data=json.loads(row['data_json'] or '{}')
                        product=next((p for p in data.get('products') or [] if isinstance(p,dict) and str(p.get('id'))==product_id),None)
                        if not product: raise ValueError('Produit introuvable')
                        direct=product.get('options') if isinstance(product.get('options'),list) else []
                        central_key='central_'+group_key
                        group=next((g for g in direct if isinstance(g,dict) and str(g.get('key') or '')==central_key),None)
                        if group is None: raise ValueError('Ce groupe n’est pas matérialisé sur ce produit : aucune règle modifiée')
                        group['required']=required
                        group['max']=max_choices
                        conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb, updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
                message=f'Règles enregistrées pour « {product.get("name") or product_id} » / {group_key} : '+('obligatoire' if required else 'facultatif')+f', maximum {max_choices if max_choices else "illimité"}.'
            data=load_catalog()
            products=[]
            for p in data.get('products') or []:
                if not isinstance(p,dict) or not p.get('id'): continue
                groups=[]
                for g in p.get('options') or []:
                    if not isinstance(g,dict): continue
                    key=str(g.get('key') or '')
                    if key.startswith('central_'):
                        groups.append({'key':key[8:],'title':str(g.get('title') or g.get('name') or key[8:]),'required':bool(g.get('required',False)),'max':int(g.get('max',0) or 0)})
                if groups: products.append({'id':str(p.get('id')),'name':str(p.get('name') or 'Sans nom'),'groups':groups})
        except Exception as exc:
            error=str(exc); products=[] if 'data' not in locals() else products
        product_options=''.join(f'<option value="{escape(p["id"])}">{escape(p["name"])}</option>' for p in products)
        payload=json.dumps(products,ensure_ascii=False).replace('</','<\\/')
        ok=f'<div class="ok">{escape(message)}</div>' if message else ''
        bad=f'<div class="bad">{escape(error)}</div>' if error else ''
        html=f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Test règles options</title><style>body{{font-family:Arial;background:#f4f5f7;margin:0;color:#17191c}}.top{{background:#111827;color:#fff;padding:14px 22px}}.top a{{color:#fff;margin-left:18px}}.wrap{{max-width:760px;margin:auto;padding:24px}}.card{{background:#fff;padding:20px;border-radius:14px}}label{{display:block;font-weight:700;margin-top:14px}}select,input{{width:100%;padding:11px;margin-top:6px}}button{{margin-top:18px;background:#175cd3;color:#fff;border:0;padding:11px 18px;border-radius:8px;font-weight:700}}.ok{{background:#e8f7ee;padding:12px;margin-bottom:14px}}.bad{{background:#fff0ee;color:#9d261d;padding:12px;margin-bottom:14px}}.hint{{color:#667085}}</style></head><body><div class="top"><b>BÉCHÉFAA • Test isolé règles</b><a href="/administration/options-produits">Retour Options</a></div><div class="wrap"><h1>Règles d’un groupe sur un produit</h1>{ok}{bad}<div class="card"><p class="hint">Test ciblé : facultatif/obligatoire et maximum de choix. Aucun index central n'est modifié.</p><form method="post"><label>Produit</label><select id="product" name="product_id" required>{product_options}</select><label>Groupe déjà affecté</label><select id="group" name="group_key" required></select><label>Règle</label><select id="required" name="required"><option value="0">Facultatif</option><option value="1">Obligatoire</option></select><label>Maximum de choix (0 = illimité)</label><input id="max" name="max" type="number" min="0" max="99" value="0" required><button type="submit">Enregistrer les règles</button></form></div></div><script>const products={payload};const p=document.getElementById('product'),g=document.getElementById('group'),r=document.getElementById('required'),m=document.getElementById('max');function refresh(){{const x=products.find(v=>v.id===p.value);g.innerHTML=(x?x.groups:[]).map(v=>'<option value="'+v.key+'" data-required="'+(v.required?'1':'0')+'" data-max="'+v.max+'">'+v.title+' ('+v.key+')</option>').join('');rules()}}function rules(){{const o=g.options[g.selectedIndex];if(!o)return;r.value=o.dataset.required;m.value=o.dataset.max}}p.onchange=refresh;g.onchange=rules;refresh();</script></body></html>'''
        return Response(html,content_type='text/html; charset=utf-8')
