// Gemeinsame Bausteine der Lessons-Vault-PWA: DOM-Helfer, API, Rückmeldungen, Dialoge, Fotos.

export const view = document.getElementById("view");
const toastEl = document.getElementById("toast");
const srStatus = document.getElementById("sr-status");
const SVG_NS = "http://www.w3.org/2000/svg";

export const SEVERITY = {
  1: "kleiner Ärger",
  2: "lästig",
  3: "spürbarer Verlust",
  4: "teuer",
  5: "großer Schaden",
};
export const ZIEL_LESSONS = 60;

// Eintragsarten: Die Datenfelder sind für alle gleich, ihre Bedeutung und Beschriftung hängt von der Art ab.
export const ART = {
  erfahrung: { label: "Erfahrung", icon: "lightbulb", kontext: "Situation", inhalt: "Was ist passiert?", kern: "Regel",
    anwendung: "Nächstes Mal", gewicht: "Schwere", bestaetigen: "Erneut erlebt", bestaetigt: "erlebt",
    kernHinweis: "Ein Satz als Regel, z. B. „Vor X immer Y prüfen.“" },
  wissen: { label: "Wissen", icon: "book-open", kontext: "Wann gilt das?", inhalt: "Inhalt", kern: "Kernaussage",
    anwendung: "Anwendung", gewicht: "Wichtigkeit", bestaetigen: "Erneut bestätigt", bestaetigt: "bestätigt",
    kernHinweis: "Die wichtigste Aussage in einem Satz." },
  vorgehen: { label: "Vorgehen", icon: "list-checks", kontext: "Wann anwenden?", inhalt: "Schritte", kern: "Kernaussage",
    anwendung: "Worauf achten?", gewicht: "Wichtigkeit", bestaetigen: "Erneut angewendet", bestaetigt: "angewendet",
    kernHinweis: "Wofür das Vorgehen gut ist, in einem Satz." },
  entscheidung: { label: "Entscheidung", icon: "scale", kontext: "Ausgangslage und Optionen", inhalt: "Begründung", kern: "Entscheidung",
    anwendung: "Nächster Schritt", gewicht: "Tragweite", bestaetigen: "Erneut so entschieden", bestaetigt: "bestätigt",
    kernHinweis: "Was entschieden wurde, in einem Satz." },
};
export const ARTEN = Object.keys(ART);

// Projektphasen beruflicher Einträge (leer = phasenübergreifend)
export const PHASEN = { sales: "Sales", concept: "Concept", build: "Build", test: "Test", cutover: "Cutover", hypercare: "Hypercare" };
export function phaseBadge(phase) {
  return PHASEN[phase] ? el("span", { class: `badge phase phase-${phase}` }, PHASEN[phase]) : null;
}
export function artInfo(art) { return ART[art] || ART.erfahrung; }
export function artBadge(art, { klein = false } = {}) {
  const a = artInfo(art);
  return el("span", { class: `badge art ${klein ? "" : ""}`, title: a.label }, icon(a.icon), a.label);
}

export const store = {
  get(key, fallback = "") {
    try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, value); } catch { /* privat oder blockiert */ }
  },
  remove(key) {
    try { localStorage.removeItem(key); } catch { /* egal */ }
  },
  json(key, fallback = null) {
    try { return JSON.parse(this.get(key, "")) ?? fallback; } catch { return fallback; }
  },
  setJson(key, value) { this.set(key, JSON.stringify(value)); },
};

// ---------------------------------------------------------------- DOM
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "value") node.value = value;
    else if (key === "checked") node.checked = Boolean(value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function icon(name, cls = "icon") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

// Wie replaceChildren, aber null/false werden ausgelassen (sonst erscheint "null" als Text).
export function fill(node, ...children) {
  node.replaceChildren(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
}

export const state = { zugangNoetig: false, zugangZiel: "#/erfassen", nutzerNavigation: false };

export function routeKey(hash = location.hash) {
  return (hash || "#/erfassen").split("?")[0];
}

// Jede Ansicht merkt sich beim Start ihre Route. Ist sie beim Zeichnen nicht mehr aktiv (Nutzer hat
// weiternavigiert oder die App leitet zur Anmeldung um), zeichnet die verspätete Ansicht nichts mehr.
export function ansicht() {
  const meine = routeKey();
  const fn = (...nodes) => {
    if (!fn.aktiv()) return false;
    view.replaceChildren(el("div", {}, nodes));
    return true;
  };
  fn.aktiv = () => routeKey() === meine && !(state.zugangNoetig && meine !== "#/zugang");
  return fn;
}

// Seitentitel, Titel in der Kopfleiste (erscheint beim Scrollen) und Zurück-Knopf
const topbar = document.getElementById("topbar");
const topbarTitle = document.getElementById("topbar-title");
const backBtn = document.getElementById("nav-back");
const backText = document.getElementById("nav-back-text");
let backZiel = null;
backBtn.addEventListener("click", () => {
  // In der Home-Bildschirm-App gibt es weder Wischgeste noch Browser-Zurück.
  if (history.length > 1 && sessionStorage.getItem("lv-intern") === "1") history.back();
  else location.hash = backZiel || "#/erfassen";
});

export function kopf(titel, zurueck = null) {
  document.title = `${titel} · Lessons Vault`;
  topbarTitle.textContent = titel;
  backZiel = zurueck?.href || null;
  backBtn.hidden = !zurueck;
  backText.textContent = zurueck?.text || "Zurück";
  backBtn.setAttribute("aria-label", `Zurück: ${zurueck?.text || ""}`.trim());
}

const titelBeobachter = "IntersectionObserver" in window
  ? new IntersectionObserver(([e]) => topbar.classList.toggle("scrolled", !e.isIntersecting), { rootMargin: "-56px 0px 0px 0px" })
  : null;
export function grosserTitel(text, attrs = {}) {
  const h = el("h1", { tabindex: "-1", ...attrs }, text);
  topbar.classList.remove("scrolled");
  // Erst beobachten, wenn die Überschrift im Dokument steht, sonst meldet der Observer "nicht sichtbar".
  if (titelBeobachter) { titelBeobachter.disconnect(); requestAnimationFrame(() => { if (h.isConnected) titelBeobachter.observe(h); }); }
  return h;
}

// Nach einer Navigation durch den Nutzer: Fokus auf die Überschrift, damit VoiceOver die neue Ansicht ansagt.
export function fokusAufTitel() {
  if (!state.nutzerNavigation) return;
  const h = view.querySelector("h1");
  if (h) h.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- Ansagen und Toasts
export function say(text) {
  srStatus.textContent = "";
  setTimeout(() => { srStatus.textContent = text; }, 60);
}

let toastTimer = null;
let toastRest = 0;
let toastStart = 0;
function toastAus() {
  clearTimeout(toastTimer);
  toastEl.classList.add("aus");
  toastEl.classList.remove("fehler");
}
function toastTimerStart(ms) {
  clearTimeout(toastTimer);
  toastRest = ms;
  toastStart = Date.now();
  toastTimer = setTimeout(toastAus, ms);
}
// Pausieren, solange Finger, Maus oder Fokus auf dem Toast liegen (WCAG 2.2.1)
for (const ev of ["mouseenter", "focusin", "touchstart"]) {
  toastEl.addEventListener(ev, () => { clearTimeout(toastTimer); toastRest = Math.max(2000, toastRest - (Date.now() - toastStart)); }, { passive: true });
}
for (const ev of ["mouseleave", "focusout"]) {
  toastEl.addEventListener(ev, () => { if (toastRest && !toastEl.classList.contains("aus") && !toastEl.dataset.dauer) toastTimerStart(toastRest); });
}

/**
 * Kurze Bestätigung unten. Mit Aktion (z. B. Rückgängig) bleibt sie 10 s, Fehler bleiben bis zum Schließen.
 * toast("Gesichert", { aktion: { text: "Rückgängig", onclick } })
 */
export function toast(text, { aktion = null, fehler = false, ms } = {}) {
  const dauer = ms ?? (aktion ? 10000 : 5000);
  const inhalt = [
    el("span", { class: "ok" }, icon(fehler ? "alert" : "check", "icon sm")),
    el("span", { class: "msg" }, text),
    aktion ? el("button", { type: "button", onclick: () => { toastAus(); aktion.onclick(); } }, aktion.text) : null,
    el("button", { type: "button", class: "close", "aria-label": "Hinweis schließen", onclick: toastAus }, icon("x", "icon sm")),
  ];
  toastEl.classList.remove("aus");
  toastEl.classList.toggle("fehler", fehler);
  // Inhalt erst nach dem Einblenden setzen, sonst sagt VoiceOver die Live-Region nicht an.
  fill(toastEl);
  requestAnimationFrame(() => fill(toastEl, inhalt));
  if (fehler) { delete toastEl.dataset.dauer; clearTimeout(toastTimer); toastEl.dataset.dauer = "bleibt"; return; }
  delete toastEl.dataset.dauer;
  toastTimerStart(dauer);
}

// ---------------------------------------------------------------- Formatierung
export function debounce(fn, ms) {
  let t;
  const wrapped = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  wrapped.flush = (...args) => { clearTimeout(t); fn(...args); };
  return wrapped;
}

export function formatDate(iso, kurz = false) {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
  if (isNaN(d)) return iso.slice(0, 10);
  return d.toLocaleDateString("de-DE", kurz ? { day: "2-digit", month: "2-digit" } : { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function relTime(iso) {
  const min = Math.round((Date.now() - new Date(iso)) / 60000);
  if (min < 1) return "gerade eben";
  if (min < 60) return `vor ${min} Min.`;
  if (min < 24 * 60) return `vor ${Math.round(min / 60)} Std.`;
  return formatDate(iso);
}

// Gerade Anführungszeichen in deutsche umwandeln, damit Texte von Claude und Nutzer einheitlich aussehen.
export function anf(text) {
  return String(text ?? "").replace(/"([^"\n]+)"/g, "„$1“").replace(/(^|[\s(])'([^'\n]+)'(?=[\s.,;:!?)]|$)/g, "$1‚$2‘");
}

export function kuerzen(text, max = 80) {
  const t = String(text || "").trim().replace(/\s+/g, " ");
  if (t.length <= max) return t;
  const schnitt = t.slice(0, max - 1);
  const wort = schnitt.lastIndexOf(" ");
  return (wort > max * 0.6 ? schnitt.slice(0, wort) : schnitt).replace(/[,;:.\s]+$/, "") + "…";
}

export function wochenSchluessel(d = new Date()) {
  const montag = new Date(d);
  montag.setHours(12, 0, 0, 0);
  montag.setDate(montag.getDate() - ((montag.getDay() + 6) % 7));
  return montag.toISOString().slice(0, 10);
}

export function heute() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const IST_IOS = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

// ---------------------------------------------------------------- API
export class ApiError extends Error {
  constructor(status, message, extra = {}) {
    super(message);
    this.status = status;
    this.code = extra.code || "";
    this.hinweise = extra.hinweise || [];
    this.netz = Boolean(extra.netz);
  }
}

const FELDNAMEN = { text: "Text", titel: "Titel", situation: "Kontext", ereignis: "Inhalt", lesson: "Kernaussage", bereich: "Bereich", antwort: "Antwort" };
function pydanticText(d) {
  const feld = FELDNAMEN[d.loc?.slice(-1)[0]] || "Eingabe";
  if (d.type === "string_too_short") return `${feld} fehlt.`;
  if (d.type === "string_too_long") return `${feld} ist zu lang.`;
  return `${feld}: bitte prüfen.`;
}

export async function api(path, { method = "GET", body, raw = false, timeoutMs } = {}) {
  const headers = {};
  const token = store.get("lv-token");
  if (token) headers.Authorization = `Bearer ${token}`;
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  // Lesen soll schnell scheitern statt ewig zu hängen; Claude-Aufrufe dürfen dauern.
  const limit = timeoutMs ?? (method === "GET" ? 10000 : 150000);
  let res;
  const abbruch = new AbortController();
  const timer = setTimeout(() => abbruch.abort(), limit);
  try {
    res = await fetch(path, { method, headers, signal: abbruch.signal, body: body === undefined ? undefined : isForm ? body : JSON.stringify(body) });
  } catch (err) {
    setOffline(true);
    if (err.name === "AbortError") {
      throw new ApiError(0, "Der PC hat nicht rechtzeitig geantwortet. Bitte gleich noch einmal versuchen.", { netz: true });
    }
    throw new ApiError(0, "Der PC ist nicht erreichbar. Läuft er und ist Tailscale verbunden?", { netz: true });
  } finally {
    clearTimeout(timer);
  }
  setOffline(false);
  if (res.status === 401) {
    state.zugangNoetig = true;
    if (!location.hash.startsWith("#/zugang")) {
      state.zugangZiel = location.hash || "#/erfassen";
      location.hash = "#/zugang";
    }
    throw new ApiError(401, "Zugangstoken fehlt oder ist falsch.");
  }
  if (res.status === 502 || res.status === 503) {
    let detail = "";
    try { detail = (await res.json()).detail; } catch { /* kein JSON */ }
    throw new ApiError(res.status, typeof detail === "string" && detail ? detail : "Die App auf dem PC antwortet nicht. Läuft sie (geplante Aufgabe „Lessons Vault“)?");
  }
  if (!res.ok) {
    let detail = res.statusText;
    let extra = {};
    try {
      const data = await res.json();
      if (data.detail && typeof data.detail === "object" && !Array.isArray(data.detail)) {
        extra = data.detail;  // z. B. {code: "pruefung", meldung, hinweise}
        detail = data.detail.meldung;
      } else {
        detail = Array.isArray(data.detail) ? data.detail.map(pydanticText).join(" ") : data.detail;
      }
    } catch { /* kein JSON */ }
    throw new ApiError(res.status, detail || `Fehler ${res.status}`, extra);
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

export function istPruefung(err) {
  return err instanceof ApiError && (err.code === "pruefung" || err.code === "sperrliste");
}

// ---------------------------------------------------------------- Offline und Postausgang
const offlineEl = document.getElementById("offline");
let offline = false;
export function setOffline(wert) {
  if (wert === offline) return;
  offline = wert;
  offlineEl.hidden = !wert;
  if (!wert) ausgangSenden();
}
export function istOffline() { return offline || navigator.onLine === false; }
window.addEventListener("online", () => ausgangSenden());
window.addEventListener("offline", () => setOffline(true));

// Notizen, die den PC nicht erreicht haben, warten auf dem iPhone und gehen raus, sobald er erreichbar ist.
export function ausgang() { return store.json("lv-ausgang", []); }
export function ausgangAdd(notiz) {
  store.setJson("lv-ausgang", [...ausgang(), { ...notiz, t: Date.now() }]);
}
let sendetGerade = false;
export async function ausgangSenden() {
  const liste = ausgang();
  if (!liste.length || sendetGerade) return 0;
  sendetGerade = true;
  let gesendet = 0;
  try {
    for (const n of liste) {
      try {
        await api("/api/notiz", { method: "POST", body: { text: n.text, quelle: n.quelle || "text", bereich: n.bereich || "", erfassung_sekunden: n.erfassung_sekunden ?? null, bild_ids: n.bild_ids || [] }, timeoutMs: 15000 });
        store.setJson("lv-ausgang", ausgang().filter((x) => x.t !== n.t));
        gesendet += 1;
      } catch (err) {
        if (err.netz || err.status === 401) break;
        // Dauerhaft abgelehnt (z. B. leer): nicht ewig wiederholen
        store.setJson("lv-ausgang", ausgang().filter((x) => x.t !== n.t));
      }
    }
  } finally {
    sendetGerade = false;
  }
  if (gesendet) {
    toast(`${gesendet} gesicherte Notiz${gesendet > 1 ? "en" : ""} an den PC gesendet. Sie liegen im Eingang.`);
    refreshStats();
  }
  return gesendet;
}

// ---------------------------------------------------------------- Zwischengespeicherte Daten
// Bereiche und Status kommen sofort aus dem lokalen Speicher, damit die Erfassen-Seite ohne Netz zeichnet.
let bereicheCache = null;
export function bereicheSofort() { return bereicheCache || store.json("lv-bereiche", []); }
export async function bereiche(refresh = false) {
  if (!bereicheCache || refresh) {
    bereicheCache = await api("/api/bereiche");
    store.setJson("lv-bereiche", bereicheCache);
  }
  return bereicheCache;
}
export function bereicheVergessen() { bereicheCache = null; }

let statusPromise = null;
let statusZeit = 0;
export function statusSofort() { return store.json("lv-status", null); }
export function status(frisch = false) {
  if (!statusPromise || frisch || Date.now() - statusZeit > 30000) {
    statusZeit = Date.now();
    statusPromise = api("/api/status").then((s) => { store.setJson("lv-status", s); return s; })
      .catch((err) => { statusPromise = null; throw err; });
  }
  return statusPromise;
}

let letzteStatistik = store.json("lv-statistik", null);
export function statistikSofort() { return letzteStatistik; }

const statsEl = document.getElementById("stats");
export async function refreshStats({ anlass = "" } = {}) {
  try {
    const s = await api("/api/statistik");
    letzteStatistik = s;
    store.setJson("lv-statistik", s);
    const vorher = sitzungsStand;
    sitzungsStand = zaehlerStand(s);
    statsAnzeigen(s);
    if (vorher) feiernWennNoetig(vorher, sitzungsStand, anlass);
    return s;
  } catch {
    return letzteStatistik;
  }
}
export function statsAnzeigen(s) {
  if (!s) return;
  statsEl.hidden = false;
  const z = zaehlerStand(s);
  fill(statsEl,
    ring(z.punkte.anteil, 20, false),
    el("span", { class: "lvl" }, `Lv ${z.punkte.level}`),
    el("span", { class: `woche ${z.erreicht ? "ok" : ""}` }, `${z.diese}/${z.ziel}`),
    z.serie ? el("span", { class: "serie" }, icon("flame", "icon sm"), z.serie) : null);
  statsEl.title = "Level, Wochenziel und Serie";
  statsEl.setAttribute("aria-label", `Level ${z.punkte.level} ${z.punkte.name}, ${z.punkte.xp} Punkte. Diese Woche ${z.diese} von ${z.ziel} Einträgen${z.serie ? `, ${z.serie} ${z.serie === 1 ? "Woche" : "Wochen"} in Folge` : ""}, ${z.gesamt} Einträge insgesamt`);
  zaehlerHoerer.forEach((fn) => { try { fn(s); } catch { /* Ansicht weg */ } });
  const badge = document.getElementById("eingang-count");
  badge.hidden = !s.offene_entwuerfe;
  badge.textContent = s.offene_entwuerfe || "";
  const link = document.querySelector('.tabbar a[data-tab="eingang"]');
  link.setAttribute("aria-label", s.offene_entwuerfe ? `Eingang, ${s.offene_entwuerfe} offen` : "Eingang");
}
// ---------------------------------------------------------------- Belohnungen: Punkte, Level, Wochenziel, Serie, Wirkung
// Wochen statt Tage: Ein freier Tag bricht keine Serie. Punkte gibt es für Input (Einträge, Bestätigungen)
// und für Wirkung (Briefings, Planpunkte aus eigenen Einträgen, "hilfreich"-Rückmeldungen).
export const MEILENSTEINE = [10, 25, 50, 75, 100, 150, 200, 250, 300, 400, 500, 750, 1000];
export const LEVEL = [
  [0, "Anfänger"], [100, "Sammler"], [300, "Kenner"], [600, "Praktiker"], [1000, "Experte"],
  [1500, "Meister"], [2200, "Mentor"], [3000, "Großmeister"], [4000, "Legende"], [5500, "Orakel"],
];
export const PUNKTE = { eintrag: 10, importiert: 3, bestaetigung: 5, briefing: 15, planpunkt: 5, hilfreich: 20 };
let sitzungsStand = null;
const zaehlerHoerer = new Set();
export function aufZaehler(fn) { zaehlerHoerer.add(fn); return () => zaehlerHoerer.delete(fn); }

export function wochenziel() {
  const n = Number(store.get("lv-wochenziel", "5"));
  return Number.isInteger(n) && n >= 1 && n <= 50 ? n : 5;
}

export function punkteStand(s) {
  const importiert = s?.importiert || 0;
  const eigene = Math.max(0, (s?.gesamt || 0) - importiert);
  const wirkungPunkte = (s?.briefings || 0) * PUNKTE.briefing + (s?.plan_punkte_erfahrung || 0) * PUNKTE.planpunkt
    + (s?.feedback_hilfreich_gesamt || 0) * PUNKTE.hilfreich;
  const xp = eigene * PUNKTE.eintrag + importiert * PUNKTE.importiert + (s?.bestaetigungen_erneut || 0) * PUNKTE.bestaetigung + wirkungPunkte;
  let i = 0;
  while (i + 1 < LEVEL.length && xp >= LEVEL[i + 1][0]) i++;
  const ab = LEVEL[i][0];
  const bis = i + 1 < LEVEL.length ? LEVEL[i + 1][0] : ab + 1500 * (1 + Math.floor((xp - ab) / 1500));
  const naechsterName = i + 1 < LEVEL.length ? LEVEL[i + 1][1] : `${LEVEL[LEVEL.length - 1][1]} +${Math.floor((xp - ab) / 1500) + 1}`;
  return { xp, level: i + 1, name: LEVEL[i][1], ab, bis, naechsterName, anteil: (xp - ab) / Math.max(1, bis - ab), wirkungPunkte,
    briefings: s?.briefings || 0, planpunkte: s?.plan_punkte_erfahrung || 0, hilfreich: s?.feedback_hilfreich_gesamt || 0 };
}

export function zaehlerStand(s) {
  const ziel = wochenziel();
  const wochen = s?.wochen_zaehler || [];
  const diese = wochen[0]?.anzahl || 0;
  let serie = 0;
  for (let i = 1; i < wochen.length && wochen[i].anzahl >= ziel; i++) serie++;
  if (diese >= ziel) serie++;
  const gesamt = s?.gesamt || 0;
  const naechster = MEILENSTEINE.find((m) => m > gesamt) || (Math.floor(gesamt / 500) + 1) * 500;
  const vorher = [...MEILENSTEINE].reverse().find((m) => m <= gesamt) || 0;
  return { ziel, diese, serie, gesamt, naechster, vorher, erreicht: diese >= ziel, punkte: punkteStand(s) };
}

// Fortschrittsring als SVG (nur Zahlen im Markup, daher sicher)
export function ring(anteil, groesse = 20, voll = false) {
  const r = 8, u = 2 * Math.PI * r;
  const wert = Math.max(0, Math.min(1, anteil || 0));
  const span = el("span", { class: `ring ${voll ? "voll" : ""}`, "aria-hidden": "true" });
  span.innerHTML = `<svg viewBox="0 0 20 20" width="${groesse}" height="${groesse}"><circle cx="10" cy="10" r="${r}" class="ring-bg"/>` +
    `<circle cx="10" cy="10" r="${r}" class="ring-fg" stroke-dasharray="${(wert * u).toFixed(2)} ${u.toFixed(2)}" transform="rotate(-90 10 10)"/></svg>`;
  return span;
}

const nf = new Intl.NumberFormat("de-DE");

export function zaehlerKarte(s) {
  const z = zaehlerStand(s);
  const pk = z.punkte;
  const fehlt = Math.max(0, z.ziel - z.diese);
  const bisMeilenstein = z.naechster - z.gesamt;
  return el("a", { class: `card zaehler ${z.erreicht ? "erreicht" : ""}`, href: "#/einstellungen", "aria-label": "Fortschritt ansehen" },
    el("div", { class: "zaehler-kopf" },
      el("span", { class: "level-badge" }, el("b", {}, `Level ${pk.level}`), ` · ${pk.name}`),
      el("span", { class: "xp" }, `${nf.format(pk.xp)} Punkte`)),
    el("div", { class: "progress xp-bar", "aria-hidden": "true" }, el("span", { style: `width:${Math.round(pk.anteil * 100)}%` })),
    el("p", { class: "zaehler-sub" }, `Noch ${nf.format(pk.bis - pk.xp)} Punkte bis Level ${pk.level + 1} · ${pk.naechsterName}`),
    el("div", { class: "zaehler-zeile" },
      el("div", { class: "zaehler-ring" }, ring(z.diese / z.ziel, 44, z.erreicht), el("span", { class: `zaehler-zahl ${String(z.diese).length > 2 ? "klein" : ""}` }, String(z.diese))),
      el("div", { class: "grow" },
        el("p", { class: "zaehler-titel" }, z.erreicht ? `Wochenziel geschafft · ${z.diese} von ${z.ziel}` : `Wochenziel ${z.diese} von ${z.ziel} · noch ${fehlt}`),
        el("p", { class: "zaehler-serie" }, icon("flame", "icon sm"),
          z.serie ? `${z.serie} ${z.serie === 1 ? "Woche" : "Wochen"} in Folge` : "Erreiche das Wochenziel und starte eine Serie"))),
    el("div", { class: "zaehler-wirkung" },
      el("span", {}, icon("clipboard-list", "icon sm"), `${pk.briefings} Briefings`),
      el("span", {}, icon("user", "icon sm"), `${pk.planpunkte}× dein Wissen im Plan`),
      el("span", {}, icon("thumbs-up", "icon sm"), `${pk.hilfreich}× geholfen`)),
    el("p", { class: "zaehler-meilenstein" }, `${z.gesamt} Einträge · noch ${bisMeilenstein} bis ${z.naechster}`));
}

function feiernWennNoetig(vorher, jetzt, anlass = "") {
  const plus = jetzt.punkte.xp - vorher.punkte.xp;
  if (plus <= 0) return;
  statsEl.classList.remove("puls");
  void statsEl.offsetWidth;
  statsEl.classList.add("puls");
  const levelUp = jetzt.punkte.level > vorher.punkte.level;
  const meilenstein = jetzt.gesamt >= vorher.naechster && jetzt.gesamt > vorher.gesamt;
  const wochenziel = !vorher.erreicht && jetzt.erreicht;
  if (levelUp) {
    belohnung(`Level ${jetzt.punkte.level}: ${jetzt.punkte.name}!`, `+${plus} Punkte · ${nf.format(jetzt.punkte.xp)} insgesamt`, { gross: true });
  } else if (meilenstein) {
    belohnung(`Meilenstein: ${vorher.naechster} Einträge!`, `+${plus} Punkte · Dein Wissensschatz wächst.`, { gross: true });
  } else if (wochenziel) {
    belohnung(jetzt.serie > 1 ? `Wochenziel geschafft, ${jetzt.serie} Wochen in Folge!` : "Wochenziel geschafft! Deine Serie läuft.", `+${plus} Punkte`, { gross: true });
  } else {
    const rest = Math.max(0, jetzt.ziel - jetzt.diese);
    belohnung(`+${plus} Punkte`, anlass || (rest ? `Noch ${rest} bis zum Wochenziel · Level ${jetzt.punkte.level} ${jetzt.punkte.name}` : `Wochenziel steht · Level ${jetzt.punkte.level} ${jetzt.punkte.name}`));
  }
}

// Belohnungsbanner oben, immer mit kleinem Konfetti; gross = längere Anzeige und volles Konfetti
let belohnungTimer = null;
export function belohnung(titel, text = "", { gross = false } = {}) {
  say(`${titel} ${text}`);
  document.querySelector(".belohnung")?.remove();
  const box = el("div", { class: `belohnung ${gross ? "gross" : ""}`, role: "status" },
    el("span", { class: "belohnung-icon" }, icon(gross ? "sparkles" : "check")),
    el("div", { class: "grow" }, el("p", { class: "belohnung-titel" }, titel), text ? el("p", { class: "belohnung-text" }, text) : null),
    el("button", { type: "button", class: "icon-btn", "aria-label": "Schließen", onclick: () => box.remove() }, icon("x", "icon sm")));
  document.body.append(box);
  requestAnimationFrame(() => box.classList.add("an"));
  clearTimeout(belohnungTimer);
  belohnungTimer = setTimeout(() => { box.classList.remove("an"); setTimeout(() => box.remove(), 300); }, gross ? 7000 : 3500);
  konfetti(gross ? 60 : 14);
}

export function feiern(text) { belohnung(text, "", { gross: true }); }

function konfetti(anzahl) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const farben = ["#d9a441", "#3567a6", "#2f8a55", "#e8b45c", "#8db4e8", "#ff8f87"];
  const box = el("div", { class: "konfetti", "aria-hidden": "true" });
  for (let i = 0; i < anzahl; i++) {
    const stueck = el("span", {});
    stueck.style.left = `${Math.random() * 100}%`;
    stueck.style.background = farben[i % farben.length];
    stueck.style.animationDelay = `${Math.random() * 0.25}s`;
    stueck.style.setProperty("--drift", `${(Math.random() - 0.5) * 120}px`);
    stueck.style.setProperty("--dreh", `${Math.round(Math.random() * 720)}deg`);
    box.append(stueck);
  }
  document.body.append(box);
  setTimeout(() => box.remove(), 2200);
}

// Erst jetzt anzeigen: Die Zähler-Variablen oben müssen initialisiert sein.
statsAnzeigen(letzteStatistik);

// ---------------------------------------------------------------- Bausteine
export function errorNotice(err, { erneut = null } = {}) {
  return el("div", { class: "notice error", role: "alert" }, icon("alert"),
    el("div", {}, err?.message || String(err),
      erneut ? el("div", { class: "actions" }, el("button", { type: "button", onclick: erneut }, icon("refresh"), "Erneut versuchen")) : null));
}

export function laden(text) {
  return el("p", { class: "loading" }, el("span", { class: "spinner", "aria-hidden": "true" }), text);
}

export function skeleton(text = "") {
  return el("div", { class: "skeleton", "aria-hidden": text ? null : "true" },
    text ? el("p", { class: "waiting" }, el("span", { class: "spinner", "aria-hidden": "true" }), text) : null,
    el("div", { class: "bar big w80" }), el("div", { class: "bar" }), el("div", { class: "bar w60" }));
}

export function leer({ symbol = "inbox", titel, text = "", aktionen = [] }) {
  return el("div", { class: "empty" },
    el("span", { class: "empty-icon" }, icon(symbol)),
    el("h2", {}, titel),
    text ? el("p", {}, text) : null,
    aktionen.length ? el("div", { class: "actions" }, aktionen) : null);
}

export function sevPunkte(n, art = "erfahrung") {
  const label = artInfo(art).gewicht;
  return el("span", { class: "sev", title: `${label} ${n} von 5`, "aria-label": `${label} ${n} von 5` },
    el("span", { class: "sev-label", "aria-hidden": "true" }, label), el("span", { "aria-hidden": "true" }, "●".repeat(n) + "○".repeat(5 - n)));
}

export function quelleText(q) {
  return { sprache: "per Diktat", text: "per Text", import: "aus dem Startbestand" }[q] || "";
}

// Eine Meta-Zeile statt vieler Badges: Bereich · Schwere · erlebt · Datum
export function metaZeile(l, { datum = true, bereich = true } = {}) {
  const teile = [
    artBadge(l.art),
    phaseBadge(l.phase),
    bereich ? el("span", {}, l.bereich) : null,
    sevPunkte(l.schweregrad, l.art),
    l.bestaetigungen > 1 ? el("span", {}, `${l.bestaetigungen}× ${artInfo(l.art).bestaetigt}`) : null,
    datum ? el("span", {}, formatDate(l.erstellt_am, true)) : null,
  ].filter(Boolean);
  return el("p", { class: "meta" },
    teile.map((t, i) => (i ? [el("span", { class: "sep", "aria-hidden": "true" }), t] : t)),
    l.spezifisch === true ? el("span", { class: "badge own" }, icon("user"), "eigene Erfahrung") : null,
    l.status === "bestätigt" ? el("span", { class: "badge success" }, "bestätigt") : null,
    l.status === "überholt" ? el("span", { class: "badge" }, "überholt") : null);
}

export function lessonKarte(l, { href = `#/lesson/${l.id}`, extra = null } = {}) {
  return el("a", { class: `card result ${l.status === "überholt" ? "ueberholt" : ""}`, href, "data-id": l.id },
    el("h3", {}, anf(l.titel)),
    el("p", { class: "rule" }, anf(l.lesson)),
    metaZeile(l),
    extra);
}

// ---------------------------------------------------------------- Dialoge
function dialogOeffnen(box, { klasse = "sheet", label = "" } = {}) {
  const ausloeser = document.activeElement;
  const d = el("dialog", { class: klasse, "aria-label": label || null }, box);
  document.body.append(d);
  d.addEventListener("close", () => { d.remove(); if (ausloeser && ausloeser.isConnected) ausloeser.focus(); });
  d.addEventListener("click", (e) => { if (e.target === d) d.close(""); });
  d.showModal();
  return d;
}

export function bestaetigen({ titel, text = "", ok = "OK", gefahr = false }) {
  return new Promise((resolve) => {
    const okBtn = el("button", { type: "button", class: gefahr ? "danger-fill" : "primary" }, ok);
    const box = el("div", { class: "sheet-box" }, el("h2", {}, titel), text ? el("p", {}, text) : null,
      el("div", { class: "actions" }, okBtn, el("button", { type: "button", onclick: () => d.close("") }, "Abbrechen")));
    const d = dialogOeffnen(box, { label: titel });
    okBtn.addEventListener("click", () => d.close("ok"));
    d.addEventListener("close", () => resolve(d.returnValue === "ok"));
    okBtn.focus();
  });
}

export function eingabe({ titel, text = "", label = "Notiz", platzhalter = "", ok = "Speichern" }) {
  return new Promise((resolve) => {
    const id = `dlg-${Math.random().toString(36).slice(2, 8)}`;
    const feld = el("textarea", { id, rows: 3, placeholder: platzhalter });
    const okBtn = el("button", { type: "button", class: "primary" }, ok);
    const box = el("div", { class: "sheet-box" }, el("h2", {}, titel), text ? el("p", {}, text) : null,
      el("label", { for: id }, label, el("span", { class: "opt" }, " (optional)")), feld,
      el("div", { class: "actions" }, okBtn, el("button", { type: "button", onclick: () => d.close("") }, "Abbrechen")));
    const d = dialogOeffnen(box, { label: titel });
    okBtn.addEventListener("click", () => d.close("ok"));
    d.addEventListener("close", () => resolve(d.returnValue === "ok" ? feld.value.trim() : null));
    feld.focus();
  });
}

export function aktionsblatt(titel, aktionen) {
  const box = el("div", { class: "sheet-box" }, el("h2", {}, titel),
    el("div", { class: "actions" },
      aktionen.map((a) => el("button", { type: "button", class: a.gefahr ? "danger" : "", onclick: () => { d.close(""); a.onclick(); } }, a.icon ? icon(a.icon) : null, a.text)),
      el("button", { type: "button", class: "text", onclick: () => d.close("") }, "Abbrechen")));
  const d = dialogOeffnen(box, { label: titel });
  d.querySelector("button")?.focus();
}

// ---------------------------------------------------------------- Kopieren
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = el("textarea", { style: "position:fixed;opacity:0" });
    area.value = text;
    document.body.append(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  }
}

export function herunterladen(dateiname, inhalt, typ = "text/plain") {
  const url = URL.createObjectURL(inhalt instanceof Blob ? inhalt : new Blob([inhalt], { type: typ }));
  const a = el("a", { href: url, download: dateiname });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
}

// ---------------------------------------------------------------- Diktat
// Auf dem iPhone ist die Diktiertaste der Tastatur verlässlicher als die Spracherkennung im Browser
// (in Home-Bildschirm-Apps bricht sie oft ab). Dort öffnet der Knopf die Tastatur mit einem Hinweis.
export function diktatKnopf(textarea, { onStart = () => {}, onResult = () => {} } = {}) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const button = el("button", { type: "button", class: "icon-btn", "aria-label": "Diktieren", title: "Diktieren" }, icon("mic"));
  if (IST_IOS || !SR) {
    button.addEventListener("click", () => {
      textarea.focus();
      onStart();
      say("Tippe auf das Mikrofon unten rechts in der Tastatur.");
      toast("Tippe auf das Mikrofon unten rechts in der Tastatur.", { ms: 6000 });
    });
    return button;
  }
  button.setAttribute("aria-pressed", "false");
  let recognition = null;
  let base = "";
  const stop = () => {
    recognition?.stop();
    recognition = null;
    button.setAttribute("aria-pressed", "false");
    say("Diktat beendet.");
  };
  button.addEventListener("click", () => {
    if (recognition) return stop();
    onStart();
    recognition = new SR();
    recognition.lang = "de-DE";
    recognition.continuous = true;
    recognition.interimResults = true;
    base = textarea.value ? textarea.value.replace(/\s*$/, " ") : "";
    recognition.onresult = (event) => {
      let finalText = "";
      let interim = "";
      for (let i = 0; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      textarea.value = (base + finalText + interim).trimStart();
      textarea.dispatchEvent(new Event("input"));
      onResult(textarea.value);
    };
    recognition.onerror = (event) => {
      const meldung = {
        "not-allowed": "Mikrofon nicht erlaubt. Die App braucht HTTPS (tailscale serve) und die Freigabe für das Mikrofon.",
        "no-speech": "Nichts verstanden. Bitte näher ans Mikrofon und erneut tippen.",
        "network": "Die Spracherkennung braucht eine Internetverbindung.",
      }[event.error] || "Die Spracherkennung ist abgebrochen. Tippen geht immer.";
      toast(meldung, { ms: 8000 });
      stop();
    };
    recognition.onend = () => { if (recognition) stop(); };
    recognition.start();
    button.setAttribute("aria-pressed", "true");
    say("Diktat läuft. Zum Beenden erneut tippen.");
  });
  return button;
}

// ---------------------------------------------------------------- Fotos
export const MAX_FOTOS = 5;

function verkleinern(file, kante = 2000) {
  // Im Browser verkleinern: schneller Upload über Tailscale, Metadaten fallen weg, HEIC wird zu JPEG.
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const faktor = Math.min(1, kante / Math.max(img.naturalWidth, img.naturalHeight));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.naturalWidth * faktor);
      canvas.height = Math.round(img.naturalHeight * faktor);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => resolve(blob || file), "image/jpeg", 0.85);
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
    img.src = url;
  });
}

export async function fotosHochladen(files) {
  const liste = [...files].slice(0, MAX_FOTOS);
  if (files.length > MAX_FOTOS) toast(`Höchstens ${MAX_FOTOS} Fotos auf einmal, die ersten ${MAX_FOTOS} werden verwendet.`);
  const form = new FormData();
  for (const [i, file] of liste.entries()) form.append("dateien", await verkleinern(file), `foto-${i + 1}.jpg`);
  return api("/api/bilder", { method: "POST", body: form, timeoutMs: 300000 });
}

export function fotoInput(onFiles) {
  const input = el("input", { type: "file", accept: "image/*", multiple: true, class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
  input.addEventListener("change", () => { if (input.files.length) onFiles(input.files); input.value = ""; });
  return input;
}

const bildCache = new Map();
export function bildSrc(id, variante = "vorschau") {
  const key = `${id}/${variante}`;
  if (!bildCache.has(key)) {
    bildCache.set(key, api(`/api/bilder/${id}?variante=${variante}`, { raw: true }).then((r) => r.blob()).then((b) => URL.createObjectURL(b))
      .catch((err) => { bildCache.delete(key); throw err; }));
  }
  return bildCache.get(key);
}

export function lightbox(id, beschreibung = "Foto") {
  const img = el("img", { alt: beschreibung });
  const close = el("button", { type: "button", class: "close", "aria-label": "Foto schließen" }, icon("x"));
  const d = dialogOeffnen([img, close], { klasse: "lightbox", label: beschreibung });
  close.addEventListener("click", () => d.close(""));
  close.focus();
  bildSrc(id, "voll").then((src) => { img.src = src; }).catch(() => d.close(""));
}

export function thumbsRow(bilder, { onRemove, titel = "" } = {}) {
  return el("div", { class: "thumbs" }, bilder.map((b, i) => {
    const img = el("img", { alt: "", loading: "lazy" });
    bildSrc(b.id).then((src) => { img.src = src; }).catch(() => { img.alt = "Foto nicht ladbar"; });
    const name = `Foto ${i + 1} von ${bilder.length}${titel ? ` zu ${titel}` : ""}`;
    return el("div", { class: "thumb" },
      el("button", { type: "button", class: "thumb-open", "aria-label": `${name} vergrößern`, onclick: () => lightbox(b.id, name) }, img),
      onRemove ? el("button", { type: "button", class: "thumb-remove", "aria-label": `${name} entfernen`, onclick: () => onRemove(b) }, icon("x")) : null);
  }));
}

// ---------------------------------------------------------------- Datenschutz-Hinweise
// Treffer der Namensprüfung mit einem Tipp durch neutrale Begriffe ersetzen.
const ERSATZ = [
  [/^Firmenname erkannt: "(.+?)"/, () => "ein Unternehmen"],
  [/^Personenname erkannt: "(.+?)"/, () => "eine Ansprechperson"],
  [/^Möglicher Eigenname: "(.+?)"/, (fund) => fund.split(/\s+/)[0]],
  [/^Enthält Begriff aus deiner Sperrliste: "(.+?)"/, () => "[vertraulich]"],
];
export function ersetzungen(hinweise) {
  const liste = [];
  for (const h of hinweise || []) {
    for (const [muster, ersatz] of ERSATZ) {
      const m = h.match(muster);
      if (m && !liste.some((x) => x.von === m[1])) { liste.push({ von: m[1], nach: ersatz(m[1]) }); break; }
    }
  }
  return liste;
}
export function ersetzenIn(text, von, nach) {
  const muster = new RegExp(von.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  return String(text).replace(muster, nach);
}
export function ersetzenKnoepfe(hinweise, anwenden) {
  const liste = ersetzungen(hinweise);
  if (!liste.length) return null;
  return el("div", { class: "ersetzen" }, liste.map((r) => el("button", {
    type: "button",
    onclick: (e) => { anwenden(r); e.currentTarget.remove(); say(`${r.von} ersetzt durch ${r.nach}.`); },
  }, el("span", {}, el("b", {}, `„${r.von}“`), " ersetzen durch ", el("b", {}, `„${r.nach}“`)))));
}

// Für bereits gespeicherte Lessons: eine einklappbare Zeile statt einer großen Warnbox.
export function hinweisKompakt(hinweise) {
  if (!hinweise?.length) return null;
  return el("details", { class: "hinweis-kompakt" },
    el("summary", {}, icon("shield", "icon sm"), `Datenschutz: ${hinweise.length} Hinweis${hinweise.length > 1 ? "e" : ""}`),
    el("ul", {}, hinweise.map((h) => el("li", {}, anf(h)))),
    el("p", {}, "Nur relevant, wenn dieser Eintrag an Claude geht. Über „Bearbeiten“ kannst du Zahlen und Namen abstrahieren."));
}

export function hinweisBox(hinweise, { titel = "Datenschutz-Hinweis: bitte abstrahieren", anwenden = null } = {}) {
  const box = el("div", { class: "notice warn", role: "status" });
  const update = (list) => {
    box.hidden = !list.length;
    fill(box, icon("shield"), el("div", {},
      el("strong", {}, titel),
      el("ul", {}, list.map((h) => el("li", {}, anf(h)))),
      anwenden ? ersetzenKnoepfe(list, anwenden) : null));
  };
  update(hinweise || []);
  return { node: box, update };
}
