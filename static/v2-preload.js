// BÉCHÉFAA POS V2 — précharge Catalogue PostgreSQL avant démarrage du POS
// Ce fichier ne contient aucune donnée produit Wix/V1.

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

try {
  const r = await fetch('/api/catalog-admin?t=' + Date.now(), { cache: 'no-store' });
  if (!r.ok) throw new Error('HTTP ' + r.status);
  const j = await r.json();
  const data = j?.data;
  if (!data || !Array.isArray(data.products) || !Array.isArray(data.categories)) {
    throw new Error('Catalogue V2 absent');
  }

  const active = data.products.filter(p => p?.active !== false && (p?.channels?.caisse !== false));
  window.PRODUCTS = active.map((p, i) => ({
    id: String(p.id ?? ('v2-' + i)),
    cat: String(p.category || ''),
    name: String(p.name || 'Produit'),
    price: Number(p.price || 0),
    image: String(p.photo || ''),
    desc: String(p.ingredients || p.description || '')
  }));

  const used = new Set(window.PRODUCTS.map(p => p.cat));
  window.CATEGORIES = data.categories
    .filter(c => c?.active !== false && used.has(c.name))
    .map(c => c.name);

  window.BECHEFAA_V2_PRELOAD = {
    ok: true,
    products: window.PRODUCTS.length,
    categories: window.CATEGORIES.length,
    updatedAt: j?.updatedAt || 0
  };
} catch (e) {
  window.PRODUCTS = [];
  window.CATEGORIES = [];
  window.BECHEFAA_V2_PRELOAD = { ok: false, error: String(e?.message || e) };
  console.error('BÉCHÉFAA V2 preload:', e);
}

// On charge le moteur seulement après que PostgreSQL V2 a rempli les tableaux.
await loadScript('/app.js?v=0604');
await loadScript('/cloud.js?v=0604');
