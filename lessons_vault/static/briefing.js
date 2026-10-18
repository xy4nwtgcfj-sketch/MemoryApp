// Briefing: vor einer Situation die eigenen Erfahrungen abrufen, auf Wunsch mit Claudes Fachwissen kombiniert.
import {
  anf, ansicht, api, bereicheSofort, bereiche, copyText, diktatKnopf, el, errorNotice, fill, fokusAufTitel,
  formatDate, fotoInput, fotosHochladen, grosserTitel, hinweisBox, icon, istPruefung, kopf, kuerzen, laden, leer,
  metaZeile, refreshStats, say, skeleton, store, thumbsRow, toast, debounce, ersetzenIn,
} from "./core.js";

const briefingState = { situation: "", bereich: "", modus: store.get("lv-briefing-modus", "kombiniert") };

function planText(situation, plan) {
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
      showBriefing(result, data);
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
      showBriefing(result, data);
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
            el("span", { class: "li-sub" }, formatDate(b.erstellt_am), ` · ${b.anzahl} Lessons`, b.hilfreich ? ` · ${b.hilfreich} hilfreich` : "", b.bereich ? ` · ${b.bereich}` : "")),
          icon("chevron-right", "icon sm chev"))))));
  } catch { /* Verlauf ist optional */ }
}

function showBriefing(container, data) {
  const istEntwurf = Boolean(data.entwurf_weg);
  const istPlan = data.modus === "kombiniert" && !istEntwurf;
  const titelVon = Object.fromEntries(data.treffer.map((t) => [t.lesson.id, t.lesson]));
  const feedback = { ...data.feedback };
  const max = data.treffer[0]?.relevanz || 0;
  const stark = data.treffer.filter((t, i) => i < 4 && t.relevanz >= 0.6 * max);
  const weitere = data.treffer.filter((t) => !stark.includes(t));

  if (!data.treffer.length && !(istPlan && (data.ki_moeglich || data.plan))) {
    fill(container,
      data.bilder?.length ? el("div", { class: "card" }, el("p", { class: "overline" }, "Geprüfter Entwurf"), thumbsRow(data.bilder)) : null,
      leer({ symbol: "lightbulb", titel: "Dazu hast du noch keine Erfahrungen gespeichert", text: "Probier andere Stichworte oder ohne Bereich. Oder halte jetzt fest, was du darüber weißt." }),
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
  const planSlot = el("div");
  const beruecksichtigtSlot = el("div");
  const titelText = istEntwurf ? "Abgleich mit deinen Erfahrungen" : "Worauf es ankommt";

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
    fill(eigeneSlot,
      data.treffer.length ? el("h2", { class: "row", style: "gap:8px" }, icon("user"), "Aus deiner Erfahrung") : null,
      besonderheiten.length ? el("div", { class: "card own" },
        el("p", { class: "overline", style: "color:var(--own)" }, "Hier weichst du vom Üblichen ab"),
        el("ul", { class: "checklist" }, besonderheiten.map((b) => el("li", {},
          el("span", {}, anf(b.punkt), titelVon[b.lesson_id] ? el("a", { class: "src eigen", href: `#/lesson/${b.lesson_id}` }, icon("user"), anf(titelVon[b.lesson_id].titel)) : null))))) : null,
      stark.map(lessonKarte),
      data.treffer.length ? el("p", { class: "footnote" }, "Markiere, was geholfen hat. Das verbessert künftige Briefings.") : null);
  };

  // Planpunkt aus eigener Erfahrung: antippen zeigt die Regel, "Passt nicht" zählt als Feedback.
  const quellenKnopf = (lid) => {
    const l = titelVon[lid];
    if (!l) return el("span", { class: "src eigen" }, icon("user"), "Deine Erfahrung");
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
    fill(planSlot,
      el("h2", { class: "row", style: "gap:8px" }, icon("clipboard-list"), "Plan"),
      el("div", { class: "card" },
        el("div", { class: "legend footnote" },
          el("span", { class: "src eigen", style: "margin:0" }, icon("user"), `${plan.punkte_erfahrung} aus deiner Erfahrung`),
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
        ])));
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
      istEntwurf ? "Claude gleicht den Entwurf mit deinen Lessons ab …" : istPlan ? "Claude erstellt den Plan aus Fachwissen und deinen Erfahrungen …" : "Claude fasst deine Erfahrungen zusammen …"));
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
      el("p", { class: "lead" }, anf(res.zusammenfassung) || "Claude sah keinen klaren Bezug zu dieser Situation. Die Lessons unten sind trotzdem die besten Treffer."),
      res.ki_hinweis ? el("p", { class: "footnote" }, res.ki_hinweis) : null);
    if (res.plan) { renderEigene(res.plan.besonderheiten || []); renderPlan(res.plan); return; }
    renderEigene();
    if (istEntwurf) {
      renderChecklist(res.ki_checkliste || [], res.ki_checkliste?.length ? "Was im Entwurf fehlt, laut deinen Lessons (Claude)" : "Claude hat keine Lücken gefunden.");
      const ok = res.abgleich?.beruecksichtigt || [];
      fill(beruecksichtigtSlot, ok.length ? el("details", { class: "card" },
        el("summary", {}, `Schon berücksichtigt (${ok.length})`),
        el("ul", { class: "checklist" }, ok.map((p) => el("li", {}, icon("check"), el("span", {}, anf(p.punkt),
          titelVon[p.lesson_id] ? el("span", { class: "src eigen" }, icon("user"), anf(titelVon[p.lesson_id].titel)) : null))))) : null);
    } else if (res.ki_checkliste?.length) {
      renderChecklist(res.ki_checkliste, "Auf die Situation zugeschnitten (Claude, aus deinen Lessons)");
    }
  };

  renderEigene();
  renderChecklist(data.checkliste, "Aus den Maßnahmen deiner Lessons");

  const fuss = el("p", { class: "footnote row", style: "gap:8px;margin-top:24px;align-items:flex-start" }, icon("info", "icon sm"),
    el("span", { class: "grow" }, data.ki_moeglich
      ? `An Claude gesendet: deine Situation${data.an_claude ? ` und ${data.an_claude} Lesson${data.an_claude > 1 ? "s" : ""} (Titel, Regel, Situation, Ereignis, Nächstes Mal)` : ""}${data.bilder?.length && data.entwurf_weg === "bild" ? " sowie die Fotos" : data.entwurf_weg === "text" ? " sowie der geprüfte Text des Fotos" : ""}.`
      : "Nichts an Claude gesendet."));
  const neuFormulieren = data.ki_moeglich ? el("button", { type: "button", class: "text", onclick: () => loadSummary(true) }, icon("refresh", "icon sm"), "Neu formulieren") : null;

  fill(container, el("div", {},
    data.bilder?.length ? el("div", { class: "card" }, el("p", { class: "overline" }, "Geprüfter Entwurf"), thumbsRow(data.bilder)) : null,
    kopfZeile,
    !data.treffer.length ? el("div", { class: "notice info" }, icon("info"), el("div", {}, el("strong", {}, "Dazu hast du noch keine eigenen Erfahrungen."), "Der Plan ist reines Fachwissen von Claude.")) : null,
    data.ki_moeglich || data.zusammenfassung ? summaryCard : (data.ki_hinweis ? el("p", { class: "footnote" }, data.ki_hinweis) : null),
    eigeneSlot,
    planSlot,
    beruecksichtigtSlot,
    (!data.treffer.length || (data.plan && !data.plan.punkte_erfahrung)) && !istEntwurf ? lueckenKarte(data) : null,
    weitere.length ? el("details", { class: "card", style: "margin-top:24px" },
      el("summary", {}, `Weitere, weniger passende Treffer (${weitere.length})`),
      weitere.map(lessonKarte)) : null,
    el("div", { class: "row", style: "flex-wrap:wrap" }, fuss, neuFormulieren)));
  if (data.zusammenfassung || data.plan) showSummary(data);
  else if (data.ki_moeglich || data._wechsel) loadSummary();
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
