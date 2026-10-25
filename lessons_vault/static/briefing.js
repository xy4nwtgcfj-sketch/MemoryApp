// Briefing: vor einer Situation die eigenen Erfahrungen abrufen, auf Wunsch mit Claudes Fachwissen kombiniert.
import {
  anf, ansicht, api, bereicheSofort, bereiche, copyText, diktatKnopf, el, errorNotice, fill, fokusAufTitel,
  formatDate, fotoInput, fotosHochladen, grosserTitel, hinweisBox, icon, istPruefung, kopf, kuerzen, laden, leer,
  metaZeile, refreshStats, say, skeleton, store, thumbsRow, toast, debounce, ersetzenIn,
} from "./core.js";

const briefingState = {
  situation: "", bereich: "", modus: store.get("lv-briefing-modus", "kombiniert"),
  pptx: store.get("lv-briefing-pptx") === "1",
};
const pptxGeladen = new Set();  // je Briefing nur einmal automatisch herunterladen

// PowerPoint des Plans laden (lokal erzeugt). Der Token-Header verlangt fetch statt eines einfachen Links.
async function pptxLaden(id, situation) {
  const headers = {};
  const token = store.get("lv-token");
  if (token) headers.Authorization = "Bearer " + token;
  const res = await fetch("/api/briefing/" + encodeURIComponent(id) + "/pptx", { headers });
  if (!res.ok) {
    let text = "Fehler " + res.status;
    try { text = (await res.json()).detail || text; } catch { /* kein JSON */ }
    throw new Error(text);
  }
  const url = URL.createObjectURL(await res.blob());
  const name = "Briefing " + kuerzen(situation, 50).replace(/[\\/:*?"<>|]/g, "") + ".pptx";
  const a = el("a", { href: url, download: name, hidden: true });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 4000);
}

// Ausarbeitung (Markdown-light) sicher als DOM rendern: ## Überschrift, - Stichpunkt, **fett**, [[E:id]] als Quellenmarke
function ausarbeitungKnoten(text, titelVon) {
  const inline = (zeile) => {
    const teile = [];
    for (const stueck of zeile.split(/(\[\[E:[\w-]+\]\]|\*\*[^*]+\*\*)/)) {
      if (!stueck) continue;
      const marke = stueck.match(/^\[\[E:([\w-]+)\]\]$/);
      if (marke) {
        const titel = titelVon[marke[1]]?.titel || "eigener Eintrag";
        teile.push(el("a", { class: "marke-eigen", href: "#/lesson/" + marke[1], title: anf(titel), "aria-label": "Aus deinen Einträgen: " + anf(titel) }, icon("user", "icon sm"), "Eigenes"));
      } else if (/^\*\*[^*]+\*\*$/.test(stueck)) {
        teile.push(el("strong", {}, stueck.slice(2, -2)));
      } else {
        teile.push(stueck);
      }
    }
    return teile;
  };
  const knoten = [];
  let absatz = [];
  let liste = null;
  const absatzFertig = () => { if (absatz.length) { knoten.push(el("p", {}, inline(absatz.join(" ")))); absatz = []; } };
  for (const roh of String(text || "").split("\n")) {
    const zeile = roh.trim();
    if (!zeile) { absatzFertig(); liste = null; continue; }
    const kopf = zeile.match(/^#{1,4}\s+(.*)$/);
    const punkt = zeile.match(/^[-*•]\s+(.*)$/);
    if (kopf) { absatzFertig(); liste = null; knoten.push(el("h3", {}, kopf[1])); }
    else if (punkt) { absatzFertig(); if (!liste) { liste = el("ul", {}); knoten.push(liste); } liste.append(el("li", {}, inline(punkt[1]))); }
    else { liste = null; absatz.push(zeile); }
  }
  absatzFertig();
  return knoten;
}

function planText(situation, plan) {
  if (plan.ausarbeitung) {
    const luecken = (plan.luecken || []).length
      ? ["", "## Blind spots (not covered by your entries yet)", ...plan.luecken.map((l) => `- ${l.titel}: ${l.kern}`)]
      : [];
    return ["Briefing: " + situation, "", plan.zusammenfassung || "", "", plan.ausarbeitung.replace(/\s?\[\[E:[\w-]+\]\]/g, " (eigene Erfahrung)"), ...luecken].join("\n").trim();
  }
  const zeilen = [`Plan: ${situation}`, ""];
  if (plan.zusammenfassung) zeilen.push(plan.zusammenfassung, "");
  if (plan.besonderheiten.length) {
    zeilen.push("## Aus eigener Erfahrung anders als üblich");
    for (const b of plan.besonderheiten) zeilen.push(`- ${b.punkt}`);
    zeilen.push("");
  }
  for (const a of plan.abschnitte) {
    zeilen.push(`## ${a.titel}`);
    for (const p of a.punkte) zeilen.push(`- [ ] ${p.punkt}${p.quelle === "erfahrung" ? " (eigene Erfahrung)" : ""}`);
    zeilen.push("");
  }
  return zeilen.join("\n").trim();
}

function checklistText(situation, items) {
  return [`Checkliste: ${situation}`, "", ...items.map((i) => `- [ ] ${i.punkt}`)].join("\n");
}

export async function viewBriefing(id, params = {}) {
  const render = ansicht();
  kopf("Briefing");
  if (params.situation) briefingState.situation = params.situation;
  const situation = el("textarea", {
    id: "briefing-text",
    rows: 3,
    placeholder: "z. B. „Hypercare-Plan für ein SAP-EWM-Projekt“ oder „Besichtigung in Wuppertal morgen“",
    oninput: () => { briefingState.situation = situation.value; situation.removeAttribute("aria-invalid"); },
  });
  situation.value = briefingState.situation;
  const fehler = el("p", { class: "feld-fehler", id: "briefing-fehler" });
  const result = el("div", { id: "briefing-result" });
  const entwurfPanel = el("div");
  let bereichListe = bereicheSofort().filter((b) => b.aktiv);
  const chips = el("div", { class: "chips", role: "group", "aria-label": "Bereich (optional)" });
  const renderChips = () => fill(chips, bereichListe.map((b) => el("button", {
    type: "button",
    class: "chip",
    "aria-pressed": String(briefingState.bereich === b.name),
    onclick: () => { briefingState.bereich = briefingState.bereich === b.name ? "" : b.name; renderChips(); },
  }, briefingState.bereich === b.name ? icon("check") : null, b.name)));
  renderChips();
  bereiche().then((b) => { bereichListe = b.filter((x) => x.aktiv); renderChips(); }).catch(() => {});

  const mic = diktatKnopf(situation, { onResult: (t) => { briefingState.situation = t; } });
  const goBtn = el("button", { type: "button", class: "primary block" }, "Briefing erstellen");
  const pruefBtn = el("button", { type: "button", class: "icon-btn", "aria-label": "Plan gegenchecken: Foto eines Entwurfs mit deinen Erfahrungen abgleichen", title: "Plan gegenchecken" }, icon("camera"));

  // Nach dem Erstellen klappt die Eingabe zu einer Zeile zusammen, damit das Ergebnis oben steht.
  const formular = el("div", { class: "card" },
    el("label", { for: "briefing-text", style: "margin-top:0" }, "Was steht an?"),
    el("div", { class: "composer" }, situation, el("div", { class: "tools" }, mic, pruefBtn)),
    fehler,
    el("p", { class: "hint" }, "Ein Satz genügt. Mit der Kamera prüfst du einen fertigen Plan gegen deine Erfahrung."),
    bereichListe.length > 1 || bereicheSofort().length > 1 ? el("div", { style: "margin-top:12px" }, chips) : null,
    el("div", { class: "row", style: "margin-top:16px;gap:12px" },
      el("label", { for: "pptx-schalter", class: "grow", style: "margin:0;font-weight:500" }, "Auch als PowerPoint",
        el("span", { class: "li-sub" }, "Lädt den Plan nach dem Erstellen als .pptx herunter")),
      el("input", {
        type: "checkbox", role: "switch", class: "switch", id: "pptx-schalter", checked: briefingState.pptx,
        onchange: (e) => { briefingState.pptx = e.target.checked; store.set("lv-briefing-pptx", e.target.checked ? "1" : "0"); },
      })),
    el("div", { class: "actions", style: "margin-bottom:0" }, goBtn));
  const kurz = el("div", { class: "card flat row", hidden: true });
  const einklappen = (text) => {
    formular.hidden = true;
    kurz.hidden = false;
    fill(kurz, icon("clipboard-list"), el("p", { class: "grow", style: "margin:0;font-weight:500" }, `„${kuerzen(text, 90)}“`),
      el("button", { type: "button", class: "text", onclick: () => { formular.hidden = false; kurz.hidden = true; situation.focus(); } }, icon("pencil", "icon sm"), "Ändern"));
  };

  const go = async () => {
    const text = situation.value.trim();
    if (text.length < 3) {
      situation.setAttribute("aria-invalid", "true");
      situation.setAttribute("aria-describedby", "briefing-fehler");
      fehler.textContent = "Beschreib kurz, was ansteht.";
      situation.focus();
      say(fehler.textContent);
      return;
    }
    fill(fehler);
    goBtn.setAttribute("aria-disabled", "true");
    fill(result, skeleton("Suche passende Erfahrungen …"));
    say("Suche passende Erfahrungen.");
    try {
      const data = await api("/api/briefing", { method: "POST", body: { situation: text, bereich: briefingState.bereich, modus: briefingState.modus } });
      if (!render.aktiv()) return;
      history.replaceState(null, "", `#/briefing/${data.id}`);
      store.setJson("lv-offen", { id: data.id, situation: text, t: Date.now() });
      einklappen(text);
      showBriefing(result, data, params);
      refreshStats({ anlass: `Briefing erstellt · ${data.treffer.length} eigene Einträge gefunden` });
    } catch (err) {
      fill(result, errorNotice(err, { erneut: go }));
    } finally {
      goBtn.removeAttribute("aria-disabled");
    }
  };
  goBtn.addEventListener("click", go);

  // Plan gegenchecken: Foto eines Entwurfs gegen die eigenen Lessons abgleichen
  const briefingMitFotos = async (bilder, entwurfText = "") => {
    fill(entwurfPanel);
    fill(result, skeleton("Gleiche den Entwurf mit deinen Erfahrungen ab …"));
    try {
      const data = await api("/api/briefing", {
        method: "POST",
        body: { situation: situation.value.trim(), bereich: briefingState.bereich, modus: briefingState.modus, bild_ids: bilder.map((b) => b.id), entwurf_text: entwurfText },
      });
      if (!render.aktiv()) return;
      history.replaceState(null, "", `#/briefing/${data.id}`);
      einklappen(data.situation);
      showBriefing(result, data);
    } catch (err) {
      fill(result, errorNotice(err));
    }
  };
  const pruefIn = fotoInput(async (files) => {
    pruefBtn.setAttribute("aria-disabled", "true");
    fill(entwurfPanel, laden("Fotos werden hochgeladen und gelesen …"));
    try {
      const bilder = await fotosHochladen(files);
      const vor = await api("/api/foto/vorbereiten", { method: "POST", body: { bild_ids: bilder.map((b) => b.id), bereich: briefingState.bereich } });
      if (vor.weg !== "text") return briefingMitFotos(bilder);
      const area = el("textarea", { rows: 8, id: "ocr-text" });
      area.value = vor.text;
      const box = hinweisBox(vor.compliance_hinweise || [], { anwenden: (r) => { area.value = ersetzenIn(area.value, r.von, r.nach); } });
      area.addEventListener("input", debounce(async () => {
        try { box.update(await api("/api/compliance", { method: "POST", body: { text: area.value, bereich: briefingState.bereich || "Beruf" } })); } catch { /* bleibt */ }
      }, 600));
      fill(entwurfPanel, el("div", { class: "card" },
        thumbsRow(bilder),
        el("p", { class: "overline" }, "Erkannter Text des Entwurfs"),
        el("p", { class: "small muted", style: "margin:0 0 8px" }, "Nur dieser Text geht für den Abgleich an Claude, das Foto bleibt auf deinem PC. Lösche, was nicht raus soll."),
        vor.text ? null : el("div", { class: "notice warn" }, icon("alert"), el("div", {}, vor.texterkennung.verfuegbar ? "Kein Text erkannt. Tippe die Kernpunkte ab." : vor.texterkennung.hinweis)),
        box.node,
        el("label", { for: "ocr-text", class: "sr-only" }, "Erkannter Text"), area,
        el("div", { class: "actions" }, el("button", { type: "button", class: "primary", onclick: () => briefingMitFotos(bilder, area.value) }, "Gegenchecken"))));
    } catch (err) {
      fill(entwurfPanel, errorNotice(err));
    } finally {
      pruefBtn.removeAttribute("aria-disabled");
    }
  });
  pruefBtn.addEventListener("click", () => pruefIn.click());

  if (!render(grosserTitel("Briefing"), formular, kurz, pruefIn, entwurfPanel, result)) return;
  fokusAufTitel();

  if (id) {
    fill(result, skeleton());
    try {
      const data = await api(`/api/briefing/${encodeURIComponent(id)}`);
      situation.value = briefingState.situation = data.entwurf_weg ? "" : data.situation;
      einklappen(data.situation);
      showBriefing(result, data, params);
    } catch (err) {
      fill(result, errorNotice(err));
    }
  } else {
    showVerlauf(result);
  }
}

async function showVerlauf(container) {
  try {
    const verlauf = await api("/api/briefings?limit=10");
    if (!verlauf.length) return;
    fill(container,
      el("h2", {}, "Frühere Briefings"),
      el("ul", { class: "list" }, verlauf.map((b) => el("li", { class: "li", style: "padding:0" },
        el("a", { class: "li grow", href: `#/briefing/${b.id}`, style: "box-shadow:none" },
          b.entwurf_weg ? icon("camera") : icon("clipboard-list"),
          el("span", { class: "grow" }, anf(kuerzen(b.situation, 90)),
            el("span", { class: "li-sub" }, formatDate(b.erstellt_am), ` · ${b.anzahl} Einträge`, b.hilfreich ? ` · ${b.hilfreich} hilfreich` : "", b.bereich ? ` · ${b.bereich}` : "",
              b.rueckschau ? el("span", { class: "rs-marke" }, icon("check", "icon sm"), "Rückschau") : b.plan ? " · Rückschau offen" : "")),
          icon("chevron-right", "icon sm chev"))))));
  } catch { /* Verlauf ist optional */ }
}

function showBriefing(container, data, params = {}) {
  const istEntwurf = Boolean(data.entwurf_weg);
  const istPlan = data.modus === "kombiniert" && !istEntwurf;
  const titelVon = Object.fromEntries(data.treffer.map((t) => [t.lesson.id, t.lesson]));
  const rueckschauSlot = el("div");
  const lueckenSlot = el("div");
  const feedback = { ...data.feedback };
  const max = data.treffer[0]?.relevanz || 0;
  const stark = data.treffer.filter((t, i) => i < 4 && t.relevanz >= 0.6 * max);
  const weitere = data.treffer.filter((t) => !stark.includes(t));

  if (!data.treffer.length && !(istPlan && (data.ki_moeglich || data.plan))) {
    fill(container,
      data.bilder?.length ? el("div", { class: "card" }, el("p", { class: "overline" }, "Geprüfter Entwurf"), thumbsRow(data.bilder)) : null,
      leer({ symbol: "lightbulb", titel: "Dazu hast du noch nichts gespeichert", text: "Probier andere Stichworte oder ohne Bereich. Oder halte jetzt fest, was du darüber weißt." }),
      lueckenKarte(data));
    return;
  }

  // Aktueller Inhalt zum Kopieren (Plan oder Checkliste)
  let kopierText = checklistText(data.situation, data.checkliste);
  const kopierenBtn = el("button", {
    type: "button", class: "text",
    onclick: async () => { const ok = await copyText(kopierText); toast(ok ? "In die Zwischenablage kopiert." : "Kopieren nicht möglich.", { fehler: !ok }); },
  }, icon("copy", "icon sm"), "Kopieren");
  const modusSchalter = istEntwurf ? null : el("input", {
    type: "checkbox", role: "switch", class: "switch", id: "modus-schalter", checked: data.modus === "kombiniert",
    onchange: (e) => {
      const neu = e.target.checked ? "kombiniert" : "eigen";
      briefingState.modus = neu;
      store.set("lv-briefing-modus", neu);
      say(neu === "kombiniert" ? "Mit Claude-Fachwissen." : "Nur deine Erfahrung.");
      showBriefing(container, { ...data, zusammenfassung: "", plan: null, ki_checkliste: null, modus: neu, _wechsel: true });
    },
  });
  const kopfZeile = el("div", { class: "row", style: "margin:8px 0 12px;flex-wrap:wrap" },
    modusSchalter ? el("label", { for: "modus-schalter", class: "row grow", style: "margin:0;gap:10px;font-weight:500" }, modusSchalter, "Mit Claude-Fachwissen") : el("span", { class: "grow" }),
    kopierenBtn);

  const summaryCard = el("div", { class: "card hero" });
  const eigeneSlot = el("div");
  const besonderheitenSlot = el("div");
  const kennzahlenSlot = el("div");
  const planSlot = el("div");
  const beruecksichtigtSlot = el("div");
  const titelText = istEntwurf ? "Abgleich mit deinen Erfahrungen" : "Worauf es ankommt";

  // Mit Claude-Fachwissen ist das Briefing lang. Vier Abschnitte statt einer Endlosseite:
  // Überblick, Ausarbeitung (mit blinden Flecken), Deine Einträge, Rückschau.
  const abschnitte = { ueberblick: el("div"), ausarbeitung: el("div"), eigene: el("div"), rueckschau: el("div") };
  const segKnoepfe = {};
  let aktiverAbschnitt = params.rueckschau === "1" ? "rueckschau" : "ueberblick";
  const zeigeAbschnitt = (k, scrollen = false) => {
    aktiverAbschnitt = k;
    for (const [key, node] of Object.entries(abschnitte)) node.hidden = key !== k;
    for (const [key, b] of Object.entries(segKnoepfe)) b.setAttribute("aria-pressed", String(key === k));
    if (scrollen) {
      const oben = segmente.getBoundingClientRect().top + window.scrollY - 60;
      if (window.scrollY > oben) window.scrollTo({ top: oben, behavior: "auto" });
    }
  };
  const segmente = el("div", { class: "segmented segmente", role: "group", "aria-label": "Abschnitte des Briefings" },
    [["ueberblick", "Überblick"], ["ausarbeitung", "Ausarbeitung"], ["eigene", "Einträge"], ["rueckschau", "Rückschau"]].map(([k, t]) => {
      const b = el("button", { type: "button", "aria-pressed": String(k === aktiverAbschnitt), onclick: () => zeigeAbschnitt(k, true) }, t,
        k === "eigene" && data.treffer.length ? el("small", {}, String(data.treffer.length)) : null,
        k === "rueckschau" && data.rueckschau ? icon("check", "icon sm") : null);
      segKnoepfe[k] = b;
      return b;
    }));

  // Eigene Lessons als Karten mit Feedback (Daumen hoch/runter)
  const lessonKarte = (t) => {
    const l = t.lesson;
    const card = el("div", { class: `card result ${feedback[l.id] === "nicht_relevant" ? "abgewertet" : ""}`, "data-id": l.id });
    const up = el("button", { type: "button", class: "up", "aria-label": `„${kuerzen(l.titel, 50)}“ war hilfreich` }, icon("thumbs-up"));
    const down = el("button", { type: "button", class: "down", "aria-label": `„${kuerzen(l.titel, 50)}“ passt nicht` }, icon("thumbs-down"));
    const sync = () => {
      up.setAttribute("aria-pressed", String(feedback[l.id] === "hilfreich"));
      down.setAttribute("aria-pressed", String(feedback[l.id] === "nicht_relevant"));
      card.classList.toggle("abgewertet", feedback[l.id] === "nicht_relevant");
    };
    const send = async (bewertung) => {
      const neu = feedback[l.id] === bewertung ? "" : bewertung;
      try {
        const res = await api(`/api/briefing/${data.id}/feedback`, { method: "POST", body: { lesson_id: l.id, bewertung: neu } });
        Object.keys(feedback).forEach((k) => delete feedback[k]);
        Object.assign(feedback, res);
        sync();
        say(neu === "hilfreich" ? "Als hilfreich markiert." : neu ? "Als unpassend markiert." : "Markierung entfernt.");
        if (neu === "hilfreich") refreshStats({ anlass: "Dein Eintrag hat dir geholfen. Genau dafür sammelst du." });
      } catch (err) { toast(err.message, { fehler: true }); }
    };
    up.addEventListener("click", () => send("hilfreich"));
    down.addEventListener("click", () => send("nicht_relevant"));
    sync();
    fill(card,
      el("div", { class: "card-head" },
        el("a", { class: "grow", href: `#/lesson/${l.id}`, style: "color:inherit;text-decoration:none" }, el("h3", {}, anf(l.titel))),
        el("span", { class: "relevanz", title: "Relevanz" }, `${Math.round(t.relevanz * 100)} %`)),
      el("p", { class: `quote ${l.spezifisch ? "own" : ""}`, style: "font-size:1rem;font-weight:400;margin-top:6px" }, anf(l.lesson)),
      l.massnahme ? el("p", { class: "small", style: "margin:8px 0 0" }, el("span", { class: "overline", style: "display:inline;margin-right:6px" }, "Nächstes Mal"), anf(l.massnahme)) : null,
      metaZeile(l, { datum: false }),
      el("div", { class: "feedback", role: "group", "aria-label": `War „${kuerzen(l.titel, 50)}“ hilfreich?` }, up, down));
    return card;
  };

  const renderEigene = (besonderheiten = []) => {
    const abweichungen = besonderheiten.length ? el("div", { class: "card own" },
      el("p", { class: "overline", style: "color:var(--own)" }, "Hier weichst du vom Üblichen ab"),
      el("ul", { class: "checklist" }, besonderheiten.map((b) => el("li", {},
        el("span", {}, anf(b.punkt), titelVon[b.lesson_id] ? el("a", { class: "src eigen", href: `#/lesson/${b.lesson_id}` }, icon("user"), anf(titelVon[b.lesson_id].titel)) : null))))) : null;
    // Im Plan stehen die Abweichungen im Überblick, sonst über den eigenen Karten
    fill(besonderheitenSlot, istPlan ? abweichungen : null);
    fill(eigeneSlot,
      data.treffer.length && !istPlan ? el("h2", { class: "row", style: "gap:8px" }, icon("user"), "Aus deinen Einträgen") : null,
      istPlan ? null : abweichungen,
      stark.map(lessonKarte),
      data.treffer.length ? el("p", { class: "footnote" }, "Markiere, was geholfen hat. Das verbessert künftige Briefings.") : null);
  };

  // Planpunkt aus eigener Erfahrung: antippen zeigt die Regel, "Passt nicht" zählt als Feedback.
  const quellenKnopf = (lid) => {
    const l = titelVon[lid];
    if (!l) return el("span", { class: "src eigen" }, icon("user"), "Dein Eintrag");
    const detail = el("div", { class: "src-detail", hidden: true },
      el("p", { style: "margin:0" }, anf(l.lesson)),
      el("div", { class: "row", style: "margin-top:6px;gap:4px" },
        el("a", { class: "button text", href: `#/lesson/${l.id}`, style: "padding-left:0" }, "Ansehen"),
        el("button", { type: "button", class: "text", onclick: async (e) => {
          try {
            const res = await api(`/api/briefing/${data.id}/feedback`, { method: "POST", body: { lesson_id: l.id, bewertung: "nicht_relevant" } });
            Object.keys(feedback).forEach((k) => delete feedback[k]);
            Object.assign(feedback, res);
            e.currentTarget.replaceWith(el("span", { class: "footnote" }, "Vermerkt, danke."));
            container.querySelector(`.result[data-id="${l.id}"]`)?.classList.add("abgewertet");
          } catch (err) { toast(err.message, { fehler: true }); }
        } }, "Passt nicht")));
    const knopf = el("button", { type: "button", class: "src eigen", "aria-expanded": "false", onclick: () => {
      detail.hidden = !detail.hidden;
      knopf.setAttribute("aria-expanded", String(!detail.hidden));
    } }, icon("user"), `Deine Erfahrung: ${kuerzen(anf(l.titel), 60)}`);
    return [knopf, detail];
  };

  const renderPlan = (plan) => {
    kopierText = planText(data.situation, plan);
    const alle = plan.abschnitte.flatMap((a) => a.punkte);
    let n = 0;
    const pptxBtn = el("button", {
      type: "button",
      onclick: async (e) => {
        const knopf = e.currentTarget;
        knopf.setAttribute("aria-disabled", "true");
        try { await pptxLaden(data.id, data.situation); toast("PowerPoint erstellt."); }
        catch (err) { toast(err.message, { fehler: true }); }
        finally { knopf.removeAttribute("aria-disabled"); }
      },
    }, icon("download", "icon sm"), "Als PowerPoint");
    const ausarbeitung = plan.ausarbeitung
      ? el("div", { class: "card ausarbeitung" },
        el("div", { class: "legend footnote", style: "margin:0 0 8px" },
          el("span", { class: "src eigen", style: "margin:0" }, icon("user"), "Markiert: aus deinen Einträgen"),
          el("span", { class: "src", style: "margin:0" }, icon("sparkles"), "Übriges: Claudes Fachwissen, nicht geprüft")),
        ausarbeitungKnoten(plan.ausarbeitung, titelVon))
      : null;
    const checkliste = el(ausarbeitung ? "details" : "div", { class: "card" },
        ausarbeitung ? el("summary", {}, "Als Checkliste abhaken (" + alle.length + " Punkte)") : null,
        el("div", { class: "legend footnote" },
          el("span", { class: "src eigen", style: "margin:0" }, icon("user"), `${plan.punkte_erfahrung} aus deinen Einträgen`),
          el("span", { class: "src", style: "margin:0" }, icon("sparkles"), `${alle.length - plan.punkte_erfahrung} aus Claudes Fachwissen, nicht geprüft`)),
        plan.abschnitte.map((a) => [
          el("h3", { class: "overline plan-section" }, a.titel),
          el("ul", { class: "checklist" }, a.punkte.map((p) => {
            const cid = `pl-${n++}`;
            return el("li", {},
              el("input", { type: "checkbox", id: cid }),
              el("div", { style: "flex:1;min-width:0" },
                el("label", { for: cid }, el("span", { class: "punkt" }, anf(p.punkt))),
                p.quelle === "erfahrung" ? quellenKnopf(p.lesson_id) : el("span", { class: "src" }, icon("sparkles"), "Claude")));
          })),
        ]));
    fill(planSlot,
      el("div", { class: "row", style: "margin:4px 0 12px;gap:8px" },
        el("h2", { class: "row grow", style: "gap:8px;margin:0" }, icon("clipboard-list"), ausarbeitung ? "Ausarbeitung" : "Plan"),
        pptxBtn),
      ausarbeitung,
      checkliste);
    fill(kennzahlenSlot, el("div", { class: "kennzahlen" },
      el("div", { class: "tile" }, el("p", { class: "num gold" }, String(data.treffer.length)), el("p", { class: "lbl" }, data.treffer.length === 1 ? "eigener Eintrag" : "eigene Einträge")),
      el("div", { class: "tile" }, el("p", { class: "num" }, String(alle.length)), el("p", { class: "lbl" }, "Punkte im Plan")),
      el("div", { class: "tile" }, el("p", { class: "num violett" }, String((plan.luecken || []).length)), el("p", { class: "lbl" }, "blinde Flecken"))));
    fill(lueckenSlot, lueckenAbschnitt(data, plan, titelVon));
    fill(rueckschauSlot, rueckschauKarte(data, plan, params.rueckschau === "1") || el("p", { class: "footnote" }, "Für dieses Briefing gibt es keine Planpunkte zum Abgleichen."));
    // Die offene Frage auf der Startseite führt später zur Rückschau dieses Plans
    const offen = store.json("lv-offen", null);
    if (offen && offen.id === data.id && !offen.plan) store.setJson("lv-offen", { ...offen, plan: true });
    // Auf Wunsch einmal automatisch als PowerPoint laden
    if (briefingState.pptx && !pptxGeladen.has(data.id)) {
      pptxGeladen.add(data.id);
      pptxLaden(data.id, data.situation).then(() => toast("PowerPoint erstellt.")).catch((err) => toast(err.message, { fehler: true }));
    }
  };

  const renderChecklist = (items, quelle) => {
    kopierText = checklistText(data.situation, items);
    fill(planSlot,
      el("h2", { class: "row", style: "gap:8px" }, icon("clipboard-list"), "Checkliste"),
      el("div", { class: "card" },
        el("p", { class: "footnote", style: "margin:0 0 4px" }, quelle),
        el("ul", { class: "checklist" }, items.map((item, i) => el("li", {},
          el("input", { type: "checkbox", id: `cl-${i}` }),
          el("div", { style: "flex:1;min-width:0" },
            el("label", { for: `cl-${i}` }, el("span", { class: "punkt" }, anf(item.punkt))),
            titelVon[item.lesson_id] ? el("a", { class: "src eigen", href: `#/lesson/${item.lesson_id}` }, icon("user"), kuerzen(anf(titelVon[item.lesson_id].titel), 60)) : null))))));
  };

  const loadSummary = async (neu = false, freigabe = false) => {
    fill(summaryCard, el("p", { class: "overline" }, titelText), el("p", { class: "waiting" }, el("span", { class: "spinner", "aria-hidden": "true" }),
      istEntwurf ? "Claude gleicht den Entwurf mit deinem Wissen ab …" : istPlan ? "Claude erstellt den Plan aus Fachwissen und deinen Erfahrungen …" : "Claude fasst deine Erfahrungen zusammen …"));
    say("Claude arbeitet, bitte warten.");
    try {
      const params = new URLSearchParams();
      if (neu) params.set("neu", "true");
      if (freigabe) params.set("freigabe", "true");
      if (!istEntwurf) params.set("modus", data.modus);
      const res = await api(`/api/briefing/${data.id}/zusammenfassung?${params}`, { method: "POST" });
      showSummary(res);
      say("Briefing fertig.");
    } catch (err) {
      if (istPruefung(err)) {
        fill(summaryCard, el("p", { class: "overline" }, titelText), el("div", { class: "notice warn" }, icon("shield"), el("div", {},
          el("strong", {}, err.message), el("ul", {}, err.hinweise.map((h) => el("li", {}, anf(h)))),
          el("div", { class: "actions" },
            el("button", { type: "button", onclick: () => { const f = document.getElementById("briefing-text"); f?.closest(".card")?.removeAttribute("hidden"); f?.focus(); } }, "Text anpassen"),
            err.code === "sperrliste" ? null : el("button", { type: "button", class: "text", onclick: () => loadSummary(neu, true) }, "Trotzdem senden")))));
        return;
      }
      fill(summaryCard, el("p", { class: "overline" }, titelText), errorNotice(err, { erneut: () => loadSummary(neu) }));
    }
  };

  const showSummary = (res) => {
    fill(summaryCard,
      el("p", { class: "overline" }, titelText),
      el("p", { class: "lead" }, anf(res.zusammenfassung) || "Claude sah keinen klaren Bezug zu dieser Situation. Die Einträge unten sind trotzdem die besten Treffer."),
      res.ki_hinweis ? el("p", { class: "footnote" }, res.ki_hinweis) : null);
    if (res.plan) {
      renderEigene(res.plan.besonderheiten || []);
      renderPlan(res.plan);
      if (res.plan.punkte_erfahrung) refreshStats({ anlass: `Dein Wissen hat gewirkt: ${res.plan.punkte_erfahrung} von ${res.plan.punkte_gesamt} Planpunkten kommen aus deinen Einträgen` });
      return;
    }
    renderEigene();
    if (istEntwurf) {
      renderChecklist(res.ki_checkliste || [], res.ki_checkliste?.length ? "Was im Entwurf fehlt, laut deinem Wissen (Claude)" : "Claude hat keine Lücken gefunden.");
      const ok = res.abgleich?.beruecksichtigt || [];
      fill(beruecksichtigtSlot, ok.length ? el("details", { class: "card" },
        el("summary", {}, `Schon berücksichtigt (${ok.length})`),
        el("ul", { class: "checklist" }, ok.map((p) => el("li", {}, icon("check"), el("span", {}, anf(p.punkt),
          titelVon[p.lesson_id] ? el("span", { class: "src eigen" }, icon("user"), anf(titelVon[p.lesson_id].titel)) : null))))) : null);
    } else if (res.ki_checkliste?.length) {
      renderChecklist(res.ki_checkliste, "Auf die Situation zugeschnitten (Claude, aus deinen Einträgen)");
    }
  };

  renderEigene();
  renderChecklist(data.checkliste, "Aus der Anwendung deiner Einträge");

  const fuss = el("p", { class: "footnote row", style: "gap:8px;margin-top:24px;align-items:flex-start" }, icon("info", "icon sm"),
    el("span", { class: "grow" }, data.ki_moeglich
      ? `An Claude gesendet: deine Situation${data.an_claude ? ` und ${data.an_claude} ${data.an_claude > 1 ? "Einträge" : "Eintrag"} (Titel, Kernaussage, Kontext, Inhalt, Anwendung)` : ""}${data.bilder?.length && data.entwurf_weg === "bild" ? " sowie die Fotos" : data.entwurf_weg === "text" ? " sowie der geprüfte Text des Fotos" : ""}.`
      : "Nichts an Claude gesendet."));
  const neuFormulieren = data.ki_moeglich ? el("button", { type: "button", class: "text", onclick: () => loadSummary(true) }, icon("refresh", "icon sm"), "Neu formulieren") : null;

  const ohneEigene = !data.treffer.length ? el("div", { class: "notice info" }, icon("info"), el("div", {}, el("strong", {}, "Dazu hast du noch keine eigenen Erfahrungen."), "Der Plan ist reines Fachwissen von Claude.")) : null;
  const summaryOderHinweis = data.ki_moeglich || data.zusammenfassung ? summaryCard : (data.ki_hinweis ? el("p", { class: "footnote" }, data.ki_hinweis) : null);
  const weitereBlock = weitere.length ? el("details", { class: "card", style: "margin-top:24px" },
    el("summary", {}, `Weitere, weniger passende Treffer (${weitere.length})`),
    weitere.map(lessonKarte)) : null;
  const einladung = (!data.treffer.length || (data.plan && !data.plan.punkte_erfahrung)) && !istEntwurf ? lueckenKarte(data) : null;
  const fussZeile = el("div", { class: "row", style: "flex-wrap:wrap" }, fuss, neuFormulieren);

  if (istPlan) {
    fill(rueckschauSlot, el("p", { class: "footnote" }, "Die Rückschau erscheint, sobald der Plan steht."));
    fill(abschnitte.ueberblick, ohneEigene, summaryOderHinweis, kennzahlenSlot, besonderheitenSlot);
    fill(abschnitte.ausarbeitung, planSlot, lueckenSlot);
    fill(abschnitte.eigene, eigeneSlot, einladung, weitereBlock);
    fill(abschnitte.rueckschau, rueckschauSlot);
    zeigeAbschnitt(aktiverAbschnitt);
    fill(container, el("div", {},
      data.bilder?.length ? el("div", { class: "card" }, el("p", { class: "overline" }, "Geprüfter Entwurf"), thumbsRow(data.bilder)) : null,
      kopfZeile, segmente,
      abschnitte.ueberblick, abschnitte.ausarbeitung, abschnitte.eigene, abschnitte.rueckschau,
      fussZeile));
  } else {
    fill(container, el("div", {},
      data.bilder?.length ? el("div", { class: "card" }, el("p", { class: "overline" }, "Geprüfter Entwurf"), thumbsRow(data.bilder)) : null,
      kopfZeile,
      ohneEigene,
      summaryOderHinweis,
      eigeneSlot,
      planSlot,
      beruecksichtigtSlot,
      einladung,
      weitereBlock,
      fussZeile));
  }
  if (data.zusammenfassung || data.plan) showSummary(data);
  else if (data.ki_moeglich || data._wechsel) loadSummary();
}

// Zielbereich für Übernahmen aus dem Briefing: gewählter Bereich, sonst der häufigste unter den Treffern
function zielBereich(data) {
  if (data.bereich) return data.bereich;
  const zaehler = {};
  for (const t of data.treffer) zaehler[t.lesson.bereich] = (zaehler[t.lesson.bereich] || 0) + 1;
  const haeufigster = Object.entries(zaehler).sort((a, b) => b[1] - a[1])[0]?.[0];
  return haeufigster || bereicheSofort().find((b) => b.aktiv)?.name || "Beruf";
}

// Blinde Flecken: Themen, zu denen die eigenen Einträge nichts sagen. Claude schließt die Lücke; ein Tipp
// macht daraus einen eigenen Wissenseintrag, oder man ergänzt gleich die eigene Erfahrung dazu.
function lueckenAbschnitt(data, plan, titelVon) {
  const luecken = plan.luecken || [];
  if (!luecken.length) return null;
  const bereich = zielBereich(data);
  const beruflich = Boolean(bereicheSofort().find((b) => b.name === bereich)?.beruflich);
  const karte = (l, i) => {
    const box = el("div", { class: "card luecke" });
    const fehlerSlot = el("div");
    const uebernehmen = el("button", { type: "button", class: "primary" }, icon("plus", "icon sm"), "Als Wissen übernehmen");
    uebernehmen.addEventListener("click", async () => {
      uebernehmen.setAttribute("aria-disabled", "true");
      try {
        const res = await api("/api/lessons", { method: "POST", body: {
          art: "wissen", titel: l.titel, situation: l.kontext || `Relevant for: ${data.situation}`, ereignis: l.wissen,
          lesson: l.kern, massnahme: l.anwendung || "", bereich, phase: beruflich ? (l.phase || "") : "",
          tags: [], schweregrad: 3, spezifisch: false, quelle: "text",
        } });
        fill(box,
          el("p", { class: "overline", style: "color:var(--success)" }, "Lücke geschlossen"),
          el("p", { class: "lead" }, anf(l.titel)),
          el("p", { class: "small muted", style: "margin:6px 0 0" }, `Liegt jetzt als Wissen in ${bereich}. Ergänze dort deine eigene Erfahrung, sobald du eine hast.`),
          el("div", { class: "actions" }, el("a", { class: "button text", href: `#/lesson/${res.lesson.id}` }, "Ansehen")));
        refreshStats({ anlass: `Lücke geschlossen: „${kuerzen(l.titel, 48)}“ ist jetzt dein Wissen` });
      } catch (err) {
        uebernehmen.removeAttribute("aria-disabled");
        fill(fehlerSlot, errorNotice(err));
      }
    });
    const feldId = `luecke-${data.id}-${i}`;
    const feld = el("textarea", { id: feldId, rows: 2, placeholder: "Deine Erfahrung dazu, ein Satz genügt." });
    const eigeneBox = el("div", { class: "luecke-eigen", hidden: true },
      el("label", { for: feldId, class: "sr-only" }, "Eigene Erfahrung"),
      el("div", { class: "composer" }, feld, el("div", { class: "tools" }, diktatKnopf(feld))),
      el("div", { class: "actions" }, el("button", { type: "button", class: "primary", onclick: async (e) => {
        const text = feld.value.trim();
        if (!text) { feld.setAttribute("aria-invalid", "true"); feld.focus(); return; }
        e.currentTarget.setAttribute("aria-disabled", "true");
        try {
          await api("/api/notiz", { method: "POST", body: { text: `On "${l.titel}" (${data.situation}): ${text}`, bereich } });
          fill(eigeneBox, el("p", { class: "row", style: "gap:6px;margin:8px 0 0;color:var(--success)" }, icon("check", "icon sm"), "Gesichert. Liegt strukturiert im Eingang."));
          refreshStats({ anlass: "Eigene Erfahrung zu einem blinden Fleck. Genau das macht dein Wissen einzigartig." });
        } catch (err) { e.currentTarget.removeAttribute("aria-disabled"); fill(fehlerSlot, errorNotice(err)); }
      } }, "Sichern")));
    const eigeneBtn = el("button", { type: "button", class: "text", "aria-expanded": "false", onclick: () => {
      eigeneBox.hidden = !eigeneBox.hidden;
      eigeneBtn.setAttribute("aria-expanded", String(!eigeneBox.hidden));
      if (!eigeneBox.hidden) feld.focus();
    } }, icon("user", "icon sm"), "Eigene Erfahrung dazu");
    fill(box,
      el("div", { class: "card-head" }, el("h3", { class: "grow" }, anf(l.titel)), l.phase ? el("span", { class: `badge phase ${l.phase}` }, l.phase) : null),
      el("p", { class: "quote", style: "font-size:1rem;font-weight:400;margin-top:4px" }, anf(l.kern)),
      el("details", { class: "luecke-wissen" },
        el("summary", {}, "Was Claude dazu weiß"),
        el("div", { class: "stack small" }, ausarbeitungKnoten(l.wissen, titelVon),
          l.anwendung ? el("p", {}, el("span", { class: "overline", style: "display:inline;margin-right:6px" }, "Anwendung"), anf(l.anwendung)) : null)),
      l.frage ? el("p", { class: "small muted luecke-frage" }, icon("lightbulb", "icon sm"), anf(l.frage)) : null,
      el("div", { class: "actions", style: "flex-wrap:wrap" }, uebernehmen, eigeneBtn),
      eigeneBox, fehlerSlot);
    return box;
  };
  return el("section", { class: "luecken" },
    el("h2", { class: "row", style: "gap:8px;margin-top:28px" }, icon("lightbulb"), "Blinde Flecken"),
    el("p", { class: "footnote", style: "margin:0 0 10px" }, `Dazu sagen deine Einträge noch nichts. Claude hat die ${luecken.length === 1 ? "Lücke" : `${luecken.length} Lücken`} mit Fachwissen geschlossen; übernimm es oder halte deine eigene Erfahrung fest.`),
    luecken.map(karte));
}

// Rückschau: Nach der Situation markieren, welche Planpunkte gestimmt haben. Bestätigt eigene Einträge,
// macht aus Abweichungen und bewährtem Fachwissen neue Einträge, und schließt so den Kreis.
function rueckschauKarte(data, plan, offen = false) {
  const alle = plan.abschnitte.flatMap((a) => a.punkte);
  if (!alle.length) return null;
  const titel = el("h2", { class: "row", style: "gap:8px;margin:4px 0 12px" }, icon("refresh"), "Rückschau");
  if (data.rueckschau) {
    const r = data.rueckschau;
    const bewertet = r.punkte.filter((p) => p.ergebnis);
    return el("section", {}, titel,
      el("div", { class: "card rueckschau fertig" },
        el("p", { class: "overline", style: "color:var(--success)" }, `Kreis geschlossen · ${formatDate(r.datum)}`),
        el("p", { class: "lead" }, `${r.bestaetigt} ${r.bestaetigt === 1 ? "Eintrag" : "Einträge"} bestätigt, ${r.entwuerfe} ${r.entwuerfe === 1 ? "neuer Entwurf" : "neue Entwürfe"} aus dieser Situation.`),
        bewertet.length ? el("ul", { class: "checklist rs-liste" }, bewertet.map((p) => el("li", {},
          icon(p.ergebnis === "bestaetigt" ? "check" : "x", `icon sm ${p.ergebnis === "bestaetigt" ? "ok" : "nein"}`),
          el("div", { class: "grow" }, el("span", { class: "punkt" }, anf(p.punkt)), p.notiz ? el("span", { class: "li-sub" }, anf(p.notiz)) : null)))) : null,
        r.fazit ? el("p", { class: "small", style: "margin-top:10px" }, el("span", { class: "overline", style: "display:inline;margin-right:6px" }, "Fazit"), anf(r.fazit)) : null,
        r.entwuerfe ? el("div", { class: "actions" }, el("a", { class: "button text", href: "#/eingang" }, "Zum Eingang")) : null));
  }
  const zustand = alle.map((p) => ({ punkt: p.punkt, quelle: p.quelle, lesson_id: p.lesson_id || null, ergebnis: "", notiz: "" }));
  const stand = el("p", { class: "footnote", style: "margin:8px 0 0" });
  const zaehlen = () => {
    const ja = zustand.filter((z) => z.ergebnis === "bestaetigt").length;
    const nein = zustand.filter((z) => z.ergebnis === "abweichung").length;
    stand.textContent = ja || nein ? `${ja} ${ja === 1 ? "hat" : "haben"} gestimmt, ${nein} ${nein === 1 ? "war" : "waren"} anders.` : "Tippe an, was gestimmt hat und was anders lief. Unbewertete Punkte bleiben offen.";
  };
  const zeile = (z, i) => {
    const notizId = `rs-notiz-${data.id}-${i}`;
    const notiz = el("textarea", { id: notizId, rows: 2, placeholder: "Was war anders?", hidden: true, oninput: (e) => { z.notiz = e.target.value; } });
    const ja = el("button", { type: "button", class: "rs-ja", "aria-pressed": "false", "aria-label": `„${kuerzen(z.punkt, 50)}“ hat gestimmt` }, icon("check", "icon sm"), "Stimmte");
    const nein = el("button", { type: "button", class: "rs-nein", "aria-pressed": "false", "aria-label": `„${kuerzen(z.punkt, 50)}“ lief anders` }, icon("x", "icon sm"), "Anders");
    const sync = () => {
      ja.setAttribute("aria-pressed", String(z.ergebnis === "bestaetigt"));
      nein.setAttribute("aria-pressed", String(z.ergebnis === "abweichung"));
      notiz.hidden = z.ergebnis !== "abweichung";
      zaehlen();
    };
    ja.addEventListener("click", () => { z.ergebnis = z.ergebnis === "bestaetigt" ? "" : "bestaetigt"; sync(); });
    nein.addEventListener("click", () => { z.ergebnis = z.ergebnis === "abweichung" ? "" : "abweichung"; sync(); if (!notiz.hidden) notiz.focus(); });
    return el("li", { class: "rs-punkt" },
      el("div", { class: "grow", style: "min-width:0" },
        el("span", { class: "punkt" }, anf(z.punkt)),
        z.quelle === "erfahrung" ? el("span", { class: "src eigen" }, icon("user"), "Dein Eintrag, wird bestätigt") : el("span", { class: "src" }, icon("sparkles"), "Claude, wird bei Bestätigung dein Wissen"),
        el("label", { for: notizId, class: "sr-only" }, "Was war anders?"), notiz),
      el("div", { class: "rs-wahl", role: "group", "aria-label": "Bewertung" }, ja, nein));
  };
  const fazitId = `rs-fazit-${data.id}`;
  const fazit = el("textarea", { id: fazitId, rows: 2, placeholder: "Was nimmst du insgesamt mit? (optional)" });
  const fehlerSlot = el("div");
  const senden = el("button", { type: "button", class: "primary" }, icon("check", "icon sm"), "Rückschau abschließen");
  const box = el("details", { class: "card rueckschau", open: offen || null },
    el("summary", {}, "Wie lief es? Plan mit der Wirklichkeit abgleichen"),
    el("p", { class: "small muted", style: "margin:4px 0 0" }, "Bestätigte Punkte aus deinen Einträgen zählen als erneut erlebt. Abweichungen, bewährtes Fachwissen und dein Fazit werden als neue Einträge strukturiert."),
    stand,
    el("ul", { class: "checklist rs-liste" }, zustand.map(zeile)),
    el("label", { for: fazitId }, "Fazit"),
    el("div", { class: "composer" }, fazit, el("div", { class: "tools" }, diktatKnopf(fazit))),
    el("div", { class: "actions" }, senden), fehlerSlot);
  senden.addEventListener("click", async () => {
    const bewertet = zustand.some((z) => z.ergebnis) || fazit.value.trim();
    if (!bewertet) { toast("Bewerte mindestens einen Punkt oder schreib ein Fazit."); return; }
    senden.setAttribute("aria-disabled", "true");
    try {
      const res = await api(`/api/briefing/${data.id}/rueckschau`, { method: "POST", body: { punkte: zustand, fazit: fazit.value.trim() } });
      const offenKarte = store.json("lv-offen", null);
      if (offenKarte?.id === data.id) store.remove("lv-offen");
      box.replaceWith(rueckschauKarte(res, plan).lastChild);
      say("Rückschau gespeichert.");
      refreshStats({ anlass: `Kreis geschlossen: ${res.bestaetigt} ${res.bestaetigt === 1 ? "Eintrag" : "Einträge"} bestätigt, ${res.entwuerfe} ${res.entwuerfe === 1 ? "neuer Entwurf" : "neue Entwürfe"} im Eingang` });
    } catch (err) {
      senden.removeAttribute("aria-disabled");
      fill(fehlerSlot, errorNotice(err));
    }
  });
  zaehlen();
  return el("section", {}, titel, box);
}

// Lücke als Einladung: direkt aus dem Briefing eine Notiz sichern
function lueckenKarte(data) {
  const id = `luecke-${data.id}`;
  const feld = el("textarea", { id, rows: 2, placeholder: "Ein Satz genügt." });
  const slot = el("div");
  const knopf = el("button", { type: "button", class: "primary" }, "Sichern");
  knopf.addEventListener("click", async () => {
    const text = feld.value.trim();
    if (!text) { feld.setAttribute("aria-invalid", "true"); feld.focus(); return; }
    knopf.setAttribute("aria-disabled", "true");
    try {
      await api("/api/notiz", { method: "POST", body: { text: `Zu „${data.situation}“: ${text}`, bereich: data.bereich || "" } });
      refreshStats();
      fill(karte, el("p", { class: "row", style: "gap:6px;margin:0;color:var(--success)" }, icon("check", "icon sm"), "Gesichert. Liegt strukturiert im Eingang."));
    } catch (err) {
      knopf.removeAttribute("aria-disabled");
      fill(slot, errorNotice(err));
    }
  });
  const karte = el("div", { class: "card tinted", style: "margin-top:24px" },
    el("label", { for: id, style: "margin-top:0" }, "Was hast du dabei selbst erlebt?"),
    el("div", { class: "composer" }, feld, el("div", { class: "tools" }, diktatKnopf(feld))),
    el("div", { class: "actions" }, knopf), slot);
  return karte;
}
