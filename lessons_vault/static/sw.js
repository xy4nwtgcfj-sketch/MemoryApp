// App-Shell-Cache: sofort aus dem Cache starten, im Hintergrund aktualisieren.
// API-Aufrufe gehen immer ans Netz, damit keine veralteten Daten angezeigt werden.
const CACHE = "lessons-vault-v5";
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
  // Netz zuerst: So passen Seite, Stil und Skripte nach einem Update immer zusammen. Der Cache springt nur ein,
  // wenn der PC nicht antwortet (z. B. Tailscale verbindet nach dem Aufwachen noch), nach spätestens 4 Sekunden.
  const ziel = url.pathname === "/" ? "index.html" : event.request;
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const seite = event.request.mode === "navigate";
      // Ersatzseite nur für Seitenaufrufe, nie für Stil oder Skripte (sonst käme HTML als CSS an).
      const ausCache = () => cache.match(ziel, { ignoreSearch: true }).then((hit) => hit || (seite ? cache.match("index.html") : undefined));
      const netz = fetch(event.request, { cache: "no-store" }).then((response) => {
        // Nur erfolgreiche Antworten cachen, sonst landet z. B. eine 502-Seite als App im Cache.
        if (response.ok) cache.put(ziel, response.clone());
        return response;
      });
      const zeitlimit = new Promise((resolve) => setTimeout(resolve, 4000)).then(ausCache);
      try {
        const antwort = await Promise.race([netz, zeitlimit]);
        if (antwort) return antwort;
        return await netz;
      } catch {
        return (await ausCache()) || Response.error();
      }
    }),
  );
});
