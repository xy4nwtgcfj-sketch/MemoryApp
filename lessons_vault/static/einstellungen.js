// Einstellungen, Fortschritt und Zugang.
import {
  ZIEL_LESSONS, ansicht, api, bereiche, bereicheVergessen, copyText, el, errorNotice, fill, fokusAufTitel,
  grosserTitel, herunterladen, icon, kopf, refreshStats, say, skeleton, state, status, store, toast,
} from "./core.js";

const STUFEN = [
  ["lokal", "Nur lokal", "lock"],
  ["text", "Text an Claude", "cloud"],
  ["foto", "Claude mit Foto", "image"],
];

function stufeVon(b, einst) {
  const std = einst.strukturierung_standard;
  const ueber = einst.strukturierung_bereiche[b.name] ?? (std === "lokal" || std === "manuell" ? std : null);
  if (ueber === "lokal" || ueber === "manuell") return "lokal";
  const bild = einst.bild_bereiche[b.name] || (b.beruflich ? "text" : "bild");
  return bild === "bild" && !b.beruflich ? "foto" : "text";
}

export async function viewEinstellungen() {
  const render = ansicht();
  kopf("Einstellungen");
  if (!render(grosserTitel("Einstellungen"), skeleton())) return;
  fokusAufTitel();

  let st, s, bereichListe, einst;
  try {
    [st, s, bereichListe, einst] = await Promise.all([status(true), refreshStats(), bereiche(true), api("/api/einstellungen")]);
  } catch (err) {
    render(grosserTitel("Einstellungen"), errorNotice(err, { erneut: viewEinstellungen }), zugangKarte());
    return;
  }
  if (!s) s = await api("/api/statistik");

  const speichern = async (body) => {
    const res = await api("/api/einstellungen", { method: "PUT", body });
    Object.assign(einst, res);
    status(true).then((neu) => { st = neu; }).catch(() => {});
    say("Gespeichert.");
    return res;
  };

  // ---------------------------------------------------------- Fortschritt
  const prozent = Math.min(100, (s.gesamt / ZIEL_LESSONS) * 100);
  const fortschritt = el("section", {},
    el("h2", { style: "margin-top:8px" }, "Fortschritt"),
    el("div", { class: "tiles" },
      el("div", { class: "tile" }, el("div", { class: "num" }, s.gesamt, el("small", {}, ` / ${ZIEL_LESSONS}`)), el("div", { class: "lbl" }, "Lessons"),
        el("div", { class: "progress own", "aria-hidden": "true" }, el("span", { style: `width:${prozent}%` }))),
      el("div", { class: "tile" }, el("div", { class: "num" }, s.woche_aktiv ? el("span", { style: "color:var(--success)" }, icon("check", "icon lg")) : "–"),
        el("div", { class: "lbl" }, `Diese Woche · ${s.aktive_wochen} von ${s.wochen_betrachtet} Wochen aktiv`)),
      el("div", { class: "tile" }, el("div", { class: "num" }, s.erfassung_sekunden_schnitt == null ? "–" : `${Math.round(s.erfassung_sekunden_schnitt)} s`),
        el("div", { class: "lbl" }, s.erfassungen_gemessen ? `Ø Erfassung, ${s.erfassungen_unter_30s} von ${s.erfassungen_gemessen} unter 30 s` : "Ø Erfassung, Ziel unter 30 s")),
      el("div", { class: "tile" }, el("div", { class: "num" }, s.briefings ? s.briefings_hilfreich : "–", s.briefings ? el("small", {}, ` / ${s.briefings}`) : null),
        el("div", { class: "lbl" }, s.briefings ? "Briefings mit hilfreicher Lesson" : "Noch kein Briefing"))),
    el("ul", { class: "list" },
      el("li", {}, el("span", { class: "grow" }, "Eigene Erfahrung"), el("span", { class: "footnote" }, s.lessons_eingeschaetzt ? `${s.lessons_persoenlich} von ${s.lessons_eingeschaetzt}` : "–")),
      el("li", {}, el("span", { class: "grow" }, "Neu in den letzten 30 Tagen"), el("span", { class: "footnote" }, s.neu_erfasst_30_tage)),
      el("li", {}, el("span", { class: "grow" }, "Ohne „Nächstes Mal“"), el("span", { class: "footnote" }, s.ohne_massnahme)),
      Object.keys(s.bremsen || {}).length ? el("li", {}, el("span", { class: "grow" }, "Was dich bremst"), el("span", { class: "footnote" }, Object.entries(s.bremsen).map(([k, v]) => `${k} (${v})`).join(", "))) : null));

  // ---------------------------------------------------------- Bereiche und Datenschutz
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
          el("label", { for: aktivId, class: "grow", style: "margin:0" }, b.name, el("span", { class: "li-sub" }, b.beispiele)),
          aktiv),
        b.aktiv ? el("details", { class: "bereich-details", open: offen || null },
          el("summary", {}, `${stufenText}${b.beruflich ? " · beruflich" : ""}`),
          el("div", { class: "stack" },
            ohneClaude ? null : [seg, el("p", { class: "footnote", style: "margin:0" }, erklaerung)],
            el("div", { class: "row" },
              el("label", { for: berufId, class: "grow", style: "margin:0;font-weight:500" }, "Beruflich", el("span", { class: "li-sub" }, "Strengere Prüfung auf Namen und Zahlen, Fotos nie als Bild")),
              beruf))) : null);
    };
    zeichnen();
    return li;
  };
  const neuerBereich = el("input", { type: "text", id: "neuer-bereich", placeholder: "Neuer Bereich" });
  const bereicheListe = el("ul", { class: "list" }, bereichListe.map(bereichZeile));
  const bereicheSection = el("section", { class: "section" },
    el("h2", {}, "Bereiche und Datenschutz"),
    el("p", { class: "small muted", style: "margin-top:-4px" }, "Pro Bereich legst du fest, was an Claude gehen darf. Fokus schlägt Vollständigkeit: Lass anfangs nur zwei Bereiche aktiv."),
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

  // ---------------------------------------------------------- Erinnerungen und Kurzbefehl
  const url = `${location.origin}/api/notiz`;
  const token = store.get("lv-token");
  const erinnerungen = el("section", { class: "section" },
    el("h2", {}, "Erinnerungen"),
    el("ul", { class: "list" },
      el("li", {}, icon("calendar"), el("span", { class: "grow" }, "Wochenrückblick", el("span", { class: "li-sub" }, "Freitags 16:30, 10 Minuten, als Serie in deinem Kalender")),
        el("a", { class: "button text", href: "wochenrueckblick.ics", download: "wochenrueckblick.ics" }, "Eintragen")),
      el("li", { class: "li-col" },
        el("details", { class: "plain" },
          el("summary", { style: "color:var(--text)" }, icon("phone"), "iPhone-Kurzbefehl „Lesson merken“"),
          el("p", { class: "small", style: "margin:4px 0 8px" }, "Damit hältst du eine Lesson in unter 10 Sekunden fest, ohne die App zu öffnen: per Siri, Action-Taste, Sperrbildschirm oder Rückseite antippen. Die Notiz landet strukturiert im Eingang."),
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
          el("p", { class: "footnote", style: "margin:0" }, el("code", {}, url))))));

  // ---------------------------------------------------------- Sperrliste
  const sperrliste = el("textarea", { id: "sperrliste", rows: 4, placeholder: "Ein Begriff pro Zeile, z. B. Kundennamen, Standorte, Systemnamen" });
  sperrliste.value = einst.sperrliste.join("\n");
  const sperrSection = el("section", { class: "section" },
    el("h2", {}, "Sperrliste"),
    el("div", { class: "card" },
      el("label", { for: "sperrliste", style: "margin-top:0" }, "Begriffe, die nie an Claude gehen"),
      sperrliste,
      el("p", { class: "hint" }, "Treffer blockieren das Senden immer. Die Liste bleibt auf deinem PC."),
      el("div", { class: "actions", style: "margin-bottom:0" }, el("button", {
        type: "button",
        onclick: async () => {
          try { const res = await speichern({ sperrliste: sperrliste.value.split("\n") }); sperrliste.value = res.sperrliste.join("\n"); toast("Sperrliste gesichert."); }
          catch (err) { toast(err.message, { fehler: true }); }
        },
      }, "Sichern"))));

  // ---------------------------------------------------------- Bestand
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
  const bestand = el("section", { class: "section" },
    el("h2", {}, "Bestand"),
    el("ul", { class: "list" },
      el("li", { style: "padding:0" }, el("a", { class: "li grow", href: "#/ernte", style: "box-shadow:none" }, icon("sprout"), el("span", { class: "grow" }, "Startbestand mit Fragen anlegen"), icon("chevron-right", "icon sm chev"))),
      el("li", {}, icon("upload"), el("span", { class: "grow" }, "Importieren", el("span", { class: "li-sub" }, "Startbestand oder Backup als JSON (Vorlage: startbestand/vorlage.json)")),
        el("button", { type: "button", class: "text", onclick: () => fileInput.click() }, "Datei wählen"), fileInput),
      el("li", {}, icon("download"), el("span", { class: "grow" }, "Exportieren", el("span", { class: "li-sub" }, "Alle Lessons als JSON")),
        el("button", {
          type: "button", class: "text",
          onclick: async () => {
            try { const res = await api("/api/export", { raw: true }); herunterladen(`lessons-vault-${new Date().toISOString().slice(0, 10)}.json`, await res.blob()); }
            catch (err) { toast(err.message, { fehler: true }); }
          },
        }, "Sichern"))),
    importErgebnis);

  // ---------------------------------------------------------- Erweitert
  const optionen = [["auto", "Automatisch"], ["claude", "Claude"], ["lokal", "Lokal"], ["manuell", "Ohne KI"]];
  const standard = el("select", { id: "ki-standard" }, optionen.map(([v, t]) => el("option", { value: v, selected: einst.strukturierung_standard === v }, t)));
  standard.addEventListener("change", async () => { try { await speichern({ strukturierung_standard: standard.value }); } catch (err) { toast(err.message, { fehler: true }); } });
  const thema = store.get("lv-theme", "");
  const themaSeg = el("div", { class: "segmented", role: "group", "aria-label": "Erscheinungsbild" }, [["", "System"], ["light", "Hell"], ["dark", "Dunkel"]].map(([v, t]) => el("button", {
    type: "button", "aria-pressed": String(thema === v),
    onclick: (e) => {
      store.set("lv-theme", v);
      if (v) document.documentElement.dataset.theme = v; else delete document.documentElement.dataset.theme;
      e.currentTarget.parentElement.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget)));
    },
  }, t)));
  const l = st.lokal || {};
  const lokalInfo = !l.konfiguriert ? "nicht eingerichtet (LV_OLLAMA_MODEL leer)"
    : !l.erreichbar ? "Ollama nicht erreichbar" : l.modell_installiert ? `${l.modell}, bereit` : `${l.modell} fehlt: ollama pull ${l.modell}`;
  const embeddingInfo = st.embeddings.startsWith("ollama:") ? `${st.embeddings} (lokal, Bedeutung)` : st.semantisch ? `${st.embeddings} (Cloud, Bedeutung)` : `${st.embeddings} (nur Wortähnlichkeit; für Suche nach Bedeutung VOYAGE_API_KEY oder Ollama einrichten)`;
  const erweitert = el("section", { class: "section" },
    el("details", { class: "card" },
      el("summary", {}, "Erweitert"),
      el("label", { for: "ki-standard" }, "Strukturierung ohne Bereichswahl"),
      standard,
      el("p", { class: "hint" }, "Automatisch: Claude, wenn eingerichtet, sonst lokal, sonst ohne KI. Ist irgendein Bereich lokal, geht ohne Bereichswahl nichts an Claude."),
      el("p", { class: "label" }, "Erscheinungsbild"),
      themaSeg,
      el("dl", { class: "fields" },
        el("dt", {}, "Claude"), el("dd", {}, st.ki ? `eingerichtet (${st.modell})` : "nicht eingerichtet, ANTHROPIC_API_KEY fehlt"),
        el("dt", {}, "Lokales Modell"), el("dd", {}, lokalInfo),
        el("dt", {}, "Texterkennung für Fotos"), el("dd", {}, st.texterkennung?.verfuegbar ? "Tesseract eingerichtet" : st.texterkennung?.hinweis || "nicht verfügbar"),
        el("dt", {}, "Suchindex"), el("dd", {}, embeddingInfo),
        el("dt", {}, "Version"), el("dd", {}, st.version)),
      el("div", { class: "actions" }, el("button", {
        type: "button",
        onclick: async (e) => {
          const b = e.currentTarget;
          b.setAttribute("aria-disabled", "true");
          try { const r = await api("/api/reindex", { method: "POST" }); toast(`${r.neu_indexiert} Lessons neu indexiert.`); }
          catch (err) { toast(err.message, { fehler: true }); }
          finally { b.removeAttribute("aria-disabled"); }
        },
      }, icon("refresh", "icon sm"), "Suchindex neu aufbauen")),
      zugangKarte()));

  render(grosserTitel("Einstellungen"), fortschritt, bereicheSection, erinnerungen, sperrSection, bestand, erweitert);
}

function zugangKarte() {
  const input = el("input", { type: "password", id: "token", value: store.get("lv-token"), autocomplete: "off" });
  return el("div", { style: "margin-top:16px" },
    el("label", { for: "token" }, "Zugangstoken"),
    el("div", { class: "row" }, el("div", { class: "grow" }, input), el("button", {
      type: "button",
      onclick: () => { input.value = tokenNormalisieren(input.value); store.set("lv-token", input.value); toast("Token gesichert."); bereicheVergessen(); refreshStats(); },
    }, "Sichern")),
    el("p", { class: "hint" }, "Steht auf dem PC in data\\zugangstoken.txt."));
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
