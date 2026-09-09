"""Phase 4.4 — statistiques BÉCHÉFAA par période.

Lecture seule. Aucun Z, aucune clôture, aucune écriture métier.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from flask import jsonify, Response, request

PARIS=ZoneInfo('Europe/Paris'); UTC=ZoneInfo('UTC')

def _bounds():
    today=datetime.now(PARIS).date(); period=request.args.get('period','today')
    if period=='week': start=today-timedelta(days=today.weekday()); end=today+timedelta(days=1)
    elif period=='month': start=today.replace(day=1); end=today+timedelta(days=1)
    elif period=='custom':
        try:
            start=datetime.strptime(request.args.get('start',''),'%Y-%m-%d').date(); end=datetime.strptime(request.args.get('end',''),'%Y-%m-%d').date()+timedelta(days=1)
        except ValueError: raise ValueError('Période personnalisée invalide')
        if end<=start: raise ValueError('La date de fin doit être égale ou postérieure à la date de début')
    else: period='today'; start=today; end=today+timedelta(days=1)
    a=datetime.combine(start,time.min,PARIS); b=datetime.combine(end,time.min,PARIS)
    return int(a.astimezone(UTC).timestamp()*1000),int(b.astimezone(UTC).timestamp()*1000),period,start.isoformat(),(end-timedelta(days=1)).isoformat()

def register_statistics_phase44(app,db):
 @app.get('/api/statistics/today-phase44')
 def statistics_today_phase44():
  try: start_ms,end_ms,period,start_date,end_date=_bounds()
  except ValueError as e: return jsonify({'ok':False,'error':str(e)}),400
  try:
   with db() as conn:
    orders=conn.execute("SELECT COUNT(*) FILTER (WHERE COALESCE(cancellation_hidden,FALSE)=FALSE) orders_count,COALESCE(SUM(total) FILTER (WHERE COALESCE(cancellation_hidden,FALSE)=FALSE),0) orders_total,COALESCE(AVG(total) FILTER (WHERE COALESCE(cancellation_hidden,FALSE)=FALSE),0) average_ticket FROM caisse_orders WHERE created_at >= %s AND created_at < %s",(start_ms,end_ms)).fetchone()
    modes=conn.execute("SELECT COALESCE(NULLIF(UPPER(source),''),'CAISSE') source,COUNT(*) count,COALESCE(SUM(total),0) total FROM caisse_orders WHERE created_at >= %s AND created_at < %s AND COALESCE(cancellation_hidden,FALSE)=FALSE GROUP BY 1 ORDER BY total DESC",(start_ms,end_ms)).fetchall()
    tx=conn.execute("SELECT COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) payments,COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) refunds FROM caisse_payment_transactions WHERE created_at >= %s AND created_at < %s",(start_ms,end_ms)).fetchone()
    methods=conn.execute("SELECT UPPER(COALESCE(NULLIF(method,''),'AUTRE')) method,COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN -amount ELSE 0 END),0) net FROM caisse_payment_transactions WHERE created_at >= %s AND created_at < %s GROUP BY 1 ORDER BY net DESC",(start_ms,end_ms)).fetchall()
   paid=float(tx['payments'] or 0); refunded=float(tx['refunds'] or 0)
   return jsonify({'ok':True,'period':period,'start_date':start_date,'end_date':end_date,'orders':{'count':int(orders['orders_count'] or 0),'gross_total':float(orders['orders_total'] or 0),'average_ticket':float(orders['average_ticket'] or 0)},'cashflow':{'payments':paid,'refunds':refunded,'net':paid-refunded},'sources':[{'source':r['source'],'count':int(r['count']),'total':float(r['total'] or 0)} for r in modes],'methods':[{'method':r['method'],'net':float(r['net'] or 0)} for r in methods]})
  except Exception as exc: return jsonify({'ok':False,'error':'Statistiques indisponibles','detail':str(exc)}),500

 @app.get('/statistiques')
 def statistics_page_phase44():
  return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Statistiques</title><style>*{box-sizing:border-box}body{margin:0;background:#f4f5f7;font-family:Arial;color:#111827}.w{max-width:1050px;margin:28px auto;padding:18px}.muted{color:#667085}.filters,.cards{display:grid;gap:12px;margin:18px 0}.filters{grid-template-columns:2fr 1fr 1fr auto}.cards{grid-template-columns:repeat(5,1fr)}.card,.box{background:#fff;border-radius:15px;padding:18px;box-shadow:0 4px 18px #0001}.v{font-size:25px;font-weight:900;margin-top:8px}.lab{font-size:12px;font-weight:800;color:#667085;text-transform:uppercase}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.row{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid #eee}.row:last-child{border:0}select,input,button{min-height:44px;border:1px solid #d0d5dd;border-radius:9px;padding:8px;font-size:14px}button{background:#111827;color:white;font-weight:800}.warn{background:#fff8e6;border:1px solid #f5d38b;padding:10px;border-radius:10px;font-size:12px;margin-top:14px}@media(max-width:800px){.filters,.cards{grid-template-columns:1fr 1fr}.grid{grid-template-columns:1fr}}</style></head><body><div class="w"><h1>Statistiques / Rapports</h1><div class="filters"><select id="period"><option value="today">Aujourd'hui</option><option value="week">Cette semaine</option><option value="month">Ce mois</option><option value="custom">Période personnalisée</option></select><input type="date" id="start"><input type="date" id="end"><button onclick="load()">Afficher</button></div><div id="dates" class="muted"></div><div class="cards"><div class="card"><div class="lab">Commandes</div><div class="v" id="orders">—</div></div><div class="card"><div class="lab">Total commandes</div><div class="v" id="gross">—</div></div><div class="card"><div class="lab">Panier moyen</div><div class="v" id="avg">—</div></div><div class="card"><div class="lab">Remboursements</div><div class="v" id="refunds">—</div></div><div class="card"><div class="lab">Net encaissé</div><div class="v" id="net">—</div></div></div><div class="grid"><div class="box"><h2>Canaux / modes</h2><div id="sources"></div></div><div class="box"><h2>Moyens de paiement</h2><div id="methods"></div></div></div><div class="warn">Lecture seule : aucun bouton de clôture et aucun Z sur cette page.</div></div><script>const $=x=>document.getElementById(x),euro=n=>Number(n||0).toLocaleString('fr-FR',{style:'currency',currency:'EUR'});$('period').onchange=()=>{let c=$('period').value==='custom';$('start').disabled=!c;$('end').disabled=!c};$('period').onchange();async function load(){let p=$('period').value,u='/api/statistics/today-phase44?period='+p;if(p==='custom')u+='&start='+$('start').value+'&end='+$('end').value;try{let r=await fetch(u,{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');$('dates').textContent=d.start_date===d.end_date?d.start_date:d.start_date+' → '+d.end_date;$('orders').textContent=d.orders.count;$('gross').textContent=euro(d.orders.gross_total);$('avg').textContent=euro(d.orders.average_ticket);$('refunds').textContent=euro(d.cashflow.refunds);$('net').textContent=euro(d.cashflow.net);$('sources').innerHTML=d.sources.length?d.sources.map(x=>`<div class="row"><span>${x.source} (${x.count})</span><b>${euro(x.total)}</b></div>`).join(''):'<div class="muted">Aucune commande</div>';$('methods').innerHTML=d.methods.length?d.methods.map(x=>`<div class="row"><span>${x.method}</span><b>${euro(x.net)}</b></div>`).join(''):'<div class="muted">Aucun encaissement</div>'}catch(e){$('dates').textContent='Erreur : '+e.message}}load()</script></body></html>''',content_type='text/html; charset=utf-8')