"""Remise à zéro unique avant mise en service réelle de BÉCHÉFAA.

Supprime uniquement les données transactionnelles générées pendant les tests.
Conserve le catalogue, les clients importés, la configuration restaurant,
les utilisateurs/PIN, le matériel et les canaux de vente.
"""
import json
import time

from flask import Response, jsonify, request

CONFIRMATION = "MISE_EN_SERVICE_BECHEFAA_2026"

TRANSACTION_TABLES = [
    "caisse_z_cash_details",
    "caisse_z_closures",
    "caisse_cash_counts",
    "caisse_cash_float_openings",
    "caisse_payment_transactions",
    "caisse_order_items",
    "caisse_orders",
    "caisse_user_audit",
]

PRESERVED_TABLES = [
    "caisse_clients",
    "catalog_admin_v2",
]


def _existing_tables(conn):
    rows = conn.execute(
        """SELECT table_name
           FROM information_schema.tables
           WHERE table_schema='public'"""
    ).fetchall()
    return {r["table_name"] for r in rows}


def _count(conn, table):
    row = conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()
    return int(row["n"] or 0)


def _preview(conn):
    existing = _existing_tables(conn)
    counts = {}
    for table in TRANSACTION_TABLES:
        counts[table] = _count(conn, table) if table in existing else 0

    preserved = {}
    for table in PRESERVED_TABLES:
        preserved[table] = _count(conn, table) if table in existing else 0

    orders = 0
    revenue = 0.0
    if "caisse_orders" in existing:
        row = conn.execute(
            """SELECT COUNT(*) AS orders,
                      COALESCE(SUM(total),0) AS revenue
               FROM caisse_orders"""
        ).fetchone()
        orders = int(row["orders"] or 0)
        revenue = float(row["revenue"] or 0)

    return {
        "orders": orders,
        "revenue": round(revenue, 2),
        "transaction_tables": counts,
        "preserved": preserved,
    }


def _reset_serial(conn, table):
    try:
        row = conn.execute(
            "SELECT pg_get_serial_sequence(%s, 'id') AS seq",
            (table,),
        ).fetchone()
        seq = row["seq"] if row else None
        if seq:
            conn.execute("SELECT setval(%s, 1, false)", (seq,))
    except Exception:
        # Une table sans séquence n'a rien à réinitialiser.
        pass


def register_go_live_reset_phase6(app, db):
    @app.get("/api/maintenance/go-live-reset-phase6/preview")
    def go_live_reset_preview_phase6():
        try:
            with db() as conn:
                data = _preview(conn)
            return jsonify({"ok": True, **data})
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Aperçu de remise à zéro indisponible",
                "detail": str(exc),
            }), 500

    @app.post("/api/maintenance/go-live-reset-phase6")
    def go_live_reset_execute_phase6():
        payload = request.get_json(silent=True) or {}
        if str(payload.get("confirmation") or "").strip() != CONFIRMATION:
            return jsonify({
                "ok": False,
                "error": "Phrase de confirmation incorrecte",
            }), 400

        try:
            with db() as conn:
                with conn.transaction():
                    # Empêche deux remises à zéro simultanées.
                    conn.execute("SELECT pg_advisory_xact_lock(20260924)")

                    existing = _existing_tables(conn)
                    before = _preview(conn)
                    deleted = {}

                    for table in TRANSACTION_TABLES:
                        if table not in existing:
                            deleted[table] = 0
                            continue
                        deleted[table] = _count(conn, table)
                        conn.execute(f'DELETE FROM "{table}"')
                        _reset_serial(conn, table)

                    after = _preview(conn)

                    if after["orders"] != 0 or abs(after["revenue"]) > 0.0001:
                        raise RuntimeError(
                            "Contrôle de sécurité échoué : commandes ou CA non nuls après reset"
                        )

            return jsonify({
                "ok": True,
                "message": "Remise à zéro terminée",
                "before": before,
                "deleted": deleted,
                "after": after,
                "completed_at": int(time.time() * 1000),
            })
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Remise à zéro impossible",
                "detail": str(exc),
            }), 500

    @app.get("/maintenance/go-live-reset")
    def go_live_reset_page_phase6():
        html = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mise à zéro BÉCHÉFAA</title>
<style>
body{font-family:Arial,sans-serif;background:#f3f4f6;color:#111827;padding:22px}
.box{max-width:760px;margin:auto;background:#fff;border-radius:16px;padding:24px;box-shadow:0 8px 30px #0001}
h1{margin-top:0}.danger{background:#fef2f2;border:1px solid #fecaca;color:#991b1b;padding:14px;border-radius:10px}
.ok{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;padding:14px;border-radius:10px}
.row{display:flex;justify-content:space-between;gap:20px;padding:10px 0;border-bottom:1px solid #eee}
input{width:100%;box-sizing:border-box;padding:12px;font-size:17px;margin:10px 0;border:1px solid #cbd5e1;border-radius:9px}
button{width:100%;padding:14px;border:0;border-radius:10px;background:#991b1b;color:#fff;font-weight:800;font-size:16px}
button:disabled{opacity:.45}.muted{color:#6b7280;font-size:14px}
code{background:#f3f4f6;padding:2px 5px;border-radius:5px}
</style>
</head>
<body><div class="box">
<h1>Remise à zéro avant mise en service</h1>
<div class="danger"><b>Attention :</b> cette opération supprime définitivement les commandes et données financières de test. Le catalogue, les clients importés et la configuration sont conservés.</div>
<div id="state" style="margin-top:16px">Chargement…</div>
<div id="details"></div>
<p class="muted">Pour confirmer, saisir exactement : <code>MISE_EN_SERVICE_BECHEFAA_2026</code></p>
<input id="confirm" autocomplete="off" placeholder="Phrase de confirmation">
<button id="reset" disabled>REMETTRE LA CAISSE À ZÉRO</button>
</div>
<script>
const state=document.getElementById('state');
const details=document.getElementById('details');
const input=document.getElementById('confirm');
const btn=document.getElementById('reset');
const phrase='MISE_EN_SERVICE_BECHEFAA_2026';

function money(v){return Number(v||0).toFixed(2)+' €'}
async function load(){
  const r=await fetch('/api/maintenance/go-live-reset-phase6/preview',{cache:'no-store'});
  const d=await r.json();
  if(!r.ok||!d.ok){state.className='danger';state.textContent=d.error||'Erreur';return}
  state.className='';
  state.innerHTML='<div class="row"><span>Commandes actuellement enregistrées</span><b>'+d.orders+'</b></div>'+
                  '<div class="row"><span>Chiffre d’affaires actuellement enregistré</span><b>'+money(d.revenue)+'</b></div>'+
                  '<div class="row"><span>Clients conservés</span><b>'+Number((d.preserved||{}).caisse_clients||0)+'</b></div>';
  details.innerHTML='<p class="muted">Après validation : commandes = 0, CA = 0, paiements/Z/comptages de test = vides.</p>';
  btn.disabled=input.value.trim()!==phrase;
}
input.addEventListener('input',()=>btn.disabled=input.value.trim()!==phrase);
btn.onclick=async()=>{
  if(input.value.trim()!==phrase)return;
  if(!confirm('CONFIRMATION FINALE : supprimer définitivement toutes les données transactionnelles de test ?'))return;
  btn.disabled=true;
  const r=await fetch('/api/maintenance/go-live-reset-phase6',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({confirmation:phrase})
  });
  const d=await r.json();
  if(!r.ok||!d.ok){
    state.className='danger';
    state.textContent=(d.error||'Échec')+(d.detail?' — '+d.detail:'');
    btn.disabled=false;
    return;
  }
  input.value='';
  state.className='ok';
  state.innerHTML='<b>Remise à zéro terminée.</b><br>Commandes : '+d.after.orders+' · CA : '+money(d.after.revenue);
  details.innerHTML='<p>La caisse est prête pour la mise en service réelle.</p>';
};
load();
</script>
</body></html>"""
        return Response(html, content_type="text/html; charset=utf-8")
