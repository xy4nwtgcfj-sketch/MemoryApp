// Mehr (Übersicht mit Unterseiten), Fortschritt und Zugang.
import {
  MEILENSTEINE, PUNKTE, ansicht, statsAnzeigen, wochenziel, zaehlerStand, api, bereiche, bereicheVergessen, copyText, debounce, el, errorNotice, fill, fokusAufTitel,
  grosserTitel, herunterladen, icon, kopf, refreshStats, ring, say, skeleton, state, status, store, toast,
} from "./core.js";

const SCHRIFTEN = ["Calibri", "Open Sans", "Arial", "Segoe UI", "Georgia", "Verdana"];
const hell = (hex) => { const n = parseInt(hex.slice(1), 16); return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) > 160; };
const nf = new Intl.NumberFormat("de-DE");

const STUFEN = [
  ["lokal", "Nur lokal", "lock"],
  ["text", "Text an Claude", "cloud"],
  ["foto", "Claude mit Foto", "image"],
];

// Unterseiten von "Mehr": Titel und Route
const TEILE = {
  bereiche: "Bereiche und Datenschutz",
  erinnerungen: "Erinnerungen und Kurzbefehl",
  sperrliste: "Sperrliste",
  bestand: "Bestand",
  erweitert: "Erweitert",
};

// ---------------------------------------------------------------- Erscheinungsbild
// Dunkel ist Standard ("" oder das frühere "dark"); "light" erzwingt Hell, "system" folgt dem Gerät.
export function themaAnwenden(wert) {
  const t = wert === "light" || wert === "system" ? wert : "";
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  const hellAktiv = t === "light" || (t === "system" && matchMedia("(prefers-color-scheme: light)").matches);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", hellAktiv ? "#f3f4f7" : "#0b0d12");
}
matchMedia("(prefers-color-scheme: light)").addEventListener?.("change", () => themaAnwenden(store.get("lv-theme", "")));

function stufeVon(b, einst) {
  const std = einst.strukturierung_standard;
  const ueber = einst.strukturierung_bereiche[b.name] ?? (std === "lokal" || std === "manuell" ? std : null);
  if (ueber === "lokal" || ueber === "manuell") return "lokal";
  const bild = einst.bild_bereiche[b.name] || (b.beruflich ? "text" : "bild");
  return bild === "bild" && !b.beruflich ? "foto" : "text";
}

async function ladeDaten() {
  const [st, s, bereichListe, einst] = await Promise.all([status(true), refreshStats(), bereiche(true), api("/api/einstellungen")]);
  let marken = {};
  try { marken = await api("/api/marken"); } catch { marken = {}; }
  return { st, s: s || await api("/api/statistik"), bereichListe, einst, marken };
}

// ---------------------------------------------------------------- Mehr und Unterseiten
export async function viewEinstellungen(teil = "") {
  const render = ansicht();
  const titel = TEILE[teil] || "Mehr";
  kopf(titel, teil ? { text: "Mehr", href: "#/einstellungen" } : null);
  if (!render(grosserTitel(titel), skeleton())) return;
  fokusAufTitel();

  let daten;
  try {
    daten = await ladeDaten();
  } catch (err) {
    render(grosserTitel(titel), errorNotice(err, { erneut: () => viewEinstellungen(teil) }), zugangKarte());
    return;
  }
  if (!render.aktiv()) return;
  const { st, s, bereichListe, einst, marken } = daten;

  const speichern = async (body) => {
    const res = await api("/api/einstellungen", { method: "PUT", body });
    Object.assign(einst, res);
    status(true).then((neu) => { daten.st = neu; }).catch(() => {});
    say("Gespeichert.");
    return res;
  };

  const abschnitt = {
    bereiche: () => bereicheSection({ st, bereichListe, einst, marken, speichern }),
    erinnerungen: () => erinnerungenSection(),
    sperrliste: () => sperrSection({ einst, speichern }),
    bestand: () => bestandSection(),
    erweitert: () => erweitertSection({ st, einst, speichern }),
  }[teil];
  if (abschnitt) {
    render(grosserTitel(titel), abschnitt());
    return;
  }

  // Übersicht: Fortschritt, Arbeiten, Bereiche, Einstellungen
  const z = zaehlerStand(s);
  const pk = z.punkte;
  const aktive = bereichListe.filter((b) => b.aktiv).map((b) => b.name);
  const thema = store.get("lv-theme", "");
  const themaWert = thema === "light" || thema === "system" ? thema : "";
  const themaSeg = el("div", { class: "segmented", role: "group", "aria-label": "Erscheinungsbild", style: "max-width:260px" },
    [["", "Dunkel"], ["light", "Hell"], ["system", "System"]].map(([v, t]) => el("button", {
      type: "button", "aria-pressed": String(themaWert === v),
      onclick: (e) => {
        store.set("lv-theme", v);
        themaAnwenden(v);
        e.currentTarget.parentElement.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget)));
        say(`${t} gewählt.`);
      },
    }, t)));
  const zeile = (href, sym, text, sub, { klasse = "", rechts = null } = {}) => el("li", { style: "padding:0" },
    el("a", { class: "li grow", href },
      el("span", { class: `ic ${klasse}` }, icon(sym)),
      el("span", { class: "grow" }, el("span", { style: "display:block;font-weight:500" }, text), sub ? el("span", { class: "li-sub" }, sub) : null),
      rechts || icon("chevron-right", "icon sm chev")));
  const rueckschauSlot = el("span", { class: "li-sub" }, "Briefings ohne Abgleich");
  api("/api/briefings?limit=20").then((liste) => {
    const offen = liste.filter((b) => b.plan && !b.rueckschau).length;
    rueckschauSlot.textContent = offen ? `${offen} ${offen === 1 ? "Briefing" : "Briefings"} ohne Abgleich` : "Alle Pläne abgeglichen";
  }).catch(() => {});

  render(grosserTitel("Mehr"),
    el("a", { class: "card level-karte", href: "#/fortschritt", style: "padding:14px 16px;gap:14px;color:inherit;text-decoration:none;background:linear-gradient(135deg, var(--own-tint), var(--surface) 60%)" },
      el("span", { class: "zaehler-ring" }, ring(pk.anteil, 52, false, "gross"), el("span", { class: "zaehler-zahl", style: "color:var(--own);font-size:1.0625rem" }, String(pk.level))),
      el("span", { class: "grow" },
        el("span", { class: "level-name", style: "display:block;font-size:1.0625rem" }, `${pk.name} · ${nf.format(pk.xp)} Punkte`),
        el("span", { class: "li-sub" }, `${z.gesamt} Einträge · ${z.erreicht ? "Wochenziel erreicht" : `Wochenziel ${z.diese} von ${z.ziel}`}${z.serie ? ` · ${z.serie} ${z.serie === 1 ? "Woche" : "Wochen"} in Folge` : ""}`)),
      icon("chevron-right", "icon sm chev")),
    el("p", { class: "overline", style: "margin:20px 4px 8px" }, "Arbeiten"),
    el("ul", { class: "list" },
      zeile("#/eingang", "inbox", "Eingang", s.offene_entwuerfe ? `${s.offene_entwuerfe} ${s.offene_entwuerfe === 1 ? "Entwurf wartet" : "Entwürfe warten"}` : "Nichts offen",
        { rechts: s.offene_entwuerfe ? el("span", { class: "zahl" }, String(s.offene_entwuerfe)) : null }),
      el("li", { style: "padding:0" }, el("a", { class: "li grow", href: "#/briefing" }, el("span", { class: "ic gruen" }, icon("refresh")),
        el("span", { class: "grow" }, el("span", { style: "display:block;font-weight:500" }, "Offene Rückschauen"), rueckschauSlot), icon("chevron-right", "icon sm chev"))),
      zeile("#/ernte", "sprout", "Startbestand mit Fragen", s.gesamt < 20 ? `${Math.min(20, s.gesamt + s.offene_entwuerfe)} von 20` : "Fragenkatalog je Bereich"),
      el("li", {}, el("span", { class: "ic" }, icon("calendar")), el("span", { class: "grow" }, el("span", { style: "display:block;font-weight:500" }, "Wochenrückblick"), el("span", { class: "li-sub" }, "Freitags 16:30 als Serie im Kalender")),
        el("a", { class: "button text", href: "wochenrueckblick.ics", download: "wochenrueckblick.ics" }, "Eintragen"))),
    el("p", { class: "overline", style: "margin:20px 4px 8px" }, "Einstellungen"),
    el("ul", { class: "list" },
      zeile("#/einstellungen/bereiche", "shield", "Bereiche und Datenschutz", aktive.length ? `${aktive.join(", ")} aktiv` : "Kein Bereich aktiv", { klasse: "akzent" }),
      zeile("#/einstellungen/sperrliste", "lock", "Sperrliste", `${einst.sperrliste.length} ${einst.sperrliste.length === 1 ? "Begriff" : "Begriffe"}, die nie an Claude gehen`),
      zeile("#/einstellungen/erinnerungen", "phone", "Erinnerungen und Kurzbefehl", "„Lesson merken“ ohne die App zu öffnen"),
      zeile("#/einstellungen/bestand", "download", "Bestand", "Importieren und exportieren"),
      zeile("#/einstellungen/erweitert", "sliders", "Erweitert", st.ki ? `Claude eingerichtet (${st.modell})` : "Claude nicht eingerichtet"),
      el("li", { class: "li-col", style: "gap:8px" },
        el("span", { style: "font-weight:500" }, "Erscheinungsbild"), themaSeg)),
    el("p", { class: "footnote", style: "margin:16px 4px 0" }, `Lessons Vault ${st.version} · Daten bleiben auf deinem PC`));
}

// ---------------------------------------------------------- Bereiche und Datenschutz
function bereicheSection({ st, bereichListe, einst, marken, speichern }) {
  const ohneClaude = !st.ki;
  const bereichZeile = (b) => {
    const li = el("li", { class: "li li-col", style: "gap:10px" });
    const zeichnen = () => {
      const aktivId = `aktiv-${b.name}`;
      const berufId = `beruf-${b.name}`;
      const stufe = stufeVon(b, einst);
      const aktiv = el("input", { type: "checkbox", role: "switch", class: "switch", id: aktivId, checked: b.aktiv });
      aktiv.addEventListener("change", async () => {
        try { Object.assign(b, await api(`/api/bereiche/${encodeURIComponent(b.name)}`, { method: "PATCH", body: { aktiv: aktiv.checked } })); bereicheVergessen(); say(aktiv.checked ? `${b.name} aktiv.` : `${b.name} ausgeblendet.`); zeichnen(); li.querySelector(`#${CSS.escape(aktivId)}`)?.focus(); }
        catch (err) { aktiv.checked = !aktiv.checked; toast(err.message, { fehler: true }); }
      });
      const seg = el("div", { class: "segmented", role: "group", "aria-label": `Datenschutz-Stufe ${b.name}` }, STUFEN.map(([wert, text, sym]) => el("button", {
        type: "button",
        "aria-pressed": String(stufe === wert),
        disabled: wert === "foto" && b.beruflich ? true : null,
        title: wert === "foto" && b.beruflich ? "Berufliche Fotos gehen nie als Bild an Claude" : null,
        onclick: async (e) => {
          const strukt = { ...einst.strukturierung_bereiche };
          const bild = { ...einst.bild_bereiche };
          if (wert === "lokal") strukt[b.name] = "lokal";
          else {
            // Mit Standard "Automatisch" entscheidet die App (Claude, falls eingerichtet); sonst ausdrücklich Claude.
            if (["auto", "claude"].includes(einst.strukturierung_standard)) delete strukt[b.name]; else strukt[b.name] = "claude";
            bild[b.name] = wert === "foto" ? "bild" : "text";
          }
          try {
            await speichern({ strukturierung_bereiche: strukt, bild_bereiche: bild });
            zeichnen();
            li.querySelectorAll(".segmented button")[STUFEN.findIndex((x) => x[0] === wert)]?.focus();
          } catch (err) { toast(err.message, { fehler: true }); e.currentTarget.blur(); }
        },
      }, icon(sym, "icon sm"), text)));
      const beruf = el("input", { type: "checkbox", role: "switch", class: "switch", id: berufId, checked: b.beruflich });
      beruf.addEventListener("change", async () => {
        try { Object.assign(b, await api(`/api/bereiche/${encodeURIComponent(b.name)}`, { method: "PATCH", body: { beruflich: beruf.checked } })); bereicheVergessen(); say("Gespeichert."); zeichnen(); li.querySelector(`#${CSS.escape(berufId)}`)?.focus(); }
        catch (err) { beruf.checked = !beruf.checked; toast(err.message, { fehler: true }); }
      });
      const erklaerung = {
        lokal: st.lokal?.konfiguriert ? "Geht nie an Claude. Dein PC strukturiert im Hintergrund." : "Geht nie an Claude. Ohne lokales Modell füllst du selbst aus.",
        text: "Text geht nach der Namensprüfung an Claude. Fotos werden auf dem PC gelesen, nur der geprüfte Text geht raus.",
        foto: "Text und Fotos gehen an Claude.",
      }[stufe];
      // Eingeklappt zeigt jede Zeile nur Name, Schalter und die aktuelle Stufe; Details nur auf Wunsch.
      // Ohne Claude gibt es nichts zu wählen, daher entfällt die Stufenwahl ganz (Hinweis steht einmal oben).
      const stufenText = ohneClaude ? "Bleibt auf dem PC" : STUFEN.find((x) => x[0] === stufe)?.[1] || "";
      const offen = li.querySelector("details")?.open || false;
      fill(li,
        el("div", { class: "row" },
          el("label", { for: aktivId, class: "grow", style: "margin:0;color:var(--text);font-size:1rem" }, b.name, el("span", { class: "li-sub" }, b.beispiele)),
          aktiv),
        b.aktiv ? el("details", { class: "bereich-details", open: offen || null },
          el("summary", {}, `${stufenText}${b.beruflich ? " · beruflich" : ""}`),
          el("div", { class: "stack" },
            ohneClaude ? null : [seg, el("p", { class: "footnote", style: "margin:0" }, erklaerung)],
            el("div", { class: "row" },
              el("label", { for: berufId, class: "grow", style: "margin:0;font-weight:500;color:var(--text)" }, "Beruflich", el("span", { class: "li-sub" }, "Strengere Prüfung auf Namen und Zahlen, Fotos nie als Bild")),
              beruf),
            markeBlock(b))) : null);
    };
    zeichnen();
    return li;
  };

  // Folien-Marke: Name, Farben, Schrift und Logo für die PowerPoint-Ausgabe von Briefings dieses Bereichs
  const markeBlock = (b) => {
    const m = { name: "", untertitel: "", farbe: "#1F3A5F", akzent: "#D9A441", stil: "dunkel", hintergrund: "#F4F1E9", schrift: "Calibri", schrift_titel: "", logo: false, ...(marken[b.name] || einst.marken?.[b.name] || {}) };
    const id = (f) => `marke-${f}-${b.name}`;
    const probe = el("div", { class: "marke-probe" });
    const probeZeichnen = () => {
      const grund = m.stil === "hell" ? m.hintergrund : m.farbe;
      probe.style.background = grund;
      probe.style.color = m.stil === "hell" ? m.farbe : (hell(m.farbe) ? "#1a1d21" : "#ffffff");
      fill(probe, el("span", { class: "strich", style: `background:${m.akzent}` }),
        el("span", { style: `font-family:'${m.schrift_titel || m.schrift}',serif;letter-spacing:${m.stil === "hell" ? ".08em" : "0"}` }, m.name || "Ohne Marke"),
        el("span", { style: "margin-left:auto;font-weight:400;font-size:.8125rem;opacity:.85" }, "Titelfolie"));
      hintergrundFeld.hidden = m.stil !== "hell";
    };
    const sichern = debounce(async () => {
      try {
        const { logo, ...werte } = m;
        await speichern({ marken: { ...einst.marken, [b.name]: werte } });
        marken[b.name] = { ...m };
      } catch (err) { toast(err.message, { fehler: true }); }
    }, 600);
    const feld = (f, label, { typ = "text", max = 60, voll = false } = {}) => el("div", { class: voll ? "voll" : "" },
      el("label", { for: id(f) }, label),
      el("input", { id: id(f), type: typ, value: m[f], maxlength: max, oninput: (e) => { m[f] = e.target.value; probeZeichnen(); sichern(); } }));
    const schrift = el("select", { id: id("schrift"), onchange: (e) => { m.schrift = e.target.value; probeZeichnen(); sichern(); } },
      SCHRIFTEN.map((sName) => el("option", { value: sName, selected: m.schrift === sName ? "" : null }, sName)));
    const schriftTitel = el("select", { id: id("schrift_titel"), onchange: (e) => { m.schrift_titel = e.target.value; probeZeichnen(); sichern(); } },
      [["", "Wie Fließtext"], ...SCHRIFTEN.map((sName) => [sName, sName])].map(([v, t]) => el("option", { value: v, selected: (m.schrift_titel || "") === v ? "" : null }, t)));
    const stilSeg = el("div", { class: "segmented", role: "group", "aria-label": "Stil der Titelfolie" }, [["dunkel", "Dunkel: Hauptfarbe als Grund, Logo klein"], ["hell", "Hell: heller Grund, Wortmarke, Illustration groß"]].map(([v, t]) => el("button", {
      type: "button", "aria-pressed": String(m.stil === v), title: t,
      onclick: (e) => { m.stil = v; e.currentTarget.parentElement.querySelectorAll("button").forEach((k) => k.setAttribute("aria-pressed", String(k === e.currentTarget))); probeZeichnen(); sichern(); },
    }, v === "dunkel" ? "Dunkel" : "Hell")));
    const hintergrundFeld = el("div", {}, el("label", { for: id("hintergrund") }, "Grund der Titelfolie"),
      el("input", { id: id("hintergrund"), type: "color", value: m.hintergrund, oninput: (e) => { m.hintergrund = e.target.value; probeZeichnen(); sichern(); } }));
    const logoSlot = el("div", { style: "margin-top:8px" });
    const datei = el("input", { type: "file", accept: "image/png,image/jpeg", class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
    datei.addEventListener("change", async () => {
      if (!datei.files.length) return;
      const form = new FormData();
      form.append("datei", datei.files[0], datei.files[0].name);
      datei.value = "";
      try {
        await api(`/api/marken/${encodeURIComponent(b.name)}/logo`, { method: "POST", body: form, timeoutMs: 60000 });
        m.logo = true;
        say("Logo gespeichert.");
        logoZeichnen();
      } catch (err) { toast(err.message, { fehler: true }); }
    });
    const logoZeichnen = () => {
      const bild = m.logo ? el("img", { class: "logo-vorschau", alt: `Logo ${b.name}` }) : null;
      if (bild) api(`/api/marken/${encodeURIComponent(b.name)}/logo`, { raw: true }).then((r) => r.blob()).then((blob) => { bild.src = URL.createObjectURL(blob); }).catch(() => bild.remove());
      fill(logoSlot,
        el("p", { class: "overline", style: "margin:0" }, "Logo"),
        bild,
        el("div", { class: "row", style: "gap:8px;flex-wrap:wrap;margin-top:6px" },
          el("button", { type: "button", onclick: () => datei.click() }, icon("upload", "icon sm"), m.logo ? "Logo ersetzen" : "Logo hochladen (PNG)"),
          m.logo ? el("button", { type: "button", class: "text", onclick: async () => {
            try { await api(`/api/marken/${encodeURIComponent(b.name)}/logo`, { method: "DELETE" }); m.logo = false; say("Logo entfernt."); logoZeichnen(); }
            catch (err) { toast(err.message, { fehler: true }); }
          } }, "Entfernen") : null),
        el("p", { class: "footnote", style: "margin:4px 0 0" }, m.stil === "hell" ? "Erscheint als große Illustration auf der Titelfolie. Bleibt auf dem PC." : "Erscheint oben rechts auf jeder Folie und auf der Titelfolie. Bleibt auf dem PC."));
    };
    probeZeichnen();
    logoZeichnen();
    return el("details", { class: "marke" },
      el("summary", {}, el("span", { style: "font-weight:500" }, "Folien-Marke"), el("span", { class: "li-sub" }, m.name ? `${m.name} · ${m.schrift}` : "Neutral (Navy und Gold)")),
      el("div", { class: "marke-felder" },
        feld("name", "Name", { voll: true }),
        feld("untertitel", "Untertitel auf der Titelfolie", { max: 120, voll: true }),
        el("div", { class: "voll" }, el("p", { class: "label", style: "margin:0 0 4px;font-size:.875rem" }, "Stil"), stilSeg),
        feld("farbe", "Hauptfarbe", { typ: "color" }),
        feld("akzent", "Akzentfarbe", { typ: "color" }),
        hintergrundFeld,
        el("div", {}, el("label", { for: id("schrift") }, "Schrift Fließtext"), schrift),
        el("div", {}, el("label", { for: id("schrift_titel") }, "Schrift Überschriften"), schriftTitel)),
      probe, logoSlot, datei);
  };
  const neuerBereich = el("input", { type: "text", id: "neuer-bereich", placeholder: "Neuer Bereich" });
  const bereicheListe = el("ul", { class: "list" }, bereichListe.map(bereichZeile));
  return el("section", {},
    el("p", { class: "small muted", style: "margin-top:-8px" }, "Pro Bereich legst du fest, was an Claude gehen darf. Fokus schlägt Vollständigkeit: Lass anfangs nur zwei Bereiche aktiv. Die Folien-Marke für PowerPoint steht bei jedem Bereich."),
    ohneClaude ? el("div", { class: "notice info" }, icon("lock"), el("div", {},
      el("strong", {}, "Claude ist nicht eingerichtet."),
      "Alles bleibt auf deinem PC. Die Wahl, was an Claude gehen darf, erscheint hier, sobald ein API-Key in der .env steht.")) : null,
    bereicheListe,
    el("div", { class: "row" },
      el("div", { class: "grow" }, el("label", { for: "neuer-bereich", class: "sr-only" }, "Neuer Bereich"), neuerBereich),
      el("button", {
        type: "button",
        onclick: async () => {
          const name = neuerBereich.value.trim();
          if (!name) { neuerBereich.focus(); return; }
          try {
            const b = await api("/api/bereiche", { method: "POST", body: { name, aktiv: true } });
            bereicheVergessen();
            bereicheListe.append(bereichZeile(b));
            neuerBereich.value = "";
            say(`${name} angelegt.`);
          } catch (err) { toast(err.message, { fehler: true }); }
        },
      }, icon("plus", "icon sm"), "Anlegen")));
}

// ---------------------------------------------------------- Erinnerungen und Kurzbefehl
function erinnerungenSection() {
  const url = `${location.origin}/api/notiz`;
  const token = store.get("lv-token");
  return el("section", {},
    el("ul", { class: "list" },
      el("li", {}, el("span", { class: "ic" }, icon("calendar")), el("span", { class: "grow" }, el("span", { style: "display:block;font-weight:500" }, "Wochenrückblick"), el("span", { class: "li-sub" }, "Freitags 16:30, 10 Minuten, als Serie in deinem Kalender")),
        el("a", { class: "button text", href: "wochenrueckblick.ics", download: "wochenrueckblick.ics" }, "Eintragen"))),
    el("div", { class: "card" },
      el("p", { class: "row", style: "margin:0;font-weight:600;gap:8px" }, icon("phone"), "iPhone-Kurzbefehl „Lesson merken“"),
      el("p", { class: "small", style: "margin:8px 0" }, "Damit hältst du eine Lesson in unter 10 Sekunden fest, ohne die App zu öffnen: per Siri, Action-Taste, Sperrbildschirm oder Rückseite antippen. Die Notiz landet strukturiert im Eingang."),
      el("ol", { class: "small", style: "padding-left:20px;margin:0" },
        el("li", {}, "App Kurzbefehle öffnen, neuen Kurzbefehl anlegen."),
        el("li", {}, "Aktion „Text diktieren“ hinzufügen (Sprache Deutsch)."),
        el("li", {}, "Aktion „Inhalte von URL abrufen“: URL unten einfügen, Methode POST, Header ", el("code", {}, "Authorization"), " mit Wert ", el("code", {}, "Bearer …Token…"), ", Anfragetext JSON mit Feld ", el("code", {}, "text"), " = Diktierter Text und Feld ", el("code", {}, "quelle"), " = ", el("code", {}, "sprache"), "."),
        el("li", {}, "Optional „Mitteilung anzeigen“: Gesichert."),
        el("li", {}, "Name „Lesson merken“. Unter Einstellungen > Bedienungshilfen > Tippen > Auf Rückseite tippen oder auf der Action-Taste ablegen.")),
      el("p", { class: "small", style: "margin:12px 0 0" }, "Tipp: Eine persönliche Automation in Kurzbefehle („Uhrzeit“, Freitag 16:30 oder täglich 17:30) kann denselben Kurzbefehl starten und fragt dich dann nach deiner Lesson."),
      el("div", { class: "actions" },
        el("button", { type: "button", onclick: async () => toast((await copyText(url)) ? "Adresse kopiert." : "Kopieren nicht möglich.") }, icon("copy", "icon sm"), "Adresse kopieren"),
        token ? el("button", { type: "button", onclick: async () => toast((await copyText(`Bearer ${token}`)) ? "Header-Wert kopiert." : "Kopieren nicht möglich.") }, icon("copy", "icon sm"), "Header-Wert kopieren") : null),
      el("p", { class: "footnote", style: "margin:0" }, el("code", {}, url))));
}

// ---------------------------------------------------------- Sperrliste
function sperrSection({ einst, speichern }) {
  const sperrliste = el("textarea", { id: "sperrliste", rows: 8, placeholder: "Ein Begriff pro Zeile, z. B. Kundennamen, Standorte, Systemnamen" });
  sperrliste.value = einst.sperrliste.join("\n");
  return el("section", {},
    el("div", { class: "card" },
      el("label", { for: "sperrliste", style: "margin-top:0" }, "Begriffe, die nie an Claude gehen"),
      sperrliste,
      el("p", { class: "hint" }, "Treffer blockieren das Senden immer. Die Liste bleibt auf deinem PC."),
      el("div", { class: "actions", style: "margin-bottom:0" }, el("button", {
        type: "button", class: "primary",
        onclick: async () => {
          try { const res = await speichern({ sperrliste: sperrliste.value.split("\n") }); sperrliste.value = res.sperrliste.join("\n"); toast("Sperrliste gesichert."); }
          catch (err) { toast(err.message, { fehler: true }); }
        },
      }, "Sichern"))));
}

// ---------------------------------------------------------- Bestand
function bestandSection() {
  const fileInput = el("input", { type: "file", accept: "application/json,.json", id: "import-file", class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
  const importErgebnis = el("div", { role: "status" });
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    try {
      const res = await api("/api/import", { method: "POST", body: JSON.parse(await file.text()) });
      fill(importErgebnis, el("div", { class: res.fehler.length ? "notice warn" : "notice ok" }, icon(res.fehler.length ? "alert" : "check"),
        el("div", {}, `${res.importiert} importiert, ${res.uebersprungen} übersprungen.`, res.fehler.length ? el("ul", {}, res.fehler.slice(0, 5).map((f) => el("li", {}, f))) : null)));
      refreshStats();
    } catch (err) {
      fill(importErgebnis, errorNotice(err instanceof SyntaxError ? new Error("Die Datei ist kein gültiges JSON.") : err));
    } finally {
      fileInput.value = "";
    }
  });
  return el("section", {},
    el("ul", { class: "list" },
      el("li", { style: "padding:0" }, el("a", { class: "li grow", href: "#/ernte" }, el("span", { class: "ic akzent" }, icon("sprout")), el("span", { class: "grow" }, "Startbestand mit Fragen anlegen"), icon("chevron-right", "icon sm chev"))),
      el("li", {}, el("span", { class: "ic" }, icon("upload")), el("span", { class: "grow" }, "Importieren", el("span", { class: "li-sub" }, "Startbestand oder Backup als JSON (Vorlage: startbestand/vorlage.json)")),
        el("button", { type: "button", class: "text", onclick: () => fileInput.click() }, "Datei wählen"), fileInput),
      el("li", {}, el("span", { class: "ic" }, icon("download")), el("span", { class: "grow" }, "Exportieren", el("span", { class: "li-sub" }, "Alle Einträge als JSON")),
        el("button", {
          type: "button", class: "text",
          onclick: async () => {
            try { const res = await api("/api/export", { raw: true }); herunterladen(`lessons-vault-${new Date().toISOString().slice(0, 10)}.json`, await res.blob()); }
            catch (err) { toast(err.message, { fehler: true }); }
          },
        }, "Sichern"))),
    importErgebnis);
}

// ---------------------------------------------------------- Erweitert
function erweitertSection({ st, einst, speichern }) {
  const optionen = [["auto", "Automatisch"], ["claude", "Claude"], ["lokal", "Lokal"], ["manuell", "Ohne KI"]];
  const standard = el("select", { id: "ki-standard" }, optionen.map(([v, t]) => el("option", { value: v, selected: einst.strukturierung_standard === v }, t)));
  standard.addEventListener("change", async () => { try { await speichern({ strukturierung_standard: standard.value }); } catch (err) { toast(err.message, { fehler: true }); } });
  const l = st.lokal || {};
  const lokalInfo = !l.konfiguriert ? "nicht eingerichtet (LV_OLLAMA_MODEL leer)"
    : !l.erreichbar ? "Ollama nicht erreichbar" : l.modell_installiert ? `${l.modell}, bereit` : `${l.modell} fehlt: ollama pull ${l.modell}`;
  const embeddingInfo = st.embeddings.startsWith("ollama:") ? `${st.embeddings} (lokal, Bedeutung)` : st.semantisch ? `${st.embeddings} (Cloud, Bedeutung)` : `${st.embeddings} (nur Wortähnlichkeit; für Suche nach Bedeutung VOYAGE_API_KEY oder Ollama einrichten)`;
  return el("section", {},
    el("div", { class: "card" },
      el("label", { for: "ki-standard", style: "margin-top:0" }, "Strukturierung ohne Bereichswahl"),
      standard,
      el("p", { class: "hint" }, "Automatisch: Claude, wenn eingerichtet, sonst lokal, sonst ohne KI. Ist irgendein Bereich lokal, geht ohne Bereichswahl nichts an Claude.")),
    el("div", { class: "card" },
      el("dl", { class: "fields", style: "margin:0" },
        el("dt", { style: "margin-top:0" }, "Claude"), el("dd", {}, st.ki ? `eingerichtet (${st.modell})` : "nicht eingerichtet, ANTHROPIC_API_KEY fehlt"),
        el("dt", {}, "Lokales Modell"), el("dd", {}, lokalInfo),
        el("dt", {}, "Texterkennung für Fotos"), el("dd", {}, st.texterkennung?.verfuegbar ? "Tesseract eingerichtet" : st.texterkennung?.hinweis || "nicht verfügbar"),
        el("dt", {}, "Suchindex"), el("dd", {}, embeddingInfo),
        el("dt", {}, "Version"), el("dd", {}, st.version)),
      el("div", { class: "actions", style: "margin-bottom:0" }, el("button", {
        type: "button",
        onclick: async (e) => {
          const b = e.currentTarget;
          b.setAttribute("aria-disabled", "true");
          try { const r = await api("/api/reindex", { method: "POST" }); toast(`${r.neu_indexiert} Einträge neu indexiert.`); }
          catch (err) { toast(err.message, { fehler: true }); }
          finally { b.removeAttribute("aria-disabled"); }
        },
      }, icon("refresh", "icon sm"), "Suchindex neu aufbauen"))),
    el("div", { class: "card" }, zugangKarte()));
}

// ---------------------------------------------------------------- Fortschritt
function isoWoche(iso) {
  const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const tag = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - tag);
  const start = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return Math.ceil(((t - start) / 86400000 + 1) / 7);
}

export async function viewFortschritt() {
  const render = ansicht();
  kopf("Fortschritt", { text: "Zurück", href: "#/einstellungen" });
  if (!render(grosserTitel("Fortschritt"), skeleton())) return;
  fokusAufTitel();
  let s;
  try { s = (await refreshStats()) || await api("/api/statistik"); }
  catch (err) { render(grosserTitel("Fortschritt"), errorNotice(err, { erneut: viewFortschritt })); return; }
  if (!render.aktiv()) return;

  const z = zaehlerStand(s);
  const pk = z.punkte;
  const prozent = Math.round(((z.gesamt - z.vorher) / Math.max(1, z.naechster - z.vorher)) * 100);
  const zielWahl = el("select", { id: "wochenziel", style: "width:auto;min-width:150px" },
    [1, 2, 3, 5, 7, 10, 15, 20].map((n) => el("option", { value: String(n), selected: n === wochenziel() ? true : null }, `${n} pro Woche`)));
  zielWahl.addEventListener("change", () => { store.set("lv-wochenziel", zielWahl.value); statsAnzeigen(s); viewFortschritt(); say("Wochenziel gespeichert."); });

  // Die letzten sechs Wochen als Balken, aktuelle Woche rechts. Wurzelskala, damit eine Importwoche
  // mit 100+ Einträgen die normalen Wochen nicht auf Null drückt.
  const wochen = (s.wochen_zaehler || []).slice(0, 6).reverse();
  const maxWoche = Math.max(z.ziel, ...wochen.map((w) => w.anzahl || 0));
  const hoehe = (n) => Math.max(6, Math.round(Math.sqrt(n / maxWoche) * 100));
  const balken = el("div", { class: "wochen", role: "img", "aria-label": `Einträge der letzten ${wochen.length} Wochen: ${wochen.map((w) => w.anzahl || 0).join(", ")}` },
    wochen.map((w, i) => el("div", { class: "wk" },
      el("b", { class: i === wochen.length - 1 ? "top" : (w.anzahl || 0) >= z.ziel ? "ok" : "", style: `height:${hoehe(w.anzahl || 0)}%`, title: `${w.anzahl || 0} Einträge` }),
      el("span", {}, i === 0 ? `KW ${isoWoche(w.woche)}` : String(isoWoche(w.woche))))));

  const tile = (num, lbl, { klasse = "", extra = null, balken: bar = null } = {}) => el("div", { class: "tile" },
    el("div", { class: `num ${klasse}` }, num, extra), el("div", { class: "lbl" }, lbl), bar);

  render(grosserTitel("Fortschritt"),
    el("div", { class: "card level-karte" },
      el("div", { class: "level-ring" }, ring(pk.anteil, 96, false, "gross"),
        el("div", { class: "innen" }, el("span", { class: "num" }, String(pk.level)), el("small", {}, "LEVEL"))),
      el("div", { class: "grow" },
        el("p", { class: "level-name" }, pk.name),
        el("p", { class: "num", style: "margin:4px 0 0;font-size:.9375rem;font-weight:500;color:var(--text-2)" }, `${nf.format(pk.xp)} Punkte`),
        el("p", { class: "footnote", style: "margin:8px 0 0" }, `Noch ${nf.format(pk.bis - pk.xp)} bis ${pk.naechsterName}`))),
    el("div", { class: "card" },
      el("div", { class: "row", style: "justify-content:space-between;align-items:baseline" },
        el("p", { style: "margin:0;font-weight:600" }, "Wochenziel"),
        el("p", { class: "footnote", style: `margin:0;${z.erreicht ? "color:var(--success)" : ""}` }, z.erreicht ? `erreicht${z.serie ? ` · ${z.serie} ${z.serie === 1 ? "Woche" : "Wochen"} in Folge` : ""}` : `${z.diese} von ${z.ziel}`)),
      balken,
      el("div", { class: "row", style: "gap:12px;margin-top:14px" },
        el("label", { for: "wochenziel", class: "grow", style: "margin:0" }, "Ziel", el("span", { class: "li-sub" }, "Neue Einträge und Bestätigungen zählen. Erreichst du es Woche für Woche, wächst deine Serie.")),
        zielWahl)),
    el("div", { class: "tiles" },
      tile(`Lv ${pk.level}`, `${nf.format(pk.xp)} Punkte · noch ${nf.format(pk.bis - pk.xp)} bis Level ${pk.level + 1}`, { klasse: "gold", balken: el("div", { class: "progress own", "aria-hidden": "true" }, el("span", { style: `width:${Math.round(pk.anteil * 100)}%` })) }),
      tile(String(s.gesamt), `Einträge · noch ${z.naechster - z.gesamt} bis zum Meilenstein ${z.naechster}`, { extra: el("small", {}, ` / ${z.naechster}`), balken: el("div", { class: "progress own", "aria-hidden": "true" }, el("span", { style: `width:${prozent}%` })) }),
      tile(el("span", { class: "serie-gross" }, icon("flame", "icon lg"), String(z.serie)), `Wochen in Folge mit Wochenziel · diese Woche ${z.diese}/${z.ziel}`),
      tile(s.erfassung_sekunden_schnitt == null ? "–" : `${Math.round(s.erfassung_sekunden_schnitt)} s`, s.erfassungen_gemessen ? `Ø Erfassung, ${s.erfassungen_unter_30s} von ${s.erfassungen_gemessen} unter 30 s` : "Ø Erfassung, Ziel unter 30 s"),
      tile(s.briefings ? String(s.briefings_hilfreich) : "–", s.briefings ? "Briefings mit hilfreichem Eintrag" : "Noch kein Briefing", { extra: s.briefings ? el("small", {}, ` / ${s.briefings}`) : null }),
      tile(String(pk.rueckschauen), pk.rueckschauen === 1 ? "Rückschau · Kreis geschlossen" : "Rückschauen · Kreise geschlossen", { klasse: "violett" })),
    el("ul", { class: "list" },
      el("li", {}, el("span", { class: "grow" }, "Eigene Erfahrung"), el("span", { class: "footnote" }, s.lessons_eingeschaetzt ? `${s.lessons_persoenlich} von ${s.lessons_eingeschaetzt}` : "–")),
      el("li", {}, el("span", { class: "grow" }, "Dein Wissen in Plänen"), el("span", { class: "footnote" }, `${pk.planpunkte}×`)),
      el("li", {}, el("span", { class: "grow" }, "Als hilfreich markiert"), el("span", { class: "footnote" }, `${pk.hilfreich}×`)),
      el("li", {}, el("span", { class: "grow" }, "Neu in den letzten 30 Tagen"), el("span", { class: "footnote" }, s.neu_erfasst_30_tage)),
      el("li", {}, el("span", { class: "grow" }, "Ohne Anwendung"), el("span", { class: "footnote" }, s.ohne_massnahme)),
      Object.keys(s.bremsen || {}).length ? el("li", {}, el("span", { class: "grow" }, "Was dich bremst"), el("span", { class: "footnote" }, Object.entries(s.bremsen).map(([k, v]) => `${k} (${v})`).join(", "))) : null),
    el("div", { class: "card punkte-tabelle" },
      el("p", { class: "overline", style: "margin:10px 18px 6px" }, "So kommen Punkte zusammen"),
      [["Eintrag gesichert", PUNKTE.eintrag], ["Importierter Eintrag", PUNKTE.importiert], ["Erneut erlebt, bestätigt", PUNKTE.bestaetigung], ["Briefing erstellt", PUNKTE.briefing],
        ["Dein Eintrag im Plan", PUNKTE.planpunkt], ["Eintrag hat im Briefing geholfen", PUNKTE.hilfreich], ["Rückschau abgeschlossen", PUNKTE.rueckschau]]
        .map(([t, p]) => el("div", { class: "zeile" }, el("span", {}, t), el("span", { class: "num" }, `+${p}`)))),
    el("p", { class: "footnote", style: "margin:12px 4px 0" }, `Meilensteine: ${MEILENSTEINE.join(" · ")} Einträge`));
}

function zugangKarte() {
  const input = el("input", { type: "password", id: "token", value: store.get("lv-token"), autocomplete: "off" });
  return el("div", {},
    el("label", { for: "token", style: "margin-top:0" }, "Zugangstoken"),
    el("div", { class: "row" }, el("div", { class: "grow" }, input), el("button", {
      type: "button",
      onclick: () => { input.value = tokenNormalisieren(input.value); store.set("lv-token", input.value); toast("Token gesichert."); bereicheVergessen(); refreshStats(); },
    }, "Sichern")),
    el("p", { class: "hint" }, "Steht auf dem PC in der .env (LV_TOKEN) oder in data\\zugangstoken.txt."));
}

// ---------------------------------------------------------------- Zugang
// Lesbare Tokens (XXXX-XXXX-…) unabhängig von Groß/Klein und Leerzeichen akzeptieren; alte Tokens unverändert.
function tokenNormalisieren(wert) {
  const roh = String(wert || "").trim();
  return /^[A-Za-z0-9]{4}([ -]?[A-Za-z0-9]{4}){3}$/.test(roh) ? roh.toUpperCase().replace(/[ -]/g, "").match(/.{4}/g).join("-") : roh;
}

export function viewZugang(params = {}) {
  const render = ansicht();
  kopf("Zugang");
  const input = el("input", { type: "text", id: "zugang-token", autocomplete: "off", autocapitalize: "characters", autocorrect: "off", spellcheck: "false",
    placeholder: "XXXX-XXXX-XXXX-XXXX", value: store.get("lv-token"), "aria-describedby": "zugang-meldung" });
  const meldung = el("div", { id: "zugang-meldung", role: "status" });
  const pruefen = async () => {
    input.value = tokenNormalisieren(input.value);
    store.set("lv-token", input.value);
    try {
      state.zugangNoetig = false;
      await api("/api/status");
      bereicheVergessen();
      refreshStats();
      // Speicher dauerhaft machen, damit iOS das Token nicht aufräumt
      navigator.storage?.persist?.().catch(() => {});
      location.hash = state.zugangZiel.startsWith("#/zugang") ? "#/erfassen" : state.zugangZiel;
    } catch (err) {
      input.setAttribute("aria-invalid", "true");
      fill(meldung, el("div", { class: "notice error", role: "alert" }, icon("alert"), el("div", {}, err.status === 401 ? "Das Token passt nicht. Am einfachsten am PC kopieren und hier einfügen." : err.message)));
    }
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") pruefen(); });
  const einfuegen = navigator.clipboard?.readText ? el("button", {
    type: "button",
    onclick: async () => {
      try { input.value = (await navigator.clipboard.readText()).trim(); input.focus(); say("Eingefügt."); }
      catch { toast("Einfügen nicht erlaubt. Bitte lange auf das Feld tippen und Einsetzen wählen.", { ms: 8000 }); }
    },
  }, icon("copy", "icon sm"), "Einfügen") : null;
  render(
    grosserTitel("Zugang"),
    el("div", { class: "card" },
      el("p", { style: "margin-top:0" }, "Diese App ist mit einem Zugangstoken geschützt. Es steht auf dem PC in der ", el("code", {}, ".env"), " (LV_TOKEN) oder, falls dort leer, in ", el("code", {}, "data\\zugangstoken.txt"), ". Groß- und Kleinschreibung und Bindestriche sind egal."),
      el("p", { class: "small muted" }, "Mit der gemeinsamen Zwischenablage kopierst du es am Mac oder PC und fügst es hier ein. Die installierte App braucht es einmal extra, auch wenn Safari es schon kennt."),
      el("label", { for: "zugang-token" }, "Zugangstoken"),
      el("div", { class: "row" }, el("div", { class: "grow" }, input), einfuegen),
      meldung,
      el("div", { class: "actions", style: "margin-bottom:0" }, el("button", { type: "button", class: "primary block", onclick: pruefen }, "Anmelden"))));
  // Einrichtungslink (#/zugang?t=…): Token übernehmen, aus der Adresszeile entfernen, direkt prüfen.
  // Der Teil nach # geht nie an den Server und landet so in keinem Log.
  if (params.t) {
    input.value = params.t;
    history.replaceState(null, "", "#/zugang");
    pruefen();
    return;
  }
  input.focus();
}
