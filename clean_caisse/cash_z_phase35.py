"""Phase 3.5/3.7 — Z de caisse BÉCHÉFAA.

Clôture définitive, association des commandes au Z et consultation imprimable
des clôtures déjà enregistrées. Aucun archivage ne modifie les commandes.
"""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from flask import Response, jsonify

PARIS = ZoneInfo("Europe/Paris")


def _fallback_tax(ttc):
    total=Decimal(str(ttc or 0)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP); ht=(total/Decimal("1.10")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
    return ht,(total-ht).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP),total

def _bounds():
    now=datetime.now(PARIS); start=now.replace(hour=0,minute=0,second=0,microsecond=0)
    return now,start,int(start.timestamp()*1000),int(now.timestamp()*1000)

def _ensure_z_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS caisse_z_closures (id BIGSERIAL PRIMARY KEY,business_date TEXT NOT NULL UNIQUE,closed_at BIGINT NOT NULL,first_order_num BIGINT NULL,last_order_num BIGINT NULL,order_count INTEGER NOT NULL DEFAULT 0,total_ht NUMERIC(12,2) NOT NULL DEFAULT 0,tax_rate NUMERIC(6,3) NOT NULL DEFAULT 10,tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0,total_ttc NUMERIC(12,2) NOT NULL DEFAULT 0,payments_json JSONB NOT NULL DEFAULT '{}'::jsonb)""")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS z_closure_id BIGINT NULL")

def _snapshot(rows):
    ht=Decimal("0.00"); tax=Decimal("0.00"); ttc=Decimal("0.00"); payments={}
    for row in rows:
        fht,ftax,fttc=_fallback_tax(row.get("total")); rh=Decimal(str(row.get("total_ht") if row.get("total_ht") is not None else fht)); rt=Decimal(str(row.get("tax_amount") if row.get("tax_amount") is not None else ftax)); rc=Decimal(str(row.get("total_ttc") if row.get("total_ttc") is not None else fttc)); ht+=rh; tax+=rt; ttc+=rc; p=str(row.get("payment") or "À ENCAISSER"); payments[p]=payments.get(p,Decimal("0.00"))+rc
    nums=[int(r["num"]) for r in rows]
    return {"count":len(rows),"first":min(nums) if nums else None,"last":max(nums) if nums else None,"ht":ht.quantize(Decimal("0.01")),"tax":tax.quantize(Decimal("0.01")),"ttc":ttc.quantize(Decimal("0.01")),"payments":payments}

def _eur(v): return f"{Decimal(str(v or 0)):.2f}".replace(".",",")+" €"

def register_cash_z_phase35(app,db,ensure_order_schema):
    @app.get("/api/caisse/z/status")
    def z_status():
        now,start,start_ms,end_ms=_bounds(); day=start.strftime("%Y-%m-%d")
        try:
            with db() as conn:
                ensure_order_schema(conn); _ensure_z_schema(conn); conn.commit(); closed=conn.execute("SELECT * FROM caisse_z_closures WHERE business_date=%s",(day,)).fetchone(); open_rows=conn.execute("SELECT num,status FROM caisse_orders WHERE created_at >= %s AND created_at <= %s AND status <> 'Terminée' ORDER BY num",(start_ms,end_ms)).fetchall(); count=conn.execute("SELECT COUNT(*) AS n FROM caisse_orders WHERE created_at >= %s AND created_at <= %s",(start_ms,end_ms)).fetchone()["n"]
            return jsonify({"ok":True,"business_date":day,"already_closed":bool(closed),"orders":int(count),"open_orders":[{"num":r["num"],"status":r["status"]} for r in open_rows],"can_close":not closed and int(count)>0 and not open_rows})
        except Exception as exc: return jsonify({"ok":False,"error":"État Z indisponible","detail":str(exc)}),500

    @app.post("/api/caisse/z/close")
    def z_close():
        now,start,start_ms,end_ms=_bounds(); day=start.strftime("%Y-%m-%d"); closed_at=int(time.time()*1000)
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn); _ensure_z_schema(conn); conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ttc NUMERIC(12,2)"); conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ht NUMERIC(12,2)"); conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(12,2)")
                    if conn.execute("SELECT id FROM caisse_z_closures WHERE business_date=%s FOR UPDATE",(day,)).fetchone(): return jsonify({"ok":False,"error":"La journée est déjà clôturée par un Z"}),409
                    rows=conn.execute("SELECT id,num,payment,status,total,total_ttc,total_ht,tax_amount,z_closure_id FROM caisse_orders WHERE created_at >= %s AND created_at <= %s ORDER BY num FOR UPDATE",(start_ms,end_ms)).fetchall()
                    if not rows: return jsonify({"ok":False,"error":"Aucune commande à clôturer aujourd'hui"}),409
                    opened=[r for r in rows if r["status"]!="Terminée"]
                    if opened: return jsonify({"ok":False,"error":"Z refusé : toutes les commandes doivent être terminées","open_orders":[{"num":r["num"],"status":r["status"]} for r in opened]}),409
                    if any(r.get("z_closure_id") is not None for r in rows): return jsonify({"ok":False,"error":"Z refusé : une commande du jour appartient déjà à une clôture"}),409
                    snap=_snapshot(rows); closure=conn.execute("""INSERT INTO caisse_z_closures (business_date,closed_at,first_order_num,last_order_num,order_count,total_ht,tax_rate,tax_amount,total_ttc,payments_json) VALUES (%s,%s,%s,%s,%s,%s,10,%s,%s,%s::jsonb) RETURNING id""",(day,closed_at,snap["first"],snap["last"],snap["count"],snap["ht"],snap["tax"],snap["ttc"],json.dumps({k:float(v) for k,v in snap["payments"].items()},ensure_ascii=False))).fetchone(); closure_id=closure["id"]; conn.execute("UPDATE caisse_orders SET z_closure_id=%s WHERE id = ANY(%s)",(closure_id,[r["id"] for r in rows]))
            return jsonify({"ok":True,"closed":True,"business_date":day,"closure_id":closure_id,"orders":snap["count"],"total_ht":float(snap["ht"]),"tax_amount":float(snap["tax"]),"total_ttc":float(snap["ttc"])})
        except Exception as exc: return jsonify({"ok":False,"error":"Clôture Z impossible","detail":str(exc)}),500

    @app.get("/api/caisse/z/archive")
    def z_archive_api():
        try:
            with db() as conn:
                ensure_order_schema(conn); _ensure_z_schema(conn); conn.commit(); rows=conn.execute("SELECT id,business_date,closed_at,first_order_num,last_order_num,order_count,total_ht,tax_rate,tax_amount,total_ttc,payments_json FROM caisse_z_closures ORDER BY business_date DESC,id DESC LIMIT 400").fetchall()
            return jsonify({"ok":True,"closures":[dict(r) for r in rows]})
        except Exception as exc: return jsonify({"ok":False,"error":"Archives Z indisponibles","detail":str(exc)}),500

    @app.get("/caisse/z/archive")
    def z_archive_page():
        try:
            with db() as conn:
                ensure_order_schema(conn); _ensure_z_schema(conn); conn.commit(); rows=conn.execute("SELECT id,business_date,closed_at,first_order_num,last_order_num,order_count,total_ht,tax_rate,tax_amount,total_ttc,payments_json FROM caisse_z_closures ORDER BY business_date DESC,id DESC LIMIT 400").fetchall()
            cards=[]
            for r in rows:
                pays=r.get("payments_json") or {}; payhtml="".join(f'<div class="row"><span>{escape(str(k))}</span><b>{_eur(v)}</b></div>' for k,v in pays.items()); dt=datetime.fromtimestamp(int(r["closed_at"])/1000,tz=PARIS).strftime("%d/%m/%Y %H:%M")
                cards.append(f'''<section class="z"><h2>Z #{r["id"]} — {escape(str(r["business_date"]))}</h2><div class="muted">Clôturé le {dt}</div><div class="row"><span>Commandes</span><b>{r["order_count"]}</b></div><div class="row"><span>N° commandes</span><b>{r["first_order_num"] or "—"} à {r["last_order_num"] or "—"}</b></div><div class="row"><span>Total HT</span><b>{_eur(r["total_ht"])}</b></div><div class="row"><span>TVA {r["tax_rate"]} %</span><b>{_eur(r["tax_amount"])}</b></div><div class="row total"><span>Total TTC</span><b>{_eur(r["total_ttc"])}</b></div>{payhtml}</section>''')
            body="".join(cards) if cards else '<section class="z"><b>Aucun Z archivé pour le moment.</b></section>'
            return Response(f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Archives Z</title><style>body{{font-family:Arial;background:#f4f5f7;margin:0;color:#17191c}}header{{background:#111827;color:white;padding:14px 22px}}main{{max-width:760px;margin:25px auto;padding:0 16px}}.z{{background:white;padding:20px;border-radius:12px;margin-bottom:16px}}.row{{display:flex;justify-content:space-between;border-top:1px solid #eee;padding:8px 0}}.total{{font-size:18px}}.muted{{color:#666;margin-bottom:12px}}button,a{{margin-right:10px}}@media print{{header,.actions{{display:none}}body{{background:white}}.z{{break-inside:avoid;border:1px solid #ddd}}}}</style></head><body><header><b>BÉCHÉFAA — Archives Z</b></header><main><div class="actions"><button onclick="print()">IMPRIMER</button><a href="/caisse/z">Z du jour</a><a href="/pos">Retour caisse</a></div>{body}</main></body></html>''',content_type="text/html; charset=utf-8")
        except Exception as exc: return Response("Archives Z indisponibles : "+escape(str(exc)),status=500)

    @app.get("/caisse/z")
    def z_page():
        html='''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Z de caisse</title><style>*{box-sizing:border-box}body{margin:0;background:#f4f5f7;font-family:Arial;color:#17191c}.top{background:#111827;color:#fff;padding:14px 22px}.wrap{max-width:700px;margin:28px auto;padding:0 18px}.card{background:#fff;border-radius:14px;padding:22px}.warn{background:#fff7ed;border:1px solid #fdba74;padding:13px;border-radius:9px;font-weight:700}.ok{background:#ecfdf5;border-color:#86efac}.bad{background:#fef2f2;border-color:#fca5a5}.row{display:flex;justify-content:space-between;padding:8px 0;border-top:1px solid #eee}button{margin-top:18px;width:100%;padding:13px;border:0;border-radius:9px;background:#b91c1c;color:#fff;font-weight:900}.back{color:#fff;text-decoration:none;float:right}</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><a class="back" href="/caisse/z/archive">Archives Z</a></div><main class="wrap"><section class="card"><h1>Z de fin de journée</h1><div id="state" class="warn">Vérification…</div><div id="details"></div><button id="close" disabled>CLÔTURER DÉFINITIVEMENT LA JOURNÉE</button></section></main><script>const state=document.getElementById('state'),details=document.getElementById('details'),btn=document.getElementById('close');async function load(){let r=await fetch('/api/caisse/z/status'),d=await r.json();if(!r.ok||!d.ok){state.className='warn bad';state.textContent=d.error||'Erreur';return}details.innerHTML='<div class="row"><span>Commandes du jour</span><strong>'+d.orders+'</strong></div>';if(d.already_closed){state.className='warn ok';state.textContent='Journée déjà clôturée par le Z.';btn.disabled=true;btn.style.display='none'}else if(d.open_orders.length){state.className='warn bad';state.textContent='Clôture impossible : '+d.open_orders.length+' commande(s) ne sont pas terminée(s).';btn.disabled=true;btn.style.display='block'}else if(!d.orders){state.textContent='Aucune commande à clôturer.';btn.disabled=true;btn.style.display='block'}else{state.className='warn ok';state.textContent='Toutes les commandes sont terminées. Le Z peut être effectué.';btn.disabled=false;btn.style.display='block'}}btn.onclick=async()=>{if(!confirm('Confirmer le Z ? Cette clôture est définitive pour la journée.'))return;btn.disabled=true;let r=await fetch('/api/caisse/z/close',{method:'POST'}),d=await r.json();if(!r.ok||!d.ok){alert(d.error||'Clôture impossible');load();return}state.className='warn ok';state.textContent='Z effectué — journée clôturée.';details.innerHTML='<div class="row"><span>Commandes</span><b>'+d.orders+'</b></div><div class="row"><span>Total HT</span><b>'+d.total_ht.toFixed(2)+' €</b></div><div class="row"><span>TVA 10 %</span><b>'+d.tax_amount.toFixed(2)+' €</b></div><div class="row"><span>Total TTC</span><b>'+d.total_ttc.toFixed(2)+' €</b></div>';btn.style.display='none'};load();</script></body></html>'''
        return Response(html,content_type="text/html; charset=utf-8")
