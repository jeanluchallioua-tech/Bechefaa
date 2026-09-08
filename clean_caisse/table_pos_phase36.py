"""Phase 3.6 — choix Salle / Table 1 à 9 dans la caisse.

Injection UI isolée : le socle PostgreSQL reste dans table_core_phase36.
"""
from flask import request


def register_table_pos_phase36(app, db):
    @app.before_request
    def table_phase36_capture_create():
        if request.method != "POST" or request.path != "/api/orders":
            return None
        payload = request.get_json(silent=True) or {}
        mode = str(payload.get("service_mode") or "").strip().upper()
        if mode != "SALLE":
            return None
        try:
            table_number = int(payload.get("table_number"))
        except (TypeError, ValueError):
            from flask import jsonify
            return jsonify({"ok": False, "error": "Choisissez une table de 1 à 9 pour une commande Salle"}), 400
        if table_number < 1 or table_number > 9:
            from flask import jsonify
            return jsonify({"ok": False, "error": "Choisissez une table de 1 à 9 pour une commande Salle"}), 400
        request.environ["bechefaa.table_number"] = table_number
        return None

    @app.after_request
    def table_phase36_after(response):
        # Persistance après création réussie, sans modifier le endpoint historique de création.
        if request.method == "POST" and request.path == "/api/orders" and response.status_code == 201:
            table_number = request.environ.get("bechefaa.table_number")
            if table_number:
                try:
                    data = response.get_json(silent=True) or {}
                    order_id = data.get("id")
                    if order_id:
                        with db() as conn:
                            with conn.transaction():
                                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_number INTEGER NULL")
                                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_label TEXT NULL")
                                conn.execute(
                                    "UPDATE caisse_orders SET table_number=%s, table_label=%s WHERE id=%s",
                                    (table_number, f"Table {table_number}", order_id),
                                )
                        data["service_mode"] = "Salle"
                        data["table_number"] = table_number
                        data["table_label"] = f"Table {table_number}"
                        response.set_data(app.json.dumps(data, ensure_ascii=False))
                        response.content_type = "application/json; charset=utf-8"
                except Exception:
                    # Ne jamais casser une commande déjà enregistrée à cause de l'enrichissement UI.
                    pass

        if request.path != "/pos" or response.status_code != 200 or not response.is_sequence:
            return response
        ctype = response.headers.get("Content-Type", "")
        if "text/html" not in ctype:
            return response
        try:
            html = response.get_data(as_text=True)
        except Exception:
            return response
        if "phase36-table-selector" in html:
            return response

        marker = '<div class="ticket-choice">'
        selector = '''<div id="phase36-table-selector" style="margin:8px 0 12px">
<div style="font-size:12px;font-weight:800;margin-bottom:6px">Mode de service</div>
<div style="display:flex;gap:6px"><button type="button" id="p36-emporter" style="flex:1;padding:9px;border:1px solid #ccd1d8;border-radius:8px;background:#111827;color:#fff;font-weight:800">Emporter</button><button type="button" id="p36-salle" style="flex:1;padding:9px;border:1px solid #ccd1d8;border-radius:8px;background:#fff;font-weight:800">Salle</button></div>
<div id="p36-tables" style="display:none;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px"></div>
</div>'''
        if marker not in html:
            return response
        html = html.replace(marker, selector + marker, 1)

        script = r'''<script id="phase36-table-selector-script">
(function(){
 let mode='EMPORTER', tableNumber=null;
 const box=document.getElementById('p36-tables'), salle=document.getElementById('p36-salle'), emporter=document.getElementById('p36-emporter');
 if(!box||!salle||!emporter)return;
 box.innerHTML=Array.from({length:9},(_,i)=>`<button type="button" data-p36-table="${i+1}" style="padding:9px;border:1px solid #ccd1d8;border-radius:8px;background:#fff;font-weight:800">Table ${i+1}</button>`).join('');
 function paint(){
   salle.style.background=mode==='SALLE'?'#111827':'#fff'; salle.style.color=mode==='SALLE'?'#fff':'#17191c';
   emporter.style.background=mode==='EMPORTER'?'#111827':'#fff'; emporter.style.color=mode==='EMPORTER'?'#fff':'#17191c';
   box.style.display=mode==='SALLE'?'grid':'none';
   box.querySelectorAll('[data-p36-table]').forEach(b=>{let on=Number(b.dataset.p36Table)===tableNumber;b.style.background=on?'#d97706':'#fff';b.style.color=on?'#fff':'#17191c'});
 }
 salle.onclick=()=>{mode='SALLE';paint()}; emporter.onclick=()=>{mode='EMPORTER';tableNumber=null;paint()};
 box.onclick=e=>{let b=e.target.closest('[data-p36-table]');if(!b)return;tableNumber=Number(b.dataset.p36Table);paint()};
 const nativeFetch=window.fetch.bind(window);
 window.fetch=function(input,init){
   let url=typeof input==='string'?input:(input&&input.url)||'';
   if(url==='/api/orders' && init && String(init.method||'GET').toUpperCase()==='POST'){
     if(mode==='SALLE' && !tableNumber){document.getElementById('order-message').innerHTML='<div class="error"><b>Choisissez une table de 1 à 9.</b></div>';return Promise.reject(new Error('Choisissez une table de 1 à 9'))}
     try{let p=JSON.parse(init.body||'{}');p.service_mode=mode;p.table_number=mode==='SALLE'?tableNumber:null;init=Object.assign({},init,{body:JSON.stringify(p)})}catch(e){}
   }
   return nativeFetch(input,init);
 };
 paint();
})();
</script>'''
        html = html.replace("</body>", script + "</body>", 1)
        response.set_data(html)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response
