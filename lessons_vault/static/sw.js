// App-Shell-Cache: sofort aus dem Cache starten, im Hintergrund aktualisieren.
// API-Aufrufe gehen immer ans Netz, damit keine veralteten Daten angezeigt werden.
const CACHE = "lessons-vault-v3";
const SHELL = [
  "./", "index.html", "style.css", "app.js", "core.js", "entwurf.js", "erfassen.js", "eingang.js", "briefing.js",
  "suche.js", "einstellungen.js", "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png",
  "icon-maskable-512.png", "apple-touch-icon.png", "chevron.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  // Cache zuerst: Die App startet sofort, auch wenn Tailscale nach dem Aufwachen noch verbindet.
  // Das Netz aktualisiert den Cache im Hintergrund; die neue Version gilt ab dem nächsten Start.
  const ziel = url.pathname === "/" ? "index.html" : event.request;
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const hit = await cache.match(ziel, { ignoreSearch: true });
      const netz = fetch(event.request)
        .then((response) => {
          // Nur erfolgreiche Antworten cachen, sonst landet z. B. eine 502-Seite als App im Cache.
          if (response.ok) cache.put(ziel, response.clone());
          return response;
        })
        .catch(() => hit || cache.match("index.html"));
      if (hit) {
        event.waitUntil(netz.catch(() => {}));
        return hit;
      }
      return netz;
    }),
  );
});
