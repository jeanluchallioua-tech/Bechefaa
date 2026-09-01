
from flask import Flask, jsonify, request, send_from_directory
import sqlite3, json, os, time
from pathlib import Path
import startup_patch  # V0.5.42 applique les correctifs statiques avant de servir le POS

BASE = Path(__file__).resolve().parent
DB = Path(os.getenv("BECHEFAA_DB", BASE / "bechefaa.db"))
app = Flask(__name__, static_folder="static", static_url_path="")


DELIVERY_ZONES = {
    "A": {"minimum":25.0, "cities":["fontenay sous bois","montreuil"]},
    "B": {"minimum":40.0, "cities":["champigny sur marne","le perreux sur marne","nogent sur marne","noisy le sec","neuilly plaisance","neuilly sur marne","rosny sous bois","vincennes"]},
    "C": {"minimum":80.0, "cities":["villemomble","romainville","saint mande","saint maurice"]},
}
def _norm_city(v):
    import unicodedata, re as _re
    s=unicodedata.normalize("NFD", str(v or ""))
    s="".join(ch for ch in s if unicodedata.category(ch)!="Mn").lower()
    return _re.sub(r"[^a-z0-9]+"," ",s).strip()
def delivery_zone_for(city):
    n=_norm_city(city)
    for z,info in DELIVERY_ZONES.items():
        if n in info["cities"]:
            return z, info["minimum"]
    return None, None


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS orders(
            id TEXT PRIMARY KEY,
            num INTEGER,
            customer_id TEXT,
            customer TEXT,
            source TEXT,
            payment TEXT,
            status TEXT,
            total REAL,
            items_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )""")
        for col, decl in [
            ("phone","TEXT DEFAULT ''"),("address","TEXT DEFAULT ''"),("postal_code","TEXT DEFAULT ''"),
            ("city","TEXT DEFAULT ''"),("email","TEXT DEFAULT ''"),("change_summary","TEXT DEFAULT '{}'"),("modification_flag","INTEGER DEFAULT 0"),("modified_at","INTEGER DEFAULT 0")
        ]:
            try: c.execute(f"ALTER TABLE orders ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError: pass
        c.execute("""CREATE TABLE IF NOT EXISTS clients(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT DEFAULT '',
            updated_at INTEGER NOT NULL
        )""")
        for col, decl in [
            ("first_name","TEXT DEFAULT ''"),
            ("last_name","TEXT DEFAULT ''"),
            ("email","TEXT DEFAULT ''"),
            ("postal_code","TEXT DEFAULT ''"),
            ("city","TEXT DEFAULT ''")
        ]:
            try:
                c.execute(f"ALTER TABLE clients ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError:
                pass

def order_dict(r):
    return {
        "id": r["id"], "num": r["num"], "customerId": r["customer_id"],
        "customer": r["customer"], "source": r["source"], "payment": r["payment"],
        "status": r["status"], "total": r["total"],
        "items": json.loads(r["items_json"] or "[]"),
        "createdAt": r["created_at"], "updatedAt": r["updated_at"], "phone": r["phone"] if "phone" in r.keys() else "", "address": r["address"] if "address" in r.keys() else "", "postalCode": r["postal_code"] if "postal_code" in r.keys() else "", "city": r["city"] if "city" in r.keys() else "", "email": r["email"] if "email" in r.keys() else "", "changeSummary": json.loads(r["change_summary"] or "{}") if "change_summary" in r.keys() else {}, "modificationFlag": bool(r["modification_flag"]) if "modification_flag" in r.keys() else False
    }

def ensure_catalog_admin_table(c):
    c.execute("""CREATE TABLE IF NOT EXISTS catalog_admin (
        id INTEGER PRIMARY KEY CHECK (id=1),
        data_json TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    )""")


@app.get("/api/public/catalog")
def public_catalog():
    with conn() as c:
        ensure_catalog_admin_table(c)
        row = c.execute(
            "SELECT data_json, updated_at FROM catalog_admin WHERE id=1"
        ).fetchone()

        if not row:
            return jsonify({
                "categories": [],
                "products": [],
                "updatedAt": 0
            })

        try:
            data = json.loads(row["data_json"])
        except Exception:
            data = {}

        categories = [
            x for x in (data.get("categories") or [])
            if x.get("active", True)
        ]

        products = [
            x.copy() for x in (data.get("products") or [])
            if x.get("active", True)
            and (x.get("channels") or {}).get("site", False)
        ]

        allowed = {x.get("name") for x in categories}
        products = [
            x for x in products
            if x.get("category") in allowed
        ]

        # Récupération automatique des photos déjà utilisées par la caisse
        try:
            index_path = BASE / "static" / "index.html"
            html = index_path.read_text(encoding="utf-8")

            marker = "window.PRODUCTS="
            start = html.find(marker)

            if start >= 0:
                start += len(marker)
                end = html.find("];window.CATEGORIES=", start)

                if end >= 0:
                    raw = html[start:end + 1]
                    pos_products = json.loads(raw)

                    photos_by_id = {
                        str(p.get("id")): p.get("image", "")
                        for p in pos_products
                    }

                    photos_by_name = {
                        str(p.get("name", "")).strip().lower(): p.get("image", "")
                        for p in pos_products
                    }

                    for p in products:
                        photo = photos_by_id.get(str(p.get("id")), "")

                        if not photo:
                            photo = photos_by_name.get(
                                str(p.get("name", "")).strip().lower(),
                                ""
                            )

                        if photo:
                            p["photo"] = photo

        except Exception as e:
            print("Photos catalogue :", e)

        return jsonify({
            "categories": categories,
            "products": products,
            "updatedAt": row["updated_at"]
        })

@app.get("/api/catalog-admin")
def get_catalog_admin():
    with conn() as c:
        ensure_catalog_admin_table(c)
        row=c.execute("SELECT data_json, updated_at FROM catalog_admin WHERE id=1").fetchone()
        if not row: return jsonify({"data":None,"updatedAt":0})
        try: data=json.loads(row["data_json"])
        except Exception: data=None
        return jsonify({"data":data,"updatedAt":row["updated_at"]})

@app.put("/api/catalog-admin")
def put_catalog_admin():
    payload=request.get_json(force=True) or {}
    data=payload.get("data")
    if not isinstance(data,dict): return jsonify({"error":"Catalogue invalide"}),400
    now=int(time.time()*1000)
    with conn() as c:
        ensure_catalog_admin_table(c)
        c.execute("""INSERT INTO catalog_admin(id,data_json,updated_at) VALUES(1,?,?)
        ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at""",
        (json.dumps(data,ensure_ascii=False),now))
        c.commit()
    return jsonify({"ok":True,"updatedAt":now})

@app.get("/api/health")
def health():
    return {"ok": True, "service": "BECHEFAA POS V0.5 Cloud"}


@app.post("/api/public/orders")
def public_post_order():
    x=request.get_json(force=True) or {}
    customer=x.get("customer") or {}
    items=x.get("items") or []
    if not isinstance(items,list) or not items:
        return jsonify({"error":"Panier vide"}),400
    first=str(customer.get("firstName") or "").strip()
    last=str(customer.get("lastName") or "").strip()
    phone=str(customer.get("phone") or "").strip()
    if not first or not last or len("".join(ch for ch in phone if ch.isdigit())) < 10:
        return jsonify({"error":"Coordonnées client incomplètes"}),400
    mode=str(x.get("mode") or "À EMPORTER").upper()
    if mode not in ("À EMPORTER","LIVRAISON"):
        mode="À EMPORTER"
    if mode=="LIVRAISON" and (not str(customer.get("address") or "").strip() or not str(customer.get("postalCode") or "").strip() or not str(customer.get("city") or "").strip()):
        return jsonify({"error":"Adresse de livraison incomplète"}),400
    if mode=="LIVRAISON":
        zone,minimum=delivery_zone_for(customer.get("city"))
        if not zone:
            return jsonify({"error":"Adresse hors zone de livraison","deliveryZone":None}),400
    else:
        zone,minimum=None,0.0

    now=int(time.time()*1000)
    oid="SITE-"+str(now)
    clean_items=[]
    total=0.0
    for i,it in enumerate(items):
        try: qty=max(1,int(it.get("qty") or 1))
        except Exception: qty=1
        try: unit=float(it.get("price") or it.get("unit") or 0)
        except Exception: unit=0.0
        clean={
            "lineId":str(it.get("cartId") or f"{oid}-{i}"),
            "id":it.get("id"),
            "name":str(it.get("name") or "Article"),
            "qty":qty,
            "unit":unit,
            "price":unit,
            "optionsText":str(it.get("optionsText") or ""),
            "prepared":False
        }
        clean_items.append(clean)
        total += qty*unit

    if mode=="LIVRAISON" and total < float(minimum or 0):
        return jsonify({"error":f"Minimum de commande Zone {zone} : {minimum:.0f} €","deliveryZone":zone,"minimum":minimum,"missing":round(minimum-total,2)}),400

    full_name=(first+" "+last).strip()
    address=str(customer.get("address") or "").strip() if mode=="LIVRAISON" else ""
    postal=str(customer.get("postalCode") or "").strip() if mode=="LIVRAISON" else ""
    city=str(customer.get("city") or "").strip() if mode=="LIVRAISON" else ""
    email=str(customer.get("email") or "").strip()
    slot=str(x.get("slot") or "DÈS QUE POSSIBLE")
    instructions=str(customer.get("instructions") or "").strip()
    # Metadata visible in kitchen/order details without changing DB schema.
    if clean_items:
        meta=[]
        if slot: meta.append("Créneau : "+slot)
        if instructions: meta.append("Instructions : "+instructions)
        if meta:
            clean_items[0]["siteInfo"]=" · ".join(meta)

    with conn() as c:
        maxnum=c.execute("SELECT COALESCE(MAX(num),999) AS n FROM orders").fetchone()["n"]
        num=int(maxnum or 999)+1
        cid="SITECLIENT-"+str(now)
        c.execute("""INSERT INTO clients(id,name,phone,address,updated_at,first_name,last_name,email,postal_code,city)
          VALUES(?,?,?,?,?,?,?,?,?,?)""",
          (cid,full_name,phone,address,now,first,last,email,postal,city))
        c.execute("""INSERT INTO orders(
            id,num,customer_id,customer,source,payment,status,total,items_json,
            created_at,updated_at,phone,address,postal_code,city,email
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (oid,num,cid,full_name,mode,"À ENCAISSER","À préparer",round(total,2),
           json.dumps(clean_items,ensure_ascii=False),now,now,phone,address,postal,city,email))
        c.commit()
    return jsonify({"ok":True,"id":oid,"num":num,"status":"À préparer","total":round(total,2),"deliveryZone":zone,"minimum":minimum})

@app.get("/api/orders")
def get_orders():
    with conn() as c:
        rows = c.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return jsonify([order_dict(r) for r in rows])

@app.post("/api/orders")
def post_order():
    o = request.get_json(force=True)
    now = int(time.time()*1000)
    oid = str(o.get("id") or now)
    items = o.get("items") or []
    for item in items:
        item.setdefault("prepared", False)
    with conn() as c:
        c.execute("""INSERT INTO orders(
            id,num,customer_id,customer,source,payment,status,total,items_json,
            created_at,updated_at,phone,address,postal_code,city,email
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            num=excluded.num,
            customer_id=excluded.customer_id,
            customer=excluded.customer,
            source=excluded.source,
            payment=excluded.payment,
            status=excluded.status,
            total=excluded.total,
            items_json=excluded.items_json,
            phone=excluded.phone,
            address=excluded.address,
            postal_code=excluded.postal_code,
            city=excluded.city,
            email=excluded.email,
            updated_at=excluded.updated_at""",
          (
            oid, o.get("num"), str(o.get("customerId") or ""),
            o.get("customer","Client comptoir"), o.get("source","CAISSE"),
            o.get("payment","À ENCAISSER"), o.get("status","À préparer"),
            float(o.get("total") or 0), json.dumps(items, ensure_ascii=False),
            now, now, o.get("phone",""), o.get("address",""),
            o.get("postalCode",""), o.get("city",""), o.get("email","")
          ))
    return jsonify({"ok":True,"id":oid})

@app.patch("/api/orders/<oid>")
def patch_order(oid):
    data = request.get_json(force=True)
    allowed = {"status","customer","payment","source"}
    fields = {k:v for k,v in data.items() if k in allowed}
    if not fields: return jsonify({"ok":True})
    fields["updated_at"] = int(time.time()*1000)
    sql = "UPDATE orders SET " + ", ".join(f"{k}=?" for k in fields) + " WHERE id=?"
    with conn() as c:
        c.execute(sql, [*fields.values(), oid])
    return jsonify({"ok":True})

@app.patch("/api/orders/<oid>/items/<int:index>")
def patch_item(oid, index):
    data = request.get_json(force=True)
    with conn() as c:
        r = c.execute("SELECT items_json FROM orders WHERE id=?", (oid,)).fetchone()
        if not r: return jsonify({"error":"order not found"}),404
        items = json.loads(r["items_json"] or "[]")
        if index < 0 or index >= len(items): return jsonify({"error":"item not found"}),404
        items[index]["prepared"] = bool(data.get("prepared"))
        c.execute("UPDATE orders SET items_json=?, updated_at=? WHERE id=?",
                  (json.dumps(items,ensure_ascii=False), int(time.time()*1000), oid))
    return jsonify({"ok":True})


@app.patch("/api/orders/<oid>/full")
def patch_order_full(oid):
    data = request.get_json(force=True)
    items = data.get("items") or []
    now = int(time.time()*1000)
    with conn() as c:
        row = c.execute("SELECT status, customer_id FROM orders WHERE id=?", (oid,)).fetchone()
        if not row:
            return jsonify({"error":"order not found"}), 404

        # On conserve le statut cuisine actuel pendant une modification.
        current_status = row["status"]

        c.execute("""UPDATE orders SET
            customer_id=?,
            customer=?,
            source=?,
            total=?,
            items_json=?,
            phone=?,
            address=?,
            postal_code=?,
            city=?,
            email=?,
            change_summary=?,
            modification_flag=?,
            modified_at=?,
            updated_at=?,
            status=?
            WHERE id=?""",
            (
                str(data.get("customerId") or ""),
                data.get("customer","Client comptoir"),
                data.get("source","CAISSE"),
                float(data.get("total") or 0),
                json.dumps(items,ensure_ascii=False),
                data.get("phone",""),
                data.get("address",""),
                data.get("postalCode",""),
                data.get("city",""),
                data.get("email",""),
                json.dumps(data.get("changeSummary") or {},ensure_ascii=False),
                1 if data.get("modificationFlag") else 0,
                int(data.get("modifiedAt") or now),
                now,
                current_status,
                oid
            )
        )
    return jsonify({"ok":True,"id":oid,"status":current_status})

@app.get("/api/orders/<oid>")
def get_order(oid):
    with conn() as c:
        r=c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
    if not r:
        return jsonify({"error":"order not found"}),404
    return jsonify(order_dict(r))

@app.get("/api/clients")
def get_clients():
    with conn() as c:
        rows = c.execute("SELECT * FROM clients ORDER BY name").fetchall()
    return jsonify([{
        "id":r["id"],
        "name":r["name"],
        "firstName":r["first_name"] if "first_name" in r.keys() else "",
        "lastName":r["last_name"] if "last_name" in r.keys() else "",
        "phone":r["phone"],
        "email":r["email"] if "email" in r.keys() else "",
        "address":r["address"],
        "postalCode":r["postal_code"] if "postal_code" in r.keys() else "",
        "city":r["city"] if "city" in r.keys() else ""
    } for r in rows])

@app.post("/api/clients")
def post_client():
    x = request.get_json(force=True)
    cid = str(x.get("id") or int(time.time()*1000))
    with conn() as c:
        c.execute("""INSERT INTO clients(
            id,name,phone,address,updated_at,first_name,last_name,email,postal_code,city
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            phone=excluded.phone,
            address=excluded.address,
            first_name=excluded.first_name,
            last_name=excluded.last_name,
            email=excluded.email,
            postal_code=excluded.postal_code,
            city=excluded.city,
            updated_at=excluded.updated_at""",
          (
            cid, x.get("name",""), x.get("phone",""), x.get("address",""),
            int(time.time()*1000), x.get("firstName",""), x.get("lastName",""),
            x.get("email",""), x.get("postalCode",""), x.get("city","")
          ))
    return jsonify({"ok":True,"id":cid})

@app.get("/")
@app.get("/caisse")
@app.get("/salle")
@app.get("/cuisine")
def frontend():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)

if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT","5000"))
    app.run(host="0.0.0.0", port=port)
else:
    init_db()
