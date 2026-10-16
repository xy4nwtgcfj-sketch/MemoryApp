// Lessons Vault PWA: Vanilla JS, keine Build-Schritte.

const view = document.getElementById("view");
const statsEl = document.getElementById("stats");
const toastEl = document.getElementById("toast");

const SEVERITY = {
  1: "1 · kleiner Ärger",
  2: "2 · lästig",
  3: "3 · spürbarer Verlust",
  4: "4 · teuer",
  5: "5 · großer Schaden",
};
const FIELD_LABELS = { titel: "Titel", situation: "Situation", ereignis: "Ereignis", lesson: "Lesson (Regel)", bereich: "Bereich" };

const store = {
  get(key, fallback = "") {
    try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, value); } catch { /* privat oder blockiert */ }
  },
};

// ---------------------------------------------------------------- Helfer
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "value") node.value = value;
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function render(...nodes) {
  view.replaceChildren(el("div", {}, nodes));
}

let toastTimer;
function toast(content, ms = 4000) {
  toastEl.replaceChildren(content instanceof Node ? content : document.createTextNode(content));
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, ms);
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
  return isNaN(d) ? iso.slice(0, 10) : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function api(path, { method = "GET", body, raw = false } = {}) {
  const headers = {};
  const token = store.get("lv-token");
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Server nicht erreichbar. Läuft der Home-PC und ist Tailscale verbunden?");
  }
  if (res.status === 401) {
    throw new ApiError(401, "Token fehlt oder ist falsch. Bitte unter Einstellungen eintragen.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = Array.isArray(data.detail) ? data.detail.map((d) => `${d.loc?.slice(-1)[0] ?? ""}: ${d.msg}`).join("; ") : data.detail;
    } catch { /* kein JSON */ }
    throw new ApiError(res.status, detail || `Fehler ${res.status}`);
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

function errorNotice(err) {
  return el("div", { class: "notice warn", role: "alert" }, err.message || String(err));
}

let bereicheCache = null;
async function bereiche(refresh = false) {
  if (!bereicheCache || refresh) bereicheCache = await api("/api/bereiche");
  return bereicheCache;
}

async function refreshStats() {
  try {
    const [s, status] = await Promise.all([api("/api/statistik"), api("/api/status").catch(() => null)]);
    statsEl.textContent = `${s.gesamt} Lessons · ${s.neu_erfasst_7_tage} diese Woche`;
    // "Prüfen" nur zeigen, wenn lokal strukturiert wird oder Entwürfe offen sind.
    const lokalAktiv = status && (status.modus_standard === "lokal" || Object.values(status.modi || {}).includes("lokal"));
    document.querySelector('.tabbar a[data-tab="pruefen"]').hidden = !(s.offene_entwuerfe || lokalAktiv || location.hash.startsWith("#/pruefen") || location.hash.startsWith("#/entwurf"));
    const badge = document.getElementById("pruefen-count");
    badge.hidden = !s.offene_entwuerfe;
    badge.textContent = s.offene_entwuerfe || "";
  } catch {
    statsEl.textContent = "";
  }
}

// --------------------------------------------------------- Lesson-Formular
function lessonForm(data, { bereichListe, onChange } = {}) {
  const fields = {};
  const changed = () => onChange && onChange(read());

  const input = (name, label, { multiline = false, hint = "", rows = 2, max } = {}) => {
    const id = `f-${name}`;
    const control = multiline
      ? el("textarea", { id, name, rows, oninput: changed }, data[name] ?? "")
      : el("input", { id, name, type: "text", value: data[name] ?? "", maxlength: max, oninput: changed });
    if (multiline) control.value = data[name] ?? "";
    fields[name] = control;
    return [el("label", { for: id }, label, hint ? el("span", { class: "hint" }, ` ${hint}`) : null), control];
  };

  const aktive = bereichListe.filter((b) => b.aktiv || b.name === data.bereich);
  const bereichSelect = el(
    "select",
    { id: "f-bereich", name: "bereich", onchange: changed },
    el("option", { value: "" }, "Bitte wählen"),
    aktive.map((b) => el("option", { value: b.name, selected: b.name === data.bereich }, b.name)),
  );
  fields.bereich = bereichSelect;

  const sevSelect = el(
    "select",
    { id: "f-schweregrad", name: "schweregrad", onchange: changed },
    [1, 2, 3, 4, 5].map((n) => el("option", { value: n, selected: Number(data.schweregrad || 3) === n }, SEVERITY[n])),
  );
  fields.schweregrad = sevSelect;

  const tags = el("input", { id: "f-tags", type: "text", value: (data.tags || []).join(", "), oninput: changed, autocapitalize: "off" });
  fields.tags = tags;

  // Persönlich vs. Allgemeinwissen: vorbelegt aus gespeichertem Wert oder Claudes Einschätzung, änderbar.
  const startwert = data.spezifisch ?? (data.spezifitaet === "persoenlich" ? true : data.spezifitaet === "allgemein" ? false : null);
  let spezifischBeruehrt = false;
  const spezifisch = el("input", {
    type: "checkbox",
    id: "f-spezifisch",
    checked: startwert === true,
    onchange: () => { spezifischBeruehrt = true; changed(); },
  });

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
      spezifisch: spezifischBeruehrt || startwert !== null ? spezifisch.checked : null,
    };
  }

  const node = el(
    "div",
    {},
    input("lesson", "Lesson", { multiline: true, hint: "(ein Satz, als Regel: „Vor X immer Y“)" }),
    input("titel", "Titel", { hint: "(max. 80 Zeichen)", max: 80 }),
    input("situation", "Situation", { multiline: true, rows: 3 }),
    input("ereignis", "Was ist passiert?", { multiline: true, rows: 3 }),
    input("massnahme", "Maßnahme", { multiline: true, hint: "(optional: Checklisten-Punkt)" }),
    el(
      "div",
      { class: "grid2" },
      el("div", {}, el("label", { for: "f-bereich" }, "Bereich"), bereichSelect),
      el("div", {}, el("label", { for: "f-schweregrad" }, "Schweregrad"), sevSelect),
    ),
    el("label", { for: "f-tags" }, "Tags", el("span", { class: "hint" }, " (mit Komma getrennt)")),
    tags,
    el("label", { class: "check", style: "margin-top:12px" }, spezifisch,
      el("span", {}, "Persönliche Erfahrung", el("br"),
        el("span", { class: "muted small" }, "Etwas, das kein Lehrbuch und kein KI-Assistent von sich aus sagen würde"))),
  );
  return { node, read };
}

function missingFields(data) {
  return Object.keys(FIELD_LABELS).filter((key) => !String(data[key] || "").trim());
}

function complianceBox(hinweise) {
  const box = el("div", { class: "notice warn", role: "alert", hidden: !hinweise.length });
  const update = (list) => {
    box.hidden = !list.length;
    box.replaceChildren(
      el("strong", {}, "Datenschutz-Hinweis: bitte abstrahieren"),
      el("ul", {}, list.map((h) => el("li", {}, h))),
    );
  };
  update(hinweise);
  return { node: box, update };
}

// ----------------------------------------------------------------- Erfassen
const capture = { text: "", quelle: "text", start: null, rueckfrage: "", bereich: "" };
const MODUS_TEXT = {
  claude: "Claude, sofort",
  lokal: "lokal im Hintergrund",
  manuell: "manuell ausfüllen",
};

function resetCapture() {
  capture.text = "";
  capture.quelle = "text";
  capture.start = null;
  capture.rueckfrage = "";
}

function captureSeconds() {
  return capture.start ? Math.round((Date.now() - capture.start) / 100) / 10 : null;
}

function startTimer() {
  if (!capture.start) capture.start = Date.now();
}

function speechButton(textarea, {
  onStart = startTimer,
  onResult = (text) => { capture.text = text; capture.quelle = "sprache"; },
} = {}) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  let recognition = null;
  let base = "";
  const button = el("button", { type: "button", class: "mic", "aria-pressed": "false", title: "Diktieren" }, "🎤 Diktieren");
  const stop = () => {
    recognition?.stop();
    recognition = null;
    button.setAttribute("aria-pressed", "false");
    button.textContent = "🎤 Diktieren";
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
      onResult(textarea.value);
    };
    recognition.onerror = (event) => {
      toast(event.error === "not-allowed" ? "Mikrofon nicht erlaubt. Braucht HTTPS (tailscale serve) und Freigabe im Browser." : `Spracherkennung: ${event.error}`);
      stop();
    };
    recognition.onend = () => { if (recognition) stop(); };
    recognition.start();
    button.setAttribute("aria-pressed", "true");
    button.textContent = "■ Stopp";
  });
  return button;
}

async function viewErfassen() {
  const textarea = el("textarea", {
    id: "capture-text",
    class: "capture",
    placeholder: "Was ist passiert, was nimmst du mit? Drei Stichworte reichen.\nz. B. \u201EBankgespräch, Gehaltsnachweise vergessen, zweiter Termin\u201C",
    oninput: () => { startTimer(); capture.text = textarea.value; },
  });
  textarea.value = capture.text;
  const [status, bereichListe] = await Promise.all([
    api("/api/status").catch(() => ({ ki: false, modi: {}, modus_standard: "manuell" })),
    bereiche().catch(() => []),
  ]);
  const aktive = bereichListe.filter((b) => b.aktiv);
  if (capture.bereich && !aktive.some((b) => b.name === capture.bereich)) capture.bereich = "";
  const modusFuer = (bereich) => (bereich ? status.modi?.[bereich] : status.modus_standard) || "manuell";

  const mic = speechButton(textarea);
  const result = el("div", { id: "draft" });
  const modusInfo = el("p", { class: "muted small", "aria-live": "polite" });
  const structureBtn = el("button", { type: "button", class: "primary" });

  const updateModus = () => {
    const modus = modusFuer(capture.bereich);
    modusInfo.textContent = `Verarbeitung: ${MODUS_TEXT[modus]}.` +
      (modus === "lokal" && mic ? " Hinweis: Das Diktat nutzt die Spracherkennung des Browsers (Google/Apple). Für vertrauliche Inhalte lieber tippen." : "");
    structureBtn.textContent = modus === "lokal" ? "Speichern" : modus === "claude" ? "Strukturieren" : "Weiter";
  };

  const chips = el("div", { class: "chips", role: "group", "aria-label": "Bereich (optional)" });
  const renderChips = () => {
    chips.replaceChildren(...aktive.map((b) => el("button", {
      type: "button",
      class: "chip",
      "aria-pressed": String(capture.bereich === b.name),
      onclick: () => { capture.bereich = capture.bereich === b.name ? "" : b.name; renderChips(); updateModus(); },
    }, b.name, modusFuer(b.name) === "lokal" ? el("small", {}, "lokal") : null)));
  };
  renderChips();
  updateModus();

  const go = async (manual = false) => {
    const text = textarea.value.trim();
    if (!text && !manual) {
      textarea.focus();
      return toast("Erst ein paar Stichworte eingeben.");
    }
    startTimer();
    capture.text = text;
    if (manual) {
      return showDraft(result, { titel: text.split("\n")[0].slice(0, 80), ereignis: text, bereich: capture.bereich, quelle: capture.quelle, schweregrad: 3, tags: [], compliance_hinweise: [], aehnliche: [], ki_verwendet: false });
    }
    structureBtn.disabled = true;
    const modus = modusFuer(capture.bereich);
    if (modus === "claude") result.replaceChildren(el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Claude strukturiert …"));
    try {
      const res = await api("/api/erfassen", {
        method: "POST",
        body: { text, quelle: capture.quelle, bereich: capture.bereich, erfassung_sekunden: captureSeconds() },
      });
      if (res.modus === "hintergrund") {
        const seconds = captureSeconds();
        resetCapture();
        refreshStats();
        toast(el("span", {}, `Gespeichert${seconds ? ` in ${Math.round(seconds)} s` : ""}. Wird lokal strukturiert und erscheint dann unter `, el("a", { href: "#/pruefen" }, "Prüfen"), "."), 7000);
        return viewErfassen();
      }
      showDraft(result, res.entwurf);
    } catch (err) {
      result.replaceChildren(errorNotice(err));
    } finally {
      structureBtn.disabled = false;
    }
  };
  structureBtn.addEventListener("click", () => go(false));

  render(
    el("h2", {}, "Neue Lesson"),
    el("label", { for: "capture-text", class: "sr-only" }, "Stichworte"),
    textarea,
    aktive.length > 1 ? chips : null,
    modusInfo,
    el("div", { class: "actions" }, structureBtn, mic, el("button", { type: "button", class: "ghost", onclick: () => go(true) }, "Manuell")),
    result,
  );
  if (!capture.text) textarea.focus();
}

async function requestDraft(container, body) {
  container.replaceChildren(el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Claude strukturiert …"));
  try {
    const entwurf = await api("/api/erfassen/entwurf", { method: "POST", body: { ...body, bereich: capture.bereich } });
    showDraft(container, entwurf);
  } catch (err) {
    container.replaceChildren(errorNotice(err));
  }
}

async function showDraft(container, entwurf, { entwurfId = null } = {}) {
  const fertig = () => {
    resetCapture();
    refreshStats();
  };
  const bereichListe = await bereiche();
  const compliance = complianceBox(entwurf.compliance_hinweise || []);
  const missingNote = el("p", { class: "muted small" });
  const saveBtn = el("button", { type: "button", class: "primary" }, "Speichern");

  const recheck = debounce(async (data) => {
    try {
      const text = [data.titel, data.situation, data.ereignis, data.lesson, data.massnahme, ...data.tags].join("\n");
      compliance.update(await api("/api/compliance", { method: "POST", body: { text, bereich: data.bereich } }));
    } catch { /* Hinweis bleibt wie er war */ }
  }, 600);

  const updateMissing = (data) => {
    const missing = missingFields(data);
    saveBtn.disabled = missing.length > 0;
    missingNote.textContent = missing.length ? `Noch offen: ${missing.map((m) => FIELD_LABELS[m]).join(", ")}` : "";
  };

  const form = lessonForm(entwurf, {
    bereichListe,
    onChange: (data) => { updateMissing(data); recheck(data); },
  });

  const parts = [];
  if (entwurf.ki_fehler) parts.push(el("div", { class: "notice warn" }, entwurf.ki_fehler));

  if (entwurf.rueckfrage) {
    const persoenlich = entwurf.rueckfrage_art === "spezifitaet";
    const answer = el("input", { type: "text", id: "rueckfrage-antwort", placeholder: persoenlich ? "Was war bei dir konkret?" : "Kurze Antwort" });
    const submit = async () => {
      if (!answer.value.trim()) return answer.focus();
      if (entwurfId) {
        try {
          await api(`/api/entwuerfe/${entwurfId}/antwort`, { method: "POST", body: { antwort: answer.value.trim() } });
          toast("Antwort gespeichert. Der Entwurf wird im Hintergrund neu strukturiert.");
          location.hash = "#/pruefen";
        } catch (err) { toast(err.message); }
        return;
      }
      requestDraft(container, { text: capture.text, quelle: entwurf.quelle, rueckfrage: entwurf.rueckfrage, antwort: answer.value.trim() });
    };
    answer.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
    parts.push(
      el(
        "div",
        { class: "card" },
        persoenlich ? el("strong", {}, "Was ist dein persönlicher Teil?") : null,
        el("label", { for: "rueckfrage-antwort", style: persoenlich ? "font-weight:400" : null }, persoenlich ? entwurf.rueckfrage : `Rückfrage: ${entwurf.rueckfrage}`),
        el("div", { class: "row" }, el("div", { class: "grow" }, answer), el("button", { type: "button", onclick: submit }, "Antworten")),
        el("p", { class: "muted small" }, persoenlich
          ? "Optional. Genau das unterscheidet deine Lesson von dem, was Claude ohnehin weiß. Du kannst auch direkt speichern."
          : "Oder unten direkt ergänzen."),
      ),
    );
  }

  if (entwurf.spezifitaet === "allgemein" && !entwurf.rueckfrage) {
    parts.push(el("div", { class: "notice info" },
      el("strong", {}, "Klingt noch nach Allgemeinwissen"),
      `${entwurf.spezifitaet_hinweis ? entwurf.spezifitaet_hinweis + " " : ""}Ergänze in der Lesson, was bei dir konkret anders war, oder speichere so.`));
  }

  if (entwurf.dublette) {
    const d = entwurf.dublette;
    parts.push(
      el(
        "div",
        { class: "card" },
        el("strong", {}, "Das kennst du schon:"),
        el("h3", {}, d.titel),
        el("p", { class: "rule" }, d.lesson),
        el("p", { class: "muted small" }, entwurf.dublette_begruendung || "", ` Bisher ${d.bestaetigungen}× erlebt, Status ${d.status}.`),
        el(
          "div",
          { class: "actions" },
          el("button", {
            type: "button",
            class: "primary",
            onclick: async (e) => {
              e.target.disabled = true;
              try {
                const lesson = await api(`/api/lessons/${d.id}/bestaetigen`, { method: "POST", body: { notiz: capture.text || entwurf.ereignis || "", entwurf_id: entwurfId } });
                fertig();
                toast(`Als Bestätigung gezählt (${lesson.bestaetigungen}×, ${lesson.status}).`);
                location.hash = `#/lesson/${d.id}`;
              } catch (err) {
                e.target.disabled = false;
                toast(err.message);
              }
            },
          }, "Als Bestätigung zählen"),
          el("button", { type: "button", onclick: (e) => e.target.closest(".card").remove() }, "Neu anlegen"),
        ),
      ),
    );
  }

  parts.push(compliance.node, form.node, missingNote);

  if (entwurf.aehnliche?.length) {
    parts.push(
      el(
        "details",
        { class: "card" },
        el("summary", {}, `Ähnliche Lessons (${entwurf.aehnliche.length})`),
        entwurf.aehnliche.map((a) => el("p", {}, el("a", { href: `#/lesson/${a.id}` }, a.titel), el("br"), el("span", { class: "muted small" }, a.lesson))),
      ),
    );
  }

  saveBtn.addEventListener("click", async () => {
    const data = form.read();
    if (missingFields(data).length) return;
    saveBtn.disabled = true;
    const seconds = entwurfId ? null : captureSeconds();
    try {
      const res = await api("/api/lessons", {
        method: "POST",
        body: { ...data, quelle: entwurf.quelle || capture.quelle, erfassung_sekunden: seconds, entwurf_id: entwurfId },
      });
      fertig();
      const msg = el("span", {}, `Gespeichert${seconds ? ` in ${Math.round(seconds)} s` : ""}. `, el("a", { href: `#/lesson/${res.lesson.id}` }, "Ansehen"));
      if (res.compliance_hinweise.length) msg.append(" · Datenschutz-Hinweise beachten.");
      if (res.embedding_fehler) msg.append(` · ${res.embedding_fehler}`);
      toast(msg, 6000);
      if (entwurfId) location.hash = "#/pruefen";
      else viewErfassen();
    } catch (err) {
      saveBtn.disabled = false;
      toast(err.message, 6000);
    }
  });

  parts.push(el("div", { class: "actions" }, saveBtn, el("button", {
    type: "button",
    class: "ghost",
    onclick: async () => {
      if (!entwurfId) { resetCapture(); return viewErfassen(); }
      if (!confirm("Entwurf endgültig verwerfen?")) return;
      try { await api(`/api/entwuerfe/${entwurfId}`, { method: "DELETE" }); refreshStats(); location.hash = "#/pruefen"; }
      catch (err) { toast(err.message); }
    },
  }, "Verwerfen")));
  container.replaceChildren(el("div", {}, parts));
  updateMissing(form.read());
  container.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ----------------------------------------------------------------- Briefing
const briefingState = { situation: "", bereich: "" };

function checklistText(situation, items) {
  return [`Checkliste: ${situation}`, "", ...items.map((i) => `- [ ] ${i.punkt}`)].join("\n");
}

async function copyText(text) {
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

function whyLine(t) {
  const l = t.lesson;
  const teile = [`Relevanz ${Math.round(t.relevanz * 100)} %`, `Schwere ${l.schweregrad}`];
  if (l.bestaetigungen > 1) teile.push(`${l.bestaetigungen}× erlebt`);
  if (t.faktoren.feedback > 1.01) teile.push("früher hilfreich");
  if (t.faktoren.feedback < 0.99) teile.push("früher als unpassend markiert");
  return teile.join(" · ");
}

async function viewBriefing(id) {
  const situation = el("textarea", {
    id: "briefing-text",
    rows: 3,
    placeholder: "Was steht an? z. B. \u201EProjektplanung für Rollout Welle 4 schreiben\u201C oder \u201EBesichtigung in Wuppertal morgen\u201C",
    oninput: () => { briefingState.situation = situation.value; },
  });
  situation.value = briefingState.situation;
  const result = el("div", { id: "briefing-result" });
  const bereichListe = (await bereiche().catch(() => [])).filter((b) => b.aktiv);
  const chips = el("div", { class: "chips", role: "group", "aria-label": "Bereich (optional)" });
  const renderChips = () => chips.replaceChildren(...bereichListe.map((b) => el("button", {
    type: "button",
    class: "chip",
    "aria-pressed": String(briefingState.bereich === b.name),
    onclick: () => { briefingState.bereich = briefingState.bereich === b.name ? "" : b.name; renderChips(); },
  }, b.name)));
  renderChips();
  const mic = speechButton(situation, { onStart: () => {}, onResult: (t) => { briefingState.situation = t; } });

  const go = async () => {
    const text = situation.value.trim();
    if (text.length < 3) { situation.focus(); return toast("Beschreib kurz, was ansteht."); }
    goBtn.disabled = true;
    result.replaceChildren(el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Suche passende Erfahrungen …"));
    try {
      const data = await api("/api/briefing", { method: "POST", body: { situation: text, bereich: briefingState.bereich } });
      history.replaceState(null, "", `#/briefing/${data.id}`);
      showBriefing(result, data);
    } catch (err) {
      result.replaceChildren(errorNotice(err));
    } finally {
      goBtn.disabled = false;
    }
  };
  const goBtn = el("button", { type: "button", class: "primary", onclick: go }, "Briefing erstellen");

  render(
    el("h2", {}, "Briefing"),
    el("p", { class: "muted small", style: "margin-top:0" }, "Beschreib die anstehende Situation in einem Satz. Du bekommst deine wichtigsten Erfahrungen dazu und eine Checkliste."),
    el("label", { for: "briefing-text", class: "sr-only" }, "Situation"),
    situation,
    bereichListe.length > 1 ? chips : null,
    el("div", { class: "actions" }, goBtn, mic),
    result,
  );

  if (id) {
    try {
      const data = await api(`/api/briefing/${encodeURIComponent(id)}`);
      situation.value = briefingState.situation = data.situation;
      showBriefing(result, data);
    } catch (err) {
      result.replaceChildren(errorNotice(err));
    }
  } else {
    showVerlauf(result);
  }
}

async function showVerlauf(container) {
  try {
    const verlauf = await api("/api/briefings?limit=10");
    if (!verlauf.length) return;
    container.replaceChildren(
      el("h2", {}, "Frühere Briefings"),
      ...verlauf.map((b) => el("a", { class: "card result", href: `#/briefing/${b.id}` },
        el("p", { class: "rule" }, b.situation),
        el("div", { class: "badges" },
          el("span", { class: "badge" }, formatDate(b.erstellt_am)),
          el("span", { class: "badge" }, `${b.anzahl} Lessons`),
          b.hilfreich ? el("span", { class: "badge status-bestätigt" }, `${b.hilfreich} hilfreich`) : null,
          b.bereich ? el("span", { class: "badge" }, b.bereich) : null))),
    );
  } catch { /* Verlauf ist optional */ }
}

function showBriefing(container, data) {
  if (!data.treffer.length) {
    container.replaceChildren(
      el("div", { class: "notice info" },
        el("strong", {}, "Dazu hast du noch keine Erfahrungen gespeichert."),
        "Probier andere Stichworte oder ohne Bereichsfilter. Und nach der Aufgabe: ",
        el("a", { href: "#/erfassen" }, "eine Lesson erfassen"), "."),
    );
    return;
  }
  const feedback = { ...data.feedback };
  const summaryCard = el("div", { class: "card" }, el("strong", {}, "Worauf du achten solltest"));
  const checklistCard = el("div", { class: "card" });

  const renderChecklist = (items, quelle) => {
    const titel = Object.fromEntries(data.treffer.map((t) => [t.lesson.id, t.lesson.titel]));
    checklistCard.replaceChildren(
      el("div", { class: "row" },
        el("strong", { class: "grow" }, "Checkliste"),
        el("button", {
          type: "button",
          onclick: async () => toast((await copyText(checklistText(data.situation, items))) ? "Checkliste kopiert." : "Kopieren nicht möglich."),
        }, "Kopieren")),
      el("p", { class: "muted small", style: "margin:4px 0 0" }, quelle),
      el("ul", { class: "checklist" }, items.map((item, i) => el("li", {},
        el("input", { type: "checkbox", id: `cl-${i}` }),
        el("label", { for: `cl-${i}`, style: "margin:0;font-weight:400" },
          el("span", {}, item.punkt),
          titel[item.lesson_id] ? el("span", { class: "src" }, `aus: ${titel[item.lesson_id]}`) : null)))),
    );
  };

  const loadSummary = async (neu = false) => {
    summaryCard.replaceChildren(el("strong", {}, "Worauf du achten solltest"),
      el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Claude fasst zusammen …"));
    try {
      const res = await api(`/api/briefing/${data.id}/zusammenfassung${neu ? "?neu=true" : ""}`, { method: "POST" });
      showSummary(res);
    } catch (err) {
      summaryCard.replaceChildren(el("strong", {}, "Worauf du achten solltest"),
        el("div", { class: "notice warn" }, err.message),
        el("button", { type: "button", onclick: () => loadSummary(neu) }, "Erneut versuchen"));
    }
  };

  const showSummary = (res) => {
    summaryCard.replaceChildren(
      el("strong", {}, "Worauf du achten solltest"),
      el("p", { class: "summary" }, res.zusammenfassung || "Claude sah keinen klaren Bezug zu dieser Situation. Die Lessons unten sind trotzdem die besten Treffer."),
      res.ki_hinweis ? el("p", { class: "muted small" }, res.ki_hinweis) : null,
      el("p", { class: "muted small" }, "Zusammengefasst von Claude, nur aus deinen Lessons. ",
        el("button", { type: "button", class: "ghost", style: "min-height:32px;padding:2px 6px", onclick: () => loadSummary(true) }, "Neu formulieren")),
    );
    if (res.ki_checkliste?.length) renderChecklist(res.ki_checkliste, "Auf die Situation zugeschnitten (Claude)");
  };

  renderChecklist(data.checkliste, "Aus den Maßnahmen deiner Lessons");

  const lessonCards = data.treffer.map((t) => {
    const l = t.lesson;
    const card = el("div", { class: `card result ${feedback[l.id] === "nicht_relevant" ? "abgewertet" : ""}` });
    const up = el("button", { type: "button", class: "up" }, "👍 Hilfreich");
    const down = el("button", { type: "button", class: "down" }, "Nicht relevant");
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
      } catch (err) { toast(err.message); }
    };
    up.addEventListener("click", () => send("hilfreich"));
    down.addEventListener("click", () => send("nicht_relevant"));
    sync();
    card.append(...[
      el("a", { href: `#/lesson/${l.id}`, style: "color:inherit;text-decoration:none" },
        el("h3", {}, l.titel),
        el("p", { class: "rule" }, l.lesson)),
      l.massnahme ? el("p", { class: "small", style: "margin:6px 0 0" }, el("strong", { style: "display:inline" }, "Maßnahme: "), l.massnahme) : null,
      badges(l),
      el("p", { class: "why" }, whyLine(t)),
      el("div", { class: "feedback", role: "group", "aria-label": "War das hilfreich?" }, up, down),
    ].filter(Boolean));
    return card;
  });

  container.replaceChildren(
    data.ki_moeglich || data.zusammenfassung ? summaryCard : (data.ki_hinweis ? el("p", { class: "muted small" }, data.ki_hinweis) : null),
    checklistCard,
    el("h2", {}, `Deine Erfahrungen (${data.treffer.length})`),
    el("p", { class: "muted small", style: "margin-top:0" }, "Markiere, was dir geholfen hat. Das verbessert künftige Briefings zu ähnlichen Situationen."),
    ...lessonCards,
  );
  if (data.zusammenfassung) showSummary(data);
  else if (data.ki_moeglich) loadSummary();
}

// ------------------------------------------------------------------- Prüfen
const STATUS_TEXT = { wartet: "wartet", in_arbeit: "wird strukturiert", fertig: "bereit zur Prüfung", fehler: "Fehler" };
let pruefenTimer = null;

function relTime(iso) {
  const min = Math.round((Date.now() - new Date(iso)) / 60000);
  if (min < 1) return "gerade eben";
  if (min < 60) return `vor ${min} Min.`;
  if (min < 24 * 60) return `vor ${Math.round(min / 60)} Std.`;
  return formatDate(iso);
}

function entwurfCard(e) {
  const klickbar = e.status === "fertig" || e.status === "fehler";
  const inhalt = [
    el("h3", {}, e.entwurf?.titel || e.rohtext.split("\n")[0].slice(0, 80)),
    el("p", { class: "raw muted" }, e.rohtext.length > 180 ? e.rohtext.slice(0, 180) + " …" : e.rohtext),
    el("div", { class: "badges" },
      el("span", { class: `badge st-${e.status}` }, STATUS_TEXT[e.status]),
      e.bereich_vorgabe ? el("span", { class: "badge" }, e.bereich_vorgabe) : null,
      el("span", { class: "badge" }, relTime(e.erstellt_am)),
      e.dauer_sekunden ? el("span", { class: "badge" }, `${Math.round(e.dauer_sekunden)} s Rechenzeit`) : null,
    ),
    e.fehler ? el("p", { class: "small", style: "color:var(--danger)" }, e.fehler) : null,
  ];
  return klickbar
    ? el("a", { class: "card result", href: `#/entwurf/${e.id}` }, inhalt)
    : el("div", { class: "card result" }, inhalt);
}

async function viewPruefen() {
  const [data, status] = await Promise.all([api("/api/entwuerfe"), api("/api/status").catch(() => ({}))]);
  const offen = data.eintraege.filter((e) => e.status === "wartet" || e.status === "in_arbeit").length;
  const bereit = data.eintraege.filter((e) => e.status === "fertig" || e.status === "fehler");
  const warten = data.eintraege.filter((e) => e.status === "wartet" || e.status === "in_arbeit").reverse();
  const lokal = status.lokal || {};
  render(
    el("h2", {}, "Prüfen"),
    offen && lokal.konfiguriert && !lokal.erreichbar
      ? el("div", { class: "notice warn" }, "Ollama ist nicht erreichbar. Die Entwürfe warten, bis es wieder läuft. Nichts geht verloren.")
      : null,
    offen && lokal.erreichbar && !lokal.modell_installiert
      ? el("div", { class: "notice warn" }, `Das Modell ${lokal.modell} ist nicht installiert: `, el("code", {}, `ollama pull ${lokal.modell}`))
      : null,
    !data.eintraege.length ? el("div", { class: "empty" }, "Nichts zu prüfen. Lokal erfasste Lessons erscheinen hier, sobald sie strukturiert sind.") : null,
    bereit.length ? el("p", { class: "muted small" }, `${bereit.length} bereit`) : null,
    bereit.map(entwurfCard),
    warten.length ? el("h2", {}, `In Arbeit (${warten.length})`) : null,
    warten.length ? el("p", { class: "muted small" }, "Ein lokales Modell braucht auf deinem PC etwa 1 bis 3 Minuten pro Lesson.") : null,
    warten.map(entwurfCard),
  );
  clearTimeout(pruefenTimer);
  if (offen) {
    pruefenTimer = setTimeout(() => { if (location.hash === "#/pruefen") { refreshStats(); viewPruefen(); } }, 10000);
  }
}

async function viewEntwurf(id) {
  let e;
  try {
    e = await api(`/api/entwuerfe/${encodeURIComponent(id)}`);
  } catch (err) {
    return render(errorNotice(err), el("a", { href: "#/pruefen" }, "Zur Liste"));
  }
  const container = el("div");
  const neuBtn = el("button", {
    type: "button",
    class: "ghost",
    onclick: async () => {
      try { await api(`/api/entwuerfe/${e.id}/neu`, { method: "POST" }); toast("Wird neu strukturiert."); location.hash = "#/pruefen"; }
      catch (err) { toast(err.message); }
    },
  }, "Neu strukturieren");
  render(
    el("p", {}, el("a", { href: "#/pruefen" }, "← Prüfen")),
    el("div", { class: "card" },
      el("strong", {}, "Deine Notiz"),
      el("p", { class: "raw" }, e.rohtext),
      e.antwort ? el("p", { class: "raw muted small" }, `Ergänzung: ${e.antwort}`) : null,
      el("p", { class: "muted small" }, `${relTime(e.erstellt_am)}${e.modell ? ` · ${e.modell}` : ""}${e.dauer_sekunden ? ` · ${Math.round(e.dauer_sekunden)} s` : ""}`),
      el("div", { class: "actions" }, neuBtn),
    ),
    e.status === "fehler" ? el("div", { class: "notice warn" }, `Strukturierung fehlgeschlagen: ${e.fehler}. Du kannst selbst ausfüllen oder es neu versuchen.`) : null,
    container,
  );
  capture.text = e.rohtext;
  const entwurf = e.entwurf || { titel: e.rohtext.split("\n")[0].slice(0, 80), ereignis: e.rohtext, bereich: e.bereich_vorgabe, quelle: e.quelle, schweregrad: 3, tags: [], compliance_hinweise: [], aehnliche: [] };
  await showDraft(container, entwurf, { entwurfId: e.id });
  window.scrollTo(0, 0);
}

// -------------------------------------------------------------------- Suche
const searchState = { q: "", modus: "hybrid", bereich: "", status: "", schweregrad_min: "", von: "", bis: "" };

function badges(l) {
  return el(
    "div",
    { class: "badges" },
    el("span", { class: "badge" }, l.bereich),
    el("span", { class: `badge status-${l.status}` }, l.status),
    el("span", { class: "badge sev", title: "Schweregrad" }, `Schwere ${l.schweregrad}`),
    l.bestaetigungen > 1 ? el("span", { class: "badge" }, `${l.bestaetigungen}× erlebt`) : null,
    l.spezifisch === true ? el("span", { class: "badge", title: "Persönliche Erfahrung" }, "persönlich") : null,
    l.spezifisch === false ? el("span", { class: "badge", title: "Eher Allgemeinwissen" }, "allgemein") : null,
    el("span", { class: "badge" }, formatDate(l.erstellt_am)),
  );
}

function resultCard(item) {
  const l = item.lesson;
  return el(
    "a",
    { class: `card result ${l.status === "überholt" ? "ueberholt" : ""}`, href: `#/lesson/${l.id}` },
    el("h3", {}, l.titel),
    el("p", { class: "rule" }, l.lesson),
    badges(l),
    item.gefunden_durch?.length ? el("p", { class: "muted small" }, `gefunden über ${item.gefunden_durch.join(" + ")}`) : null,
  );
}

async function viewSuche() {
  const status = await api("/api/status").catch(() => ({}));
  const bereichListe = await bereiche().catch(() => []);
  const results = el("div", { "aria-live": "polite" });
  const q = el("input", { type: "search", id: "q", value: searchState.q, placeholder: "Stichwort oder Frage, z. B. „Was weiß ich über Bankgespräche?“", enterkeyhint: "search" });

  const run = async () => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(searchState)) if (v !== "") params.set(k, v);
    results.replaceChildren(el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Suche …"));
    try {
      const [items, drafts] = await Promise.all([
        api(`/api/suche?${params}`),
        searchState.q.trim() ? api(`/api/entwuerfe?q=${encodeURIComponent(searchState.q)}`).catch(() => ({ eintraege: [] })) : { eintraege: [] },
      ]);
      results.replaceChildren(
        drafts.eintraege.length
          ? el("details", { class: "card" },
            el("summary", {}, `Ungeprüfte Entwürfe (${drafts.eintraege.length})`),
            drafts.eintraege.map((d) => el("p", {},
              d.status === "fertig" || d.status === "fehler" ? el("a", { href: `#/entwurf/${d.id}` }, d.entwurf?.titel || d.rohtext.slice(0, 80)) : el("span", {}, d.rohtext.slice(0, 80)),
              el("br"), el("span", { class: "muted small" }, STATUS_TEXT[d.status]))))
          : null,
        items.length
          ? el("p", { class: "muted small" }, searchState.q ? `${items.length} Treffer` : "Neueste Lessons")
          : el("div", { class: "empty" }, searchState.q ? "Nichts gefunden. Anderes Stichwort oder Modus probieren." : "Noch keine Lessons. Leg los unter „Erfassen“ oder importiere deinen Startbestand."),
        ...items.map(resultCard),
      );
    } catch (err) {
      results.replaceChildren(errorNotice(err));
    }
  };
  const runDebounced = debounce(run, 300);
  q.addEventListener("input", () => { searchState.q = q.value; runDebounced(); });

  const modes = [["hybrid", "Hybrid"], ["volltext", "Volltext"], ["semantisch", "Semantisch"]];
  const seg = el("div", { class: "segmented", role: "group", "aria-label": "Suchmodus" });
  for (const [value, label] of modes) {
    seg.append(el("button", {
      type: "button",
      "aria-pressed": String(searchState.modus === value),
      onclick: () => {
        searchState.modus = value;
        seg.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-pressed", String(modes[i][0] === value)));
        run();
      },
    }, label));
  }

  const select = (key, label, options) => {
    const node = el("select", { id: `s-${key}`, onchange: (e) => { searchState[key] = e.target.value; run(); } },
      options.map(([v, t]) => el("option", { value: v, selected: searchState[key] === String(v) }, t)));
    return el("div", {}, el("label", { for: `s-${key}` }, label), node);
  };
  const date = (key, label) => el("div", {}, el("label", { for: `s-${key}` }, label),
    el("input", { type: "date", id: `s-${key}`, value: searchState[key], onchange: (e) => { searchState[key] = e.target.value; run(); } }));
  const activeFilters = ["bereich", "status", "schweregrad_min", "von", "bis"].filter((k) => searchState[k]).length;

  render(
    el("h2", {}, "Suchen"),
    el("label", { for: "q", class: "sr-only" }, "Suchbegriff"),
    q,
    el("div", { style: "margin-top:8px" }, seg),
    status.semantisch === false && searchState.modus !== "volltext"
      ? el("p", { class: "muted small" }, "Hinweis: Ohne VOYAGE_API_KEY ist „Semantisch“ nur unscharf (Wortteile, Tippfehler), keine echte Bedeutungssuche.")
      : null,
    el(
      "details",
      { class: "card", open: activeFilters > 0 },
      el("summary", {}, `Filter${activeFilters ? ` (${activeFilters} aktiv)` : ""}`),
      el(
        "div",
        { class: "grid2" },
        select("bereich", "Bereich", [["", "Alle"], ...bereichListe.map((b) => [b.name, b.name])]),
        select("status", "Status", [["", "Alle"], ["neu", "neu"], ["bestätigt", "bestätigt"], ["überholt", "überholt"]]),
        select("schweregrad_min", "Schweregrad ab", [["", "Alle"], ...[2, 3, 4, 5].map((n) => [String(n), `${n}+`])]),
        el("div"),
        date("von", "Erfasst ab"),
        date("bis", "Erfasst bis"),
      ),
      el("div", { class: "actions" }, el("button", {
        type: "button",
        class: "ghost",
        onclick: () => { Object.assign(searchState, { bereich: "", status: "", schweregrad_min: "", von: "", bis: "" }); viewSuche(); },
      }, "Filter zurücksetzen")),
    ),
    results,
  );
  run();
}

// ------------------------------------------------------------------- Detail
async function viewLesson(id) {
  render(el("p", { class: "muted" }, "Lade …"));
  let data;
  try {
    data = await api(`/api/lessons/${encodeURIComponent(id)}`);
  } catch (err) {
    return render(errorNotice(err), el("a", { href: "#/suche" }, "Zur Suche"));
  }
  const l = data.lesson;
  const compliance = complianceBox(data.compliance_hinweise);

  const confirmBtn = el("button", {
    type: "button",
    class: "primary",
    onclick: async () => {
      const notiz = prompt("Erneut erlebt. Kurze Notiz (optional):", "");
      if (notiz === null) return;
      try {
        const updated = await api(`/api/lessons/${l.id}/bestaetigen`, { method: "POST", body: { notiz } });
        toast(`Bestätigt: jetzt ${updated.bestaetigungen}× erlebt.`);
        viewLesson(l.id);
      } catch (err) { toast(err.message); }
    },
  }, "Erneut erlebt");

  const statusBtn = el("button", {
    type: "button",
    onclick: async () => {
      const next = l.status === "überholt" ? (l.bestaetigungen >= 2 ? "bestätigt" : "neu") : "überholt";
      if (next === "überholt" && !confirm("Als überholt markieren? Sie bleibt sichtbar, wird aber später nicht mehr in Briefings ausgespielt.")) return;
      try {
        await api(`/api/lessons/${l.id}`, { method: "PUT", body: { status: next } });
        viewLesson(l.id);
      } catch (err) { toast(err.message); }
    },
  }, l.status === "überholt" ? "Wieder aktivieren" : "Als überholt markieren");

  const editBtn = el("button", { type: "button", onclick: () => editLesson(l) }, "Bearbeiten");
  const deleteBtn = el("button", {
    type: "button",
    class: "danger ghost",
    onclick: async () => {
      if (!confirm(`„${l.titel}“ endgültig löschen?`)) return;
      try {
        await api(`/api/lessons/${l.id}`, { method: "DELETE" });
        toast("Gelöscht.");
        refreshStats();
        location.hash = "#/suche";
      } catch (err) { toast(err.message); }
    },
  }, "Löschen");

  const field = (label, value) => (value ? [el("dt", {}, label), el("dd", {}, value)] : []);
  render(
    el("p", {}, el("a", { href: "#/suche" }, "← Suche")),
    el(
      "article",
      { class: "card" },
      el("h2", {}, l.titel),
      el("p", { class: "rule-big" }, l.lesson),
      badges(l),
      el(
        "dl",
        { class: "fields" },
        field("Maßnahme", l.massnahme || "Keine. Was würdest du beim nächsten Mal konkret anders machen?"),
        field("Situation", l.situation),
        field("Ereignis", l.ereignis),
        field("Tags", l.tags.join(", ")),
        field("Quelle", `${l.quelle}${l.erfassung_sekunden ? `, erfasst in ${Math.round(l.erfassung_sekunden)} s` : ""}`),
        field("Zuletzt geändert", formatDate(l.geaendert_am)),
      ),
    ),
    compliance.node,
    el("div", { class: "actions" }, confirmBtn, editBtn, statusBtn, deleteBtn),
    el("h2", {}, "Erlebt"),
    el("ul", { class: "card" }, data.protokoll.map((p) => el("li", {}, formatDate(p.datum), p.notiz ? ` · ${p.notiz}` : ""))),
  );
}

async function editLesson(l) {
  const form = lessonForm(l, { bereichListe: await bereiche() });
  const saveBtn = el("button", {
    type: "button",
    class: "primary",
    onclick: async () => {
      const data = form.read();
      const missing = missingFields(data);
      if (missing.length) return toast(`Noch offen: ${missing.map((m) => FIELD_LABELS[m]).join(", ")}`);
      saveBtn.disabled = true;
      try {
        const res = await api(`/api/lessons/${l.id}`, { method: "PUT", body: data });
        toast(res.compliance_hinweise.length ? "Gespeichert. Datenschutz-Hinweise beachten." : "Gespeichert.");
        viewLesson(l.id);
      } catch (err) {
        saveBtn.disabled = false;
        toast(err.message, 6000);
      }
    },
  }, "Speichern");
  render(
    el("h2", {}, "Lesson bearbeiten"),
    form.node,
    el("div", { class: "actions" }, saveBtn, el("button", { type: "button", class: "ghost", onclick: () => viewLesson(l.id) }, "Abbrechen")),
  );
}

// ------------------------------------------------------------ Einstellungen
function kiSection(status, einst, bereichListe) {
  const optionen = [["claude", "Claude (sofort)"], ["lokal", "Lokal (Hintergrund)"], ["manuell", "Manuell"]];
  const speichern = async (body) => {
    try { await api("/api/einstellungen", { method: "PUT", body }); toast("Gespeichert."); viewEinstellungen(); }
    catch (err) { toast(err.message); }
  };
  const standard = el("select", { id: "ki-standard", onchange: (e) => speichern({ strukturierung_standard: e.target.value }) },
    [["auto", "Automatisch"], ...optionen].map(([v, t]) => el("option", { value: v, selected: einst.strukturierung_standard === v }, t)));
  const proBereich = bereichListe.filter((b) => b.aktiv).map((b) => {
    const sel = el("select", {
      id: `ki-${b.name}`,
      onchange: (e) => {
        const map = { ...einst.strukturierung_bereiche };
        if (e.target.value) map[b.name] = e.target.value; else delete map[b.name];
        speichern({ strukturierung_bereiche: map });
      },
    }, [["", "wie Standard"], ...optionen].map(([v, t]) => el("option", { value: v, selected: (einst.strukturierung_bereiche[b.name] || "") === v }, t)));
    return el("div", {}, el("label", { for: `ki-${b.name}` }, b.name, el("span", { class: "hint" }, ` (wirksam: ${MODUS_TEXT[status.modi[b.name]]})`)), sel);
  });
  const l = status.lokal;
  const lokalInfo = !l.konfiguriert
    ? "Kein lokales Modell konfiguriert (LV_OLLAMA_MODEL leer)."
    : !l.erreichbar
      ? "Ollama ist nicht erreichbar. Läuft die Ollama-App auf dem PC?"
      : l.modell_installiert
        ? `Ollama läuft, Modell ${l.modell} ist installiert.`
        : `Ollama läuft, aber ${l.modell} fehlt: ollama pull ${l.modell}`;
  return el("div", { class: "card" },
    el("p", { class: "muted small", style: "margin-top:0" },
      "Automatisch: Claude, wenn ein API-Key da ist, sonst lokal, sonst manuell. Bereiche auf \u201Elokal\u201C werden nie an Claude geschickt, auch nicht als Vergleich für Dubletten."),
    el("label", { for: "ki-standard" }, "Standard", el("span", { class: "hint" }, ` (wirksam: ${MODUS_TEXT[status.modus_standard]})`)),
    standard,
    el("div", { class: "grid2" }, proBereich),
    el("p", { class: "small" }, lokalInfo),
  );
}
async function viewEinstellungen() {
  const tokenInput = el("input", { type: "password", id: "token", value: store.get("lv-token"), autocomplete: "off" });
  const tokenSection = [
    el("h2", {}, "Zugang"),
    el(
      "div",
      { class: "card" },
      el("label", { for: "token" }, "Token", el("span", { class: "hint" }, " (nur nötig, wenn LV_TOKEN gesetzt ist)")),
      el("div", { class: "row" }, el("div", { class: "grow" }, tokenInput), el("button", {
        type: "button",
        onclick: () => { store.set("lv-token", tokenInput.value.trim()); toast("Token gespeichert."); bereicheCache = null; viewEinstellungen(); refreshStats(); },
      }, "Speichern")),
    ),
  ];

  let status, stat, bereichListe, einst;
  try {
    [status, stat, bereichListe, einst] = await Promise.all([
      api("/api/status"), api("/api/statistik"), bereiche(true), api("/api/einstellungen"),
    ]);
  } catch (err) {
    return render(errorNotice(err), ...tokenSection);
  }

  const kriterien = [
    ["Lessons gesamt (Ziel nach 3 Monaten: 60)", `${stat.gesamt}`],
    ["Neu erfasst, letzte 7 Tage (Ziel ≥ 1)", `${stat.neu_erfasst_7_tage}`],
    ["Neu erfasst, letzte 30 Tage", `${stat.neu_erfasst_30_tage}`],
    ["Ø Erfassungsdauer (Ziel < 30 s)", stat.erfassung_sekunden_schnitt == null ? "noch keine Messung" : `${stat.erfassung_sekunden_schnitt} s (${stat.erfassungen_unter_30s}/${stat.erfassungen_gemessen} unter 30 s)`],
    ["Briefings mit mind. einer hilfreichen Lesson (Ziel: jedes)", stat.briefings ? `${stat.briefings_hilfreich} von ${stat.briefings} (${stat.briefings_bewertet} bewertet)` : "noch kein Briefing"],
    ["Persönliche Erfahrung statt Lehrbuchwissen", stat.lessons_eingeschaetzt ? `${stat.lessons_persoenlich} von ${stat.lessons_eingeschaetzt} eingeschätzten Lessons` : "noch keine Einschätzung"],
    ["Lessons ohne Maßnahme", `${stat.ohne_massnahme}`],
  ];

  const newBereich = el("input", { type: "text", id: "neuer-bereich", placeholder: "Neuer Bereich" });
  const sperrliste = el("textarea", { id: "sperrliste", rows: 5, placeholder: "Ein Begriff pro Zeile, z. B. Kundennamen, Standorte, Systemnamen" });
  sperrliste.value = einst.sperrliste.join("\n");
  const fileInput = el("input", { type: "file", accept: "application/json,.json", id: "import-file", class: "sr-only" });

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    try {
      const payload = JSON.parse(await file.text());
      const res = await api("/api/import", { method: "POST", body: payload });
      toast(`${res.importiert} importiert, ${res.uebersprungen} übersprungen${res.fehler.length ? `, ${res.fehler.length} Fehler: ${res.fehler.slice(0, 2).join("; ")}` : ""}.`, 9000);
      refreshStats();
      viewEinstellungen();
    } catch (err) {
      toast(err instanceof SyntaxError ? "Datei ist kein gültiges JSON." : err.message, 7000);
    } finally {
      fileInput.value = "";
    }
  });

  render(
    el("h2", {}, "Erfolgskriterien"),
    el("div", { class: "card" }, el("dl", { class: "fields" }, kriterien.map(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]))),

    el("h2", {}, "Bereiche"),
    el(
      "div",
      { class: "card" },
      el("p", { class: "muted small", style: "margin-top:0" }, "Phase 1: nur Beruf und Immobilien aktiv lassen. Fokus schlägt Vollständigkeit."),
      bereichListe.map((b) =>
        el("label", { class: "check" },
          el("input", {
            type: "checkbox",
            checked: b.aktiv,
            onchange: async (e) => {
              try { await api(`/api/bereiche/${encodeURIComponent(b.name)}`, { method: "PATCH", body: { aktiv: e.target.checked } }); bereicheCache = null; }
              catch (err) { e.target.checked = !e.target.checked; toast(err.message); }
            },
          }),
          el("span", {}, b.name, el("br"), el("span", { class: "muted small" }, b.beispiele)),
        )),
      el("div", { class: "row", style: "margin-top:8px" },
        el("div", { class: "grow" }, newBereich),
        el("button", {
          type: "button",
          onclick: async () => {
            const name = newBereich.value.trim();
            if (!name) return;
            try { await api("/api/bereiche", { method: "POST", body: { name, aktiv: true } }); bereicheCache = null; viewEinstellungen(); }
            catch (err) { toast(err.message); }
          },
        }, "Anlegen")),
    ),

    el("h2", {}, "KI-Strukturierung"),
    kiSection(status, einst, bereichListe),

    el("h2", {}, "Sperrliste"),
    el(
      "div",
      { class: "card" },
      el("label", { for: "sperrliste", style: "margin-top:0" }, "Begriffe, die nie in einer Lesson stehen sollen"),
      sperrliste,
      el("p", { class: "muted small" }, "Treffer lösen beim Erfassen eine Warnung aus. Die Liste bleibt lokal."),
      el("button", {
        type: "button",
        onclick: async () => {
          try {
            const res = await api("/api/einstellungen", { method: "PUT", body: { sperrliste: sperrliste.value.split("\n") } });
            sperrliste.value = res.sperrliste.join("\n");
            toast("Sperrliste gespeichert.");
          } catch (err) { toast(err.message); }
        },
      }, "Speichern"),
    ),

    el("h2", {}, "Bestand"),
    el(
      "div",
      { class: "card" },
      el("p", { style: "margin-top:0" }, "Startbestand oder Backup als JSON importieren. Vorlage: ", el("code", {}, "startbestand/vorlage.json"), "."),
      el("div", { class: "actions" },
        el("button", { type: "button", onclick: () => fileInput.click() }, "Importieren"),
        fileInput,
        el("button", {
          type: "button",
          onclick: async () => {
            try {
              const res = await api("/api/export", { raw: true });
              const blob = await res.blob();
              const a = el("a", { href: URL.createObjectURL(blob), download: `lessons-vault-${new Date().toISOString().slice(0, 10)}.json` });
              document.body.append(a);
              a.click();
              setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
            } catch (err) { toast(err.message); }
          },
        }, "Exportieren"),
        el("button", {
          type: "button",
          class: "ghost",
          onclick: async (e) => {
            e.target.disabled = true;
            try { const r = await api("/api/reindex", { method: "POST" }); toast(`${r.neu_indexiert} Lessons neu indexiert (${r.embeddings}).`); }
            catch (err) { toast(err.message); }
            finally { e.target.disabled = false; }
          },
        }, "Neu indexieren"),
      ),
    ),

    el("h2", {}, "System"),
    el(
      "div",
      { class: "card" },
      el("dl", { class: "fields" },
        el("dt", {}, "KI-Strukturierung"), el("dd", {}, status.ki ? `aktiv (${status.modell})` : "aus, kein ANTHROPIC_API_KEY"),
        el("dt", {}, "Embeddings"), el("dd", {}, status.embeddings, status.embeddings.startsWith("ollama:") ? " (lokal, semantisch)" : status.semantisch ? " (semantisch, Cloud)" : " (lokal, nur unscharf-lexikalisch)"),
        el("dt", {}, "Version"), el("dd", {}, status.version),
      ),
    ),
    ...tokenSection,
  );
}

// ------------------------------------------------------------------- Router
const routes = [
  [/^#\/erfassen$/, viewErfassen, "erfassen"],
  [/^#\/briefing$/, viewBriefing, "briefing"],
  [/^#\/briefing\/([\w-]+)$/, viewBriefing, "briefing"],
  [/^#\/pruefen$/, viewPruefen, "pruefen"],
  [/^#\/entwurf\/([\w-]+)$/, viewEntwurf, "pruefen"],
  [/^#\/suche$/, viewSuche, "suche"],
  [/^#\/einstellungen$/, viewEinstellungen, "einstellungen"],
  [/^#\/lesson\/([\w-]+)$/, viewLesson, "suche"],
];

async function route() {
  const hash = location.hash || "#/erfassen";
  for (const [pattern, handler, tab] of routes) {
    const match = hash.match(pattern);
    if (!match) continue;
    document.querySelectorAll(".tabbar a").forEach((a) => {
      if (a.dataset.tab === tab) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    try {
      await handler(...match.slice(1));
    } catch (err) {
      render(errorNotice(err));
    }
    window.scrollTo(0, 0);
    return;
  }
  location.hash = "#/erfassen";
}

window.addEventListener("hashchange", route);
route();
refreshStats();

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("sw.js").catch(() => { /* optional */ });
}
