// Entwurfskarte: Was Claude (oder das lokale Modell) aus einer Notiz gemacht hat, prüfen und sichern.
import {
  ZIEL_LESSONS, SEVERITY, anf, api, bereiche, bestaetigen, debounce, diktatKnopf, el, errorNotice, fill, hinweisBox,
  icon, istPruefung, kuerzen, ersetzenIn, ersetzenKnoepfe, refreshStats, say, statistikSofort, thumbsRow, toast,
} from "./core.js";

// ---------------------------------------------------------------- Formular
let formZaehler = 0;

/** Lesson-Formular. kompakt: Regel und Bereich oben, Rest unter "Details". */
export function lessonForm(data, { bereichListe, onChange, kompakt = false, kiAusgefuellt = false } = {}) {
  const p = `f${++formZaehler}`;
  const fields = {};
  const fehler = {};
  const changed = () => onChange && onChange(read());

  const feld = (name, label, { multiline = false, opt = "", rows = 2, max, pflicht = false, klasse = "" } = {}) => {
    const id = `${p}-${name}`;
    const fehlerId = `${id}-fehler`;
    const control = multiline
      ? el("textarea", { id, name, rows, class: klasse || null, oninput: changed, "aria-describedby": pflicht ? fehlerId : null, "aria-required": pflicht ? "true" : null })
      : el("input", { id, name, type: "text", maxlength: max, oninput: changed, "aria-describedby": pflicht ? fehlerId : null, "aria-required": pflicht ? "true" : null });
    control.value = data[name] ?? "";
    fields[name] = control;
    fehler[name] = el("p", { class: "feld-fehler", id: fehlerId });
    return [el("label", { for: id }, label, opt ? el("span", { class: "opt" }, ` ${opt}`) : null), control, pflicht ? fehler[name] : null];
  };

  const aktive = bereichListe.filter((b) => b.aktiv || b.name === data.bereich);
  const bereichSelect = el("select", { id: `${p}-bereich`, name: "bereich", onchange: changed, "aria-required": "true", "aria-describedby": `${p}-bereich-fehler` },
    el("option", { value: "" }, "Bitte wählen"),
    aktive.map((b) => el("option", { value: b.name, selected: b.name === data.bereich }, b.name)));
  fields.bereich = bereichSelect;
  fehler.bereich = el("p", { class: "feld-fehler", id: `${p}-bereich-fehler` });

  const sevSelect = el("select", { id: `${p}-schweregrad`, name: "schweregrad", onchange: changed },
    [1, 2, 3, 4, 5].map((n) => el("option", { value: n, selected: Number(data.schweregrad || 3) === n }, `${n} · ${SEVERITY[n]}`)));
  fields.schweregrad = sevSelect;

  const tags = el("input", { id: `${p}-tags`, type: "text", oninput: changed, autocapitalize: "off" });
  tags.value = (data.tags || []).join(", ");
  fields.tags = tags;

  // Eigene Erfahrung: aus gespeichertem Wert oder Claudes Einschätzung, sonst Ja.
  const startwert = data.spezifisch ?? (data.spezifitaet === "allgemein" ? false : true);
  const spezifisch = el("input", { type: "checkbox", role: "switch", class: "switch", id: `${p}-spezifisch`, checked: startwert, onchange: changed });

  function read() {
    return {
      titel: fields.titel.value.trim(),
      situation: fields.situation.value.trim(),
      ereignis: fields.ereignis.value.trim(),
      lesson: fields.lesson.value.trim(),
      massnahme: fields.massnahme.value.trim(),
      bereich: fields.bereich.value,
      schweregrad: Number(fields.schweregrad.value),
      tags: fields.tags.value.split(",").map((t) => t.trim()).filter(Boolean),
      spezifisch: spezifisch.checked,
    };
  }

  // Pflicht sind nur Regel und Bereich; den Rest ergänzt die App beim Sichern aus der Notiz.
  function pruefen() {
    const data = read();
    const fehlend = [];
    for (const [name, text] of [["lesson", "Bitte die Regel in einem Satz notieren."], ["bereich", "Bitte einen Bereich wählen."]]) {
      const leer = !data[name];
      fields[name].setAttribute("aria-invalid", leer ? "true" : "false");
      fehler[name].textContent = leer ? text : "";
      if (leer) fehlend.push(fields[name]);
    }
    if (fehlend.length) { fehlend[0].focus(); say(fehler[fehlend[0] === fields.lesson ? "lesson" : "bereich"].textContent); }
    return !fehlend.length;
  }

  // Ersetzen per Tipp in allen Textfeldern
  function ersetzen(von, nach) {
    for (const name of ["titel", "situation", "ereignis", "lesson", "massnahme", "tags"]) fields[name].value = ersetzenIn(fields[name].value, von, nach);
    changed();
  }

  const regelFeld = feld("lesson", "Regel", { multiline: true, rows: 2, pflicht: true, klasse: "regel" });
  const bereichFeld = [el("label", { for: `${p}-bereich` }, "Bereich"), bereichSelect, fehler.bereich];
  const schwereFeld = [el("label", { for: `${p}-schweregrad` }, "Schwere"), sevSelect];
  const persoenlich = el("label", { class: "row", for: `${p}-spezifisch`, style: "margin-top:16px;gap:12px" },
    el("span", { class: "grow" }, "Eigene Erfahrung", el("span", { class: "li-sub" }, "Selbst erlebt, nicht nur gelesen")), spezifisch);
  const details = [
    feld("titel", "Titel", { opt: "(max. 80 Zeichen, sonst aus der Regel)", max: 80 }),
    feld("situation", "Situation", { multiline: true, rows: 2 }),
    feld("ereignis", "Was ist passiert?", { multiline: true, rows: 3 }),
    feld("massnahme", "Nächstes Mal", { multiline: true, opt: "(optional, ein konkreter Schritt)" }),
    el("label", { for: `${p}-tags` }, "Stichworte", el("span", { class: "opt" }, " (mit Komma getrennt, helfen beim Wiederfinden)")),
    tags,
  ];

  const node = kompakt
    ? el("div", {},
      regelFeld,
      el("div", { class: "grid2" }, el("div", {}, bereichFeld), el("div", {}, schwereFeld)),
      persoenlich,
      el("details", { class: "plain", style: "margin-top:8px" },
        el("summary", {}, kiAusgefuellt ? "Details, von Claude ausgefüllt" : "Details"),
        details))
    : el("div", {}, regelFeld, details, el("div", { class: "grid2" }, el("div", {}, bereichFeld), el("div", {}, schwereFeld)), persoenlich);
  return { node, read, pruefen, ersetzen, fields };
}

// Felder, die der Server verlangt, aus Notiz und Regel ergänzen
export function lessonBody(data, rohtext = "") {
  const roh = String(rohtext || "").trim();
  return {
    ...data,
    titel: data.titel || kuerzen(data.lesson, 80),
    situation: data.situation || roh || data.lesson,
    ereignis: data.ereignis || roh || data.lesson,
  };
}

export function bereitZumUebernehmen(eintrag) {
  const e = eintrag.entwurf;
  return Boolean(eintrag.status === "fertig" && e && e.lesson && e.bereich && !e.pruefung && !e.dublette && !(e.compliance_hinweise || []).length);
}

/** Entwurf direkt übernehmen (Eingang: ein Tipp). Liefert die gespeicherte Lesson. */
export async function uebernehmen(eintrag) {
  const e = eintrag.entwurf;
  const body = lessonBody({
    titel: e.titel, situation: e.situation, ereignis: e.ereignis, lesson: e.lesson, massnahme: e.massnahme,
    bereich: e.bereich, schweregrad: e.schweregrad || 3, tags: e.tags || [],
    spezifisch: e.spezifitaet === "allgemein" ? false : true,
  }, eintrag.rohtext);
  const res = await api("/api/lessons", { method: "POST", body: { ...body, quelle: e.quelle || eintrag.quelle, entwurf_id: eintrag.id, erfassung_sekunden: eintrag.erfassung_sekunden ?? null } });
  return res.lesson;
}

// Rückgängig: Lesson löschen und den Entwurf wieder in den Eingang legen
export async function rueckgaengig(lesson, eintrag) {
  await api(`/api/lessons/${lesson.id}`, { method: "DELETE" });
  const neu = await api("/api/notiz", { method: "POST", body: { text: eintrag.rohtext, quelle: eintrag.quelle, bereich: eintrag.bereich_vorgabe || "", entwurf: eintrag.entwurf } });
  refreshStats();
  return neu;
}

// ---------------------------------------------------------------- Entwurfskarte
/**
 * Zeigt einen gesicherten Entwurf (EntwurfEintrag) zum Prüfen.
 * onGesichert(lesson, eintrag), onSpaeter(), onVerworfen(eintrag), onNeu(eintrag) (nach erneuter Strukturierung)
 */
export async function entwurfKarte(container, eintrag, { onGesichert, onSpaeter, onVerworfen, onNeu, spaeterText = "Später" } = {}) {
  const e = eintrag.entwurf;
  if (eintrag.status === "fehler" || !e) return fehlerKarte(container, eintrag, { onNeu, onVerworfen, onGesichert, onSpaeter, spaeterText });
  if (e.pruefung) return pruefungsKarte(container, eintrag, { onNeu, onGesichert, onVerworfen, onSpaeter, spaeterText });

  const bereichListe = await bereiche().catch(() => []);
  const compliance = hinweisBox(e.compliance_hinweise || [], { anwenden: (r) => form.ersetzen(r.von, r.nach) });
  const recheck = debounce(async (data) => {
    try {
      const text = [data.titel, data.situation, data.ereignis, data.lesson, data.massnahme, ...data.tags].join("\n");
      compliance.update(await api("/api/compliance", { method: "POST", body: { text, bereich: data.bereich } }));
    } catch { /* Hinweis bleibt wie er war */ }
  }, 600);
  const form = lessonForm(e, { bereichListe, onChange: (d) => recheck(d), kompakt: true, kiAusgefuellt: e.ki_verwendet });

  const teile = [];
  if (e.ki_fehler) teile.push(el("div", { class: "notice warn" }, icon("alert"), el("div", {}, e.ki_fehler)));
  if (e.dublette) teile.push(dublettenKarte(e, eintrag, { onGesichert }));

  const kopfZeile = e.ki_verwendet
    ? el("p", { class: "overline row", style: "gap:6px" }, icon("sparkles", "icon sm"), "Claude hat daraus gemacht")
    : el("p", { class: "overline" }, "Dein Entwurf");
  const pflichtFrage = e.rueckfrage && e.rueckfrage_art === "pflichtfeld"
    ? el("p", { class: "hint" }, icon("info", "icon sm"), " Claude fragt: ", anf(e.rueckfrage)) : null;
  const aehnlich = (e.aehnliche || []).slice(0, 2);

  teile.push(el("div", { class: "card hero" },
    kopfZeile,
    form.node,
    pflichtFrage,
    eintrag.bilder?.length ? el("div", {}, el("p", { class: "overline", style: "margin-top:16px" }, "Fotos"), thumbsRow(eintrag.bilder)) : null,
    aehnlich.length ? el("p", { class: "footnote", style: "margin-top:12px" }, "Ähnlich: ",
      aehnlich.map((a, i) => [i ? ", " : "", el("a", { href: `#/lesson/${a.id}` }, anf(a.titel))])) : null));
  teile.push(compliance.node);

  const sichern = el("button", { type: "button", class: "primary" }, icon("check"), "Sichern");
  const spaeter = onSpaeter ? el("button", { type: "button", onclick: onSpaeter }, spaeterText) : null;
  const verwerfen = el("button", { type: "button", class: "icon-btn", "aria-label": "Entwurf verwerfen", title: "Verwerfen" }, icon("trash"));
  verwerfen.addEventListener("click", () => verwerfenMitRueckgaengig(container, eintrag, onVerworfen));

  sichern.addEventListener("click", async () => {
    if (!form.pruefen()) return;
    if (sichern.getAttribute("aria-disabled") === "true") return;
    sichern.setAttribute("aria-disabled", "true");
    say("Wird gesichert.");
    try {
      const body = lessonBody(form.read(), eintrag.rohtext);
      const res = await api("/api/lessons", {
        method: "POST",
        body: { ...body, quelle: e.quelle || eintrag.quelle, erfassung_sekunden: eintrag.erfassung_sekunden ?? null, entwurf_id: eintrag.id },
      });
      if (res.embedding_fehler) toast(res.embedding_fehler, { ms: 8000 });
      onGesichert?.(res.lesson, eintrag);
    } catch (err) {
      sichern.removeAttribute("aria-disabled");
      fill(fehlerSlot, errorNotice(err));
    }
  });
  const fehlerSlot = el("div", { role: "status" });
  teile.push(fehlerSlot, el("div", { class: "sticky-actions" }, sichern, spaeter, verwerfen));

  fill(container, el("div", {}, teile));
  say(e.ki_verwendet ? "Entwurf fertig. Bitte kurz prüfen und sichern." : "Entwurf bereit. Bitte ergänzen und sichern.");
}

function fehlerKarte(container, eintrag, { onNeu, onVerworfen, onGesichert, onSpaeter, spaeterText }) {
  const nochmal = el("button", { type: "button", class: "primary" }, icon("refresh"), "Erneut versuchen");
  nochmal.addEventListener("click", async () => {
    fill(container, el("div", { class: "skeleton" }, el("p", { class: "waiting" }, el("span", { class: "spinner", "aria-hidden": "true" }), "Wird strukturiert …")));
    try { onNeu?.(await api(`/api/entwuerfe/${eintrag.id}/strukturieren`, { method: "POST", body: {} })); }
    catch (err) { fill(container, errorNotice(err)); }
  });
  const selbst = el("button", { type: "button", onclick: () => entwurfKarte(container, { ...eintrag, status: "fertig", entwurf: { titel: "", situation: "", ereignis: eintrag.rohtext, lesson: "", bereich: eintrag.bereich_vorgabe || "", schweregrad: 3, tags: [], quelle: eintrag.quelle, compliance_hinweise: [] } }, { onGesichert, onVerworfen, onSpaeter, spaeterText }) }, "Selbst ausfüllen");
  fill(container, el("div", { class: "card" },
    el("p", { class: "overline" }, "Deine Notiz ist gesichert"),
    el("p", { style: "white-space:pre-wrap" }, eintrag.rohtext),
    el("div", { class: "notice warn" }, icon("alert"), el("div", {}, "Die Strukturierung hat nicht geklappt", eintrag.fehler ? `: ${eintrag.fehler}` : ".")),
    el("div", { class: "actions" }, nochmal, selbst,
      el("button", { type: "button", class: "icon-btn", "aria-label": "Notiz verwerfen", onclick: () => verwerfenMitRueckgaengig(container, eintrag, onVerworfen) }, icon("trash")))));
}

// Namensprüfung hat angeschlagen: nichts ist an Claude gegangen. Ersetzen, bearbeiten, bewusst senden oder selbst ausfüllen.
function pruefungsKarte(container, eintrag, { onNeu, onGesichert, onVerworfen, onSpaeter, spaeterText }) {
  const p = eintrag.entwurf.pruefung;
  const gesperrt = p.code === "sperrliste";
  const feld = el("textarea", { id: `notiz-${eintrag.id}`, rows: 4, "aria-describedby": `pruef-${eintrag.id}` });
  feld.value = eintrag.rohtext;
  const fehlerSlot = el("div");

  const senden = async (body) => {
    fill(fehlerSlot, el("p", { class: "waiting" }, el("span", { class: "spinner", "aria-hidden": "true" }), "Claude strukturiert …"));
    say("Claude strukturiert, bitte warten.");
    try {
      const neu = await api(`/api/entwuerfe/${eintrag.id}/strukturieren`, { method: "POST", body });
      onNeu?.(neu);
    } catch (err) { fill(fehlerSlot, errorNotice(err)); }
  };
  const nachErsetzen = async () => {
    // Wenn nach dem Ersetzen nichts mehr auffällt, direkt an Claude geben.
    try {
      const rest = await api("/api/compliance", { method: "POST", body: { text: feld.value, bereich: eintrag.bereich_vorgabe || "" } });
      if (!rest.length) senden({ text: feld.value.trim() });
    } catch { /* bleibt, Nutzer kann manuell senden */ }
  };
  const knoepfe = ersetzenKnoepfe(p.hinweise, (r) => { feld.value = ersetzenIn(feld.value, r.von, r.nach); nachErsetzen(); });

  const mitText = el("button", { type: "button", class: "primary", onclick: () => senden({ text: feld.value.trim() }) }, icon("sparkles"), "Geänderten Text senden");
  const trotzdem = gesperrt ? null : el("button", { type: "button", onclick: () => senden({ text: feld.value.trim(), freigabe: true }) }, "Trotzdem senden");
  const selbst = el("button", {
    type: "button", class: "text",
    onclick: () => entwurfKarte(container, { ...eintrag, entwurf: { ...eintrag.entwurf, pruefung: null } }, { onGesichert, onVerworfen, onSpaeter, spaeterText }),
  }, "Ohne Claude ausfüllen");

  fill(container, el("div", { class: "card hero" },
    el("p", { class: "overline row", style: "gap:6px" }, icon("shield", "icon sm"), "Kurz prüfen, bevor es an Claude geht"),
    el("p", { id: `pruef-${eintrag.id}`, style: "margin:0 0 4px" }, gesperrt
      ? "Ein Begriff aus deiner Sperrliste steht im Text. So geht er nie an Claude."
      : "Das sieht nach Namen oder Projektdaten aus. Noch ist nichts an Claude gegangen."),
    el("ul", { class: "small", style: "margin:4px 0 0;padding-left:18px" }, p.hinweise.map((h) => el("li", {}, anf(h)))),
    knoepfe,
    el("label", { for: `notiz-${eintrag.id}` }, "Deine Notiz"),
    feld,
    el("p", { class: "footnote" }, "Deine Notiz ist auf dem PC gesichert."),
    el("div", { class: "actions" }, mitText, trotzdem, selbst),
    fehlerSlot));
  say("Namensprüfung: bitte kurz prüfen, bevor es an Claude geht.");
}

function dublettenKarte(e, eintrag, { onGesichert }) {
  const d = e.dublette;
  const karte = el("div", { class: "card own" },
    el("p", { class: "overline" }, "Das kennst du schon"),
    el("h3", {}, anf(d.titel)),
    el("p", { class: "rule", style: "margin:4px 0 0" }, anf(d.lesson)),
    el("p", { class: "footnote" }, e.dublette_begruendung ? `${anf(e.dublette_begruendung)} ` : "", `Bisher ${d.bestaetigungen}× erlebt.`));
  const zaehlen = el("button", { type: "button", class: "primary" }, "Als erneut erlebt zählen");
  zaehlen.addEventListener("click", async () => {
    zaehlen.setAttribute("aria-disabled", "true");
    try {
      const lesson = await api(`/api/lessons/${d.id}/bestaetigen`, { method: "POST", body: { notiz: eintrag.rohtext, entwurf_id: eintrag.id } });
      onGesichert?.(lesson, eintrag, { bestaetigt: true });
    } catch (err) {
      zaehlen.removeAttribute("aria-disabled");
      toast(err.message, { fehler: true });
    }
  });
  karte.append(el("div", { class: "actions" }, zaehlen, el("button", { type: "button", onclick: () => karte.remove() }, "Neue Lesson daraus")));
  return karte;
}

function verwerfenMitRueckgaengig(container, eintrag, onVerworfen) {
  // Erst nach Ablauf des Toasts wirklich löschen; bis dahin lässt es sich zurückholen.
  let abgebrochen = false;
  const inhalt = [...container.childNodes];
  fill(container);
  const timer = setTimeout(async () => {
    if (abgebrochen) return;
    try { await api(`/api/entwuerfe/${eintrag.id}`, { method: "DELETE" }); refreshStats(); } catch { /* bleibt im Eingang */ }
  }, 10000);
  toast("Entwurf verworfen.", {
    aktion: { text: "Rückgängig", onclick: () => { abgebrochen = true; clearTimeout(timer); fill(container, inhalt); say("Entwurf wiederhergestellt."); } },
  });
  onVerworfen?.(eintrag);
}

// ---------------------------------------------------------------- Nach dem Sichern
/** Abschlusskarte: die Regel als Zitat, wo sie wieder auftaucht, Fortschritt und optional Schärfen. */
export function abschlussKarte(lesson, eintrag, { bestaetigt = false, modus = "claude" } = {}) {
  const e = eintrag?.entwurf || {};
  const s = statistikSofort();
  const gesamt = s ? s.gesamt : null;
  const stichworte = (lesson.tags || []).slice(0, 4);
  const verwandt = (e.aehnliche || []).find((a) => a.id !== lesson.id);
  const karte = el("div", { class: "card hero", role: "status" },
    el("p", { class: "overline row", style: "gap:6px;color:var(--success)" }, icon("check", "icon sm"), bestaetigt ? "Als erneut erlebt gezählt" : "Gesichert"),
    el("p", { class: `quote ${lesson.spezifisch ? "own" : ""}` }, anf(lesson.lesson)),
    bestaetigt
      ? el("p", { class: "footnote" }, `Jetzt ${lesson.bestaetigungen}× erlebt.`)
      : el("p", { class: "small muted", style: "margin:12px 0 0" }, "Taucht wieder auf bei: ",
        stichworte.length ? stichworte.join(", ") : lesson.bereich, "."),
    verwandt && !bestaetigt ? el("p", { class: "small muted", style: "margin:4px 0 0" }, "Verwandt mit ", el("a", { href: `#/lesson/${verwandt.id}` }, anf(verwandt.titel)),
      verwandt.bestaetigungen > 1 ? ` (${verwandt.bestaetigungen}× erlebt)` : "", ".") : null,
    gesamt !== null ? el("div", {},
      el("p", { class: "footnote", style: "margin-top:12px" }, `${gesamt + (bestaetigt ? 0 : 1)} von ${ZIEL_LESSONS} Lessons`),
      el("div", { class: "progress own", "aria-hidden": "true" }, el("span", { style: `width:${Math.min(100, ((gesamt + 1) / ZIEL_LESSONS) * 100)}%` }))) : null,
    el("div", { class: "actions" }, el("a", { class: "button text", href: `#/lesson/${lesson.id}` }, "Ansehen", icon("chevron-right", "icon sm"))));
  if (!bestaetigt && e.rueckfrage && e.rueckfrage_art !== "pflichtfeld") karte.append(schaerfenBlock(lesson, eintrag, modus, karte));
  return karte;
}

function schaerfenBlock(lesson, eintrag, modus, karte) {
  const e = eintrag.entwurf;
  const id = `schaerfen-${lesson.id}`;
  const feld = el("textarea", { id, rows: 2, placeholder: "Ein Satz genügt." });
  const knopf = el("button", { type: "button", class: "primary" }, "Ergänzen");
  const slot = el("div");
  const box = el("div", { class: "card tinted", style: "margin:16px 0 0" },
    el("label", { for: id, style: "margin-top:0" }, "Schärfen? ", el("span", { class: "opt" }, anf(e.rueckfrage))),
    el("div", { class: "composer" }, feld, el("div", { class: "tools" }, diktatKnopf(feld))),
    el("div", { class: "actions" }, knopf, el("button", { type: "button", class: "text", onclick: () => box.remove() }, "So lassen")),
    slot);

  const anwenden = async (freigabe = false) => {
    const antwort = feld.value.trim();
    if (!antwort) { feld.setAttribute("aria-invalid", "true"); feld.focus(); return; }
    knopf.setAttribute("aria-disabled", "true");
    fill(slot, el("p", { class: "waiting" }, el("span", { class: "spinner", "aria-hidden": "true" }), modus === "claude" ? "Claude schärft die Lesson …" : "Wird ergänzt …"));
    try {
      let update;
      if (modus === "claude") {
        const neu = await api("/api/erfassen/entwurf", {
          method: "POST",
          body: { text: eintrag.rohtext, quelle: eintrag.quelle, bereich: lesson.bereich, rueckfrage: e.rueckfrage, antwort, freigabe },
        });
        update = { lesson: neu.lesson || lesson.lesson, titel: neu.titel || lesson.titel, situation: neu.situation || lesson.situation,
          ereignis: neu.ereignis || lesson.ereignis, massnahme: neu.massnahme || lesson.massnahme, tags: neu.tags?.length ? neu.tags : lesson.tags };
      } else {
        // Lokal oder manuell: nichts an Claude, die Antwort ergänzt das Ereignis.
        update = { ereignis: `${lesson.ereignis}\n${antwort}` };
      }
      if (e.rueckfrage_art === "spezifitaet") update.spezifisch = true;
      const res = await api(`/api/lessons/${lesson.id}`, { method: "PUT", body: update });
      const q = karte.querySelector(".quote");
      if (q) { q.textContent = anf(res.lesson.lesson); q.classList.toggle("own", Boolean(res.lesson.spezifisch)); }
      fill(box, el("p", { class: "row", style: "gap:6px;margin:0;color:var(--success)" }, icon("check", "icon sm"), "Geschärft."));
      say("Lesson geschärft.");
    } catch (err) {
      knopf.removeAttribute("aria-disabled");
      if (istPruefung(err)) {
        fill(slot, el("div", { class: "notice warn" }, icon("shield"), el("div", {}, el("strong", {}, err.message),
          el("ul", {}, err.hinweise.map((h) => el("li", {}, anf(h)))),
          el("div", { class: "actions" },
            err.code === "sperrliste" ? null : el("button", { type: "button", onclick: () => anwenden(true) }, "Trotzdem senden"),
            el("button", { type: "button", class: "text", onclick: () => { fill(slot); feld.focus(); } }, "Text anpassen")))));
      } else {
        fill(slot, errorNotice(err));
      }
    }
  };
  knopf.addEventListener("click", () => anwenden(false));
  return box;
}

export async function loeschenBestaetigen(lesson) {
  return bestaetigen({ titel: `„${kuerzen(lesson.titel, 60)}“ löschen?`, text: "Das lässt sich nicht rückgängig machen. Fotos werden mit gelöscht.", ok: "Löschen", gefahr: true });
}
