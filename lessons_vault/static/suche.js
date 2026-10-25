// Suchen, Lesson ansehen und bearbeiten.
import {
  anf, aktionsblatt, ansicht, api, bereiche, bereicheSofort, el, errorNotice, eingabe, fill, fokusAufTitel, formatDate,
  fotoInput, fotosHochladen, grosserTitel, hinweisKompakt, icon, kopf, leer, lessonKarte, metaZeile, quelleText,
  refreshStats, say, skeleton, thumbsRow, toast, bestaetigen, ART, ARTEN, PHASEN, artInfo, statistikSofort,
} from "./core.js";
import { lessonForm, loeschenBestaetigen } from "./entwurf.js";

const searchState = { q: "", modus: "hybrid", art: "", phase: "", bereich: "", status: "", schweregrad_min: "", von: "", bis: "", aktiv: "" };
const FILTER = ["art", "phase", "bereich", "status", "schweregrad_min", "von", "bis", "modus"];

export async function viewSuche(params = {}) {
  const render = ansicht();
  kopf("Suchen");
  if (params.q !== undefined) searchState.q = params.q;
  const results = el("div", { id: "treffer" });
  const anzahl = el("p", { class: "sr-only", role: "status" });
  const q = el("input", { type: "search", id: "q", value: searchState.q, placeholder: "Stichwort oder Frage", enterkeyhint: "search", autocomplete: "off" });
  const leeren = el("button", { type: "button", class: "leeren", "aria-label": "Eingabe löschen", hidden: !searchState.q,
    onclick: () => { q.value = ""; searchState.q = ""; leeren.hidden = true; q.focus(); run(); } }, icon("x", "icon sm"));
  const aktiveFilter = () => FILTER.filter((k) => (k === "modus" ? searchState.modus !== "hybrid" : searchState[k])).length;
  const filterBtn = el("button", { type: "button", class: "text", "aria-expanded": "false", "aria-controls": "filter-panel" });
  const filterPanel = el("div", { id: "filter-panel", class: "card", hidden: true });
  const updateFilterBtn = () => {
    const n = aktiveFilter();
    fill(filterBtn, icon("sliders"), el("span", {}, "Filter"), n ? el("span", { class: "badge", style: "min-height:18px;padding:0 6px" }, n) : null);
    filterBtn.setAttribute("aria-label", n ? `Filter, ${n} aktiv` : "Filter");
    filterBtn.style.position = "relative";
  };
  updateFilterBtn();
  filterBtn.addEventListener("click", () => {
    filterPanel.hidden = !filterPanel.hidden;
    filterBtn.setAttribute("aria-expanded", String(!filterPanel.hidden));
    if (!filterPanel.hidden) filterPanel.querySelector("select")?.focus();
  });

  const run = async () => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(searchState)) if (v !== "") p.set(k, v);
    if (!results.childNodes.length) fill(results, skeleton());
    try {
      const [items, drafts] = await Promise.all([
        api(`/api/suche?${p}`),
        searchState.q.trim() ? api(`/api/entwuerfe?q=${encodeURIComponent(searchState.q)}`).catch(() => ({ eintraege: [] })) : { eintraege: [] },
      ]);
      if (!render.aktiv()) return;
      anzahl.textContent = searchState.q ? `${items.length} Treffer` : "";
      fill(results,
        drafts.eintraege.length ? el("a", { class: "card result row", href: "#/eingang", style: "gap:12px" }, icon("inbox"),
          el("span", { class: "grow" }, `${drafts.eintraege.length} passende Notiz${drafts.eintraege.length > 1 ? "en" : ""} im Eingang`), icon("chevron-right", "icon sm")) : null,
        items.length
          ? el("p", { class: "overline", style: "margin-top:16px" }, searchState.q ? `${items.length} Treffer` : "Neueste Einträge")
          : searchState.q
            ? leer({ symbol: "search", titel: "Nichts gefunden", text: "Probier ein anderes Stichwort oder entferne Filter." })
            : leer({ symbol: "sprout", titel: "Noch keine Einträge", text: "Leg den Startbestand an oder erfasse deinen ersten Eintrag.",
              aktionen: [el("a", { class: "button primary", href: "#/ernte" }, "Startbestand anlegen"), el("a", { class: "button", href: "#/erfassen" }, "Erfassen")] }),
        items.map((item) => lessonKarte(item.lesson)));
    } catch (err) {
      fill(results, errorNotice(err, { erneut: run }));
    }
  };
  let t;
  q.addEventListener("input", () => { searchState.q = q.value; leeren.hidden = !q.value; clearTimeout(t); t = setTimeout(run, 300); });
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); q.blur(); } });

  const bereichListe = bereicheSofort();
  const select = (key, label, options) => {
    const node = el("select", { id: `s-${key}`, onchange: (e) => { searchState[key] = e.target.value; updateFilterBtn(); run(); } },
      options.map(([v, tx]) => el("option", { value: v, selected: searchState[key] === String(v) }, tx)));
    return el("div", {}, el("label", { for: `s-${key}` }, label), node);
  };
  const datum = (key, label) => el("div", {}, el("label", { for: `s-${key}` }, label),
    el("input", { type: "date", id: `s-${key}`, value: searchState[key], onchange: (e) => { searchState[key] = e.target.value; updateFilterBtn(); run(); } }));
  const modi = [["hybrid", "Beides"], ["volltext", "Wörter"], ["semantisch", "Bedeutung"]];
  const seg = el("div", { class: "segmented", role: "group", "aria-label": "Suchart" }, modi.map(([v, tx]) => el("button", {
    type: "button", "aria-pressed": String(searchState.modus === v),
    onclick: (e) => {
      searchState.modus = v;
      seg.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-pressed", String(modi[i][0] === v)));
      updateFilterBtn();
      run();
      e.currentTarget.focus();
    },
  }, tx)));
  fill(filterPanel,
    el("div", { class: "grid2" },
      select("art", "Art", [["", "Alle"], ...ARTEN.map((a) => [a, ART[a].label])]),
      select("phase", "Projektphase", [["", "Alle"], ...Object.entries(PHASEN)]),
      select("bereich", "Bereich", [["", "Alle"], ...bereichListe.map((b) => [b.name, b.name])]),
      select("status", "Status", [["", "Alle"], ["neu", "neu"], ["bestätigt", "bestätigt"], ["überholt", "überholt"]]),
      select("schweregrad_min", "Gewicht ab", [["", "Alle"], ...[2, 3, 4, 5].map((n) => [String(n), `${n} und mehr`])]),
      datum("von", "Erfasst ab"),
      datum("bis", "Erfasst bis")),
    el("details", { class: "plain", style: "margin-top:12px" }, el("summary", {}, "Erweitert: Suchart"),
      el("p", { class: "footnote", style: "margin:0 0 8px" }, "Standard ist beides: genaue Wörter und ähnliche Bedeutung."), seg),
    el("div", { class: "actions" }, el("button", {
      type: "button", class: "text",
      onclick: () => { Object.assign(searchState, { art: "", phase: "", bereich: "", status: "", schweregrad_min: "", von: "", bis: "", modus: "hybrid" }); viewSuche(); },
    }, "Filter zurücksetzen")));

  // Projektphasen als Schnellfilter: zeigt, wie sich das berufliche Wissen über die Phasen verteilt
  const proPhase = statistikSofort()?.pro_phase || {};
  const phasenChips = el("div", { class: "chips phasen", role: "group", "aria-label": "Projektphase" });
  const renderPhasen = () => fill(phasenChips, Object.entries(PHASEN).map(([v, tx]) => el("button", {
    type: "button", class: `chip phase-${v}`, "aria-pressed": String(searchState.phase === v),
    onclick: () => { searchState.phase = searchState.phase === v ? "" : v; renderPhasen(); updateFilterBtn(); const sel = document.getElementById("s-phase"); if (sel) sel.value = searchState.phase; run(); },
  }, tx, el("small", {}, String(proPhase[v] || 0)))));
  renderPhasen();

  // Desktop: zwei Spalten. Ein Treffer öffnet rechts, die Liste bleibt stehen. Am Handy bleibt es die Detailseite.
  const breit = matchMedia("(min-width: 900px)");
  const detail = el("aside", { class: "suche-detail", "aria-label": "Eintrag" });
  const detailLeer = () => fill(detail, el("div", { class: "empty" }, el("span", { class: "empty-icon" }, icon("search")),
    el("h2", {}, "Wähle einen Treffer"), el("p", {}, "Der Eintrag erscheint hier, die Liste bleibt stehen.")));
  const detailZeigen = async (id) => {
    searchState.aktiv = id;
    results.querySelectorAll(".result").forEach((r) => r.classList.toggle("aktiv", r.dataset.id === id));
    fill(detail, skeleton());
    const node = await lessonDetail(id, { neuLaden: () => detailZeigen(id) });
    if (render.aktiv() && searchState.aktiv === id) { fill(detail, node); detail.scrollTop = 0; }
  };
  results.addEventListener("click", (e) => {
    const karte = e.target.closest("a.result");
    if (!karte || !breit.matches || !karte.dataset.id) return;
    e.preventDefault();
    detailZeigen(karte.dataset.id);
  });
  detailLeer();
  const liste = el("div", { class: "suche-liste" },
    el("div", { class: "row" },
      el("div", { class: "suchfeld grow" }, icon("search"), el("label", { for: "q", class: "sr-only" }, "Suchbegriff"), q, leeren),
      filterBtn),
    Object.keys(proPhase).length ? phasenChips : null,
    filterPanel, anzahl, results);
  if (!render(grosserTitel("Suchen"), el("div", { class: "suche-layout" }, liste, detail))) return;
  fokusAufTitel();
  await run();
  if (breit.matches && searchState.aktiv && results.querySelector(`.result[data-id="${searchState.aktiv}"]`)) detailZeigen(searchState.aktiv);
}

// ---------------------------------------------------------------- Detail
export async function viewLesson(id) {
  const render = ansicht();
  const zurueck = { text: "Zurück", href: "#/suche" };
  kopf("Eintrag", zurueck);
  render(skeleton());
  const node = await lessonDetail(id, { neuLaden: () => viewLesson(id), titel: (t) => kopf(t, zurueck), seite: true });
  if (render(node)) fokusAufTitel();
}

// Der Eintrag als Baustein: ganze Seite (seite = true, mit großem Titel) oder rechte Spalte der Suche.
async function lessonDetail(id, { neuLaden, titel = () => {}, seite = false }) {
  let data;
  try {
    data = await api(`/api/lessons/${encodeURIComponent(id)}`);
  } catch (err) {
    return el("div", {}, seite ? grosserTitel("Eintrag") : null, errorNotice(err), seite ? el("a", { href: "#/suche" }, "Zur Suche") : null);
  }
  const l = data.lesson;
  titel(l.titel);
  const compliance = hinweisKompakt(data.compliance_hinweise);

  const a = artInfo(l.art);
  const erneut = el("button", { type: "button", class: "primary block" }, icon("refresh"), a.bestaetigen);
  erneut.addEventListener("click", async () => {
    const notiz = await eingabe({ titel: a.bestaetigen, text: "Das zählt den Eintrag als bestätigt. Was war diesmal?", label: "Kurze Notiz", ok: "Zählen" });
    if (notiz === null) return;
    try {
      const updated = await api(`/api/lessons/${l.id}/bestaetigen`, { method: "POST", body: { notiz } });
      toast(`Gezählt: jetzt ${updated.bestaetigungen}× ${a.bestaetigt}.`);
      refreshStats();
      neuLaden();
    } catch (err) { toast(err.message, { fehler: true }); }
  });

  const mehr = el("button", { type: "button", class: "icon-btn", "aria-label": "Weitere Aktionen" }, icon("more"));
  mehr.addEventListener("click", () => aktionsblatt(l.titel, [
    { text: "Bearbeiten", icon: "pencil", onclick: () => { location.hash = `#/lesson/${l.id}/bearbeiten`; } },
    {
      text: l.status === "überholt" ? "Wieder aktivieren" : "Als überholt markieren",
      icon: "clock",
      onclick: async () => {
        const next = l.status === "überholt" ? (l.bestaetigungen >= 2 ? "bestätigt" : "neu") : "überholt";
        if (next === "überholt" && !(await bestaetigen({ titel: "Als überholt markieren?", text: "Sie bleibt sichtbar, erscheint aber nicht mehr in Briefings.", ok: "Markieren" }))) return;
        try { await api(`/api/lessons/${l.id}`, { method: "PUT", body: { status: next } }); neuLaden(); }
        catch (err) { toast(err.message, { fehler: true }); }
      },
    },
    {
      text: "Löschen", icon: "trash", gefahr: true,
      onclick: async () => {
        if (!(await loeschenBestaetigen(l))) return;
        try { await api(`/api/lessons/${l.id}`, { method: "DELETE" }); toast("Gelöscht."); refreshStats(); if (seite) location.hash = "#/suche"; else viewSuche(); }
        catch (err) { toast(err.message, { fehler: true }); }
      },
    },
  ]));

  const feld = (label, value) => (value ? [el("dt", {}, label), el("dd", {}, anf(value))] : []);
  const kopfTitel = seite
    ? grosserTitel(anf(l.titel), { style: "font-size:1.375rem;margin:8px 0 12px" })
    : el("h2", { style: "font-size:1.375rem;margin:4px 0 12px" }, anf(l.titel));
  return el("div", { class: "lesson-detail" },
    el("div", { class: "card-head" },
      el("div", { class: "grow" }, kopfTitel),
      el("a", { class: "button icon-btn", href: `#/lesson/${l.id}/bearbeiten`, "aria-label": "Bearbeiten", style: "margin-top:4px" }, icon("pencil")),
      el("span", { style: "margin-top:4px" }, mehr)),
    el("p", { class: `quote ${l.spezifisch ? "own" : ""}` }, anf(l.lesson)),
    metaZeile(l, { voll: true }),
    data.hilfreich ? el("p", { class: "helped" }, icon("thumbs-up", "icon sm"), `${data.hilfreich}× im Briefing geholfen`) : null,
    el("dl", { class: "fields" },
      feld(a.anwendung, l.massnahme || (l.art === "erfahrung" ? "Noch offen. Was würdest du beim nächsten Mal konkret anders machen?" : "")),
      feld(a.kontext, l.situation),
      feld(a.inhalt, l.ereignis),
      feld("Stichworte", l.tags.join(", "))),
    compliance,
    el("div", { class: "actions", style: "margin-top:24px" }, erneut),
    fotoSection(l, data.bilder || [], neuLaden),
    el("h2", {}, "Verlauf"),
    el("ul", { class: "timeline" }, data.protokoll.map((p) => el("li", {}, el("span", { class: "footnote" }, formatDate(p.datum)), p.notiz && p.notiz !== "erstmals erlebt" ? el("span", {}, ` · ${anf(p.notiz)}`) : el("span", {}, p.notiz === "erstmals erlebt" ? (l.art === "erfahrung" ? " · erstmals erlebt" : " · erfasst") : "")))),
    el("p", { class: "footnote", style: "margin-top:24px" }, `Erfasst am ${formatDate(l.erstellt_am)}`, quelleText(l.quelle) ? ` ${quelleText(l.quelle)}` : "",
      l.geaendert_am !== l.erstellt_am ? `, zuletzt geändert am ${formatDate(l.geaendert_am)}` : "", "."),
  );
}

function fotoSection(l, bilder, neuLaden) {
  const btn = el("button", { type: "button", class: "text" }, icon("camera", "icon sm"), "Foto hinzufügen");
  const input = fotoInput(async (files) => {
    btn.setAttribute("aria-disabled", "true");
    try {
      const neu = await fotosHochladen(files);
      await api(`/api/lessons/${l.id}/bilder`, { method: "POST", body: { bild_ids: neu.map((b) => b.id) } });
      toast("Foto angehängt.");
      neuLaden();
    } catch (err) {
      btn.removeAttribute("aria-disabled");
      toast(err.message, { fehler: true });
    }
  });
  btn.addEventListener("click", () => input.click());
  return el("div", {},
    el("h2", {}, `Fotos${bilder.length ? ` (${bilder.length})` : ""}`),
    bilder.length ? thumbsRow(bilder, {
      titel: l.titel,
      onRemove: async (b) => {
        if (!(await bestaetigen({ titel: "Foto entfernen?", text: "Das Foto wird von diesem Eintrag gelöst.", ok: "Entfernen", gefahr: true }))) return;
        try { await api(`/api/lessons/${l.id}/bilder/${b.id}`, { method: "DELETE" }); neuLaden(); }
        catch (err) { toast(err.message, { fehler: true }); }
      },
    }) : el("p", { class: "footnote", style: "margin-top:0" }, "Zum Beispiel die Folie oder das Whiteboard, aus dem der Eintrag stammt."),
    btn, input);
}

export async function editLesson(id) {
  const render = ansicht();
  kopf("Bearbeiten", { text: "Eintrag", href: `#/lesson/${id}` });
  let l;
  try {
    l = (await api(`/api/lessons/${encodeURIComponent(id)}`)).lesson;
  } catch (err) {
    render(grosserTitel("Bearbeiten"), errorNotice(err));
    return;
  }
  const form = lessonForm(l, { bereichListe: await bereiche().catch(() => bereicheSofort()) });
  const slot = el("div");
  const saveBtn = el("button", { type: "button", class: "primary" }, icon("check"), "Sichern");
  saveBtn.addEventListener("click", async () => {
    if (!form.pruefen()) return;
    const data = form.read();
    if (!data.titel) data.titel = l.titel;
    if (!data.situation) data.situation = l.situation;
    if (!data.ereignis) data.ereignis = l.ereignis;
    saveBtn.setAttribute("aria-disabled", "true");
    try {
      const res = await api(`/api/lessons/${l.id}`, { method: "PUT", body: data });
      toast(res.compliance_hinweise.length ? "Gesichert. Datenschutz-Hinweise beachten." : "Gesichert.");
      location.hash = `#/lesson/${l.id}`;
    } catch (err) {
      saveBtn.removeAttribute("aria-disabled");
      fill(slot, errorNotice(err));
    }
  });
  if (render(grosserTitel("Bearbeiten"), form.node, slot,
    el("div", { class: "sticky-actions" }, saveBtn, el("a", { class: "button", href: `#/lesson/${l.id}` }, "Abbrechen")))) fokusAufTitel();
  say("");
}
