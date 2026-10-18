// Lessons Vault PWA: Vanilla JS als ES-Module, kein Build-Schritt.
import { ausgangSenden, errorNotice, refreshStats, state, store, view } from "./core.js";
import { viewBriefing } from "./briefing.js";
import { viewEingang, viewEntwurf } from "./eingang.js";
import { viewEinstellungen, viewZugang } from "./einstellungen.js";
import { viewErfassen, viewErnte } from "./erfassen.js";
import { editLesson, viewLesson, viewSuche } from "./suche.js";

const thema = store.get("lv-theme", "");
if (thema) document.documentElement.dataset.theme = thema;
if (!store.get("lv-erste-nutzung")) store.set("lv-erste-nutzung", String(Date.now()));

const routes = [
  [/^#\/erfassen$/, (p) => viewErfassen(p), "erfassen"],
  [/^#\/ernte$/, (p) => viewErnte(p), "erfassen"],
  [/^#\/briefing$/, (p) => viewBriefing(null, p), "briefing"],
  [/^#\/briefing\/([\w-]+)$/, (p, id) => viewBriefing(id, p), "briefing"],
  [/^#\/eingang$/, () => viewEingang(), "eingang"],
  [/^#\/pruefen$/, () => { location.replace("#/eingang"); }, "eingang"],
  [/^#\/entwurf\/([\w-]+)$/, (p, id) => viewEntwurf(id), "eingang"],
  [/^#\/suche$/, (p) => viewSuche(p), "suche"],
  [/^#\/lesson\/([\w-]+)$/, (p, id) => viewLesson(id), "suche"],
  [/^#\/lesson\/([\w-]+)\/bearbeiten$/, (p, id) => editLesson(id), "suche"],
  [/^#\/einstellungen$/, () => viewEinstellungen(), "einstellungen"],
  [/^#\/zugang$/, () => viewZugang(), ""],
];

// Scrollposition je Route merken, damit "Zurück" in langen Listen an derselben Stelle landet.
const scrollPos = new Map();
let aktuelleRoute = null;

async function route() {
  const hash = location.hash || "#/erfassen";
  const [pfad, query = ""] = hash.split("?");
  const params = Object.fromEntries(new URLSearchParams(query));
  if (aktuelleRoute) scrollPos.set(aktuelleRoute, window.scrollY);
  for (const [pattern, handler, tab] of routes) {
    const match = pfad.match(pattern);
    if (!match) continue;
    document.querySelectorAll(".tabbar a").forEach((a) => {
      if (a.dataset.tab === tab) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    aktuelleRoute = pfad;
    try {
      await handler(params, ...match.slice(1));
    } catch (err) {
      view.replaceChildren(errorNotice(err));
    }
    window.scrollTo(0, scrollPos.get(pfad) || 0);
    state.nutzerNavigation = true;
    return;
  }
  location.replace("#/erfassen");
}

window.addEventListener("hashchange", () => { sessionStorage.setItem("lv-intern", "1"); route(); });

// Tastatur offen: Tabbar ausblenden und Hinweise oben zeigen, damit nichts verdeckt wird.
document.addEventListener("focusin", (e) => {
  if (e.target.matches?.("input:not([type=checkbox]):not([type=radio]):not([type=file]), textarea, select")) document.body.classList.add("kb");
});
document.addEventListener("focusout", () => {
  setTimeout(() => {
    if (!document.activeElement?.matches?.("input:not([type=checkbox]):not([type=radio]), textarea, select")) document.body.classList.remove("kb");
  }, 50);
});

// Zurück aus dem Hintergrund: Zahlen aktualisieren und wartende Notizen senden.
document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  refreshStats();
  ausgangSenden();
  const tippt = document.activeElement?.matches?.("input, textarea");
  if (!tippt && (location.hash.startsWith("#/eingang") || location.hash.startsWith("#/einstellungen"))) {
    state.nutzerNavigation = false;
    route();
  }
});

// iOS zeigt :active nur, wenn ein touchstart-Listener existiert.
document.addEventListener("touchstart", () => {}, { passive: true });

route();
refreshStats();
ausgangSenden();

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("sw.js").catch(() => { /* optional */ });
}
