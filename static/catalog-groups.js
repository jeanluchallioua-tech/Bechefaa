/* BÉCHÉFAA V0.5.46 — bibliothèque de groupes isolée du moteur POS */
(() => {
  const normChoice = c => Array.isArray(c)
    ? [String(c[0] ?? "Option"), Number(c[1] || 0)]
    : [String(c?.name ?? c?.label ?? "Option"), Number(c?.price ?? c?.extra ?? 0)];

  const normalizeGroup = g => ({
    title: String(g?.title || g?.key || "Options"),
    required: !!g?.required,
    max: Math.max(0, Number(g?.max ?? 1)),
    choices: (Array.isArray(g?.choices) ? g.choices : []).map(normChoice)
  });

  const signature = g => JSON.stringify(normalizeGroup(g));

  async function loadSavedGroups(){
    const r = await fetch('/api/catalog-admin?t=' + Date.now(), {cache:'no-store'});
    if(!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json();
    const products = Array.isArray(j?.data?.products) ? j.data.products : [];
    const out = [];
    const seen = new Set();
    products.forEach(p => (Array.isArray(p.options) ? p.options : []).forEach(g => {
      const x = normalizeGroup(g);
      const s = signature(x);
      if(seen.has(s)) return;
      seen.add(s);
      out.push(x);
    }));
    return out.sort((a,b)=>a.title.localeCompare(b.title,'fr'));
  }

  function currentGroupCount(){
    return document.querySelectorAll('#pfOptionsList [data-og-title]').length;
  }

  function addTemplateToCurrentProduct(group){
    const addGroup = document.getElementById('pfAddOptionGroup');
    if(!addGroup) return;
    addGroup.click();
    const gi = currentGroupCount() - 1;
    if(gi < 0) return;

    const title = document.querySelector(`[data-og-title="${gi}"]`);
    const required = document.querySelector(`[data-og-required="${gi}"]`);
    const max = document.querySelector(`[data-og-max="${gi}"]`);
    if(title) title.value = group.title;
    if(required) required.value = group.required ? '1' : '0';
    if(max) max.value = String(group.max);

    group.choices.forEach((choice, ci) => {
      const addChoice = document.querySelector(`[data-ca="${gi}"]`);
      if(!addChoice) return;
      addChoice.click();
      const name = document.querySelector(`[data-cn="${gi}:${ci}"]`);
      const price = document.querySelector(`[data-cp="${gi}:${ci}"]`);
      if(name) name.value = choice[0];
      if(price) price.value = String(choice[1]);
    });
  }

  async function enhanceProductForm(){
    const list = document.getElementById('pfOptionsList');
    const addGroup = document.getElementById('pfAddOptionGroup');
    if(!list || !addGroup || document.getElementById('pfSavedGroupLibrary')) return;

    const box = document.createElement('div');
    box.id = 'pfSavedGroupLibrary';
    box.style.cssText = 'display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0;padding:10px;border:1px solid #ddd;border-radius:10px;background:#fafafa';
    box.innerHTML = '<b style="width:100%">Groupes enregistrés</b><select id="pfSavedGroupSelect" style="min-width:260px;padding:8px"><option value="">Chargement…</option></select><button type="button" id="pfSavedGroupAdd">Ajouter au produit</button><small style="width:100%;opacity:.7">La liste reprend automatiquement les groupes déjà sauvegardés dans le Catalogue central.</small>';
    list.parentNode.insertBefore(box, list);

    try{
      const groups = await loadSavedGroups();
      const sel = document.getElementById('pfSavedGroupSelect');
      if(!sel) return;
      sel.innerHTML = '<option value="">Choisir un groupe enregistré…</option>' + groups.map((g,i)=>`<option value="${i}">${g.title} — ${g.choices.length} choix</option>`).join('');
      const btn = document.getElementById('pfSavedGroupAdd');
      if(btn) btn.onclick = () => {
        if(sel.value === '') return;
        const g = groups[Number(sel.value)];
        if(g) addTemplateToCurrentProduct(g);
      };
    }catch(e){
      const sel = document.getElementById('pfSavedGroupSelect');
      if(sel) sel.innerHTML = '<option value="">Bibliothèque indisponible</option>';
      console.error('BÉCHÉFAA groupes enregistrés:', e);
    }
  }

  const observer = new MutationObserver(() => enhanceProductForm());
  window.addEventListener('DOMContentLoaded', () => {
    observer.observe(document.body, {childList:true, subtree:true});
    enhanceProductForm();
  });
})();
