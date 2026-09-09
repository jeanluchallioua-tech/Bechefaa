"""Phase 4.4 — comptage espèces définitif de fermeture BÉCHÉFAA.

Module isolé. Enregistre au maximum un comptage par date commerciale.
Le Z historique n'est pas modifié dans cette étape.
"""
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from flask import jsonify, request

PARIS = ZoneInfo("Europe/Paris")
CENT = Decimal("0.01")


def _money(value):
    try:
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Montant compté invalide")


def _bounds():
    now = datetime.now(PARIS)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return now.strftime("%Y-%m-%d"), int(start.timestamp()*1000), int(now.timestamp()*1000)


def _ensure_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caisse_cash_counts (
            id BIGSERIAL PRIMARY KEY,
            business_date TEXT NOT NULL UNIQUE,
            opening_amount NUMERIC(12,2) NOT NULL,
            cash_sales NUMERIC(12,2) NOT NULL,
            theoretical_amount NUMERIC(12,2) NOT NULL,
            counted_amount NUMERIC(12,2) NOT NULL CHECK (counted_amount >= 0),
            difference_amount NUMERIC(12,2) NOT NULL,
            counted_at BIGINT NOT NULL
        )
    """)


def _cash_state(conn, day, start_ms, end_ms):
    opening = conn.execute(
        "SELECT opening_amount FROM caisse_cash_float_openings WHERE business_date=%s",
        (day,),
    ).fetchone()
    if not opening:
        return None
    row = conn.execute("""
        SELECT COALESCE(SUM(amount),0) AS cash_sales
        FROM caisse_payment_transactions
        WHERE transaction_type='PAYMENT' AND status='SUCCEEDED'
          AND UPPER(method) IN ('ESPÈCES','ESPECES')
          AND created_at >= %s AND created_at <= %s
    """, (start_ms, end_ms)).fetchone()
    opening_amount = Decimal(str(opening["opening_amount"] or 0)).quantize(CENT)
    cash_sales = Decimal(str(row["cash_sales"] or 0)).quantize(CENT)
    return opening_amount, cash_sales, (opening_amount + cash_sales).quantize(CENT)


def register_cash_count_phase44(app, db):
    @app.get("/api/caisse/cash-count-phase44")
    def cash_count_status_phase44():
        day, start_ms, end_ms = _bounds()
        try:
            with db() as conn:
                _ensure_schema(conn); conn.commit()
                state = _cash_state(conn, day, start_ms, end_ms)
                saved = conn.execute("SELECT * FROM caisse_cash_counts WHERE business_date=%s", (day,)).fetchone()
            if not state:
                return jsonify({"ok":True,"business_date":day,"opening":False,"counted":False})
            opening, sales, theoretical = state
            return jsonify({"ok":True,"business_date":day,"opening":True,"opening_amount":float(opening),"cash_sales":float(sales),"theoretical_amount":float(theoretical),"counted":bool(saved),"count":dict(saved) if saved else None})
        except Exception as exc:
            return jsonify({"ok":False,"error":"Comptage espèces indisponible","detail":str(exc)}),500

    @app.post("/api/caisse/cash-count-phase44")
    def cash_count_save_phase44():
        day, start_ms, end_ms = _bounds()
        payload = request.get_json(silent=True) or {}
        try:
            counted = _money(payload.get("counted_amount"))
            if counted < 0 or counted > Decimal("5000.00"):
                return jsonify({"ok":False,"error":"Le montant compté doit être compris entre 0 et 5 000 €"}),400
            counted_at = int(time.time()*1000)
            with db() as conn:
                with conn.transaction():
                    _ensure_schema(conn)
                    existing = conn.execute("SELECT id FROM caisse_cash_counts WHERE business_date=%s FOR UPDATE", (day,)).fetchone()
                    if existing:
                        return jsonify({"ok":False,"error":"Le comptage espèces du jour est déjà enregistré"}),409
                    state = _cash_state(conn, day, start_ms, end_ms)
                    if not state:
                        return jsonify({"ok":False,"error":"Aucun fond de caisse enregistré aujourd'hui"}),409
                    opening, sales, theoretical = state
                    difference = (counted - theoretical).quantize(CENT)
                    row = conn.execute("""
                        INSERT INTO caisse_cash_counts
                        (business_date,opening_amount,cash_sales,theoretical_amount,counted_amount,difference_amount,counted_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        RETURNING *
                    """, (day,opening,sales,theoretical,counted,difference,counted_at)).fetchone()
            return jsonify({"ok":True,"saved":True,"opening_amount":float(row["opening_amount"]),"cash_sales":float(row["cash_sales"]),"theoretical_amount":float(row["theoretical_amount"]),"counted_amount":float(row["counted_amount"]),"difference_amount":float(row["difference_amount"])})
        except ValueError as exc:
            return jsonify({"ok":False,"error":str(exc)}),400
        except Exception as exc:
            return jsonify({"ok":False,"error":"Enregistrement du comptage impossible","detail":str(exc)}),500

    @app.get("/maintenance/phase44/cash-count-save")
    def cash_count_save_page_phase44():
        return '''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Comptage espèces</title><style>body{font-family:Arial;background:#f4f5f7;color:#17191c;padding:22px}.box{max-width:650px;margin:auto;background:#fff;border-radius:15px;padding:24px}.row{display:flex;justify-content:space-between;border-top:1px solid #eee;padding:12px 0}.note,.state{padding:12px;border-radius:9px;margin:14px 0}.note{background:#fff7ed;border:1px solid #fdba74}.state{background:#f8fafc;font-weight:700}input{width:100%;box-sizing:border-box;font-size:25px;padding:12px;border:1px solid #cbd5e1;border-radius:9px}button{width:100%;margin-top:12px;padding:13px;border:0;border-radius:9px;background:#111827;color:white;font-weight:800}.ok{background:#ecfdf5}.bad{background:#fef2f2;color:#991b1b}</style></head><body><div class="box"><h1>Comptage espèces définitif</h1><div class="note">Attention : une seule saisie est autorisée aujourd'hui. Cette étape n'effectue pas encore le Z.</div><div id="state" class="state">Vérification…</div><div id="details"></div><div id="form" style="display:none"><p><b>Espèces réellement comptées (€)</b></p><input id="amount" type="number" min="0" max="5000" step="0.01"><button id="save">ENREGISTRER LE COMPTAGE</button></div></div><script>const state=document.getElementById('state'),details=document.getElementById('details'),form=document.getElementById('form'),amount=document.getElementById('amount'),save=document.getElementById('save');async function load(){let r=await fetch('/api/caisse/cash-count-phase44'),d=await r.json();if(!r.ok||!d.ok){state.className='state bad';state.textContent=d.error||'Erreur';return}if(!d.opening){state.className='state bad';state.textContent='Aucun fond de caisse enregistré aujourd’hui.';return}details.innerHTML='<div class="row"><span>Fond initial</span><b>'+d.opening_amount.toFixed(2)+' €</b></div><div class="row"><span>Ventes espèces</span><b>'+d.cash_sales.toFixed(2)+' €</b></div><div class="row"><span>Tiroir théorique</span><b>'+d.theoretical_amount.toFixed(2)+' €</b></div>';if(d.counted){state.className='state ok';state.textContent='Comptage déjà enregistré : '+Number(d.count.counted_amount).toFixed(2)+' € · écart '+Number(d.count.difference_amount).toFixed(2)+' €';form.style.display='none'}else{state.textContent='Prêt pour le comptage définitif.';form.style.display='block'}}save.onclick=async()=>{if(amount.value==='')return alert('Saisissez le montant compté.');if(!confirm('Enregistrer définitivement '+Number(amount.value).toFixed(2)+' € ?'))return;save.disabled=true;let r=await fetch('/api/caisse/cash-count-phase44',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({counted_amount:amount.value})}),d=await r.json();if(!r.ok||!d.ok){state.className='state bad';state.textContent=d.error||'Erreur';save.disabled=false;return}load()};load();</script></body></html>'''
