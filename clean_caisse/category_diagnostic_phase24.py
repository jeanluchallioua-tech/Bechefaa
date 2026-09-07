"""Phase 2.4 — diagnostic catégories en lecture seule.
Aucune écriture dans catalog_admin_v2.
"""
import json
from flask import Response, jsonify


def register_category_diagnostic_phase24(app, db):
    def read_categories():
        with db() as conn:
            row = conn.execute("SELECT data_json::text AS data_json, updated_at FROM catalog_admin_v2 WHERE id=1").fetchone()
        if not row:
            raise RuntimeError("Catalogue catalog_admin_v2 introuvable")
        data = json.loads(row['data_json'] or '{}')
        raw_categories = data.get('categories') or []
        products = [p for p in (data.get('products') or []) if isinstance(p, dict)]
        result = []
        seen = set()
        for index, c in enumerate(raw_categories):
            if isinstance(c, str):
                name = c.strip(); active = True; kind = 'string'
            elif isinstance(c, dict):
                name = str(c.get('name') or c.get('label') or '').strip()
                active = c.get('active', True) is not False
                kind = 'object'
            else:
                continue
            if not name:
                continue
            key = name.casefold()
            duplicate = key in seen
            seen.add(key)
            attached = [p for p in products if str(p.get('category') or p.get('cat') or '').strip() == name]
            result.append({
                'index': index,
                'name': name,
                'active': active,
                'storageType': kind,
                'duplicate': duplicate,
                'products': len(attached),
                'activeProducts': sum(1 for p in attached if p.get('active', True) is not False),
            })
        known = {x['name'] for x in result}
        orphan = {}
        for p in products:
            category = str(p.get('category') or p.get('cat') or '').strip()
            if category and category not in known:
                orphan[category] = orphan.get(category, 0) + 1
        return result, orphan, len(products), row['updated_at']

    @app.get('/api/admin/categories-diagnostic')
    def categories_diagnostic_phase24_api():
        try:
            categories, orphan, product_count, updated_at = read_categories()
            return jsonify({'ok': True, 'readOnly': True, 'source': 'catalog_admin_v2', 'count': len(categories), 'productCount': product_count, 'categories': categories, 'orphanProductCategories': orphan, 'updatedAt': updated_at})
        except Exception as exc:
            return jsonify({'ok': False, 'error': 'Diagnostic catégories indisponible', 'detail': str(exc)}), 500

    @app.get('/administration/categories-diagnostic')
    def categories_diagnostic_phase24_page():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Diagnostic catégories</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.top{background:#111827;color:#fff;padding:14px 22px}.top a{color:#fff;margin-left:18px}.wrap{max-width:950px;margin:auto;padding:24px}.card{background:#fff;border-radius:14px;padding:18px;margin:14px 0}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #eee}.good{background:#e8f7ee;padding:10px;border-radius:8px}.bad{background:#fff0ee;color:#9d261d;padding:10px;border-radius:8px}.hint{color:#667085;font-size:13px}</style></head><body><div class="top"><b>BÉCHÉFAA • Phase 2.4</b><a href="/administration/produits">Produits</a><a href="/pos">Caisse</a></div><div class="wrap"><h1>Diagnostic des catégories</h1><p class="hint">Lecture seule de catalog_admin_v2. Aucun bouton de modification et aucune écriture PostgreSQL.</p><div id="status">Chargement…</div><div class="card"><table><thead><tr><th>Catégorie</th><th>État</th><th>Produits</th><th>Actifs</th><th>Stockage</th></tr></thead><tbody id="rows"></tbody></table></div><div class="card"><h2>Contrôle</h2><div id="control"></div></div></div><script>const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));(async()=>{try{const r=await fetch('/api/admin/categories-diagnostic?t='+Date.now(),{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');document.getElementById('status').innerHTML='<div class="good">'+d.count+' catégories lues, '+d.productCount+' produits. Lecture seule.</div>';document.getElementById('rows').innerHTML=d.categories.map(c=>'<tr><td><b>'+E(c.name)+'</b>'+(c.duplicate?' ⚠ doublon':'')+'</td><td>'+(c.active?'Active':'Inactive')+'</td><td>'+c.products+'</td><td>'+c.activeProducts+'</td><td>'+E(c.storageType)+'</td></tr>').join('');const o=Object.entries(d.orphanProductCategories||{});document.getElementById('control').innerHTML=o.length?'<div class="bad">Produits rattachés à des catégories absentes : '+o.map(x=>E(x[0])+' ('+x[1]+')').join(', ')+'</div>':'<div class="good">Aucune catégorie orpheline détectée.</div>'}catch(e){document.getElementById('status').innerHTML='<div class="bad">'+E(e.message)+'</div>'}})();</script></body></html>''', content_type='text/html; charset=utf-8')
