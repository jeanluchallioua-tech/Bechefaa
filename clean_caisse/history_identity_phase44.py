"""Phase 4.4 — identité et présentation épurée de l'Historique.

Affichage uniquement : aucune modification du moteur de commande, paiement,
remboursement, tickets ou PostgreSQL.
- Salle -> Table N
- Emporter -> À EMPORTER — Nom client
- Livraison -> LIVRAISON — Nom client
- Masque les identifiants techniques et les actions secondaires de la liste.
- Les actions opérationnelles restent accessibles derrière « Voir ».
"""
from flask import request


def register_history_identity_phase44(app):
    @app.after_request
    def history_identity_phase44(response):
        if request.method != "GET" or request.path != "/historique-modification":
            return response
        if response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        marker = "function render(){"
        helper = r'''function historyIdentity(o){
  let table=String(o.table_label||'').trim();
  if(table)return table.toUpperCase();
  let source=String(o.source||'').toUpperCase();
  let customer=String(o.customer_name||'').trim();
  let generic=/^client\s+(comptoir|livraison|emporter)$/i.test(customer);
  if(source==='LIVRAISON'||source==='DELIVERY')return generic||!customer?'LIVRAISON':'LIVRAISON — '+customer;
  if(source==='EMPORTER'||source==='TAKEAWAY')return generic||!customer?'À EMPORTER':'À EMPORTER — '+customer;
  return generic||!customer?'À EMPORTER':'À EMPORTER — '+customer;
}
'''
        if marker in html and "function historyIdentity(o)" not in html:
            html = html.replace(marker, helper + marker, 1)

        html = html.replace(
            "#${esc(o.num)} · ${esc(o.customer_name)} ",
            "${esc(historyIdentity(o))} ",
            1,
        )
        html = html.replace(
            "#${esc(o.num)} · ${esc(o.service_label||o.table_label||o.customer_name)}",
            "${esc(historyIdentity(o))}",
            1,
        )
        html = html.replace(
            "alert('#'+o.num+'\\n'+o.status",
            "alert(historyIdentity(o)+'\\n'+o.status",
            1,
        )
        html = html.replace(
            "document.getElementById('mtitle').textContent='Modifier commande #'+o.num;",
            "document.getElementById('mtitle').textContent='Modifier — '+historyIdentity(o);",
            1,
        )
        html = html.replace(
            "document.getElementById('mmsg').innerHTML='<div class=\"success\">Commande #'+esc(d.num)+' modifiée. Statut : '+esc(d.status)",
            "document.getElementById('mmsg').innerHTML='<div class=\"success\">Commande modifiée. Statut : '+esc(d.status)",
            1,
        )

        addon = r'''
<style id="history-clean-ui-phase5">
/* Historique = consultation rapide. La caisse et les moteurs métier restent inchangés. */
#list.list{gap:8px!important}
#list .order{
  padding:12px 14px!important;
  border:1px solid #e5e7eb;
  box-shadow:none!important;
  min-height:74px;
  flex-wrap:wrap;
  align-items:center!important;
}
#list .order .info{min-width:260px}
#list .order .num{font-size:17px!important;font-weight:900!important}
#list .order .meta{margin-top:4px!important;font-size:12px!important;color:#667085!important}
#list .order .items{display:none!important}
#list .order .btn.edit,#list .order .btn.locked{display:none!important}
#list .order .history-print-actions{display:none!important}
#list .order .p44-ticket-badge{display:none!important}
#list .order>.p41-pay-btn,#list .order>.p44-refund-action-btn{display:none!important}
#list .order .btn:not(.edit):not(.locked){min-width:74px;padding:9px 12px}
.history-clean-date{font-size:11px;color:#98a2b3;margin-top:4px}
.history-clean-overlay{display:none;position:fixed;inset:0;z-index:18000;background:rgba(15,23,42,.62);padding:18px;align-items:center;justify-content:center}
.history-clean-overlay.open{display:flex}
.history-clean-panel{width:min(620px,96vw);max-height:90vh;overflow:auto;background:#fff;border-radius:16px;padding:18px;box-shadow:0 22px 70px #0005}
.history-clean-head{display:flex;gap:12px;align-items:flex-start;border-bottom:1px solid #e5e7eb;padding-bottom:12px;margin-bottom:12px}
.history-clean-head-main{flex:1}.history-clean-head h2{margin:0;font-size:21px}.history-clean-sub{font-size:13px;color:#667085;margin-top:5px}
.history-clean-close{width:42px;height:42px;border:0;border-radius:9px;background:#eef1f4;font-size:24px;font-weight:900;cursor:pointer}
.history-clean-lines{display:grid;gap:0}.history-clean-line{padding:11px 0;border-bottom:1px solid #eee}.history-clean-line-top{display:flex;justify-content:space-between;gap:12px;font-weight:800}.history-clean-opt{font-size:12px;color:#667085;margin-top:4px}.history-clean-total{display:flex;justify-content:space-between;font-size:20px;font-weight:900;padding:14px 0 4px}
.history-clean-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;padding-top:14px;border-top:1px solid #e5e7eb}
.history-clean-actions button,.history-clean-actions a{min-height:44px;border:0;border-radius:9px;padding:10px 14px;font-weight:900;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}.history-clean-print-client{background:#2563eb;color:#fff}.history-clean-print-kitchen{background:#d97706;color:#fff}
.history-clean-modify{background:#111827;color:#fff}.history-clean-actions .p41-pay-btn,.history-clean-actions .p44-refund-action-btn{display:inline-block!important;margin:0!important;min-height:44px}
.history-clean-empty{padding:18px 0;color:#667085;text-align:center}
@media(max-width:700px){#list .order{align-items:flex-start!important}.history-clean-actions{flex-direction:column}.history-clean-actions button{width:100%}}
</style>
<div id="history-clean-overlay" class="history-clean-overlay" aria-hidden="true">
  <div class="history-clean-panel" role="dialog" aria-modal="true">
    <div class="history-clean-head">
      <div class="history-clean-head-main"><h2 id="history-clean-title">Commande</h2><div id="history-clean-sub" class="history-clean-sub"></div></div>
      <button type="button" class="history-clean-close" aria-label="Fermer">×</button>
    </div>
    <div id="history-clean-lines" class="history-clean-lines"></div>
    <div class="history-clean-total"><span>Total</span><span id="history-clean-total">0,00 €</span></div>
    <div id="history-clean-actions" class="history-clean-actions"></div>
  </div>
</div>
<script id="history-clean-script-phase5">
(function(){
  function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
  function euro(v){return Number(v||0).toFixed(2).replace('.',',')+' €'}
  function dt(ms){if(!ms)return '';return new Date(Number(ms)).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}
  function oid(card){
    const buttons=[...card.querySelectorAll('button')];
    for(const b of buttons){const oc=b.getAttribute('onclick')||'';let m=oc.match(/viewOrder\('([^']+)'\)/);if(!m)m=oc.match(/editOrder\('([^']+)'\)/);if(m)return m[1]}
    return null;
  }
  function decorateCards(){
    document.querySelectorAll('#list .order').forEach(card=>{
      const id=oid(card);if(!id)return;
      const o=(window.ORDERS||ORDERS||[]).find(x=>String(x.id)===String(id));if(!o)return;
      const info=card.querySelector('.info');if(!info)return;
      let date=info.querySelector('.history-clean-date');if(!date){date=document.createElement('div');date.className='history-clean-date';info.appendChild(date)}
      date.textContent=dt(o.created_at);
      const view=[...card.querySelectorAll('.btn')].find(b=>String(b.textContent||'').trim()==='Voir');
      if(view)view.textContent='Voir';
    });
  }
  ready(function(){
    const overlay=document.getElementById('history-clean-overlay'),title=document.getElementById('history-clean-title'),sub=document.getElementById('history-clean-sub'),lines=document.getElementById('history-clean-lines'),total=document.getElementById('history-clean-total'),actions=document.getElementById('history-clean-actions');
    if(!overlay)return;
    let moved=[];
    function restore(){moved.forEach(x=>{if(x.node&&x.card)x.card.appendChild(x.node)});moved=[]}
    function close(){restore();overlay.classList.remove('open');overlay.setAttribute('aria-hidden','true');actions.innerHTML=''}
    overlay.querySelector('.history-clean-close').onclick=close;overlay.addEventListener('click',e=>{if(e.target===overlay)close()});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&overlay.classList.contains('open'))close()});

    window.viewOrder=function(id){
      const o=(window.ORDERS||ORDERS||[]).find(x=>String(x.id)===String(id));if(!o)return;
      restore();actions.innerHTML='';
      title.textContent=(typeof historyIdentity==='function'?historyIdentity(o):String(o.customer_name||'Commande'));
      sub.textContent=[dt(o.created_at),o.status,o.table_number?'Salle':o.ticket_type].filter(Boolean).join(' · ');
      const arr=o.items||[];
      lines.innerHTML=arr.length?arr.map(i=>'<div class="history-clean-line"><div class="history-clean-line-top"><span>'+esc(i.qty+'× '+i.name)+'</span><span>'+euro(Number(i.unit_price||0)*Number(i.qty||0))+'</span></div>'+(i.options_text?'<div class="history-clean-opt">'+esc(i.options_text)+'</div>':'')+'</div>').join(''):'<div class="history-clean-empty">Aucun article</div>';
      total.textContent=euro(o.total);
      const mod=document.createElement('button');mod.type='button';mod.className='history-clean-modify';mod.textContent='Modifier';mod.onclick=function(){close();if(typeof editOrder==='function')editOrder(id)};actions.appendChild(mod);
      const clientTicket=document.createElement('button');clientTicket.type='button';clientTicket.className='history-clean-print-client';clientTicket.textContent='Ticket client';clientTicket.onclick=function(){if(typeof window.bechefaaPrintClient==='function')window.bechefaaPrintClient(id);else window.location.href='/impression/client/'+encodeURIComponent(id)};actions.appendChild(clientTicket);
      const kitchenTicket=document.createElement('button');kitchenTicket.type='button';kitchenTicket.className='history-clean-print-kitchen';kitchenTicket.textContent='Ticket cuisine';kitchenTicket.onclick=function(){if(typeof window.bechefaaPrintKitchen==='function')window.bechefaaPrintKitchen(id);else window.location.href='/impression/cuisine/'+encodeURIComponent(id)};actions.appendChild(kitchenTicket);
      const card=[...document.querySelectorAll('#list .order')].find(c=>String(oid(c))===String(id));
      if(card){
        [...card.querySelectorAll(':scope > .p41-pay-btn,:scope > .p44-refund-action-btn')].forEach(node=>{moved.push({node,card});actions.appendChild(node)});
      }
      overlay.classList.add('open');overlay.setAttribute('aria-hidden','false');
    };

    if(typeof render==='function'&&!render.__historyCleanWrapped){
      const original=render;
      const wrapped=function(){const result=original.apply(this,arguments);setTimeout(decorateCards,0);return result};
      wrapped.__historyCleanWrapped=true;render=wrapped;
    }
    decorateCards();
    const list=document.getElementById('list');if(list)new MutationObserver(()=>setTimeout(decorateCards,0)).observe(list,{childList:true,subtree:true});
  });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")

        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
