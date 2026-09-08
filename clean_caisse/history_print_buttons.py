"""Étape 6 — boutons de réimpression dans l'historique.
Réutilise les routes 80 mm déjà fournies par printing_phase1.
Aucun changement de données / PostgreSQL / Wix.
"""
from flask import request


def register_history_print_buttons(app):
    @app.after_request
    def inject_history_print_buttons(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style>
.history-print-actions{display:flex;gap:7px;flex-wrap:wrap}
.history-print-actions a{display:inline-block;text-decoration:none;border-radius:8px;padding:10px 12px;font-weight:800;font-size:12px;color:#fff;white-space:nowrap}
.history-print-client{background:#2563eb}.history-print-kitchen{background:#d97706}
</style>
<script>
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const originalRender=window.render;
   if(typeof originalRender!=='function')return;

   function addPrintButtons(){
     document.querySelectorAll('#list .order').forEach(card=>{
       if(card.querySelector('.history-print-actions'))return;
       const buttons=[...card.querySelectorAll('button')];
       const edit=buttons.find(b=>String(b.textContent||'').trim()==='Modifier');
       const view=buttons.find(b=>String(b.textContent||'').trim()==='Voir');
       const sourceButton=edit||view;
       if(!sourceButton)return;
       const onclick=sourceButton.getAttribute('onclick')||'';
       let match=onclick.match(/editOrder\('([^']+)'\)/);
       if(!match)match=onclick.match(/viewOrder\('([^']+)'\)/);
       if(!match)return;
       const id=match[1];
       const wrap=document.createElement('div');wrap.className='history-print-actions';
       wrap.innerHTML='<a class="history-print-client" target="_blank" href="/impression/client/'+encodeURIComponent(id)+'">Ticket client</a><a class="history-print-kitchen" target="_blank" href="/impression/cuisine/'+encodeURIComponent(id)+'">Ticket cuisine</a>';
       card.appendChild(wrap);
     });
   }

   window.render=function(){const result=originalRender.apply(this,arguments);setTimeout(addPrintButtons,0);return result};
   setTimeout(addPrintButtons,0);
   new MutationObserver(()=>setTimeout(addPrintButtons,0)).observe(document.getElementById('list'),{childList:true,subtree:true});
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
