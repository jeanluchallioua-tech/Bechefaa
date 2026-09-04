// BÉCHÉFAA POS V2 — précharge robuste PostgreSQL
// Aucune donnée Wix/V1. Compatible catégories V2 stockées en chaînes ou objets.

async function loadScript(src) {
  await new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.async = false;
    s.onload = resolve;
    s.onerror = () => reject(new Error('Chargement impossible: ' + src));
    document.head.appendChild(s);
  });
}

function v2Price(v) {
  const s = String(v == null ? 0 : v)
    .replace(/\s/g, '')
    .replace('€', '')
    .replace(',', '.');
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

(async () => {
  try {
    const r = await fetch('/api/catalog-admin?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json();
    const data = j && j.data;
    if (!data || !Array.isArray(data.products)) throw new Error('Catalogue V2 absent');

    const active = data.products.filter(p => p && p.active !== false && (!p.channels || p.channels.caisse !== false));

    window.PRODUCTS = active.map((p, i) => ({
      id: String(p.id != null ? p.id : ('v2-' + i)),
      cat: String(p.category || p.cat || ''),
      name: String(p.name || 'Produit'),
      price: v2Price(p.price),
      image: String(p.photo || p.image || ''),
      desc: String(p.ingredients || p.description || p.desc || ''),
      options: Array.isArray(p.options) ? p.options : [],
      optionSelections: p.optionSelections || {}
    })).filter(p => p.name && p.cat);

    const used = new Set(window.PRODUCTS.map(p => p.cat));
    let cats = [];

    if (Array.isArray(data.categories)) {
      cats = data.categories.map(c => {
        if (typeof c === 'string') return c;
        if (c && c.active !== false) return String(c.name || c.label || '');
        return '';
      }).filter(Boolean).filter(name => used.has(name));
    }

    if (!cats.length) {
      const seen = new Set();
      cats = [];
      window.PRODUCTS.forEach(p => {
        if (p.cat && !seen.has(p.cat)) {
          seen.add(p.cat);
          cats.push(p.cat);
        }
      });
    }

    window.CATEGORIES = cats;
    window.BECHEFAA_V2_PRELOAD = {
      ok: true,
      products: window.PRODUCTS.length,
      categories: window.CATEGORIES.length,
      updatedAt: j && j.updatedAt || 0
    };
    console.log('BÉCHÉFAA V2 preload OK', window.BECHEFAA_V2_PRELOAD);
  } catch (e) {
    window.PRODUCTS = [];
    window.CATEGORIES = [];
    window.BECHEFAA_V2_PRELOAD = { ok: false, error: String(e && e.message || e) };
    console.error('BÉCHÉFAA V2 preload:', e);
  }

  await loadScript('/app.js?v=0607');
  await loadScript('/cloud.js?v=0607');
  await loadScript('/client-ticket-v2-fix.js?v=0613');
})();
