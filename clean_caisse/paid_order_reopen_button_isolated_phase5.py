"""Phase 5 — bouton Modifier pour commande payée/Terminée.

INACTIF : ce module n'est ni importé ni enregistré dans wsgi_caisse.py.

Couche d'interface uniquement :
- rend le bouton Modifier disponible sur les commandes au statut Terminée ;
- ouvre la modale de modification existante ;
- laisse le backend de réouverture, le paiement, le Z et le ledger inchangés.
"""
from flask import request


def register_paid_order_reopen_button_isolated_phase5(app):
    @app.after_request
    def paid_order_reopen_button_after_phase5(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<script id="phase5-paid-reopen-button-isolated">
(function(){
  function install(){
    if(typeof render!=='function' || typeof editOrder!=='function') return;

    const originalRender = render;
    render = function(){
      originalRender();
      const cards = Array.from(document.querySelectorAll('#list .order'));
      cards.forEach(function(card){
        const title = card.querySelector('.num');
        if(!title) return;
        const match = (title.textContent || '').match(/#([^ ·]+)/);
        if(!match) return;
        const order = ORDERS.find(function(o){ return String(o.num) === String(match[1]); });
        if(!order || order.status !== 'Terminée') return;

        const locked = card.querySelector('.btn.locked');
        if(!locked) return;
        locked.disabled = false;
        locked.classList.remove('locked');
        locked.classList.add('edit');
        locked.textContent = 'Modifier';
        locked.onclick = function(){ editOrder(order.id); };
      });
    };

    const originalEdit = editOrder;
    editOrder = function(id){
      const order = ORDERS.find(function(o){ return String(o.id) === String(id); });
      if(order && order.status === 'Terminée'){
        EDIT = JSON.parse(JSON.stringify(order));
        document.getElementById('mtitle').textContent = 'Modifier commande #' + order.num;
        document.getElementById('mmsg').innerHTML = '<div class="notice">Commande déjà payée : la modification sera renvoyée en cuisine. Si le total augmente, seul le complément restera à encaisser. Une commande clôturée par le Z reste verrouillée.</div>';
        document.getElementById('modal').classList.add('open');
        renderEdit();
        return;
      }
      return originalEdit(id);
    };

    render();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', function(){ setTimeout(install, 0); });
  }else{
    setTimeout(install, 0);
  }
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
