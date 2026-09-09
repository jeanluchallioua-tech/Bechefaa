"""Phase 4.4 — statistiques journalières BÉCHÉFAA.

Lecture seule. Aucun Z, aucune clôture, aucune écriture métier.
Les bornes de journée sont calculées en Europe/Paris puis comparées aux timestamps ms.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from flask import jsonify, Response

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")


def _bounds_ms():
    now = datetime.now(PARIS)
    start_local = datetime.combine(now.date(), time.min, PARIS)
    end_local = start_local + timedelta(days=1)
    return int(start_local.astimezone(UTC).timestamp()*1000), int(end_local.astimezone(UTC).timestamp()*1000), now.date().isoformat()


def register_statistics_phase44(app, db):
    @app.get('/api/statistics/today-phase44')
    def statistics_today_phase44():
        start_ms, end_ms, day = _bounds_ms()
        try:
            with db() as conn:
                orders = conn.execute("""
                    SELECT
                      COUNT(*) FILTER (WHERE COALESCE(cancellation_hidden,FALSE)=FALSE) AS orders_count,
                      COALESCE(SUM(total) FILTER (WHERE COALESCE(cancellation_hidden,FALSE)=FALSE),0) AS orders_total,
                      COALESCE(AVG(total) FILTER (WHERE COALESCE(cancellation_hidden,FALSE)=FALSE),0) AS average_ticket
                    FROM caisse_orders
                    WHERE created_at >= %s AND created_at < %s
                """, (start_ms,end_ms)).fetchone()
                modes = conn.execute("""
                    SELECT COALESCE(NULLIF(UPPER(source),''),'CAISSE') AS source, COUNT(*) AS count, COALESCE(SUM(total),0) AS total
                    FROM caisse_orders
                    WHERE created_at >= %s AND created_at < %s AND COALESCE(cancellation_hidden,FALSE)=FALSE
                    GROUP BY 1 ORDER BY total DESC
                """, (start_ms,end_ms)).fetchall()
                tx = conn.execute("""
                    SELECT
                      COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS payments,
                      COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunds
                    FROM caisse_payment_transactions
                    WHERE created_at >= %s AND created_at < %s
                """, (start_ms,end_ms)).fetchone()
                methods = conn.execute("""
                    SELECT UPPER(COALESCE(NULLIF(method,''),'AUTRE')) AS method,
                      COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount
                                        WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN -amount ELSE 0 END),0) AS net
                    FROM caisse_payment_transactions
                    WHERE created_at >= %s AND created_at < %s
                    GROUP BY 1 ORDER BY net DESC
                """, (start_ms,end_ms)).fetchall()
            paid=float(tx['payments'] or 0); refunded=float(tx['refunds'] or 0)
            return jsonify({"ok":True,"date":day,"orders":{"count":int(orders['orders_count'] or 0),"gross_total":float(orders['orders_total'] or 0),"average_ticket":float(orders['average_ticket'] or 0)},"cashflow":{"payments":paid,"refunds":refunded,"net":paid-refunded},"sources":[{"source":r['source'],"count":int(r['count']),"total":float(r['total'] or 0)} for r in modes],"methods":[{"method":r['method'],"net":float(r['net'] or 0)} for r in methods]})
        except Exception as exc:
            return jsonify({"ok":False,"error":"Statistiques indisponibles","detail":str(exc)}),500

    @app.get('/statistiques')
    def statistics_page_phase44():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Statistiques</title><style>*{box-sizing:border-box}body{margin:0;background:#f4f5f7;font-family:Arial;color:#111827}.w{max-width:1000px;margin:28px auto;padding:18px}h1{margin:0 0 5px}.muted{color:#667085}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.card,.box{background:white;border-radius:15px;padding:18px;box-shadow:0 4px 18px #0001}.v{font-size:27px;font-weight:900;margin-top:8px}.lab{font-size:12px;font-weight:800;color:#667085;text-transform:uppercase}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.row{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid #eee}.row:last-child{border:0}.warn{background:#fff8e6;border:1px solid #f5d38b;padding:10px;border-radius:10px;font-size:12px;margin-top:14px}@media(max-width:760px){.cards{grid-template-columns:1fr 1fr}.grid{grid-template-columns:1fr}}</style></head><body><div class="w"><h1>Statistiques du jour</h1><div id="date" class="muted"></div><div class="cards"><div class="card"><div class="lab">Commandes</div><div class="v" id="orders">—</div></div><div class="card"><div class="lab">Total commandes</div><div class="v" id="gross">—</div></div><div class="card"><div class="lab">Panier moyen</div><div class="v" id="avg">—</div></div><div class="card"><div class="lab">Net encaissé</div><div class="v" id="net">—</div></div></div><div class="grid"><div class="box"><h2>Canaux / modes</h2><div id="sources"></div></div><div class="box"><h2>Moyens de paiement</h2><div id="methods"></div></div></div><div class="warn">Lecture seule : cette page ne clôture rien et ne déclenche aucun Z.</div></div><script>const euro=n=>Number(n||0).toLocaleString('fr-FR',{style:'currency',currency:'EUR'});async function load(){try{let r=await fetch('/api/statistics/today-phase44',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');document.getElementById('date').textContent=d.date;document.getElementById('orders').textContent=d.orders.count;document.getElementById('gross').textContent=euro(d.orders.gross_total);document.getElementById('avg').textContent=euro(d.orders.average_ticket);document.getElementById('net').textContent=euro(d.cashflow.net);document.getElementById('sources').innerHTML=d.sources.length?d.sources.map(x=>`<div class="row"><span>${x.source} (${x.count})</span><b>${euro(x.total)}</b></div>`).join(''):'<div class="muted">Aucune commande</div>';document.getElementById('methods').innerHTML=d.methods.length?d.methods.map(x=>`<div class="row"><span>${x.method}</span><b>${euro(x.net)}</b></div>`).join(''):'<div class="muted">Aucun encaissement</div>'}catch(e){document.body.innerHTML='<div class="w"><div class="box">Erreur : '+e.message+'</div></div>'}}load()</script></body></html>''',content_type='text/html; charset=utf-8')
