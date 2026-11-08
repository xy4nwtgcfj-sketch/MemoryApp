// Wissensnetz: Landkarte der Themen, Themenseiten, Pflegeliste, Wiederholen und Verbindungen zwischen Einträgen.
import {
  aktionsblatt, anf, ansicht, api, artInfo, bestaetigen, el, errorNotice, eingabe, fill, fokusAufTitel,
  grosserTitel, icon, kopf, kuerzen, leer, lessonKarte, relTime, say, skeleton, toast,
} from "./core.js";

const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, ...kinder) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v);
  for (const k of kinder.flat()) if (k !== null && k !== undefined) node.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return node;
}

// Farben je Bereich (in der Reihenfolge der Bereiche) und je Eintragsart
const BEREICH_FARBEN = ["var(--primary-fill)", "var(--own-line)", "var(--ai)", "#4fd1c5", "#ff9f6e", "#f08aa8"];
const ART_FARBEN = { erfahrung: "var(--own-line)", wissen: "var(--ai)", vorgehen: "#4fd1c5", entscheidung: "#ff9f6e" };
const BEZ_FARBEN = { widerspricht: "var(--danger)", ersetzt: "var(--text-3)", ergaenzt: "var(--primary-fill)", beispiel_fuer: "var(--ai)" };

// Wie eine Verbindung aus Sicht eines Eintrags heißt: richtung "aus" = dieser Eintrag ist der Ausgangspunkt
export const BEZIEHUNG = {
  ergaenzt: { aus: "Ergänzt", ein: "Ergänzt durch", icon: "plus" },
  widerspricht: { aus: "Widerspricht", ein: "Widerspricht", icon: "alert" },
  ersetzt: { aus: "Ersetzt", ein: "Ersetzt durch", icon: "refresh" },
  beispiel_fuer: { aus: "Beispiel für", ein: "Beispiel dazu", icon: "lightbulb" },
};

const PFLEGE_ARTEN = {
  widerspruch: { label: "Widerspruch", icon: "alert", klasse: "danger" },
  veraltet: { label: "Vielleicht veraltet", icon: "clock", klasse: "warn" },
  unklar: { label: "Unklar formuliert", icon: "pencil", klasse: "warn" },
  doppelt: { label: "Doppelt", icon: "copy", klasse: "ai" },
  duenn: { label: "Dünnes Thema", icon: "sprout", klasse: "own" },
  luecke: { label: "Lücke", icon: "lightbulb", klasse: "ai" },
};

// ---------------------------------------------------------------- Kräftebasiertes Layout
// Kleine, deterministische Simulation (Fruchterman-Reingold): Knoten stoßen sich ab, Kanten ziehen an, jeder
// Knoten wird zum Anker seiner Gruppe gezogen. Danach Überlappungen auflösen. Gleiches Netz = gleiches Bild.
function zufall(seed) {
  let s = seed % 2147483647 || 1;
  return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
}

// Maße eines Knotens samt Beschriftung: Kreis oben, bis zu zwei Zeilen Text darunter.
function masse(k, beschriftung) {
  k.zeilen = beschriftung ? zeilenUmbruch(k.titel) : [];
  const textBreite = Math.max(0, ...k.zeilen.map((z) => z.length * 6.3));
  k.halb = Math.max(k.r, textBreite / 2);
  k.oben = k.r;
  k.unten = k.r + (k.zeilen.length ? 6 + k.zeilen.length * 13 : 0);
}

// Kräfte (Fruchterman-Reingold) für eine Gruppe um den Nullpunkt, danach Überlappungen der Rechtecke auflösen.
// grenze: halbe verfügbare Breite; die Gruppe wächst dann in die Höhe statt aus dem Bild.
function simuliere(knoten, kanten, { abstand, grenze, rnd }) {
  const n = knoten.length;
  const flaeche = knoten.reduce((s, k) => s + (2 * k.halb + abstand) * (k.oben + k.unten + abstand), 0) * 2.2;
  const seite = Math.sqrt(flaeche);
  const kk = Math.sqrt(flaeche / n);
  const klemmen = (k) => { k.x = Math.max(-grenze + k.halb, Math.min(grenze - k.halb, k.x)); };
  knoten.forEach((k, i) => {
    const w = (2 * Math.PI * i) / n + rnd() * 0.6;
    k.x = Math.cos(w) * seite * 0.3 * (0.6 + rnd() * 0.4);
    k.y = Math.sin(w) * seite * 0.3 * (0.6 + rnd() * 0.4);
    klemmen(k);
  });
  const index = new Map(knoten.map((k, i) => [k.id, i]));
  const schwere = (1.4 * kk) / seite;
  let temperatur = seite / 6;
  for (let it = 0; n > 1 && it < 400; it += 1) {
    const dx = new Float64Array(n);
    const dy = new Float64Array(n);
    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        let x = knoten[i].x - knoten[j].x;
        let y = knoten[i].y - knoten[j].y;
        let d = Math.hypot(x, y);
        if (d < 0.01) { x = rnd() - 0.5; y = rnd() - 0.5; d = 0.5; }
        const f = (kk * kk) / d;
        dx[i] += (x / d) * f; dy[i] += (y / d) * f;
        dx[j] -= (x / d) * f; dy[j] -= (y / d) * f;
      }
    }
    for (const e of kanten) {
      const a = index.get(e.von); const b = index.get(e.zu);
      if (a === undefined || b === undefined) continue;
      const x = knoten[a].x - knoten[b].x;
      const y = knoten[a].y - knoten[b].y;
      const d = Math.max(Math.hypot(x, y), 0.01);
      const f = ((d * d) / kk) * Math.min(1 + Math.log1p(e.gewicht || 1) * 0.5, 2.5);
      dx[a] -= (x / d) * f; dy[a] -= (y / d) * f;
      dx[b] += (x / d) * f; dy[b] += (y / d) * f;
    }
    for (let i = 0; i < n; i += 1) {
      dx[i] -= knoten[i].x * schwere * kk;
      dy[i] -= knoten[i].y * schwere * kk;
      const d = Math.max(Math.hypot(dx[i], dy[i]), 0.01);
      knoten[i].x += (dx[i] / d) * Math.min(d, temperatur);
      knoten[i].y += (dy[i] / d) * Math.min(d, temperatur);
      klemmen(knoten[i]);
    }
    temperatur = Math.max(0.5, temperatur * 0.985);
  }
  for (let runde = 0; runde < 300; runde += 1) {
    let bewegt = false;
    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        const a = knoten[i]; const b = knoten[j];
        const ux = (a.halb + b.halb + abstand) - Math.abs(b.x - a.x);
        const [o, u] = b.y >= a.y ? [a, b] : [b, a];
        const uy = (o.y + o.unten + abstand) - (u.y - u.oben);
        if (ux <= 0 || uy <= 0) continue;
        bewegt = true;
        const xFrei = Math.abs(b.x - a.x) + ux < 2 * grenze - a.halb - b.halb;
        if (ux < uy && xFrei) {
          const richtung = b.x >= a.x ? 1 : -1;
          a.x -= (richtung * ux) / 2; b.x += (richtung * ux) / 2;
          klemmen(a); klemmen(b);
        } else {
          o.y -= uy / 2; u.y += uy / 2;
        }
      }
    }
    if (!bewegt) break;
  }
}

function rahmen(knoten) {
  return {
    links: Math.min(...knoten.map((k) => k.x - k.halb)), rechts: Math.max(...knoten.map((k) => k.x + k.halb)),
    oben: Math.min(...knoten.map((k) => k.y - k.oben)), unten: Math.max(...knoten.map((k) => k.y + k.unten)),
  };
}

// Jede Gruppe (Bereich) für sich anordnen, dann die Gruppen zeilenweise nebeneinander legen und zentrieren.
function layout(knoten, kanten, { breite = 600, abstand = 12, beschriftung = true } = {}) {
  if (!knoten.length) return;
  knoten.forEach((k) => masse(k, beschriftung));
  const rnd = zufall(knoten.length * 7919 + kanten.length * 104729);
  const gruppen = new Map();
  for (const k of knoten) gruppen.set(k.gruppe, [...(gruppen.get(k.gruppe) || []), k]);
  const sortiert = [...gruppen.values()].sort((a, b) => b.length - a.length);
  const LUECKE = 34;
  const zeilen = [[]];
  let x = 0; let y = 0; let zeilenHoehe = 0;
  for (const gruppe of sortiert) {
    const ids = new Set(gruppe.map((k) => k.id));
    simuliere(gruppe, kanten.filter((e) => ids.has(e.von) && ids.has(e.zu)), { abstand, grenze: breite / 2, rnd });
    const r = rahmen(gruppe);
    const w = r.rechts - r.links; const h = r.unten - r.oben;
    if (x > 0 && x + w > breite) { x = 0; y += zeilenHoehe + LUECKE; zeilenHoehe = 0; zeilen.push([]); }
    for (const k of gruppe) { k.x += x - r.links; k.y += y - r.oben; }
    zeilen[zeilen.length - 1].push(...gruppe);
    x += w + LUECKE; zeilenHoehe = Math.max(zeilenHoehe, h);
  }
  for (const zeile of zeilen) {
    if (!zeile.length) continue;
    const r = rahmen(zeile);
    const schub = (breite - (r.rechts - r.links)) / 2 - r.links;
    for (const k of zeile) k.x += schub;
  }
}

function zeilenUmbruch(text, max = 16) {
  const woerter = text.split(/\s+/);
  const zeilen = [""];
  for (const w of woerter) {
    const z = zeilen[zeilen.length - 1];
    if (!z) zeilen[zeilen.length - 1] = w;
    else if ((z + " " + w).length <= max) zeilen[zeilen.length - 1] = `${z} ${w}`;
    else zeilen.push(w);
  }
  if (zeilen.length > 2) return [zeilen[0], kuerzen(zeilen.slice(1).join(" "), max)];
  return zeilen;
}

/**
 * Netz als SVG. knoten: {id, titel, r, farbe, gruppe, zahl?, markiert?, gestrichelt?}; kanten: {von, zu, gewicht, farbe?, strich?}.
 * onWahl(knoten) beim Antippen.
 */
function netzGrafik(knoten, kanten, { onWahl, beschriftung = true, label = "Netz", abstand = 12 } = {}) {
  // In Bildschirmpixeln rechnen, damit Schrift und Kreise am Handy lesbar bleiben (keine Verkleinerung).
  const breite = Math.max(280, Math.min((document.getElementById("view")?.clientWidth || 600) - 48, 960));
  layout(knoten, kanten, { breite, abstand, beschriftung });
  const r = rahmen(knoten);
  const minX = Math.min(r.links, 0) - 6; const maxX = Math.max(r.rechts, breite) + 6;
  const minY = r.oben - 8; const maxY = r.unten + 6;
  const pos = new Map(knoten.map((k) => [k.id, k]));
  const kantenNodes = kanten.map((e) => {
    const a = pos.get(e.von); const b = pos.get(e.zu);
    if (!a || !b) return null;
    const linie = svg("line", {
      x1: a.x.toFixed(1), y1: a.y.toFixed(1), x2: b.x.toFixed(1), y2: b.y.toFixed(1), class: "netz-kante",
      style: `stroke:${e.farbe || "var(--text-3)"};stroke-width:${(1 + Math.min(4, Math.log1p(e.gewicht || 1) * 1.4)).toFixed(1)}`,
      "stroke-dasharray": e.strich ? "6 5" : null,
    });
    linie.dataset.von = e.von; linie.dataset.zu = e.zu;
    return linie;
  });
  const grafik = svg("svg", {
    viewBox: `${minX.toFixed(0)} ${minY.toFixed(0)} ${(maxX - minX).toFixed(0)} ${(maxY - minY).toFixed(0)}`,
    class: "netz", role: "img", "aria-label": label, preserveAspectRatio: "xMidYMid meet",
  });
  const knotenNodes = knoten.map((k) => {
    const g = svg("g", { class: `netz-knoten${k.gestrichelt ? " veraltet" : ""}`, tabindex: "0", role: "button", "aria-label": k.aria || k.titel,
      transform: `translate(${k.x.toFixed(1)} ${k.y.toFixed(1)})` },
    svg("circle", { r: k.r.toFixed(1), class: "netz-kreis", style: `fill:${k.farbe};stroke:${k.farbe}` }),
    k.zahl !== undefined && k.r >= 14 ? svg("text", { class: "netz-zahl", "text-anchor": "middle", dy: "0.35em", style: `font-size:${Math.min(20, Math.max(10, k.r * 0.75)).toFixed(0)}px` }, String(k.zahl)) : null,
    k.markiert ? svg("circle", { r: "4.5", cx: (k.r * 0.72).toFixed(1), cy: (-k.r * 0.72).toFixed(1), class: "netz-marke" }) : null,
    k.zeilen.length ? svg("text", { class: "netz-label", "text-anchor": "middle", y: (k.r + 15).toFixed(1) },
      k.zeilen.map((z, i) => svg("tspan", { x: "0", dy: i ? "13" : "0" }, z))) : null,
    svg("title", {}, k.aria || k.titel));
    g.dataset.id = k.id;
    const waehlen = () => {
      grafik.querySelectorAll(".netz-knoten").forEach((x) => x.classList.toggle("gewaehlt", x === g));
      grafik.classList.add("auswahl");
      grafik.querySelectorAll(".netz-kante").forEach((l) => l.classList.toggle("an", l.dataset.von === k.id || l.dataset.zu === k.id));
      onWahl?.(k);
    };
    g.addEventListener("click", waehlen);
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); waehlen(); } });
    return g;
  });
  grafik.append(svg("g", { class: "kanten" }, kantenNodes.filter(Boolean)), svg("g", {}, knotenNodes));
  return grafik;
}

// ---------------------------------------------------------------- Wissen (Übersicht)
let laufTimer = null;

export async function viewWissen() {
  const render = ansicht();
  kopf("Wissen");
  clearTimeout(laufTimer);
  if (!render(grosserTitel("Wissen"), skeleton())) return;
  fokusAufTitel();
  let data;
  try { data = await api("/api/wissen"); }
  catch (err) { render(grosserTitel("Wissen"), errorNotice(err, { erneut: viewWissen })); return; }
  if (!render.aktiv()) return;
  const z = data.zahlen;
  const bereiche = Object.keys(data.pro_bereich).sort((a, b) => data.pro_bereich[b] - data.pro_bereich[a]);
  const farbe = (b) => BEREICH_FARBEN[Math.max(0, bereiche.indexOf(b)) % BEREICH_FARBEN.length];

  const tile = (zahl, lbl, klasse = "") => el("div", { class: "tile" }, el("div", { class: `num ${klasse}` }, zahl), el("div", { class: "lbl" }, lbl));
  const kacheln = el("div", { class: "tiles wissen-tiles" },
    tile(String(z.eintraege), "Einträge"),
    tile(String(z.themen), z.themen === 1 ? "Thema" : "Themen", "violett"),
    tile(String(z.beziehungen), z.beziehungen === 1 ? "Verbindung" : "Verbindungen"),
    tile(String(z.widersprueche), z.widersprueche === 1 ? "Widerspruch" : "Widersprüche", z.widersprueche ? "gold" : ""));

  const wdh = z.wiederholung;
  const aufgaben = el("div", { class: "wissen-aufgaben" },
    el("a", { class: "card aufgabe", href: "#/wiederholen" },
      el("span", { class: "ic akzent" }, icon("refresh")),
      el("span", { class: "grow" }, el("strong", {}, "Wiederholen"),
        el("span", { class: "li-sub" }, wdh.faellig ? `${wdh.faellig} heute fällig` : "Nichts fällig · neue Einträge üben",
          wdh.gefestigt ? ` · ${wdh.gefestigt} gefestigt` : "")),
      icon("chevron-right", "icon sm chev")),
    el("a", { class: "card aufgabe", href: "#/pflege" },
      el("span", { class: `ic ${z.pflege_offen ? "gold" : "gruen"}` }, icon(z.pflege_offen ? "alert" : "check")),
      el("span", { class: "grow" }, el("strong", {}, "Pflege"),
        el("span", { class: "li-sub" }, z.pflege_offen ? `${z.pflege_offen} ${z.pflege_offen === 1 ? "Punkt" : "Punkte"} offen` : "Alles gepflegt")),
      icon("chevron-right", "icon sm chev")));

  const laufSlot = el("div");
  const zeigeLauf = (lauf) => {
    if (!lauf.laeuft) { fill(laufSlot); return; }
    const anteil = lauf.gesamt ? Math.round((lauf.fertig / lauf.gesamt) * 100) : 0;
    fill(laufSlot, el("div", { class: "card tinted", role: "status" },
      el("p", { class: "waiting", style: "margin:0" }, el("span", { class: "spinner", "aria-hidden": "true" }),
        `${lauf.schritt || "Startet"} …`, lauf.gesamt ? ` ${lauf.fertig} von ${lauf.gesamt}` : ""),
      el("div", { class: "progress own", "aria-hidden": "true", style: "margin-top:10px" }, el("span", { style: `width:${anteil}%` })),
      el("p", { class: "footnote", style: "margin:8px 0 0" }, "Läuft auf dem PC weiter, auch wenn du die App schließt.")));
  };
  const beobachten = () => {
    clearTimeout(laufTimer);
    laufTimer = setTimeout(async () => {
      if (!render.aktiv()) return;
      try {
        const neu = await api("/api/wissen");
        if (neu.lauf.laeuft) { zeigeLauf(neu.lauf); beobachten(); return; }
        if (neu.lauf.fehler) toast(`Wissenspflege: ${neu.lauf.fehler}`, { fehler: true, ms: 8000 });
        else if (neu.lauf.ergebnis) toast(`Fertig: ${neu.lauf.ergebnis}.`);
        viewWissen();
      } catch { beobachten(); }
    }, 2500);
  };
  const starten = async (arten, knopf) => {
    knopf?.setAttribute("aria-disabled", "true");
    try {
      const r = await api(`/api/wissen/lauf?arten=${arten}`, { method: "POST" });
      zeigeLauf(r.lauf);
      say("Läuft im Hintergrund.");
      beobachten();
    } catch (err) {
      knopf?.removeAttribute("aria-disabled");
      toast(err.message, { fehler: true });
    }
  };
  zeigeLauf(data.lauf);
  if (data.lauf.laeuft) beobachten();

  // Noch keine Themen: Aufbau anbieten
  if (!data.themen.length) {
    const aufbauen = el("button", { type: "button", class: "primary" }, icon("sparkles"), "Themenseiten aufbauen");
    aufbauen.addEventListener("click", () => starten("zuordnen,verdichten", aufbauen));
    render(grosserTitel("Wissen"), kacheln, laufSlot,
      data.lauf.laeuft ? null : el("div", { class: "card hero" },
        el("p", { class: "overline row", style: "gap:6px" }, icon("sparkles", "icon sm"), "Dein Wissen verdichten"),
        el("p", { class: "lead" }, "Claude ordnet deine Einträge Themen zu und schreibt je Thema eine Seite: Kernaussagen, was sich bewährt hat, Fallstricke und Widersprüche."),
        el("p", { class: "small muted", style: "margin:8px 0 0" },
          `Danach hältst du sie nachts automatisch aktuell. Der erste Aufbau dauert bei ${z.eintraege} Einträgen einige Minuten und kostet einmalig ein paar Euro.`,
          data.lokale_bereiche.length ? ` Lokale Bereiche (${data.lokale_bereiche.join(", ")}) bleiben außen vor.` : ""),
        data.ki ? el("div", { class: "actions" }, aufbauen) : el("div", { class: "notice warn" }, icon("alert"), el("div", {}, "Claude ist nicht eingerichtet."))),
      aufgaben);
    return;
  }

  // Landkarte
  const infoSlot = el("div", { class: "netz-info", "aria-live": "polite" });
  const themaInfo = (t) => fill(infoSlot, el("a", { class: "card result", href: `#/thema/${t.id}` },
    el("div", { class: "card-head" }, el("h3", { class: "grow" }, anf(t.titel)), icon("chevron-right", "icon sm chev")),
    t.zusammenfassung ? el("p", { class: "rule" }, anf(t.zusammenfassung)) : el("p", { class: "rule" }, "Noch nicht verdichtet."),
    el("p", { class: "meta" }, el("span", {}, t.bereich), el("span", { class: "sep", "aria-hidden": "true" }), el("span", {}, `${t.anzahl} Einträge`),
      t.widersprueche ? [el("span", { class: "sep", "aria-hidden": "true" }), el("span", { style: "color:var(--danger)" }, `${t.widersprueche} Widerspr.`)] : null)));
  const max = Math.max(...data.themen.map((t) => t.anzahl), 1);
  const knoten = data.themen.map((t) => ({
    id: t.id, titel: t.titel, gruppe: t.bereich, farbe: farbe(t.bereich), zahl: t.anzahl,
    r: 10 + 20 * Math.sqrt(t.anzahl / max), markiert: t.widersprueche > 0, gestrichelt: t.veraltet,
    aria: `${t.titel}, ${t.anzahl} Einträge${t.widersprueche ? `, ${t.widersprueche} Widersprüche` : ""}`, thema: t,
  }));
  const karte = netzGrafik(knoten, data.kanten, { onWahl: (k) => themaInfo(k.thema), label: `Landkarte mit ${knoten.length} Themen` });
  const legende = el("div", { class: "netz-legende" },
    [...new Set(data.themen.map((t) => t.bereich))].map((b) => el("span", {}, el("i", { style: `background:${farbe(b)}` }), b)),
    el("span", {}, el("i", { class: "rot" }), "Widerspruch"),
    data.themen.some((t) => t.veraltet) ? el("span", {}, el("i", { class: "strich" }), "wird aktualisiert") : null);

  // Themenliste je Bereich
  const nachBereich = {};
  for (const t of data.themen) (nachBereich[t.bereich] ||= []).push(t);
  const liste = Object.entries(nachBereich).map(([b, themen]) => [
    el("h2", { class: "row", style: "gap:8px" }, el("i", { class: "punkt", style: `background:${farbe(b)}` }), b,
      el("small", { class: "footnote", style: "margin-left:auto;font-weight:400" }, `${themen.length} Themen`)),
    el("ul", { class: "list" }, themen.map((t) => el("li", { style: "padding:0" },
      el("a", { class: "li grow", href: `#/thema/${t.id}` },
        el("span", { class: "grow" }, el("span", { style: "display:block;font-weight:600" }, anf(t.titel)),
          el("span", { class: "li-sub" }, `${t.anzahl} Einträge`, t.widersprueche ? ` · ${t.widersprueche} Widerspr.` : "", t.veraltet ? " · wird aktualisiert" : "")),
        icon("chevron-right", "icon sm chev"))))),
  ]);

  const laeufe = data.laeufe;
  const aktualisieren = el("button", { type: "button" }, icon("refresh", "icon sm"), "Jetzt aktualisieren");
  aktualisieren.addEventListener("click", () => starten("zuordnen,verdichten", aktualisieren));
  const stand = el("div", { class: "card flat", style: "margin-top:24px" },
    el("p", { class: "overline" }, "Automatisch jede Nacht"),
    el("p", { class: "small", style: "margin:4px 0 0" },
      "Neue Einträge kommen ins passende Thema, geänderte Themenseiten werden neu verdichtet, einmal pro Woche prüft Claude den Bestand."),
    el("p", { class: "footnote", style: "margin:8px 0 0" },
      laeufe.verdichten ? `Zuletzt verdichtet ${relTime(laeufe.verdichten.zuletzt_am)} (${laeufe.verdichten.ergebnis}).` : "",
      laeufe.pruefen ? ` Zuletzt geprüft ${relTime(laeufe.pruefen.zuletzt_am)}.` : "",
      z.ohne_thema ? ` ${z.ohne_thema} Einträge noch ohne Thema.` : ""),
    data.ki && !data.lauf.laeuft ? el("div", { class: "actions" }, aktualisieren) : null);

  render(grosserTitel("Wissen"), kacheln, laufSlot, aufgaben,
    el("h2", { class: "row", style: "gap:8px" }, icon("network"), "Landkarte"),
    el("p", { class: "footnote", style: "margin:0 0 8px" }, "Je größer, desto mehr Einträge. Linien verbinden Themen mit gemeinsamen Einträgen. Tippe ein Thema an."),
    el("div", { class: "card netz-karte" }, karte, legende), infoSlot,
    liste, stand);
}

// ---------------------------------------------------------------- Themenseite
function quellenChips(ids, lessons) {
  const nr = new Map(lessons.map((l, i) => [l.id, [i + 1, l]]));
  const chips = ids.map((id) => nr.get(id)).filter(Boolean);
  if (!chips.length) return null;
  return el("span", { class: "quellen" }, chips.map(([n, l]) => el("a", { class: "quelle", href: `#/lesson/${l.id}`, title: l.titel, "aria-label": `Eintrag ${n}: ${l.titel}` }, `E${n}`)));
}

export async function viewThema(id) {
  const render = ansicht();
  const zurueck = { text: "Wissen", href: "#/wissen" };
  kopf("Thema", zurueck);
  if (!render(skeleton())) return;
  let t;
  try { t = await api(`/api/themen/${encodeURIComponent(id)}`); }
  catch (err) { render(grosserTitel("Thema"), errorNotice(err), el("a", { href: "#/wissen" }, "Zur Übersicht")); return; }
  if (!render.aktiv()) return;
  kopf(t.titel, zurueck);
  const s = t.seite;
  const nummer = new Map(t.lessons.map((l, i) => [l.id, i + 1]));
  const abschnitt = (titel, symbol, punkte, klasse = "") => (punkte?.length ? el("section", { class: `thema-abschnitt ${klasse}` },
    el("h2", { class: "row", style: "gap:8px" }, icon(symbol), titel),
    el("ul", { class: "thema-punkte" }, punkte.map((p) => el("li", {}, el("span", {}, anf(p.text)), quellenChips(p.quellen || [], t.lessons))))) : null);

  const verdichten = el("button", { type: "button" }, icon("sparkles", "icon sm"), s ? "Neu verdichten" : "Jetzt verdichten");
  const wartenSlot = el("div");
  verdichten.addEventListener("click", async () => {
    verdichten.setAttribute("aria-disabled", "true");
    fill(wartenSlot, el("p", { class: "waiting" }, el("span", { class: "spinner", "aria-hidden": "true" }), "Claude verdichtet die Seite …"));
    try { await api(`/api/themen/${t.id}/verdichten`, { method: "POST", timeoutMs: 260000 }); toast("Themenseite aktualisiert."); viewThema(id); }
    catch (err) { verdichten.removeAttribute("aria-disabled"); fill(wartenSlot, errorNotice(err)); }
  });

  // Netz der Einträge, wenn sie untereinander verbunden sind
  let netz = null;
  const verbunden = new Set(t.beziehungen.flatMap((b) => [b.von_id, b.zu_id]));
  const titelVon = new Map(t.lessons.map((l) => [l.id, l]));
  if (t.beziehungen.length && verbunden.size < 3) {
    // Wenige Verbindungen: als Sätze lesbarer als eine Grafik
    netz = el("section", {},
      el("h2", { class: "row", style: "gap:8px" }, icon("network"), "Verbindungen"),
      el("ul", { class: "thema-punkte" }, t.beziehungen.map((b) => el("li", { class: "entwurf-verbindungen" },
        el("span", { class: "row", style: "gap:8px;align-items:flex-start" },
          el("span", { class: "bez-punkt", style: `background:${BEZ_FARBEN[b.art]}`, "aria-hidden": "true" }),
          el("span", {}, el("a", { href: `#/lesson/${b.von_id}` }, `E${nummer.get(b.von_id)}`), ` ${BEZIEHUNG[b.art]?.aus.toLowerCase() || b.art} `,
            el("a", { href: `#/lesson/${b.zu_id}` }, `E${nummer.get(b.zu_id)}`),
            el("span", { class: "li-sub" }, `${kuerzen(titelVon.get(b.von_id)?.titel || "", 60)} → ${kuerzen(titelVon.get(b.zu_id)?.titel || "", 60)}`)))))));
  } else if (t.beziehungen.length) {
    const knoten = t.lessons.filter((l) => verbunden.has(l.id)).map((l) => ({
      id: l.id, titel: `E${nummer.get(l.id)}`, gruppe: "x", farbe: ART_FARBEN[l.art] || "var(--text-3)", r: 10 + l.schweregrad * 2,
      aria: `E${nummer.get(l.id)}: ${l.titel}`, lesson: l,
    }));
    const info = el("div", { "aria-live": "polite" });
    const grafik = netzGrafik(knoten, t.beziehungen.map((b) => ({ von: b.von_id, zu: b.zu_id, gewicht: 2, farbe: BEZ_FARBEN[b.art], strich: b.art === "ersetzt" })),
      { onWahl: (k) => fill(info, lessonKarte(k.lesson)), label: "Verbindungen zwischen den Einträgen", abstand: 26 });
    netz = el("section", {},
      el("h2", { class: "row", style: "gap:8px" }, icon("network"), "Verbindungen"),
      el("div", { class: "card netz-karte klein" }, grafik,
        el("div", { class: "netz-legende" }, Object.entries(BEZ_FARBEN).map(([art, f]) => el("span", {}, el("i", { class: art === "ersetzt" ? "strich" : "", style: `background:${f}` }), BEZIEHUNG[art].aus)))),
      info);
  }

  render(
    grosserTitel(anf(t.titel), { style: "font-size:1.5rem;margin:8px 0 6px" }),
    el("p", { class: "meta", style: "margin:0 0 14px" }, el("span", {}, t.bereich), el("span", { class: "sep", "aria-hidden": "true" }),
      el("span", {}, `${t.lessons.length} Einträge`),
      t.aktualisiert_am ? [el("span", { class: "sep", "aria-hidden": "true" }), el("span", {}, `verdichtet ${relTime(t.aktualisiert_am)}`)] : null,
      t.veraltet ? el("span", { class: "status" }, el("span", { class: "badge warn" }, "neue Einträge seitdem")) : null),
    s ? el("div", { class: "card hero" }, el("p", { class: "overline row", style: "gap:6px" }, icon("sparkles", "icon sm"), "Dein Gesamtbild"),
      el("p", { class: "lead" }, anf(s.zusammenfassung)))
      : el("div", { class: "notice info" }, icon("info"), el("div", {}, "Diese Seite ist noch nicht verdichtet. Das passiert nachts automatisch, oder jetzt per Knopf.")),
    s ? [
      abschnitt("Kernaussagen", "sparkles", s.kernaussagen),
      abschnitt("Bewährt", "check", s.bewaehrt, "gut"),
      abschnitt("Fallstricke", "alert", s.fallstricke, "achtung"),
      abschnitt("Widersprüche", "alert", s.widersprueche, "widerspruch"),
      s.offene_fragen?.length ? el("section", { class: "thema-abschnitt" }, el("h2", { class: "row", style: "gap:8px" }, icon("lightbulb"), "Offene Fragen"),
        el("ul", { class: "thema-punkte" }, s.offene_fragen.map((f) => el("li", {}, el("span", {}, anf(f)),
          el("a", { class: "quelle neu", href: `#/erfassen?text=${encodeURIComponent(`${f} `)}` }, icon("plus", "icon sm"), "Notieren"))))) : null,
    ] : null,
    netz,
    el("h2", {}, `Einträge (${t.lessons.length})`),
    t.lessons.map((l) => lessonKarte(l, { extra: el("span", { class: "nr" }, `E${nummer.get(l.id)}`) })),
    el("div", { class: "actions", style: "margin-top:16px" }, verdichten), wartenSlot);
  fokusAufTitel();
}

// ---------------------------------------------------------------- Pflege
export async function viewPflege(params = {}) {
  const render = ansicht();
  kopf("Pflege", { text: "Wissen", href: "#/wissen" });
  const status = ["offen", "erledigt", "ignoriert"].includes(params.status) ? params.status : "offen";
  if (!render(grosserTitel("Pflege"), skeleton())) return;
  fokusAufTitel();
  let punkte; let wissen;
  try { [punkte, wissen] = await Promise.all([api(`/api/pflege?status=${status}`), api("/api/wissen")]); }
  catch (err) { render(grosserTitel("Pflege"), errorNotice(err, { erneut: () => viewPflege(params) })); return; }
  if (!render.aktiv()) return;

  const seg = el("div", { class: "segmented", role: "group", "aria-label": "Status", style: "margin:4px 0 16px" },
    [["offen", "Offen"], ["erledigt", "Erledigt"], ["ignoriert", "Ignoriert"]].map(([k, tx]) => el("button", {
      type: "button", "aria-pressed": String(k === status), onclick: () => { location.hash = `#/pflege?status=${k}`; },
    }, tx)));

  const karte = (p) => {
    const a = PFLEGE_ARTEN[p.art] || { label: p.art, icon: "info", klasse: "" };
    const node = el("div", { class: "card pflege-punkt" });
    const setzen = async (neu, text) => {
      try {
        await api(`/api/pflege/${p.id}`, { method: "PATCH", body: { status: neu } });
        node.remove();
        toast(text, { aktion: { text: "Rückgängig", onclick: () => api(`/api/pflege/${p.id}`, { method: "PATCH", body: { status } }).then(() => viewPflege(params)).catch(() => {}) } });
      } catch (err) { toast(err.message, { fehler: true }); }
    };
    fill(node,
      el("div", { class: "card-head" }, el("span", { class: `badge ${a.klasse}` }, icon(a.icon), a.label),
        el("span", { class: "grow" }), el("span", { class: "footnote" }, relTime(p.erstellt_am))),
      el("h3", { style: "margin:10px 0 4px" }, anf(p.titel)),
      p.hinweis ? el("p", { class: "small", style: "margin:0" }, anf(p.hinweis)) : null,
      p.vorschlag ? el("p", { class: "small", style: "margin:8px 0 0" }, el("span", { class: "overline", style: "display:inline;margin-right:6px" }, "Vorschlag"), anf(p.vorschlag)) : null,
      p.lessons.length ? el("ul", { class: "pflege-eintraege" }, p.lessons.map((l) => el("li", {},
        el("a", { href: `#/lesson/${l.id}` }, el("span", { class: `art art-${l.art}`, "aria-hidden": "true" }), anf(l.titel)),
        l.status === "überholt" ? el("span", { class: "badge" }, "überholt") : null))) : null,
      el("div", { class: "actions" },
        status === "offen"
          ? [el("button", { type: "button", onclick: () => setzen("erledigt", "Als erledigt markiert.") }, icon("check", "icon sm"), "Erledigt"),
            el("button", { type: "button", class: "text", onclick: () => setzen("ignoriert", "Ignoriert. Dieser Befund kommt nicht wieder.") }, "Ignorieren")]
          : el("button", { type: "button", class: "text", onclick: () => setzen("offen", "Wieder offen.") }, icon("undo", "icon sm"), "Wieder öffnen")));
    return node;
  };

  const pruefen = el("button", { type: "button" }, icon("search", "icon sm"), "Bestand jetzt prüfen");
  pruefen.addEventListener("click", async () => {
    pruefen.setAttribute("aria-disabled", "true");
    try {
      await api("/api/wissen/lauf?arten=pruefen", { method: "POST" });
      toast("Claude prüft deinen Bestand. Neue Punkte erscheinen hier in ein bis zwei Minuten.", { ms: 6000 });
    } catch (err) { pruefen.removeAttribute("aria-disabled"); toast(err.message, { fehler: true }); }
  });
  const zuletzt = wissen.laeufe.pruefen;
  render(grosserTitel("Pflege"),
    el("p", { class: "small muted", style: "margin:0 0 12px" }, "Einmal pro Woche sucht Claude nach Widersprüchen, veraltetem Wissen, unklaren und doppelten Einträgen und Lücken. Geändert wird nichts ohne dich."),
    seg,
    punkte.length ? punkte.map(karte) : leer({
      symbol: status === "offen" ? "check" : "inbox",
      titel: status === "offen" ? "Alles gepflegt" : "Nichts hier",
      text: status === "offen" ? "Gerade gibt es nichts zu tun." : "",
    }),
    el("div", { class: "card flat", style: "margin-top:20px" },
      el("p", { class: "footnote", style: "margin:0" }, zuletzt ? `Zuletzt geprüft ${relTime(zuletzt.zuletzt_am)}: ${zuletzt.ergebnis}.` : "Noch nie geprüft."),
      wissen.ki && !wissen.lauf.laeuft ? el("div", { class: "actions" }, pruefen) : null));
}

// ---------------------------------------------------------------- Wiederholen
const FRAGE = {
  erfahrung: "Was hast du daraus gelernt?",
  wissen: "Was ist der Kern?",
  vorgehen: "Wie gehst du vor?",
  entscheidung: "Wie hast du entschieden?",
};

/** Karteikarte: Kontext zeigen, selbst erinnern, aufdecken, ehrlich einschätzen. onFertig(ergebnis, antwort). */
export function wiederholKarte(l, { onFertig, kopfzeile = "Erinnerst du dich?", zusatz = null } = {}) {
  const karte = el("div", { class: "card wiederhol-karte" });
  const hinweis = (l.situation || "").trim() || (l.tags || []).join(", ");
  const antworten = async (ergebnis) => {
    karte.querySelectorAll("button").forEach((b) => b.setAttribute("aria-disabled", "true"));
    try {
      const r = await api(`/api/wiederholen/${l.id}`, { method: "POST", body: { ergebnis } });
      say(ergebnis === "parat" ? `Gut. Wieder in ${r.tage} Tagen.` : `Kommt in ${r.tage} Tagen wieder.`);
      onFertig?.(ergebnis, r);
    } catch (err) {
      karte.querySelectorAll("button").forEach((b) => b.removeAttribute("aria-disabled"));
      toast(err.message, { fehler: true });
    }
  };
  const ueberholt = async () => {
    try {
      await api(`/api/lessons/${l.id}`, { method: "PUT", body: { status: "überholt" } });
      toast("Als überholt markiert.", { aktion: { text: "Rückgängig", onclick: () => api(`/api/lessons/${l.id}`, { method: "PUT", body: { status: l.status } }).catch(() => {}) } });
      onFertig?.("ueberholt", null);
    } catch (err) { toast(err.message, { fehler: true }); }
  };
  const aufdecken = el("button", { type: "button", class: "primary block" }, "Aufdecken");
  fill(karte,
    el("div", { class: "card-head" }, el("p", { class: "overline grow" }, kopfzeile), zusatz),
    el("p", { class: "meta", style: "margin:0 0 8px" }, el("span", { class: `art art-${l.art}` }, artInfo(l.art).label), el("span", { class: "sep", "aria-hidden": "true" }), el("span", {}, l.bereich)),
    hinweis ? el("p", { class: "wiederhol-hinweis" }, anf(kuerzen(hinweis, 240))) : null,
    el("p", { class: "lead", style: "margin:10px 0 14px" }, FRAGE[l.art] || FRAGE.erfahrung),
    aufdecken);
  aufdecken.addEventListener("click", () => {
    aufdecken.replaceWith(el("div", { class: "aufgedeckt" },
      el("p", { style: "margin:0 0 6px;font-weight:600" }, el("a", { href: `#/lesson/${l.id}`, style: "color:inherit" }, anf(l.titel))),
      el("p", { class: `quote ${l.spezifisch ? "own" : ""}` }, anf(l.lesson)),
      l.massnahme ? el("p", { class: "small", style: "margin:8px 0 0" }, el("span", { class: "overline", style: "display:inline;margin-right:6px" }, artInfo(l.art).anwendung), anf(l.massnahme)) : null,
      el("div", { class: "actions wiederhol-knoepfe" },
        el("button", { type: "button", class: "primary", onclick: () => antworten("parat") }, icon("check", "icon sm"), "Wusste ich"),
        el("button", { type: "button", onclick: () => antworten("vergessen") }, "Hatte ich vergessen")),
      el("div", { class: "actions", style: "margin-top:4px" },
        el("a", { class: "button text", href: `#/lesson/${l.id}/bearbeiten` }, icon("pencil", "icon sm"), "Schärfen"),
        el("button", { type: "button", class: "text", onclick: ueberholt }, "Überholt"))));
    karte.querySelector(".wiederhol-knoepfe button")?.focus();
  });
  return karte;
}

export async function viewWiederholen() {
  const render = ansicht();
  kopf("Wiederholen", { text: "Wissen", href: "#/wissen" });
  if (!render(grosserTitel("Wiederholen"), skeleton())) return;
  fokusAufTitel();
  let data;
  try { data = await api("/api/wiederholen?limit=10"); }
  catch (err) { render(grosserTitel("Wiederholen"), errorNotice(err, { erneut: viewWiederholen })); return; }
  if (!render.aktiv()) return;
  if (!data.lessons.length) {
    render(grosserTitel("Wiederholen"), leer({ symbol: "check", titel: "Heute nichts zu wiederholen", text: "Einträge kommen erst nach einer Woche dazu und dann in wachsenden Abständen wieder." }));
    return;
  }
  const slot = el("div");
  const ergebnis = { parat: 0, vergessen: 0 };
  let i = 0;
  const weiter = () => {
    if (i >= data.lessons.length) {
      fill(slot, el("div", { class: "card hero", role: "status" },
        el("p", { class: "overline row", style: "gap:6px;color:var(--success)" }, icon("check", "icon sm"), "Runde fertig"),
        el("p", { class: "lead" }, `${ergebnis.parat} gewusst, ${ergebnis.vergessen} aufgefrischt.`),
        el("p", { class: "small muted", style: "margin:8px 0 0" }, "Was du wusstest, kommt erst in Wochen wieder. Was du vergessen hattest, schon in zwei Tagen."),
        el("div", { class: "actions" }, el("button", { type: "button", class: "primary", onclick: viewWiederholen }, "Noch eine Runde"), el("a", { class: "button", href: "#/wissen" }, "Fertig"))));
      say("Runde fertig.");
      return;
    }
    const l = data.lessons[i];
    fill(slot, wiederholKarte(l, {
      kopfzeile: `${i + 1} von ${data.lessons.length}`,
      onFertig: (e) => { if (e in ergebnis) ergebnis[e] += 1; i += 1; weiter(); },
    }));
  };
  render(grosserTitel("Wiederholen"),
    el("p", { class: "small muted", style: "margin:0 0 12px" }, data.stand.faellig ? `${data.stand.faellig} fällig. ` : "", "Erst selbst erinnern, dann aufdecken. Ehrlich einschätzen: Was du wusstest, kommt seltener wieder."),
    slot);
  weiter();
}

// ---------------------------------------------------------------- Verbindungen im Eintrag
async function verbindenDialog(l, neuLaden) {
  const suchtext = await eingabe({ titel: "Mit Eintrag verbinden", text: "Nach welchem Eintrag suchst du?", label: "Suchbegriff", ok: "Suchen" });
  if (!suchtext) return;
  let treffer;
  try { treffer = (await api(`/api/suche?q=${encodeURIComponent(suchtext)}&limit=6`)).filter((t) => t.lesson.id !== l.id); }
  catch (err) { toast(err.message, { fehler: true }); return; }
  if (!treffer.length) { toast("Nichts gefunden."); return; }
  aktionsblatt("Welcher Eintrag?", treffer.map(({ lesson: z }) => ({
    text: kuerzen(z.titel, 60),
    onclick: () => aktionsblatt(`„${kuerzen(l.titel, 40)}“ …`, Object.entries(BEZIEHUNG).map(([art, b]) => ({
      text: `${b.aus} „${kuerzen(z.titel, 34)}“`, icon: b.icon,
      onclick: async () => {
        try { await api(`/api/lessons/${l.id}/beziehungen`, { method: "POST", body: { zu_id: z.id, art } }); toast("Verbunden."); neuLaden(); }
        catch (err) { toast(err.message, { fehler: true }); }
      },
    }))),
  })));
}

/** Abschnitt "Verbindungen" und Themen für die Detailansicht eines Eintrags. */
export function verbindungenAbschnitt(l, data, neuLaden) {
  const bez = data.beziehungen || [];
  const themen = data.themen || [];
  const ueberholtSetzen = async (ziel) => {
    if (!(await bestaetigen({ titel: "Als überholt markieren?", text: `„${kuerzen(ziel.titel, 70)}“ bleibt sichtbar, erscheint aber nicht mehr in Briefings.`, ok: "Markieren" }))) return;
    try { await api(`/api/lessons/${ziel.id}`, { method: "PUT", body: { status: "überholt" } }); toast("Als überholt markiert."); neuLaden(); }
    catch (err) { toast(err.message, { fehler: true }); }
  };
  const zeile = (b) => {
    const text = BEZIEHUNG[b.art]?.[b.richtung] || b.art;
    // Ersetzt: der ältere Eintrag ist vermutlich überholt, ein Tipp erledigt das
    const altes = b.art === "ersetzt" ? (b.richtung === "aus" ? { id: b.id, titel: b.titel, status: b.status } : { id: l.id, titel: l.titel, status: l.status }) : null;
    return el("li", { class: "verbindung" },
      el("span", { class: "bez-punkt", style: `background:${BEZ_FARBEN[b.art]}`, "aria-hidden": "true" }),
      el("span", { class: "grow" },
        el("span", { class: "li-sub" }, text),
        el("a", { href: `#/lesson/${b.id}`, class: b.status === "überholt" ? "durch" : "" }, anf(b.titel)),
        b.begruendung ? el("span", { class: "li-sub" }, anf(b.begruendung)) : null,
        altes && altes.status !== "überholt" ? el("button", { type: "button", class: "text", style: "padding:4px 0", onclick: () => ueberholtSetzen(altes) },
          icon("clock", "icon sm"), b.richtung === "aus" ? "Alten Eintrag als überholt markieren" : "Diesen Eintrag als überholt markieren") : null),
      el("button", {
        type: "button", class: "icon-btn", "aria-label": `Verbindung zu „${kuerzen(b.titel, 40)}“ lösen`,
        onclick: async () => {
          try { await api(`/api/lessons/${l.id}/beziehungen/${b.id}`, { method: "DELETE" }); toast("Verbindung gelöst."); neuLaden(); }
          catch (err) { toast(err.message, { fehler: true }); }
        },
      }, icon("x", "icon sm")));
  };
  return el("section", {},
    themen.length ? el("p", { class: "themen-chips" }, el("span", { class: "overline", style: "display:inline;margin-right:8px" }, "Themen"),
      themen.map((t) => el("a", { class: "chip", href: `#/thema/${t.id}` }, anf(t.titel)))) : null,
    el("h2", { class: "row", style: "gap:8px" }, icon("network"), "Verbindungen"),
    bez.length ? el("ul", { class: "list verbindungen" }, bez.map(zeile))
      : el("p", { class: "footnote", style: "margin-top:0" }, "Noch keine. Claude erkennt sie beim Erfassen; du kannst auch selbst verbinden."),
    el("button", { type: "button", class: "text", onclick: () => verbindenDialog(l, neuLaden) }, icon("plus", "icon sm"), "Mit Eintrag verbinden"));
}

/** Kurzer Hinweis auf erkannte Verbindungen im Entwurf (vor dem Sichern). */
export function entwurfVerbindungen(e) {
  const bez = e?.beziehungen || [];
  if (!bez.length) return null;
  return el("div", { class: "entwurf-verbindungen" },
    el("p", { class: "overline row", style: "gap:6px;margin:14px 0 4px" }, icon("network", "icon sm"), "Hängt zusammen mit"),
    el("ul", {}, bez.map((b) => el("li", {},
      el("span", { class: "bez-punkt", style: `background:${BEZ_FARBEN[b.art]}`, "aria-hidden": "true" }),
      el("span", {}, `${BEZIEHUNG[b.art]?.aus || b.art} `, el("a", { href: `#/lesson/${b.id}` }, anf(b.titel)),
        b.begruendung ? el("span", { class: "li-sub" }, anf(b.begruendung)) : null)))),
    el("p", { class: "footnote", style: "margin:4px 0 0" }, "Wird beim Sichern als Verbindung gespeichert."));
}

