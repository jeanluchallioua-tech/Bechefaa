"""Phase 3.6 — socle PostgreSQL des 9 tables Salle."""
import re
from flask import jsonify, request


# Full payment releases a table; kitchen completion alone does not.
OPEN_TABLE_ORDER_SQL = """table_number IS NOT NULL
    AND COALESCE(status,'') NOT IN ('Annulée','ANNULÉE','Annulee','Cancelled','Canceled')
    AND COALESCE(payment_status,'À ENCAISSER') <> 'PAYÉE'
    AND (COALESCE(total,0)<=0 OR COALESCE(paid_amount,0)<total)"""


def ensure_table_availability_schema(conn):
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_number INTEGER NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_label TEXT NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'À ENCAISSER'")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(12,2) NOT NULL DEFAULT 0")
    conn.execute("""CREATE TABLE IF NOT EXISTS caisse_table_reservations (
        table_number INTEGER PRIMARY KEY CHECK (table_number BETWEEN 1 AND 9),
        owner_token TEXT NOT NULL UNIQUE,
        expires_at TIMESTAMPTZ NOT NULL
    )""")


def table_conflict(conn, number, token='', exclude_order_id=''):
    # Caller holds the same orders lock as create_order. This serializes claims,
    # order creation and table transfers across processes, not just one browser.
    row=conn.execute("SELECT id,num FROM caisse_orders WHERE "+OPEN_TABLE_ORDER_SQL+
                     " AND table_number=%s AND id<>%s LIMIT 1",(number,exclude_order_id)).fetchone()
    if row:
        return {"ok":False,"code":"TABLE_OCCUPIED","error":f"Table {number} occupée : réglez ou modifiez la commande existante.","order_id":row['id'],"num":row['num']}
    reservation=conn.execute("SELECT owner_token FROM caisse_table_reservations WHERE table_number=%s AND expires_at>NOW()",(number,)).fetchone()
    if reservation and reservation['owner_token']!=token:
        return {"ok":False,"code":"TABLE_RESERVED","error":f"Table {number} déjà sélectionnée sur une autre commande."}
    return None


def register_table_core_phase36(app, db):
    def ensure_table_schema(conn):
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_number INTEGER NULL")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_label TEXT NULL")

    @app.get('/api/tables-phase36/availability')
    def table_availability():
        token=request.headers.get('X-BECHEFAA-TABLE-TOKEN','')
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_table_availability_schema(conn)
                    orders=conn.execute("SELECT id,num,table_number FROM caisse_orders WHERE "+OPEN_TABLE_ORDER_SQL).fetchall()
                    reservations=conn.execute("SELECT table_number,owner_token FROM caisse_table_reservations WHERE expires_at>NOW()").fetchall()
            occupied={int(row['table_number']):row for row in orders}
            reserved={int(row['table_number']):row['owner_token'] for row in reservations}
            tables=[]
            for number in range(1,10):
                order=occupied.get(number)
                mine=number in reserved and reserved[number]==token
                tables.append({'table_number':number,'occupied':bool(order),
                               'reserved':number in reserved,'mine':mine,
                               'available':not order and (number not in reserved or mine),
                               'order_num':order['num'] if order else None})
            response=jsonify({'ok':True,'tables':tables});response.headers['Cache-Control']='no-store';return response
        except Exception:
            return jsonify({'ok':False,'error':'Disponibilité des tables indisponible'}),503

    @app.put('/api/tables-phase36/reservation')
    def reserve_table():
        payload=request.get_json(silent=True) or {}
        token=str(payload.get('token') or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',token):
            return jsonify({'ok':False,'error':'Session de table invalide'}),400
        raw=payload.get('table_number')
        try:
            number=None if raw is None else int(raw)
        except (TypeError,ValueError):
            return jsonify({'ok':False,'error':'Numéro de table invalide'}),400
        if number is not None and (isinstance(raw,bool) or str(number)!=str(raw) or not 1<=number<=9):
            return jsonify({'ok':False,'error':'Choisissez une table de 1 à 9'}),400
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_table_availability_schema(conn)
                    conn.execute('LOCK TABLE caisse_orders IN EXCLUSIVE MODE')
                    if payload.get('renew_only') and number is not None:
                        owned=conn.execute('SELECT owner_token FROM caisse_table_reservations WHERE table_number=%s AND expires_at>NOW()',(number,)).fetchone()
                        if not owned or owned['owner_token']!=token:
                            return jsonify({'ok':False,'error':'Réservation expirée : sélectionnez à nouveau la table.'}),409
                    if number is not None:
                        conflict=table_conflict(conn,number,token)
                        if conflict:return jsonify(conflict),409
                    if number is None and payload.get('previous_table') is not None:
                        conn.execute('DELETE FROM caisse_table_reservations WHERE owner_token=%s AND table_number=%s',(token,payload['previous_table']))
                    else:
                        conn.execute('DELETE FROM caisse_table_reservations WHERE owner_token=%s OR expires_at<=NOW()',(token,))
                    if number is not None:
                        conn.execute("INSERT INTO caisse_table_reservations(table_number,owner_token,expires_at) VALUES (%s,%s,NOW()+INTERVAL '2 minutes')",(number,token))
            return jsonify({'ok':True,'table_number':number})
        except Exception:
            return jsonify({'ok':False,'error':'Réservation de table impossible'}),503

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
                    ensure_table_availability_schema(conn)
                    conn.execute('LOCK TABLE caisse_orders IN EXCLUSIVE MODE')
                    row=conn.execute("SELECT id,num,status FROM caisse_orders WHERE id=%s FOR UPDATE",(order_id,)).fetchone()
                    if not row:return jsonify({"ok":False,"error":"Commande introuvable"}),404
                    if row["status"]=="Terminée":return jsonify({"ok":False,"error":"Une commande terminée ne peut plus changer de table"}),409
                    if table_number:
                        conflict=table_conflict(conn,table_number,exclude_order_id=order_id)
                        if conflict:return jsonify(conflict),409
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

