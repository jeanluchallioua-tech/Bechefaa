/* Modify the same unpaid cashier order before kitchen admission. */
(function () {
  function install() {
    const message = document.getElementById('order-message');
    if (!message || typeof renderOrder !== 'function' || typeof saveOrder !== 'function') return;
    const state = { editing: null, busy: false };
    const originalRender = renderOrder, originalSave = saveOrder;
    const esc = value => String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const money = value => Number(value || 0).toFixed(2).replace('.', ',') + ' €';

    function savedActions(order) {
      const label = typeof posOrderIdentity === 'function' ? posOrderIdentity(order) : order.customer_name || 'Commande';
      message.innerHTML = '<div class="success"><b>' + esc(label) +
        ' • Commande enregistrée</b><br>Total ' + money(order.total) +
        ' • En attente d’envoi en cuisine</div><button type="button" class="action kitchen" data-action="send-kitchen" data-order-id="' +
        esc(order.id) + '" data-order-num="' + esc(order.num) + '">Envoyer en cuisine</button>';
      decorate();
    }
    function decorate() {
      if (state.editing || !LAST_SAVED_ORDER || LAST_SAVED_ORDER.status !== 'Enregistrée') return;
      const kitchen = message.querySelector('[data-action="send-kitchen"]');
      if (!kitchen || message.querySelector('[data-pos-edit-pending]')) return;
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'action'; button.dataset.posEditPending = '1';
      button.textContent = 'Modifier / Ajouter';
      button.style.cssText = 'width:100%;min-height:52px;margin-top:8px;background:#fff;color:#111827;border:2px solid #d99a18;border-radius:10px;font-size:17px;font-weight:900';
      kitchen.insertAdjacentElement('afterend', button);
    }
    renderOrder = function () {
      const result = originalRender.apply(this, arguments);
      if (state.editing) {
        const save = document.querySelector('#order [data-action="save-order"]');
        if (save) {
          save.removeAttribute('data-action'); save.dataset.posPendingSave = '1';
          save.textContent = 'Enregistrer les modifications'; save.disabled = state.busy;
        }
      }
      return result;
    };
    async function read(url) {
      const response = await fetch(url, { cache: 'no-store' }), data = await response.json();
      if (!response.ok || !data.ok) throw Error(data.error || 'Lecture impossible');
      return data.order;
    }
    async function open() {
      if (state.busy || state.editing || !LAST_SAVED_ORDER || !LAST_SAVED_ORDER.id) return;
      if (ORDER.length && !confirm('Remplacer le panier actuel par la commande enregistrée ?')) return;
      state.busy = true;
      const id = LAST_SAVED_ORDER.id;
      try {
        const [order, payment] = await Promise.all([
          read('/api/orders/' + encodeURIComponent(id)),
          read('/api/orders/' + encodeURIComponent(id) + '/payment-phase41')
        ]);
        if (order.status !== 'Enregistrée' || Number(payment.paid_amount || 0) !== 0 || payment.z_locked ||
            !['À ENCAISSER','A ENCAISSER','NON PAYÉE','NON PAYEE'].includes(String(payment.payment_status || 'À ENCAISSER').toUpperCase())) {
          throw Error('Cette commande est déjà envoyée, réglée ou clôturée. Utilisez l’historique.');
        }
        state.editing = order;
        ORDER = JSON.parse(JSON.stringify(order.items || []));
        message.innerHTML = '<div class="success"><b>' + esc(order.customer_name || 'Commande') +
          ' • Modification en cours</b><br>Ajoutez ou retirez les articles, puis enregistrez les modifications.</div>' +
          '<button type="button" data-pos-pending-discard>Abandonner les modifications</button>';
      } catch (error) { alert(error.message); }
      finally { state.busy = false; renderOrder(); }
    }
    async function savePending() {
      if (!state.editing || state.busy) return;
      if (!ORDER.length) { alert('La commande doit contenir au moins un article.'); return; }
      state.busy = true; renderOrder();
      try {
        const items = ORDER.map((item, index) => ({ ...item,
          line_id: item.line_id || 'pos-edit-' + Date.now() + '-' + index }));
        const response = await fetch('/api/orders/' + encodeURIComponent(state.editing.id), {
          method: 'PUT', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({items, edit_context:'pos_before_kitchen'})
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw Error(data.error || 'Modification impossible');
        LAST_SAVED_ORDER = {...LAST_SAVED_ORDER, ...state.editing, ...data};
        state.editing = null; ORDER = []; savedActions(LAST_SAVED_ORDER);
      } catch (error) { alert(error.message); }
      finally { state.busy = false; renderOrder(); }
    }
    function discard() {
      if (!state.editing || state.busy) return;
      if (!confirm('Abandonner les modifications ? La commande enregistrée sera conservée.')) return;
      state.editing = null; ORDER = []; renderOrder(); savedActions(LAST_SAVED_ORDER);
    }
    saveOrder = function () {
      return state.editing ? savePending() : originalSave.apply(this, arguments);
    };
    document.addEventListener('click', function (event) {
      const target = event.target;
      if (target.closest('[data-pos-edit-pending]')) {
        event.preventDefault(); event.stopImmediatePropagation(); open();
      } else if (target.closest('[data-pos-pending-save]')) {
        event.preventDefault(); event.stopImmediatePropagation(); savePending();
      } else if (state.editing && target.closest('[data-pos-pending-discard],.pos-cancel-current')) {
        event.preventDefault(); event.stopImmediatePropagation(); discard();
      } else if ((state.editing || state.busy) && target.closest('[data-action="send-kitchen"],.pos-ref-kitchen,.pos-ref-top-kitchen,.pos-ref-pay,.ticket-choice [data-ticket],#svc-current')) {
        event.preventDefault(); event.stopImmediatePropagation();
        alert('Enregistrez ou abandonnez les modifications avant de poursuivre.');
      }
    }, true);
    window.addEventListener('beforeunload', event => {
      if (state.editing) { event.preventDefault(); event.returnValue = ''; }
    });
    new MutationObserver(decorate).observe(message, {childList:true,subtree:true});
    decorate();
    window.bechefaaPendingEdit = {open, save:savePending, isEditing:() => !!state.editing};
  }
  function ready() { setTimeout(install, 0); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready);
  else ready();
})();
