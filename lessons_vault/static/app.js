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
    const s = await api("/api/statistik");
    statsEl.textContent = `${s.gesamt} Lessons · ${s.neu_erfasst_7_tage} diese Woche`;
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
const capture = { text: "", quelle: "text", start: null, rueckfrage: "" };

function resetCapture() {
  capture.text = "";
  capture.quelle = "text";
  capture.start = null;
  capture.rueckfrage = "";
}

function startTimer() {
  if (!capture.start) capture.start = Date.now();
}

function speechButton(textarea) {
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
    startTimer();
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
      capture.text = textarea.value;
      capture.quelle = "sprache";
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
    placeholder: "Was ist passiert, was nimmst du mit? Drei Stichworte reichen.\nz. B. „Bankgespräch, Gehaltsnachweise vergessen, zweiter Termin“",
    oninput: () => { startTimer(); capture.text = textarea.value; },
  });
  textarea.value = capture.text;
  const status = await api("/api/status").catch(() => ({ ki: false }));
  const mic = speechButton(textarea);
  const result = el("div", { id: "draft" });

  const go = async (manual = false) => {
    const text = textarea.value.trim();
    if (!text && !manual) {
      textarea.focus();
      return toast("Erst ein paar Stichworte eingeben.");
    }
    startTimer();
    capture.text = text;
    if (manual || !status.ki) {
      return showDraft(result, { titel: text.split("\n")[0].slice(0, 80), ereignis: text, quelle: capture.quelle, schweregrad: 3, tags: [], compliance_hinweise: [], aehnliche: [], ki_verwendet: false }, status);
    }
    await requestDraft(result, { text, quelle: capture.quelle }, status);
  };

  const structureBtn = el("button", { type: "button", class: "primary", onclick: () => go(false) }, status.ki ? "Strukturieren" : "Weiter");
  render(
    el("h2", {}, "Neue Lesson"),
    el("label", { for: "capture-text", class: "sr-only" }, "Stichworte"),
    textarea,
    el("div", { class: "actions" }, structureBtn, mic, status.ki ? el("button", { type: "button", class: "ghost", onclick: () => go(true) }, "Manuell") : null),
    status.ki ? null : el("p", { class: "muted small" }, "KI-Strukturierung ist nicht aktiv (kein ANTHROPIC_API_KEY). Du füllst das Formular selbst aus."),
    result,
  );
  if (!capture.text) textarea.focus();
}

async function requestDraft(container, body, status) {
  container.replaceChildren(el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Claude strukturiert …"));
  try {
    const entwurf = await api("/api/erfassen/entwurf", { method: "POST", body });
    showDraft(container, entwurf, status);
  } catch (err) {
    container.replaceChildren(errorNotice(err));
  }
}

async function showDraft(container, entwurf, status) {
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
    const answer = el("input", { type: "text", id: "rueckfrage-antwort", placeholder: "Kurze Antwort" });
    const submit = () => {
      if (!answer.value.trim()) return answer.focus();
      requestDraft(container, { text: capture.text, quelle: entwurf.quelle, rueckfrage: entwurf.rueckfrage, antwort: answer.value.trim() }, status);
    };
    answer.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
    parts.push(
      el(
        "div",
        { class: "card" },
        el("label", { for: "rueckfrage-antwort" }, `Rückfrage: ${entwurf.rueckfrage}`),
        el("div", { class: "row" }, el("div", { class: "grow" }, answer), el("button", { type: "button", onclick: submit }, "Antworten")),
        el("p", { class: "muted small" }, "Oder unten direkt ergänzen."),
      ),
    );
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
                const lesson = await api(`/api/lessons/${d.id}/bestaetigen`, { method: "POST", body: { notiz: capture.text } });
                resetCapture();
                toast(`Als Bestätigung gezählt (${lesson.bestaetigungen}×, ${lesson.status}).`);
                refreshStats();
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
    const seconds = capture.start ? Math.round((Date.now() - capture.start) / 100) / 10 : null;
    try {
      const res = await api("/api/lessons", {
        method: "POST",
        body: { ...data, quelle: entwurf.quelle || capture.quelle, erfassung_sekunden: seconds },
      });
      resetCapture();
      refreshStats();
      const msg = el("span", {}, `Gespeichert${seconds ? ` in ${Math.round(seconds)} s` : ""}. `, el("a", { href: `#/lesson/${res.lesson.id}` }, "Ansehen"));
      if (res.compliance_hinweise.length) msg.append(" · Datenschutz-Hinweise beachten.");
      if (res.embedding_fehler) msg.append(` · ${res.embedding_fehler}`);
      toast(msg, 6000);
      viewErfassen();
    } catch (err) {
      saveBtn.disabled = false;
      toast(err.message, 6000);
    }
  });

  parts.push(el("div", { class: "actions" }, saveBtn, el("button", { type: "button", class: "ghost", onclick: () => { resetCapture(); viewErfassen(); } }, "Verwerfen")));
  container.replaceChildren(el("div", {}, parts));
  updateMissing(form.read());
  container.scrollIntoView({ behavior: "smooth", block: "start" });
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
      const items = await api(`/api/suche?${params}`);
      results.replaceChildren(
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
        el("dt", {}, "Embeddings"), el("dd", {}, status.embeddings, status.semantisch ? " (semantisch)" : " (lokal, nur unscharf-lexikalisch)"),
        el("dt", {}, "Version"), el("dd", {}, status.version),
      ),
    ),
    ...tokenSection,
  );
}

// ------------------------------------------------------------------- Router
const routes = [
  [/^#\/erfassen$/, viewErfassen, "erfassen"],
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
