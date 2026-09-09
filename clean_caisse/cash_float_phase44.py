"""Phase 4.4 — fond de caisse journalier BÉCHÉFAA.

Module isolé : enregistre une seule ouverture par date commerciale dans
PostgreSQL. Ne modifie ni le X, ni le Z, ni les paiements existants.
"""
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
from zoneinfo import ZoneInfo

from flask import Response, jsonify, request

PARIS = ZoneInfo("Europe/Paris")
CENT = Decimal("0.01")


def _money(value):
    try:
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Montant invalide")


def _ensure_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caisse_cash_float_openings (
            id BIGSERIAL PRIMARY KEY,
            business_date TEXT NOT NULL UNIQUE,
            opening_amount NUMERIC(12,2) NOT NULL CHECK (opening_amount >= 0),
            opened_at BIGINT NOT NULL
        )
    """)


def _today():
    return datetime.now(PARIS).strftime("%Y-%m-%d")


def register_cash_float_phase44(app, db):
    @app.get("/api/caisse/cash-float-phase44")
    def cash_float_status_phase44():
        day = _today()
        try:
            with db() as conn:
                _ensure_schema(conn)
                conn.commit()
                row = conn.execute(
                    "SELECT id,business_date,opening_amount,opened_at FROM caisse_cash_float_openings WHERE business_date=%s",
                    (day,),
                ).fetchone()
            return jsonify({"ok": True, "business_date": day, "opened": bool(row), "opening": dict(row) if row else None})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Fond de caisse indisponible", "detail": str(exc)}), 500

    @app.post("/api/caisse/cash-float-phase44")
    def cash_float_open_phase44():
        day = _today()
        payload = request.get_json(silent=True) or {}
        try:
            amount = _money(payload.get("amount"))
            if amount < 0 or amount > Decimal("500.00"):
                return jsonify({"ok": False, "error": "Le fond de caisse doit être compris entre 0 et 500 €"}), 400
            opened_at = int(time.time() * 1000)
            with db() as conn:
                with conn.transaction():
                    _ensure_schema(conn)
                    existing = conn.execute(
                        "SELECT id,opening_amount FROM caisse_cash_float_openings WHERE business_date=%s FOR UPDATE",
                        (day,),
                    ).fetchone()
                    if existing:
                        return jsonify({"ok": False, "error": "Le fond de caisse du jour est déjà enregistré", "opening_amount": float(existing["opening_amount"])}), 409
                    row = conn.execute("""
                        INSERT INTO caisse_cash_float_openings (business_date,opening_amount,opened_at)
                        VALUES (%s,%s,%s)
                        RETURNING id,business_date,opening_amount,opened_at
                    """, (day, amount, opened_at)).fetchone()
            return jsonify({"ok": True, "opened": True, "opening": dict(row) | {"opening_amount": float(row["opening_amount"])}})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Enregistrement du fond de caisse impossible", "detail": str(exc)}), 500

    @app.get("/maintenance/phase44/cash-float-opening")
    def cash_float_opening_page_phase44():
        html = '''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ouverture fond de caisse</title><style>
body{font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c;padding:22px}.box{max-width:620px;margin:auto;background:#fff;border-radius:15px;padding:24px}.note{background:#eef6ff;border:1px solid #bfdbfe;border-radius:9px;padding:12px;margin:15px 0}.state{padding:13px;border-radius:9px;background:#f8fafc;margin:15px 0;font-weight:700}label{display:block;font-weight:700;margin:15px 0 7px}input{width:100%;font-size:25px;padding:12px;border:1px solid #cbd5e1;border-radius:9px}button{width:100%;margin-top:12px;padding:13px;border:0;border-radius:9px;background:#111827;color:white;font-weight:800;font-size:16px}button:disabled{opacity:.45}.ok{background:#ecfdf5}.bad{background:#fef2f2;color:#991b1b}
</style></head><body><div class="box"><h1>Ouverture du fond de caisse</h1><div class="note">Une seule saisie est autorisée par journée. Cette étape n'entre pas dans le chiffre d'affaires.</div><div id="state" class="state">Vérification…</div><div id="form"><label for="amount">Fond initial (€)</label><input id="amount" type="number" min="0" max="500" step="0.01" value="40.00"><button id="save">ENREGISTRER LE FOND DE CAISSE</button></div></div><script>
const state=document.getElementById('state'),form=document.getElementById('form'),btn=document.getElementById('save'),amount=document.getElementById('amount');
async function load(){const r=await fetch('/api/caisse/cash-float-phase44'),d=await r.json();if(!r.ok||!d.ok){state.className='state bad';state.textContent=d.error||'Erreur';btn.disabled=true;return}if(d.opened){state.className='state ok';state.textContent='Fond de caisse déjà enregistré : '+Number(d.opening.opening_amount).toFixed(2)+' €';form.style.display='none'}else{state.textContent='Aucun fond de caisse enregistré aujourd’hui.';form.style.display='block'}}
btn.onclick=async()=>{if(!confirm('Confirmer le fond initial de '+Number(amount.value||0).toFixed(2)+' € ? Cette saisie ne pourra pas être remplacée aujourd’hui.'))return;btn.disabled=true;const r=await fetch('/api/caisse/cash-float-phase44',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({amount:amount.value})}),d=await r.json();if(!r.ok||!d.ok){state.className='state bad';state.textContent=d.error||'Enregistrement impossible';btn.disabled=false;return}await load()};load();
</script></body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")
