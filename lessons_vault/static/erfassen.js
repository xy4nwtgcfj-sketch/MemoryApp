// Erfassen: erst sichern, dann veredeln. Jede Notiz liegt sofort auf dem PC, Claude strukturiert danach.
import {
  ZIEL_LESSONS, MAX_FOTOS, anf, ansicht, aufZaehler, zaehlerKarte, api, ausgangAdd, bereiche, bereicheSofort, debounce, diktatKnopf, el,
  errorNotice, fill, fokusAufTitel, fotoInput, fotosHochladen, grosserTitel, heute, hinweisBox, icon, istOffline,
  kopf, kuerzen, refreshStats, say, skeleton, statistikSofort, status, statusSofort, store, thumbsRow, toast,
  wochenSchluessel, ersetzenIn,
} from "./core.js";
import { abschlussKarte, entwurfKarte, rueckgaengig, uebernehmen } from "./entwurf.js";

// ---------------------------------------------------------------- Zustand (überlebt Neustart der App)
export const capture = Object.assign(
  { text: "", quelle: "text", bereich: "", start: null, bilder: [] },
  store.json("lv-capture", {}),
);
const sichernLokal = debounce(() => {
  if (capture.text.trim() || capture.bilder.length) store.setJson("lv-capture", capture);
  else store.remove("lv-capture");
}, 400);
document.addEventListener("visibilitychange", () => { if (document.hidden) sichernLokal.flush(); });

function captureLeeren() {
  Object.assign(capture, { text: "", quelle: "text", start: null, bilder: [] });
  store.remove("lv-capture");
}
function startTimer() { if (!capture.start) { capture.start = Date.now(); sichernLokal(); } }
function sekunden() { return capture.start ? Math.round((Date.now() - capture.start) / 100) / 10 : null; }

const MODUS_ZEILE = {
  claude: ["cloud", "Claude strukturiert. Namen und Projektdaten prüft die App vorher."],
  lokal: ["lock", "Bleibt auf deinem PC und wird dort strukturiert."],
  manuell: ["pencil", "Ohne KI: „Sichern“ öffnet das Formular, „Nur merken“ legt die Notiz in den Eingang."],
};

function modusFuer(st, bereich) {
  if (!st) return "claude";
  return (bereich ? st.modi?.[bereich] : st.modus_standard) || "manuell";
}

// ---------------------------------------------------------------- Ansicht
export async function viewErfassen(params = {}) {
  const render = ansicht();
  kopf("Erfassen");
  let st = statusSofort();
  let bereichListe = bereicheSofort();
  const wiederhergestellt = Boolean(capture.text) && !params.text;
  if (params.text) { capture.text = params.text; startTimer(); }
  if (params.bereich) capture.bereich = params.bereich;
  if (params.text || params.bereich) history.replaceState(null, "", "#/erfassen");

  const textId = "capture-text";
  const textarea = el("textarea", {
    id: textId,
    class: "capture",
    placeholder: "Erfahrung, Wissen, Vorgehen oder Entscheidung. Drei Stichworte reichen.\nz. B. „Bankgespräch, Gehaltsnachweise vergessen, zweiter Termin“ oder „Wave-Schnitt: kritische Läger nach hinten, keine Peak Seasons“",
    "aria-describedby": "capture-hint",
    enterkeyhint: "enter",
    oninput: () => { startTimer(); capture.text = textarea.value; textarea.removeAttribute("aria-invalid"); fill(textFehler); sichernLokal(); },
  });
  textarea.value = capture.text;
  const textFehler = el("p", { class: "feld-fehler", id: "capture-fehler" });

  const mic = diktatKnopf(textarea, { onStart: () => { startTimer(); capture.quelle = "sprache"; sichernLokal(); } });
  const fotoBtn = el("button", { type: "button", class: "icon-btn", "aria-label": "Foto aufnehmen oder auswählen", title: "Foto" }, icon("camera"));
  const thumbs = el("div");
  const fotoPanel = el("div", { id: "foto-panel" });
  const oben = el("div", { id: "erfassen-oben" });
  const ergebnis = el("div", { id: "draft" });
  const fehlerSlot = el("div");
  const modusZeile = el("p", { class: "footnote row", style: "gap:8px;margin:12px 0 0" });
  const chips = el("div", { class: "chips", role: "group", "aria-labelledby": "bereich-label" });
  const bereichBlock = el("div", {}, el("p", { class: "overline", id: "bereich-label", style: "margin-top:16px" }, "Bereich ", el("span", { style: "text-transform:none;letter-spacing:0;font-weight:400" }, "(optional)")), chips);
  const sichernBtn = el("button", { type: "button", class: "primary" }, "Sichern");
  const merkenBtn = el("button", { type: "button" }, icon("inbox", "icon sm"), "Nur merken");
  const tagesSlot = el("div", { id: "erfassen-tag", style: "margin-top:24px" });

  const renderThumbs = () => fill(thumbs, capture.bilder.length ? thumbsRow(capture.bilder, {
    onRemove: (b) => {
      capture.bilder = capture.bilder.filter((x) => x.id !== b.id);
      sichernLokal();
      renderThumbs();
      if (!capture.bilder.length) fill(fotoPanel);
    },
  }) : null);

  const updateModus = () => {
    const [sym, text] = MODUS_ZEILE[modusFuer(st, capture.bereich)] || MODUS_ZEILE.manuell;
    fill(modusZeile, icon(sym, "icon sm"), el("span", {}, text));
  };
  const renderChips = () => {
    const aktive = bereichListe.filter((b) => b.aktiv);
    if (capture.bereich && aktive.length && !aktive.some((b) => b.name === capture.bereich)) capture.bereich = "";
    bereichBlock.hidden = aktive.length < 2;
    fill(chips, aktive.map((b) => el("button", {
      type: "button",
      class: "chip",
      "aria-pressed": String(capture.bereich === b.name),
      onclick: () => {
        capture.bereich = capture.bereich === b.name ? "" : b.name;
        sichernLokal();
        renderChips();
        updateModus();
        if (capture.bilder.length && fotoPanel.childNodes.length) fotoVorbereiten();
      },
    }, capture.bereich === b.name ? icon("check") : null, b.name, modusFuer(st, b.name) === "lokal" ? el("small", {}, "lokal") : null)));
  };

  const composer = el("div", { id: "composer" },
    el("label", { for: textId, style: "margin-top:0" }, "Was willst du festhalten?"),
    el("div", { class: "composer" }, textarea, el("div", { class: "tools" }, mic, fotoBtn)),
    textFehler,
    el("p", { class: "hint", id: "capture-hint" }, "Kurz ist gut. Du kannst später ergänzen."),
    wiederhergestellt ? el("p", { class: "footnote row", style: "gap:8px" }, icon("undo", "icon sm"),
      el("span", { class: "grow" }, "Deine letzte Notiz ist wiederhergestellt."),
      el("button", { type: "button", class: "text", onclick: (e) => { captureLeeren(); textarea.value = ""; renderThumbs(); e.currentTarget.parentElement.remove(); textarea.focus(); } }, "Leeren")) : null,
    thumbs,
    fotoPanel,
    bereichBlock,
    modusZeile,
    fehlerSlot,
    // Fest über der Leiste, damit Sichern ohne Scrollen erreichbar ist
    el("div", { class: "sticky-actions" }, sichernBtn, merkenBtn));

  const notizZeile = el("div", { class: "card flat", hidden: true });

  // Zwei Zustände: Eingabe (Notizfeld sichtbar) und Entwurf (Notiz eingeklappt, Entwurfskarte darunter)
  const eingabeModus = () => {
    composer.hidden = false;
    notizZeile.hidden = true;
    store.remove("lv-laufend");
  };
  const entwurfModus = (rohtext) => {
    composer.hidden = true;
    notizZeile.hidden = false;
    fill(notizZeile,
      el("div", { class: "row" },
        el("p", { class: "overline grow", style: "margin:0" }, "Deine Notiz, gesichert"),
        el("button", { type: "button", class: "text", onclick: () => { eingabeModus(); fill(ergebnis); textarea.focus(); toast("Der Entwurf wartet im Eingang."); } }, icon("plus", "icon sm"), "Neue Notiz")),
      el("p", { style: "margin:4px 0 0;white-space:pre-wrap;color:var(--text-2)" }, kuerzen(rohtext, 280)));
  };

  // ---------------------------------------------------------- Ablauf nach dem Sichern
  const gesichert = (lesson, eintrag, { bestaetigt = false } = {}) => {
    eingabeModus();
    fill(ergebnis);
    fill(oben, abschlussKarte(lesson, eintrag, { bestaetigt, modus: eintrag.modus }));
    refreshStats();
    window.scrollTo({ top: 0, behavior: "auto" });
    oben.querySelector(".card")?.setAttribute("tabindex", "-1");
    oben.querySelector(".card")?.focus({ preventScroll: true });
    toast(bestaetigt ? "Als erneut erlebt gezählt." : "Gesichert.", bestaetigt ? {} : {
      aktion: {
        text: "Rückgängig",
        onclick: async () => {
          try { const neu = await rueckgaengig(lesson, eintrag); fill(oben); zeigeEintrag(neu); }
          catch (err) { toast(err.message, { fehler: true }); }
        },
      },
    });
  };
  const handler = {
    onGesichert: gesichert,
    onSpaeter: () => { eingabeModus(); fill(ergebnis); toast("Liegt im Eingang. Du findest ihn unten in der Leiste."); textarea.focus(); },
    onVerworfen: () => { eingabeModus(); },
    onNeu: (neu) => zeigeEintrag(neu),
    spaeterText: "Später",
  };

  const warten = async (eintrag) => {
    const sp = el("button", { type: "button", class: "text", onclick: () => { abgebrochen = true; handler.onSpaeter(); } }, "Später ansehen");
    let abgebrochen = false;
    fill(ergebnis, skeleton(eintrag.modus === "claude" ? "Claude strukturiert deine Notiz …" : "Wird vorbereitet …"), el("div", { class: "actions" }, sp));
    say("Notiz gesichert. Claude strukturiert, bitte warten.");
    const start = Date.now();
    let langsamGemeldet = false;
    while (!abgebrochen && render.aktiv()) {
      await new Promise((r) => setTimeout(r, 800));
      if (abgebrochen || !render.aktiv()) return;
      let e;
      try { e = await api(`/api/entwuerfe/${eintrag.id}`, { timeoutMs: 8000 }); }
      catch (err) {
        if (err.status === 404) { eingabeModus(); fill(ergebnis); return; }
        continue;
      }
      if (e.status === "fertig" || e.status === "fehler") return zeigeEintrag(e);
      if (!langsamGemeldet && Date.now() - start > 15000) {
        langsamGemeldet = true;
        say("Dauert länger als üblich.");
        ergebnis.querySelector(".waiting")?.append(" Dauert länger als üblich.");
      }
      if (Date.now() - start > 120000) {
        fill(ergebnis, el("div", { class: "notice info" }, icon("clock"), el("div", {},
          "Das dauert ungewöhnlich lange. Deine Notiz ist sicher und erscheint fertig im ", el("a", { href: "#/eingang" }, "Eingang"), ".")));
        eingabeModus();
        return;
      }
    }
  };

  async function zeigeEintrag(eintrag) {
    if (!render.aktiv()) return;
    store.set("lv-laufend", eintrag.id);
    entwurfModus(eintrag.rohtext);
    fill(oben);
    if (eintrag.status === "wartet" || eintrag.status === "in_arbeit") {
      const lokalAktiv = eintrag.modus === "lokal" && st?.lokal?.konfiguriert;
      if (lokalAktiv) {
        eingabeModus();
        fill(ergebnis);
        fill(oben, el("div", { class: "card hero", role: "status" },
          el("p", { class: "overline row", style: "gap:6px;color:var(--success)" }, icon("check", "icon sm"), "Gesichert"),
          el("p", { style: "margin:0" }, "Dein PC strukturiert die Notiz lokal. Sie erscheint danach im ", el("a", { href: "#/eingang" }, "Eingang"), ".")));
        refreshStats();
        return;
      }
      return warten(eintrag);
    }
    await entwurfKarte(ergebnis, eintrag, handler);
    ergebnis.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  const sichern = async ({ nurMerken = false } = {}) => {
    const text = textarea.value.trim();
    if (!text && capture.bilder.length) {
      // Nur ein Foto, keine Stichworte: Die App sucht die Einträge selbst.
      await fotoVorbereiten({ automatisch: true });
      return;
    }
    if (!text) {
      textarea.setAttribute("aria-invalid", "true");
      textarea.setAttribute("aria-describedby", "capture-fehler capture-hint");
      textFehler.textContent = capture.bilder.length ? "Schreib kurz dazu, was du aus dem Foto mitnimmst." : "Erst ein paar Stichworte eingeben.";
      textarea.focus();
      say(textFehler.textContent);
      return;
    }
    if (sichernBtn.getAttribute("aria-disabled") === "true" || merkenBtn.getAttribute("aria-disabled") === "true") return;
    const notiz = { text, quelle: capture.quelle, bereich: capture.bereich, erfassung_sekunden: sekunden(), bild_ids: capture.bilder.map((b) => b.id) };
    fill(fehlerSlot);
    const imAusgang = () => {
      ausgangAdd(notiz);
      captureLeeren();
      textarea.value = "";
      renderThumbs();
      fill(oben, el("div", { class: "card hero", role: "status" },
        el("p", { class: "overline row", style: "gap:6px;color:var(--success)" }, icon("check", "icon sm"), "Auf dem iPhone gesichert"),
        el("p", { style: "margin:0" }, "Der PC ist gerade nicht erreichbar. Die Notiz geht automatisch raus, sobald die Verbindung steht, und landet dann im Eingang.")));
      say("Auf dem iPhone gesichert. Wird gesendet, sobald der PC erreichbar ist.");
    };
    if (istOffline()) return imAusgang();
    sichernBtn.setAttribute("aria-disabled", "true");
    merkenBtn.setAttribute("aria-disabled", "true");
    try {
      const eintrag = await api("/api/notiz", { method: "POST", body: notiz, timeoutMs: 15000 });
      captureLeeren();
      textarea.value = "";
      renderThumbs();
      fill(fotoPanel);
      refreshStats();
      if (nurMerken) {
        toast("Im Eingang gemerkt. Du ergänzt sie, wenn du Zeit hast.");
        say("Im Eingang gemerkt.");
        textarea.focus();
        return;
      }
      zeigeEintrag(eintrag);
    } catch (err) {
      if (err.netz) imAusgang();
      else fill(fehlerSlot, errorNotice(err));
    } finally {
      sichernBtn.removeAttribute("aria-disabled");
      merkenBtn.removeAttribute("aria-disabled");
    }
  };
  sichernBtn.addEventListener("click", () => sichern());
  merkenBtn.addEventListener("click", () => sichern({ nurMerken: true }));

  // ---------------------------------------------------------- Fotos
  const fotoIn = fotoInput(async (files) => {
    startTimer();
    fotoBtn.setAttribute("aria-disabled", "true");
    fill(fotoPanel, el("p", { class: "loading" }, el("span", { class: "spinner", "aria-hidden": "true" }), "Fotos werden hochgeladen und gelesen …"));
    say("Fotos werden hochgeladen.");
    try {
      capture.bilder = [...capture.bilder, ...(await fotosHochladen(files))].slice(0, MAX_FOTOS);
      sichernLokal();
      renderThumbs();
      // Ohne getippte Stichworte ist das Foto die Quelle: gleich nach Lessons suchen.
      await fotoVorbereiten({ automatisch: !textarea.value.trim() });
    } catch (err) {
      fill(fotoPanel, errorNotice(err));
    } finally {
      fotoBtn.removeAttribute("aria-disabled");
    }
  });
  fotoBtn.addEventListener("click", () => fotoIn.click());

  const nurAnhaengen = () => el("button", { type: "button", class: "text", onclick: () => { fill(fotoPanel, el("p", { class: "footnote" }, "Das Foto hängt an der Notiz, die du oben beschreibst.")); textarea.focus(); } }, "Nur anhängen");

  const kandidatenAnzeigen = (res) => {
    if (!res.kandidaten.length) {
      fill(fotoPanel, el("div", { class: "notice info" }, icon("info"), el("div", {}, el("strong", {}, "Nichts zum Festhalten auf dem Foto gefunden."),
        res.hinweis || "Das Foto enthält eher Organisatorisches. Es bleibt angehängt, wenn du den Eintrag selbst beschreibst.")));
      return;
    }
    const boxes = res.kandidaten.map((k, i) => el("input", { type: "checkbox", id: `kand-${i}`, checked: true }));
    const startBtn = el("button", { type: "button", class: "primary" });
    const zaehlen = () => {
      const n = boxes.filter((b) => b.checked).length;
      startBtn.textContent = n === res.kandidaten.length ? `Alle speichern (${n})` : `Ausgewählte speichern (${n})`;
      startBtn.setAttribute("aria-disabled", String(n === 0));
    };
    boxes.forEach((b) => b.addEventListener("change", zaehlen));
    zaehlen();
    startBtn.addEventListener("click", async () => {
      const auswahl = res.kandidaten.filter((_, i) => boxes[i].checked);
      if (!auswahl.length || startBtn.getAttribute("aria-disabled") === "true") return;
      startBtn.setAttribute("aria-disabled", "true");
      fill(fotoPanel, el("p", { class: "loading" }, el("span", { class: "spinner", "aria-hidden": "true" }),
        auswahl.length > 1 ? `${auswahl.length} Einträge werden formuliert und gespeichert …` : "Eintrag wird formuliert und gespeichert …"));
      say("Einträge werden erstellt, bitte warten.");
      const bildIds = capture.bilder.map((b) => b.id);
      const sek = sekunden();
      // Jede Auswahl wird sofort strukturiert (parallel) und, wenn nichts dagegen spricht, direkt gespeichert.
      // Bei Dublette, gesperrtem Inhalt oder fehlender Regel bleibt der Entwurf im Eingang zur Prüfung.
      const erstellen = async (k) => {
        const eintrag = await api("/api/notiz?warten=true", {
          method: "POST", timeoutMs: 180000,
          body: { text: `${k.titel}: ${k.kern}`, quelle: capture.quelle, bereich: capture.bereich, bild_ids: bildIds, erfassung_sekunden: sek },
        });
        const e = eintrag.entwurf;
        const speicherbar = eintrag.status === "fertig" && e && e.lesson && (e.bereich || capture.bereich) && !e.pruefung && !e.dublette;
        if (!speicherbar) return { eintrag, grund: e?.dublette ? "ähnlicher Eintrag vorhanden" : e?.pruefung ? "Datenschutz-Prüfung" : "bitte ergänzen" };
        if (!e.bereich) e.bereich = capture.bereich;
        try { return { lesson: await uebernehmen(eintrag) }; } catch (err) { return { eintrag, grund: err.message }; }
      };
      try {
        const ergebnisse = await Promise.all(auswahl.map((k) => erstellen(k).catch((err) => ({ fehler: err.message, titel: k.titel }))));
        const gespeichert = ergebnisse.filter((r) => r.lesson).map((r) => r.lesson);
        const offen = ergebnisse.filter((r) => r.eintrag);
        const fehler = ergebnisse.filter((r) => r.fehler);
        captureLeeren();
        textarea.value = "";
        renderThumbs();
        fill(fotoPanel);
        refreshStats();
        fill(oben, el("div", { class: "card hero", role: "status" },
          el("p", { class: "overline row", style: "gap:6px;color:var(--success)" }, icon("check", "icon sm"), "Aus dem Foto"),
          el("p", { class: "lead" }, gespeichert.length === 1 ? "1 Eintrag gespeichert" : `${gespeichert.length} Einträge gespeichert`),
          gespeichert.length ? el("ul", { class: "checklist" }, gespeichert.map((l) => el("li", {}, icon("check", "icon sm"),
            el("a", { href: `#/lesson/${l.id}` }, anf(l.titel))))) : null,
          offen.length ? el("p", { class: "small", style: "margin:12px 0 0" }, icon("inbox", "icon sm"), ` ${offen.length} im `, el("a", { href: "#/eingang" }, "Eingang"),
            ` zur Prüfung (${[...new Set(offen.map((r) => r.grund))].join(", ")}).`) : null,
          fehler.length ? el("p", { class: "small", style: "margin:12px 0 0;color:var(--danger)" }, `${fehler.length} nicht erstellt: ${fehler[0].fehler}`) : null));
        window.scrollTo({ top: 0, behavior: "auto" });
        say(`${gespeichert.length} Einträge gespeichert${offen.length ? `, ${offen.length} im Eingang zur Prüfung` : ""}.`);
      } catch (err) {
        fill(fotoPanel, errorNotice(err));
      }
    });
    fill(fotoPanel, el("div", { class: "card" },
      el("p", { class: "overline" }, `Auf dem Foto gefunden (${res.kandidaten.length})`),
      el("p", { class: "small muted", style: "margin:0 0 4px" }, "Die App formuliert jeden als fertigen Eintrag (Erfahrung, Wissen, Vorgehen oder Entscheidung) und speichert ihn, das Foto hängt an jedem. Abwählen, was nicht passt. Du kannst jeden Eintrag danach noch bearbeiten."),
      el("ul", { class: "checklist" }, res.kandidaten.map((k, i) => el("li", {}, boxes[i],
        el("label", { for: `kand-${i}` }, el("span", { style: "font-weight:600;display:block" }, anf(k.titel)), el("span", { class: "footnote" }, anf(k.kern)))))),
      el("div", { class: "actions" }, startBtn, nurAnhaengen())));
    say(`${res.kandidaten.length} mögliche Einträge auf dem Foto gefunden.`);
  };

  const kandidatenSuchen = async (body) => {
    fill(fotoPanel, el("p", { class: "loading" }, el("span", { class: "spinner", "aria-hidden": "true" }), "Claude liest das Foto aus …"));
    say("Claude liest das Foto aus.");
    try {
      kandidatenAnzeigen(await api("/api/foto/kandidaten", { method: "POST", body: { bild_ids: capture.bilder.map((b) => b.id), bereich: capture.bereich, notiz: textarea.value.trim(), ...body } }));
    } catch (err) {
      if (err.code === "pruefung" || err.code === "sperrliste") {
        fill(fotoPanel, el("div", { class: "notice warn" }, icon("shield"), el("div", {}, el("strong", {}, err.message),
          el("ul", {}, err.hinweise.map((h) => el("li", {}, anf(h)))),
          el("div", { class: "actions" },
            el("button", { type: "button", onclick: () => fotoVorbereiten() }, "Text bearbeiten"),
            err.code === "sperrliste" ? null : el("button", { type: "button", class: "text", onclick: () => kandidatenSuchen({ ...body, freigabe: true }) }, "Trotzdem senden")))));
      } else {
        fill(fotoPanel, errorNotice(err));
      }
    }
  };

  async function fotoVorbereiten({ automatisch = false } = {}) {
    if (!capture.bilder.length) return;
    fill(fotoPanel, el("p", { class: "loading" }, el("span", { class: "spinner", "aria-hidden": "true" }), "Foto wird ausgewertet …"));
    let res;
    try {
      res = await api("/api/foto/vorbereiten", { method: "POST", body: { bild_ids: capture.bilder.map((b) => b.id), bereich: capture.bereich } });
    } catch (err) {
      return fill(fotoPanel, errorNotice(err));
    }
    if (res.geschwaerzt?.length) toast("Aus der Sperrliste ersetzt: " + res.geschwaerzt.join(", ") + ". Geht nicht an Claude.", { ms: 6000 });
    // Automatisch weiter, solange keine Prüfung nötig ist: Bild-Weg direkt, Text-Weg nur ohne Datenschutz-Hinweise.
    if (automatisch && res.weg === "bild") return kandidatenSuchen({});
    if (automatisch && res.weg === "text" && res.text.trim().length >= 3 && !(res.compliance_hinweise || []).length) {
      return kandidatenSuchen({ text: res.text });
    }
    if (res.weg === "bild") {
      fill(fotoPanel, el("div", { class: "card" },
        el("p", { class: "overline" }, "Einträge aus dem Foto"),
        el("p", { class: "small muted", style: "margin:0" }, "Privater Bereich: Claude sieht das Foto selbst. Deine Stichworte oben gehen als Notiz mit."),
        el("div", { class: "actions" }, el("button", { type: "button", class: "primary", onclick: () => kandidatenSuchen({}) }, icon("sparkles"), "Einträge finden"), nurAnhaengen())));
    } else if (res.weg === "text") {
      const area = el("textarea", { rows: 8, id: "ocr-text" });
      area.value = res.text;
      const box = hinweisBox(res.compliance_hinweise || [], { anwenden: (r) => { area.value = ersetzenIn(area.value, r.von, r.nach); } });
      const recheck = debounce(async () => {
        try { box.update(await api("/api/compliance", { method: "POST", body: { text: area.value, bereich: capture.bereich || "Beruf" } })); } catch { /* bleibt */ }
      }, 600);
      area.addEventListener("input", recheck);
      fill(fotoPanel, el("div", { class: "card" },
        el("p", { class: "overline" }, "Erkannter Text"),
        el("p", { class: "small muted", style: "margin:0 0 8px" }, "Nur dieser Text geht an Claude, das Foto bleibt auf deinem PC. Lösche, was nicht raus soll."),
        res.text ? null : el("div", { class: "notice warn" }, icon("alert"), el("div", {}, res.texterkennung.verfuegbar ? "Kein Text erkannt. Tippe die Kernpunkte ab oder beschreibe die Lesson oben." : res.texterkennung.hinweis)),
        box.node,
        el("label", { for: "ocr-text", class: "sr-only" }, "Erkannter Text"), area,
        el("div", { class: "actions" }, el("button", {
          type: "button",
          class: "primary",
          onclick: () => (area.value.trim().length < 3 ? (area.focus(), say("Kein Text zum Auswerten.")) : kandidatenSuchen({ text: area.value })),
        }, icon("sparkles"), "Einträge finden"), nurAnhaengen())));
    } else {
      fill(fotoPanel, el("div", { class: "card" },
        el("p", { class: "overline row", style: "gap:6px" }, icon("lock", "icon sm"), "Bleibt auf deinem PC"),
        el("p", { class: "small muted", style: "margin:0 0 8px" }, "Für diesen Bereich gehen Fotos und Text nicht an Claude. Übernimm den erkannten Text als Notiz und sichere."),
        res.text ? el("p", { class: "small", style: "white-space:pre-wrap" }, res.text.slice(0, 600)) : el("p", { class: "small muted" }, res.texterkennung.hinweis || "Kein Text erkannt."),
        el("div", { class: "actions" },
          res.text ? el("button", { type: "button", onclick: () => { textarea.value = capture.text = (textarea.value ? textarea.value + "\n" : "") + res.text; sichernLokal(); fill(fotoPanel); textarea.focus(); } }, "Als Notiz übernehmen") : null,
          nurAnhaengen())));
    }
  }

  // ---------------------------------------------------------- Zeichnen
  renderChips();
  updateModus();
  renderThumbs();
  // Notizfeld zuerst: Tageskarten (Woche, Wiedersehen …) stehen darunter und verdrängen das Erfassen nicht.
  // Zähler: kompakt über dem Notizfeld, aktualisiert sich nach jedem Sichern
  const zaehlerSlot = el("div", { id: "zaehler" });
  const zeigeZaehler = (s) => { if (s && zaehlerSlot.isConnected !== false) fill(zaehlerSlot, zaehlerKarte(s)); };
  zeigeZaehler(statistikSofort());
  const abmelden = aufZaehler((s) => { if (!render.aktiv()) { abmelden(); return; } zeigeZaehler(s); });
  const ok = render(grosserTitel("Erfassen"), zaehlerSlot, oben, composer, fotoIn, notizZeile, ergebnis, tagesSlot);
  if (!ok) return;
  fokusAufTitel();

  // Läuft noch ein Entwurf aus einer vorherigen Sitzung? Dann dort weitermachen.
  const laufend = store.get("lv-laufend");
  if (laufend) {
    api(`/api/entwuerfe/${laufend}`).then((e) => zeigeEintrag(e)).catch(() => store.remove("lv-laufend"));
  } else {
    heuteKarte(tagesSlot, textarea);
  }

  // Frische Daten nachladen, ohne die Seite neu aufzubauen
  Promise.all([status().catch(() => st), bereiche(true).catch(() => bereichListe)]).then(([s, b]) => {
    if (!render.aktiv()) return;
    st = s;
    bereichListe = b;
    renderChips();
    updateModus();
  });
}

// ---------------------------------------------------------------- Tageskarten
// Höchstens eine Karte über dem Notizfeld, damit die Seite ruhig bleibt.
async function heuteKarte(slot, textarea) {
  const s = (await refreshStats()) || statistikSofort();
  if (!s || slot.childNodes.length) return;
  const vorbelegen = (text) => {
    textarea.value = text;
    textarea.dispatchEvent(new Event("input"));
    textarea.focus();
    textarea.setSelectionRange(text.length, text.length);
  };
  const karte = ernteKarte(s) || offeneSchleife(vorbelegen) || wochenKarte(s, vorbelegen) || await wiedersehenKarte(s) || eingangHinweis(s);
  if (karte && !slot.childNodes.length) fill(slot, karte);
}

function schliessen(karte, key, wert) {
  return el("button", { type: "button", class: "icon-btn", "aria-label": "Karte ausblenden", onclick: () => { store.set(key, wert); karte().remove(); } }, icon("x"));
}

function ernteKarte(s) {
  const bestand = s.gesamt + s.offene_entwuerfe;
  const aus = store.get("lv-ernte-aus");
  if (bestand >= 20 || (aus && Date.now() - Number(aus) < 3 * 86400000)) return null;
  let karte;
  const kopfzeile = el("div", { class: "card-head" },
    el("p", { class: "overline grow" }, s.gesamt === 0 ? "Willkommen" : "Dein Startbestand"),
    schliessen(() => karte, "lv-ernte-aus", String(Date.now())));
  karte = el("div", { class: "card tinted" }, kopfzeile,
    s.gesamt === 0
      ? [el("p", { class: "lead" }, "Deine Erfahrung, im richtigen Moment wieder da."),
        el("p", { class: "small muted", style: "margin:8px 0 0" }, "Starte mit deinen ersten 20 Einträgen: Die App stellt dir Fragen, du antwortest in Stichworten, Claude strukturiert. Etwa 10 Minuten.")]
      : [el("p", { class: "lead" }, `Noch ${20 - bestand} bis zu deinen ersten 20.`),
        el("div", { class: "progress own", "aria-hidden": "true" }, el("span", { style: `width:${(bestand / 20) * 100}%` }))],
    el("div", { class: "actions" }, el("a", { class: "button primary", href: "#/ernte" }, icon("sprout"), s.gesamt === 0 ? "Startbestand anlegen" : "Weiter")));
  return karte;
}

function offeneSchleife(vorbelegen) {
  const offen = store.json("lv-offen", null);
  if (!offen) return null;
  const alter = Date.now() - offen.t;
  if (alter < 12 * 3600000) return null;
  if (alter > 14 * 86400000) { store.remove("lv-offen"); return null; }
  let karte;
  karte = el("div", { class: "card tinted" },
    el("div", { class: "card-head" }, el("p", { class: "overline grow" }, "Offene Frage"), el("button", { type: "button", class: "icon-btn", "aria-label": "Karte ausblenden", onclick: () => { store.remove("lv-offen"); karte.remove(); } }, icon("x"))),
    el("p", { class: "lead" }, `Wie lief „${kuerzen(offen.situation, 70)}“? Was nimmst du mit?`),
    offen.plan ? el("p", { class: "small muted", style: "margin:6px 0 0" }, "Gleich den Plan abgleichen: Was hat gestimmt, was lief anders? Das bestätigt deine Einträge und macht aus Abweichungen neue.") : null,
    el("div", { class: "actions", style: "flex-wrap:wrap" },
      offen.plan ? el("a", { class: "button primary", href: `#/briefing/${offen.id}?rueckschau=1`, onclick: () => { karte.remove(); } }, icon("refresh", "icon sm"), "Rückschau zum Plan") : null,
      el("button", { type: "button", class: offen.plan ? "" : "primary", onclick: () => { store.remove("lv-offen"); karte.remove(); vorbelegen(`Nach „${kuerzen(offen.situation, 60)}“: `); } }, "Jetzt notieren"),
      el("button", { type: "button", class: "text", onclick: () => { store.remove("lv-offen"); karte.remove(); } }, "Nichts Neues")));
  return karte;
}

const LEITFRAGEN = ["Was hat dich diese Woche überrascht?", "Was würdest du anders machen?", "Was hat gut funktioniert?"];
const BREMSEN = ["Warten auf Claude", "Das Formular", "Datenschutz-Hinweise", "Vergessen", "Nichts"];

function wochenKarte(s, vorbelegen) {
  const tag = new Date().getDay();
  if (![5, 6, 0].includes(tag) || store.get("lv-rueckblick") === wochenSchluessel()) return null;
  let karte;
  const ersteNutzung = Number(store.get("lv-erste-nutzung", String(Date.now())));
  const bremse = Date.now() - ersteNutzung > 6 * 86400000 && store.get("lv-bremse") !== wochenSchluessel()
    ? el("div", { style: "margin-top:16px" },
      el("p", { class: "overline", id: "bremse-label" }, "Was hat dich gebremst?"),
      el("div", { class: "chips", role: "group", "aria-labelledby": "bremse-label" }, BREMSEN.map((b) => el("button", {
        type: "button", class: "chip",
        onclick: async (e) => {
          store.set("lv-bremse", wochenSchluessel());
          const gruppe = e.currentTarget.parentElement.parentElement;
          try { await api("/api/rueckmeldung", { method: "POST", body: { art: "bremse", wert: b } }); } catch { /* optional */ }
          fill(gruppe, el("p", { class: "footnote row", style: "gap:6px" }, icon("check", "icon sm"), "Danke, das fließt in die nächste Verbesserung ein."));
        },
      }, b))))
    : null;
  karte = el("div", { class: "card tinted" },
    el("div", { class: "card-head" }, el("p", { class: "overline grow" }, "Deine Woche"), schliessen(() => karte, "lv-rueckblick", wochenSchluessel())),
    el("p", { class: "lead" }, `${s.neu_erfasst_7_tage} neu · ${s.bestaetigt_7_tage} erneut erlebt`),
    el("p", { class: "footnote" }, `In ${s.aktive_wochen} der letzten ${s.wochen_betrachtet} Wochen aktiv.`),
    el("p", { class: "overline", style: "margin-top:16px" }, "Was nimmst du mit?"),
    el("div", { class: "chips" }, LEITFRAGEN.map((f) => el("button", { type: "button", class: "chip", onclick: () => vorbelegen(`${f} `) }, f))),
    bremse,
    el("div", { class: "actions" },
      el("button", { type: "button", class: "text", onclick: () => { store.set("lv-rueckblick", wochenSchluessel()); karte.remove(); } }, icon("check", "icon sm"), "Woche abschließen")));
  return karte;
}

async function wiedersehenKarte(s) {
  if (s.gesamt < 5) return null;
  const merk = store.json("lv-wiedersehen", {});
  if (merk.tag === heute()) return null;
  let l;
  try { l = await api(`/api/wiedersehen?tag=${heute()}`); } catch { return null; }
  if (!l) return null;
  const erledigt = () => { store.setJson("lv-wiedersehen", { tag: heute() }); karte.remove(); };
  const karte = el("div", { class: "card" },
    el("p", { class: "overline" }, "Erinnerst du dich?"),
    el("p", { class: `quote ${l.spezifisch ? "own" : ""}` }, anf(l.lesson)),
    el("p", { class: "footnote" }, el("a", { href: `#/lesson/${l.id}` }, anf(l.titel)), ` · ${l.bereich}`),
    el("div", { class: "actions" },
      el("button", { type: "button", onclick: () => { erledigt(); say("Gut, bleibt so."); } }, "Gilt noch"),
      el("button", { type: "button", onclick: () => { erledigt(); location.hash = `#/lesson/${l.id}/bearbeiten`; } }, "Schärfen"),
      el("button", {
        type: "button", class: "text",
        onclick: async () => {
          erledigt();
          try {
            await api(`/api/lessons/${l.id}`, { method: "PUT", body: { status: "überholt" } });
            toast("Als überholt markiert.", { aktion: { text: "Rückgängig", onclick: () => api(`/api/lessons/${l.id}`, { method: "PUT", body: { status: l.status } }).catch(() => {}) } });
          } catch (err) { toast(err.message, { fehler: true }); }
        },
      }, "Überholt")));
  return karte;
}

function eingangHinweis(s) {
  if (!s.offene_entwuerfe) return null;
  return el("a", { class: "card result row", href: "#/eingang", style: "gap:12px" },
    icon("inbox"), el("span", { class: "grow" }, `${s.offene_entwuerfe} Notiz${s.offene_entwuerfe > 1 ? "en warten" : " wartet"} im Eingang`), icon("chevron-right", "icon sm"));
}

// ---------------------------------------------------------------- Ernte-Modus (Startbestand)
const FRAGEN = {
  Beruf: [
    "Was lief beim letzten Cutover anders als geplant?",
    "Welche Frage hättest du im Kickoff stellen sollen?",
    "Wann kam eine Eskalation zu spät, und woran hättest du es früher erkannt?",
    "Was unterschätzen Kunden bei der Datenmigration fast immer?",
    "Welcher Test hat ein großes Problem verhindert, oder hätte es verhindert?",
    "Was machst du heute in der Hypercare anders als früher?",
    "Welche Absprache hättest du schriftlich festhalten sollen?",
    "Womit hat dich ein Steering Committee überrascht?",
    "Was würdest du jemandem vor dem ersten Go-live sagen?",
    "Welche Annahme in einer Aufwandsschätzung war falsch?",
  ],
  Immobilien: [
    "Was prüfst du bei der nächsten Besichtigung zuerst?",
    "Was hat dich bei einem Bankgespräch überrascht?",
    "Welche Unterlage hat beim Kauf gefehlt oder kam zu spät?",
    "Welche Sanierung wurde teurer als geplant, und warum?",
    "Was hast du mit Mietern gelernt, das du vorher nicht wusstest?",
    "Was liest du in WEG-Protokollen heute genauer als früher?",
    "Welche Frage an den Makler hättest du früher stellen sollen?",
    "Wann hat dich ein Handwerkerangebot in die Irre geführt?",
    "Was hat beim Notartermin gefehlt oder Zeit gekostet?",
    "Welche Kennzahl hast du bei einer Kaufentscheidung zu wenig beachtet?",
  ],
  Trading: [
    "Wann hast du gegen deine eigenen Regeln gehandelt, und was ist passiert?",
    "Welcher Fehler hat dich am meisten gekostet?",
    "Welches Setup hat zuverlässig funktioniert?",
    "Wann hättest du früher aussteigen sollen?",
    "Was tust du heute vor jedem Trade, was du früher nicht getan hast?",
  ],
  Projekte: [
    "Was hättest du vor dem Start eines eigenen Projekts klären sollen?",
    "Welches Werkzeug hat dich mehr Zeit gekostet als gespart?",
    "Wo hat eine unklare Anforderung zu einem Umbau geführt?",
    "Woran ist ein Projekt eingeschlafen?",
    "Was würdest du beim nächsten Projekt sofort wieder genauso machen?",
  ],
  _: [
    "Was ist schiefgelaufen, das du hättest kommen sehen können?",
    "Welche Entscheidung würdest du heute anders treffen?",
    "Was hat besser funktioniert als erwartet?",
    "Welchen Rat hättest du gern früher bekommen?",
    "Was prüfst du heute immer, bevor du anfängst?",
  ],
};

export async function viewErnte(params = {}) {
  const render = ansicht();
  kopf("Startbestand", { text: "Erfassen", href: "#/erfassen" });
  const aktive = bereicheSofort().filter((b) => b.aktiv);
  let bereich = params.bereich || store.get("lv-ernte-bereich") || aktive[0]?.name || "Beruf";
  const pos = store.json("lv-ernte-pos", {});
  let gesichertHier = 0;
  const s = statistikSofort() || { gesamt: 0, offene_entwuerfe: 0 };

  const inhalt = el("div");
  const fortschritt = el("div");
  const zeigeFortschritt = () => {
    const n = Math.min(20, s.gesamt + s.offene_entwuerfe + gesichertHier);
    fill(fortschritt, el("p", { class: "footnote" }, `${n} von 20 für deinen Startbestand`),
      el("div", { class: "progress own", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "20", "aria-valuenow": String(n), "aria-label": "Fortschritt Startbestand" },
        el("span", { style: `width:${(n / 20) * 100}%` })));
  };

  const chips = el("div", { class: "chips", role: "group", "aria-label": "Bereich" });
  const renderChips = () => fill(chips, aktive.map((b) => el("button", {
    type: "button", class: "chip", "aria-pressed": String(b.name === bereich),
    onclick: () => { bereich = b.name; store.set("lv-ernte-bereich", bereich); renderChips(); frage(); },
  }, b.name)));

  function frage() {
    const fragen = FRAGEN[bereich] || FRAGEN._;
    const i = pos[bereich] || 0;
    if (i >= fragen.length) {
      fill(inhalt, el("div", { class: "card hero" },
        el("p", { class: "overline row", style: "gap:6px;color:var(--success)" }, icon("check", "icon sm"), `Fertig mit ${bereich}`),
        el("p", { style: "margin:0" }, "Deine Antworten werden gerade strukturiert und liegen dann im Eingang. Dort übernimmst du jede mit einem Tipp."),
        el("div", { class: "actions" },
          el("a", { class: "button primary", href: "#/eingang" }, icon("inbox"), "Zum Eingang"),
          el("button", { type: "button", class: "text", onclick: () => { pos[bereich] = 0; store.setJson("lv-ernte-pos", pos); frage(); } }, "Fragen wiederholen"))));
      return;
    }
    const id = "ernte-antwort";
    const feld = el("textarea", { id, class: "capture", placeholder: "Stichworte reichen. Ohne Namen von Kunden oder Personen." });
    const startZeit = Date.now();
    const weiter = (gesichert) => { pos[bereich] = i + 1; store.setJson("lv-ernte-pos", pos); if (gesichert) gesichertHier += 1; zeigeFortschritt(); frage(); inhalt.querySelector("textarea")?.focus(); };
    const sichernBtn = el("button", { type: "button", class: "primary" }, "Sichern und weiter");
    sichernBtn.addEventListener("click", async () => {
      const antwort = feld.value.trim();
      if (!antwort) { feld.setAttribute("aria-invalid", "true"); feld.focus(); say("Bitte kurz antworten oder überspringen."); return; }
      const notiz = { text: `${fragen[i]}\n${antwort}`, quelle: "text", bereich, erfassung_sekunden: Math.round((Date.now() - startZeit) / 1000) };
      if (istOffline()) { ausgangAdd(notiz); say("Auf dem iPhone gesichert."); return weiter(true); }
      sichernBtn.setAttribute("aria-disabled", "true");
      try {
        await api("/api/notiz", { method: "POST", body: notiz, timeoutMs: 15000 });
        say("Gesichert. Nächste Frage.");
        weiter(true);
      } catch (err) {
        sichernBtn.removeAttribute("aria-disabled");
        if (err.netz) { ausgangAdd(notiz); weiter(true); } else fill(fehler, errorNotice(err));
      }
    });
    const fehler = el("div");
    fill(inhalt, el("div", { class: "card hero" },
      el("p", { class: "overline" }, `Frage ${i + 1} von ${fragen.length} · ${bereich}`),
      el("label", { for: id, class: "lead", style: "margin:0 0 12px;font-weight:500" }, fragen[i]),
      el("div", { class: "composer" }, feld, el("div", { class: "tools" }, diktatKnopf(feld))),
      el("div", { class: "actions" }, sichernBtn, el("button", { type: "button", class: "text", onclick: () => weiter(false) }, "Überspringen")),
      fehler));
  }

  renderChips();
  zeigeFortschritt();
  frage();
  if (!render(grosserTitel("Startbestand"),
    el("p", { class: "muted", style: "margin-top:-8px" }, "Eine Frage nach der anderen. Antworte in Stichworten, Claude macht daraus Einträge. Du prüfst sie danach im Eingang."),
    fortschritt,
    aktive.length > 1 ? el("div", { style: "margin:16px 0" }, chips) : null,
    inhalt)) return;
  fokusAufTitel();
  refreshStats().then((neu) => { if (neu) { Object.assign(s, neu); gesichertHier = 0; zeigeFortschritt(); } });
}
