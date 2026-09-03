const CACHE_NAME = "bechefaa-pos-v2-postgresql-0605";
const CORE = [
  "/",
  "/caisse",
  "/salle",
  "/cuisine",
  "/style.css?v=0538",
  "/manifest.webmanifest"
];

self.addEventListener("install", event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(CORE).catch(() => {}))
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);

  // PostgreSQL/API : toujours réseau, jamais de catalogue V1 en cache.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(event.request, { cache: "no-store" }));
    return;
  }

  // Moteur et préchargeur V2 : toujours réseau en priorité, sans réécriture.
  if (
    url.pathname.endsWith("/app.js") ||
    url.pathname.endsWith("/cloud.js") ||
    url.pathname.endsWith("/v2-preload.js") ||
    url.pathname === "/app.js" ||
    url.pathname === "/cloud.js" ||
    url.pathname === "/v2-preload.js"
  ) {
    event.respondWith(
      fetch(event.request, { cache: "no-store" }).catch(() => caches.match(event.request))
    );
    return;
  }

  // Pages/CSS : réseau d'abord, cache seulement comme secours hors connexion.
  if (
    url.pathname.endsWith(".css") ||
    url.pathname.endsWith(".html") ||
    ["/", "/caisse", "/salle", "/cuisine"].includes(url.pathname)
  ) {
    event.respondWith(
      fetch(event.request, { cache: "no-store" })
        .then(response => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  event.respondWith(caches.match(event.request).then(hit => hit || fetch(event.request)));
});
