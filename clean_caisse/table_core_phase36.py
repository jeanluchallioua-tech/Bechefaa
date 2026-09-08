"""Phase 3.6 — socle PostgreSQL des 9 tables Salle."""
from flask import jsonify, request


def register_table_core_phase36(app, db):
    def ensure_table_schema(conn):
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_number INTEGER NULL")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_label TEXT NULL")

    @app.get("/api/tables-phase36/status")
    def table_phase36_status():
        try:
            with db() as conn:
                with conn.transaction(): ensure_table_schema(conn)
                row = conn.execute("SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE table_number IS NOT NULL) AS with_table FROM caisse_orders").fetchone()
            return jsonify({"ok":True,"phase":"3.6","tables":list(range(1,10)),"orders":int(row["n"]),"orders_with_table":int(row["with_table"]),"storage":"caisse_orders.table_number"})
        except Exception as exc:return jsonify({"ok":False,"error":"Initialisation tables impossible","detail":str(exc)}),500

    @app.get("/api/orders/<order_id>/table-phase36")
    def get_order_table_phase36(order_id):
        try:
            with db() as conn:
                with conn.transaction(): ensure_table_schema(conn)
                row=conn.execute("SELECT id,num,table_number,table_label FROM caisse_orders WHERE id=%s",(order_id,)).fetchone()
            if not row:return jsonify({"ok":False,"error":"Commande introuvable"}),404
            return jsonify({"ok":True,"id":row["id"],"num":row["num"],"table_number":row["table_number"],"table_label":row["table_label"]})
        except Exception as exc:return jsonify({"ok":False,"error":"Lecture table impossible","detail":str(exc)}),500

    @app.put("/api/orders/<order_id>/table-phase36")
    def set_order_table_phase36(order_id):
        payload=request.get_json(silent=True) or {};raw=payload.get("table_number")
        if raw in (None,""):table_number=None;table_label=None
        else:
            try:table_number=int(raw)
            except (TypeError,ValueError):return jsonify({"ok":False,"error":"Numéro de table invalide"}),400
            if table_number<1 or table_number>9:return jsonify({"ok":False,"error":"La table doit être comprise entre 1 et 9"}),400
            table_label=f"Table {table_number}"
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_table_schema(conn)
                    row=conn.execute("SELECT id,num,status FROM caisse_orders WHERE id=%s FOR UPDATE",(order_id,)).fetchone()
                    if not row:return jsonify({"ok":False,"error":"Commande introuvable"}),404
                    if row["status"]=="Terminée":return jsonify({"ok":False,"error":"Une commande terminée ne peut plus changer de table"}),409
                    conn.execute("UPDATE caisse_orders SET table_number=%s,table_label=%s WHERE id=%s",(table_number,table_label,order_id))
            return jsonify({"ok":True,"id":order_id,"num":row["num"],"table_number":table_number,"table_label":table_label})
        except Exception as exc:return jsonify({"ok":False,"error":"Enregistrement table impossible","detail":str(exc)}),500

    @app.after_request
    def expose_table_phase36(response):
        # Enrichit uniquement les JSON cuisine/historique existants.
        if request.method!="GET" or request.path not in ("/api/kitchen/board","/api/kitchen/orders","/api/orders/history") or response.status_code!=200:
            return response
        try:
            data=response.get_json(silent=True)
            if not isinstance(data,dict) or not isinstance(data.get("orders"),list):return response
            ids=[str(o.get("id")) for o in data["orders"] if isinstance(o,dict) and o.get("id")]
            if not ids:return response
            with db() as conn:
                with conn.transaction():ensure_table_schema(conn)
                rows=conn.execute("SELECT id,table_number,table_label FROM caisse_orders WHERE id=ANY(%s)",(ids,)).fetchall()
            tables={r["id"]:(r["table_number"],r["table_label"]) for r in rows}
            for order in data["orders"]:
                if not isinstance(order,dict):continue
                number,label=tables.get(str(order.get("id")),(None,None))
                order["table_number"]=number;order["table_label"]=label
                if number:
                    order["service_mode"]="Salle"
                    order["customer_name"]=label or f"Table {number}"
                    order["ticket_type"]="Salle"
                elif str(order.get("source") or "").upper() not in ("LIVRAISON","DELIVERY"):
                    order["service_mode"]="Emporter"
                    order["ticket_type"]="Emporter"
            response.set_data(app.json.dumps(data,ensure_ascii=False));response.content_type="application/json; charset=utf-8"
        except Exception:
            pass
        return response
