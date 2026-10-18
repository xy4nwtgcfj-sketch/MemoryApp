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

// Wie replaceChildren, aber null/false werden ausgelassen (sonst erscheint "null" als Text).
function fill(node, ...children) {
  node.replaceChildren(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
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
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : isForm ? body : JSON.stringify(body) });
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

// ------------------------------------------------------------------- Fotos
const MAX_FOTOS = 5;

function verkleinern(file, kante = 2000) {
  // Im Browser verkleinern: schneller Upload über Tailscale, Metadaten fallen weg, HEIC wird zu JPEG.
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const faktor = Math.min(1, kante / Math.max(img.naturalWidth, img.naturalHeight));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.naturalWidth * faktor);
      canvas.height = Math.round(img.naturalHeight * faktor);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => resolve(blob || file), "image/jpeg", 0.85);
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
    img.src = url;
  });
}

async function fotosHochladen(files) {
  const liste = [...files].slice(0, MAX_FOTOS);
  if (files.length > MAX_FOTOS) toast(`Höchstens ${MAX_FOTOS} Fotos auf einmal, die ersten ${MAX_FOTOS} werden verwendet.`);
  const form = new FormData();
  for (const [i, file] of liste.entries()) form.append("dateien", await verkleinern(file), `foto-${i + 1}.jpg`);
  return api("/api/bilder", { method: "POST", body: form });
}

function fotoInput(onFiles) {
  const input = el("input", { type: "file", accept: "image/*", multiple: true, class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
  input.addEventListener("change", () => { if (input.files.length) onFiles(input.files); input.value = ""; });
  return input;
}

const bildCache = new Map();
async function bildSrc(id, variante = "vorschau") {
  const key = `${id}/${variante}`;
  if (!bildCache.has(key)) {
    bildCache.set(key, api(`/api/bilder/${id}?variante=${variante}`, { raw: true }).then((r) => r.blob()).then((b) => URL.createObjectURL(b)));
  }
  return bildCache.get(key);
}

function lightbox(id) {
  const img = el("img", { alt: "Foto" });
  const box = el("div", { class: "lightbox", role: "dialog", "aria-label": "Foto", tabindex: "-1" }, img,
    el("button", { type: "button", class: "lightbox-close", "aria-label": "Schließen" }, "✕"));
  const close = () => { box.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  box.addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  document.body.append(box);
  box.focus();
  bildSrc(id, "voll").then((src) => { img.src = src; }).catch(() => close());
}

function thumbsRow(bilder, { onRemove } = {}) {
  return el("div", { class: "thumbs" }, bilder.map((b) => {
    const img = el("img", { alt: "Foto", loading: "lazy" });
    bildSrc(b.id).then((src) => { img.src = src; }).catch(() => { img.alt = "Foto nicht ladbar"; });
    return el("div", { class: "thumb" },
      el("button", { type: "button", class: "thumb-open", "aria-label": "Foto vergrößern", onclick: () => lightbox(b.id) }, img),
      onRemove ? el("button", { type: "button", class: "thumb-remove", "aria-label": "Foto entfernen", onclick: () => onRemove(b) }, "✕") : null);
  }));
}

function ocrVorschau(text, bereich, hinweise) {
  // Erkannter Text: der Nutzer sieht und bearbeitet genau das, was an Claude geht.
  const area = el("textarea", { rows: 8, id: "ocr-text", "aria-label": "Erkannter Text" });
  area.value = text;
  const box = complianceBox(hinweise || []);
  const recheck = debounce(async () => {
    try { box.update(await api("/api/compliance", { method: "POST", body: { text: area.value, bereich: bereich || "Beruf" } })); } catch { /* bleibt */ }
  }, 600);
  area.addEventListener("input", recheck);
  return { area, box: box.node };
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
    fill(box, 
      el("strong", {}, "Datenschutz-Hinweis: bitte abstrahieren"),
      el("ul", {}, list.map((h) => el("li", {}, h))),
    );
  };
  update(hinweise);
  return { node: box, update };
}

// ----------------------------------------------------------------- Erfassen
const capture = { text: "", quelle: "text", start: null, rueckfrage: "", bereich: "", bilder: [], queue: [], queuePos: 0, queueTotal: 0 };
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
  capture.bilder = [];
  capture.queue = [];
  capture.queuePos = 0;
  capture.queueTotal = 0;
}

// Nach Speichern/Bestätigen: nächster Kandidat aus dem Foto oder komplett zurücksetzen.
function captureAbschliessen() {
  if (capture.queue.length) {
    capture.text = "";
    capture.start = null;
    capture.rueckfrage = "";
  } else {
    resetCapture();
  }
}

function zurueckZumErfassen() {
  if (location.hash === "#/erfassen" || location.hash === "") viewErfassen();
  else location.hash = "#/erfassen";
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
  const thumbs = el("div");
  const fotoPanel = el("div", { id: "foto-panel" });
  const queueBanner = el("div");

  const renderThumbs = () => fill(thumbs, capture.bilder.length ? thumbsRow(capture.bilder, {
    onRemove: (b) => {
      capture.bilder = capture.bilder.filter((x) => x.id !== b.id);
      renderThumbs();
      if (!capture.bilder.length) fill(fotoPanel);
    },
  }) : "");

  const kandidatenAnzeigen = (res) => {
    if (!res.kandidaten.length) {
      fill(fotoPanel, el("div", { class: "notice info" }, el("strong", {}, "Keine Erfahrungen gefunden."),
        res.hinweis || "Das Foto enthält eher Sachinformationen. Es bleibt angehängt, wenn du die Lesson selbst beschreibst."));
      return;
    }
    const boxes = res.kandidaten.map((k, i) => el("input", { type: "checkbox", id: `kand-${i}`, checked: true }));
    const startBtn = el("button", { type: "button", class: "primary" });
    const zaehlen = () => {
      const n = boxes.filter((b) => b.checked).length;
      startBtn.textContent = `Ausgewählte erfassen (${n})`;
      startBtn.disabled = n === 0;
    };
    boxes.forEach((b) => b.addEventListener("change", zaehlen));
    zaehlen();
    startBtn.addEventListener("click", () => {
      capture.queue = res.kandidaten.filter((_, i) => boxes[i].checked);
      capture.queueTotal = capture.queue.length;
      capture.queuePos = 0;
      fill(fotoPanel);
      naechsterKandidat();
    });
    fill(fotoPanel, el("div", { class: "card" },
      el("strong", {}, `Gefundene Erfahrungen (${res.kandidaten.length})`),
      el("p", { class: "muted small", style: "margin:4px 0 0" }, "Wähle aus, was eine eigene Lesson werden soll. Jede läuft danach einzeln durch die normale Erfassung, das Foto hängt an jeder."),
      el("ul", { class: "checklist" }, res.kandidaten.map((k, i) => el("li", {}, boxes[i],
        el("label", { for: `kand-${i}`, style: "margin:0;font-weight:400" }, el("span", { style: "font-weight:600" }, k.titel), el("span", { class: "src" }, k.kern))))),
      el("div", { class: "actions" }, startBtn)));
  };

  const kandidatenSuchen = async (body) => {
    fill(fotoPanel, el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Claude sucht Erfahrungen auf dem Foto …"));
    try {
      kandidatenAnzeigen(await api("/api/foto/kandidaten", { method: "POST", body: { bild_ids: capture.bilder.map((b) => b.id), bereich: capture.bereich, notiz: textarea.value.trim(), ...body } }));
    } catch (err) {
      fill(fotoPanel, errorNotice(err));
    }
  };

  const nurAnhaengen = el("button", { type: "button", class: "ghost", onclick: () => { fill(fotoPanel, el("p", { class: "muted small" }, "Das Foto wird an die Lesson gehängt, die du oben beschreibst.")); textarea.focus(); } }, "Nur anhängen");

  const fotoVorbereiten = async () => {
    if (!capture.bilder.length) return;
    fill(fotoPanel, el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Foto wird ausgewertet …"));
    let res;
    try {
      res = await api("/api/foto/vorbereiten", { method: "POST", body: { bild_ids: capture.bilder.map((b) => b.id), bereich: capture.bereich } });
    } catch (err) {
      return fill(fotoPanel, errorNotice(err));
    }
    if (res.weg === "bild") {
      fill(fotoPanel, el("div", { class: "card" },
        el("strong", {}, "Lessons aus dem Foto"),
        el("p", { class: "muted small", style: "margin:4px 0 0" }, "Privater Bereich: Claude sieht das Foto selbst. Deine Stichworte oben gehen als Notiz mit."),
        el("div", { class: "actions" }, el("button", { type: "button", class: "primary", onclick: () => kandidatenSuchen({}) }, "Lessons finden"), nurAnhaengen)));
    } else if (res.weg === "text") {
      const vorschau = ocrVorschau(res.text, capture.bereich, res.compliance_hinweise);
      fill(fotoPanel, el("div", { class: "card" },
        el("strong", {}, "Erkannter Text"),
        el("p", { class: "muted small", style: "margin:4px 0 8px" }, "Nur dieser Text geht an Claude, das Foto bleibt auf deinem PC. Lösche, was nicht raus soll."),
        res.text ? null : el("div", { class: "notice warn" }, res.texterkennung.verfuegbar ? "Kein Text erkannt. Tippe die Kernpunkte ab oder beschreibe die Lesson oben." : res.texterkennung.hinweis),
        vorschau.box, vorschau.area,
        el("div", { class: "actions" }, el("button", {
          type: "button",
          class: "primary",
          onclick: () => vorschau.area.value.trim().length < 3 ? toast("Kein Text zum Auswerten.") : kandidatenSuchen({ text: vorschau.area.value }),
        }, "Lessons finden"), nurAnhaengen)));
    } else {
      fill(fotoPanel, el("div", { class: "card" },
        el("strong", {}, "Bleibt auf deinem PC"),
        el("p", { class: "muted small", style: "margin:4px 0 8px" }, "Für diesen Bereich gehen Fotos und Text nicht an Claude. Übernimm den erkannten Text als Notiz und speichere."),
        res.text ? el("p", { class: "raw small" }, res.text.slice(0, 600)) : el("p", { class: "muted small" }, res.texterkennung.hinweis || "Kein Text erkannt."),
        el("div", { class: "actions" },
          res.text ? el("button", { type: "button", onclick: () => { textarea.value = capture.text = (textarea.value ? textarea.value + "\n" : "") + res.text; startTimer(); fill(fotoPanel); } }, "Als Notiz übernehmen") : null,
          nurAnhaengen)));
    }
  };

  const fotoBtn = el("button", { type: "button", title: "Foto aufnehmen oder auswählen" }, "📷 Foto");
  const fotoIn = fotoInput(async (files) => {
    startTimer();
    fotoBtn.disabled = true;
    fill(fotoPanel, el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Fotos werden hochgeladen und gelesen …"));
    try {
      capture.bilder = [...capture.bilder, ...(await fotosHochladen(files))].slice(0, MAX_FOTOS);
      renderThumbs();
      await fotoVorbereiten();
    } catch (err) {
      fill(fotoPanel, errorNotice(err));
    } finally {
      fotoBtn.disabled = false;
    }
  });
  fotoBtn.addEventListener("click", () => fotoIn.click());
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
    fill(chips, ...aktive.map((b) => el("button", {
      type: "button",
      class: "chip",
      "aria-pressed": String(capture.bereich === b.name),
      onclick: () => { capture.bereich = capture.bereich === b.name ? "" : b.name; renderChips(); updateModus(); if (capture.bilder.length && !capture.queue.length) fotoVorbereiten(); },
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
    if (modus === "claude") fill(result, el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Claude strukturiert …"));
    try {
      const res = await api("/api/erfassen", {
        method: "POST",
        body: { text, quelle: capture.quelle, bereich: capture.bereich, erfassung_sekunden: captureSeconds(), bild_ids: capture.bilder.map((b) => b.id) },
      });
      if (res.modus === "hintergrund") {
        const seconds = captureSeconds();
        captureAbschliessen();
        refreshStats();
        toast(el("span", {}, `Gespeichert${seconds ? ` in ${Math.round(seconds)} s` : ""}. Wird lokal strukturiert und erscheint dann unter `, el("a", { href: "#/pruefen" }, "Prüfen"), "."), 7000);
        return viewErfassen();
      }
      showDraft(result, res.entwurf);
    } catch (err) {
      fill(result, errorNotice(err));
    } finally {
      structureBtn.disabled = false;
    }
  };
  structureBtn.addEventListener("click", () => go(false));

  function naechsterKandidat() {
    const k = capture.queue.shift();
    if (!k) return;
    capture.queuePos += 1;
    textarea.value = capture.text = `${k.titel}: ${k.kern}`;
    fill(queueBanner, el("div", { class: "notice info row" },
      el("span", { class: "grow" }, `Lesson ${capture.queuePos} von ${capture.queueTotal} aus dem Foto`),
      capture.queue.length ? el("button", { type: "button", class: "ghost", onclick: () => { capture.queue = []; toast("Restliche Kandidaten übersprungen."); fill(queueBanner); } }, "Rest überspringen") : null));
    go(false);
  }

  render(
    el("h2", {}, "Neue Lesson"),
    queueBanner,
    el("label", { for: "capture-text", class: "sr-only" }, "Stichworte"),
    textarea,
    thumbs,
    aktive.length > 1 ? chips : null,
    modusInfo,
    el("div", { class: "actions" }, structureBtn, mic, fotoBtn, fotoIn, el("button", { type: "button", class: "ghost", onclick: () => go(true) }, "Manuell")),
    fotoPanel,
    result,
  );
  renderThumbs();
  if (capture.queue.length) naechsterKandidat();
  else if (!capture.text) textarea.focus();
}

async function requestDraft(container, body) {
  fill(container, el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Claude strukturiert …"));
  try {
    const entwurf = await api("/api/erfassen/entwurf", { method: "POST", body: { ...body, bereich: capture.bereich } });
    showDraft(container, entwurf);
  } catch (err) {
    fill(container, errorNotice(err));
  }
}

async function showDraft(container, entwurf, { entwurfId = null } = {}) {
  const fertig = () => {
    captureAbschliessen();
    refreshStats();
  };
  const bildIds = entwurfId ? [] : capture.bilder.map((b) => b.id);
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
                const lesson = await api(`/api/lessons/${d.id}/bestaetigen`, { method: "POST", body: { notiz: capture.text || entwurf.ereignis || "", entwurf_id: entwurfId, bild_ids: bildIds } });
                const weiter = capture.queue.length > 0;
                fertig();
                toast(`Als Bestätigung gezählt (${lesson.bestaetigungen}×, ${lesson.status}).`);
                if (weiter) zurueckZumErfassen();
                else location.hash = `#/lesson/${d.id}`;
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

  if (bildIds.length) parts.push(el("p", { class: "muted small" }, `${bildIds.length} Foto${bildIds.length > 1 ? "s" : ""} wird an die Lesson gehängt.`));
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
        body: { ...data, quelle: entwurf.quelle || capture.quelle, erfassung_sekunden: seconds, entwurf_id: entwurfId, bild_ids: bildIds },
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
      if (!entwurfId) { captureAbschliessen(); return viewErfassen(); }
      if (!confirm("Entwurf endgültig verwerfen?")) return;
      try { await api(`/api/entwuerfe/${entwurfId}`, { method: "DELETE" }); refreshStats(); location.hash = "#/pruefen"; }
      catch (err) { toast(err.message); }
    },
  }, "Verwerfen")));
  fill(container, el("div", {}, parts));
  updateMissing(form.read());
  container.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ----------------------------------------------------------------- Briefing
const briefingState = { situation: "", bereich: "", modus: store.get("lv-briefing-modus", "kombiniert") };
const MODUS_LABEL = { kombiniert: "Mit Claude-Wissen", eigen: "Nur meine Erfahrung" };

function planText(situation, plan) {
  const zeilen = [`Plan: ${situation}`, ""];
  if (plan.zusammenfassung) zeilen.push(plan.zusammenfassung, "");
  for (const a of plan.abschnitte) {
    zeilen.push(`## ${a.titel}`);
    for (const p of a.punkte) zeilen.push(`- [ ] ${p.punkt}${p.quelle === "erfahrung" ? " (eigene Erfahrung)" : ""}`);
    zeilen.push("");
  }
  if (plan.besonderheiten.length) {
    zeilen.push("## Aus eigener Erfahrung anders als üblich");
    for (const b of plan.besonderheiten) zeilen.push(`- ${b.punkt}`);
  }
  return zeilen.join("\n").trim();
}

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
  const renderChips = () => fill(chips, ...bereichListe.map((b) => el("button", {
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
    fill(result, el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Suche passende Erfahrungen …"));
    try {
      const data = await api("/api/briefing", { method: "POST", body: { situation: text, bereich: briefingState.bereich, modus: briefingState.modus } });
      history.replaceState(null, "", `#/briefing/${data.id}`);
      showBriefing(result, data);
    } catch (err) {
      fill(result, errorNotice(err));
    } finally {
      goBtn.disabled = false;
    }
  };
  const goBtn = el("button", { type: "button", class: "primary", onclick: go }, "Briefing erstellen");
  const modusSeg = el("div", { class: "segmented", role: "group", "aria-label": "Wissensquelle" });
  const renderModus = () => fill(modusSeg, Object.entries(MODUS_LABEL).map(([v, t]) => el("button", {
    type: "button",
    "aria-pressed": String(briefingState.modus === v),
    onclick: () => { briefingState.modus = v; store.set("lv-briefing-modus", v); renderModus(); },
  }, t)));
  renderModus();

  // Entwurf prüfen: Foto eines Entwurfs gegen die eigenen Lessons abgleichen
  const entwurfPanel = el("div");
  const briefingMitFotos = async (bilder, entwurfText = "") => {
    fill(entwurfPanel);
    fill(result, el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Suche passende Erfahrungen zum Entwurf …"));
    try {
      const data = await api("/api/briefing", {
        method: "POST",
        body: { situation: situation.value.trim(), bereich: briefingState.bereich, bild_ids: bilder.map((b) => b.id), entwurf_text: entwurfText },
      });
      history.replaceState(null, "", `#/briefing/${data.id}`);
      showBriefing(result, data);
    } catch (err) {
      fill(result, errorNotice(err));
    }
  };
  const pruefBtn = el("button", { type: "button", title: "Foto eines Entwurfs gegen deine Erfahrungen prüfen" }, "📷 Entwurf prüfen");
  const pruefIn = fotoInput(async (files) => {
    pruefBtn.disabled = true;
    fill(entwurfPanel, el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Fotos werden hochgeladen und gelesen …"));
    try {
      const bilder = await fotosHochladen(files);
      const vor = await api("/api/foto/vorbereiten", { method: "POST", body: { bild_ids: bilder.map((b) => b.id), bereich: briefingState.bereich } });
      if (vor.weg !== "text") return briefingMitFotos(bilder);
      const vorschau = ocrVorschau(vor.text, briefingState.bereich, vor.compliance_hinweise);
      fill(entwurfPanel, el("div", { class: "card" },
        thumbsRow(bilder),
        el("strong", {}, "Erkannter Text des Entwurfs"),
        el("p", { class: "muted small", style: "margin:4px 0 8px" }, "Nur dieser Text geht für den Abgleich an Claude, das Foto bleibt auf deinem PC. Lösche, was nicht raus soll."),
        vor.text ? null : el("div", { class: "notice warn" }, vor.texterkennung.verfuegbar ? "Kein Text erkannt. Tippe die Kernpunkte ab." : vor.texterkennung.hinweis),
        vorschau.box, vorschau.area,
        el("div", { class: "actions" }, el("button", { type: "button", class: "primary", onclick: () => briefingMitFotos(bilder, vorschau.area.value) }, "Prüfen"))));
    } catch (err) {
      fill(entwurfPanel, errorNotice(err));
    } finally {
      pruefBtn.disabled = false;
    }
  });
  pruefBtn.addEventListener("click", () => pruefIn.click());

  render(
    el("h2", {}, "Briefing"),
    el("p", { class: "muted small", style: "margin-top:0" }, "Beschreib die anstehende Situation in einem Satz. Du bekommst deine wichtigsten Erfahrungen dazu und einen Plan oder eine Checkliste."),
    el("label", { for: "briefing-text", class: "sr-only" }, "Situation"),
    situation,
    bereichListe.length > 1 ? chips : null,
    modusSeg,
    el("p", { class: "muted small", style: "margin:6px 0 0" }, "Mit Claude-Wissen: Claude ergänzt sein Fachwissen, jeder Punkt zeigt seine Quelle. Nur meine Erfahrung: ausschließlich deine Lessons."),
    el("div", { class: "actions" }, goBtn, mic, pruefBtn, pruefIn),
    entwurfPanel,
    result,
  );

  if (id) {
    try {
      const data = await api(`/api/briefing/${encodeURIComponent(id)}`);
      situation.value = briefingState.situation = data.situation;
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
      ...verlauf.map((b) => el("a", { class: "card result", href: `#/briefing/${b.id}` },
        el("p", { class: "rule" }, b.entwurf_weg ? "📷 " : "", b.situation),
        el("div", { class: "badges" },
          el("span", { class: "badge" }, formatDate(b.erstellt_am)),
          el("span", { class: "badge" }, `${b.anzahl} Lessons`),
          b.hilfreich ? el("span", { class: "badge status-bestätigt" }, `${b.hilfreich} hilfreich`) : null,
          b.bereich ? el("span", { class: "badge" }, b.bereich) : null))),
    );
  } catch { /* Verlauf ist optional */ }
}

function showBriefing(container, data) {
  const istEntwurf = Boolean(data.entwurf_weg);
  const kopf = data.bilder?.length ? el("div", { class: "card" }, el("strong", {}, "Geprüfter Entwurf"), thumbsRow(data.bilder)) : null;
  const titelText = istEntwurf ? "Abgleich mit deinen Erfahrungen" : data.modus === "kombiniert" ? "Worauf es ankommt" : "Worauf du achten solltest";
  const istPlan = data.modus === "kombiniert" && !istEntwurf;
  if (!data.treffer.length && !(istPlan && (data.ki_moeglich || data.plan))) {
    fill(container, 
      ...(kopf ? [kopf] : []),
      el("div", { class: "notice info" },
        el("strong", {}, "Dazu hast du noch keine Erfahrungen gespeichert."),
        "Probier andere Stichworte oder ohne Bereichsfilter. Und nach der Aufgabe: ",
        el("a", { href: "#/erfassen" }, "eine Lesson erfassen"), "."),
    );
    return;
  }
  const feedback = { ...data.feedback };
  const summaryCard = el("div", { class: "card" }, el("strong", {}, titelText));
  const beruecksichtigtCard = el("div");
  const besonderheitenCard = el("div");
  const titelVon = Object.fromEntries(data.treffer.map((t) => [t.lesson.id, t.lesson.titel]));

  const renderPlan = (plan) => {
    const alle = plan.abschnitte.flatMap((a) => a.punkte);
    let n = 0;
    fill(checklistCard,
      el("div", { class: "row" },
        el("strong", { class: "grow" }, "Plan"),
        el("button", { type: "button", onclick: async () => toast((await copyText(planText(data.situation, plan))) ? "Plan kopiert." : "Kopieren nicht möglich.") }, "Kopieren")),
      el("p", { class: "muted small", style: "margin:4px 0 0" },
        `${plan.punkte_erfahrung} von ${alle.length} Punkten aus deiner Erfahrung. Allgemeinwissen von Claude ist nicht geprüft.`),
      plan.abschnitte.map((a) => [
        el("h3", { class: "plan-section" }, a.titel),
        el("ul", { class: "checklist" }, a.punkte.map((p) => {
          const id = `pl-${n++}`;
          return el("li", {},
            el("input", { type: "checkbox", id }),
            el("label", { for: id, style: "margin:0;font-weight:400" },
              el("span", {}, p.punkt),
              p.quelle === "erfahrung"
                ? el("span", { class: "src src-eigen" }, "Deine Erfahrung", titelVon[p.lesson_id] ? `: ${titelVon[p.lesson_id]}` : "")
                : el("span", { class: "src" }, "Allgemein (Claude)")));
        })),
      ]));
    fill(besonderheitenCard, plan.besonderheiten.length ? el("div", { class: "card highlight" },
      el("strong", {}, "Deine Besonderheiten"),
      el("p", { class: "muted small", style: "margin:4px 0 0" }, "Hier weicht deine Erfahrung vom üblichen Vorgehen ab. Das sagt dir kein Lehrbuch."),
      el("ul", { class: "checklist" }, plan.besonderheiten.map((b) => el("li", {},
        el("span", {}, b.punkt, titelVon[b.lesson_id] ? el("span", { class: "src src-eigen" }, `aus: ${titelVon[b.lesson_id]}`) : null))))) : null);
  };

  const modusWechsel = istEntwurf ? null : el("button", {
    type: "button",
    class: "ghost",
    style: "min-height:32px;padding:2px 6px",
    onclick: () => {
      const neu = data.modus === "kombiniert" ? "eigen" : "kombiniert";
      briefingState.modus = neu;
      store.set("lv-briefing-modus", neu);
      data.modus = neu;
      showBriefing(container, { ...data, zusammenfassung: "", plan: null, ki_checkliste: null, modus: neu, _wechsel: true });
    },
  }, data.modus === "kombiniert" ? "Nur meine Erfahrung zeigen" : "Mit Claude-Wissen ergänzen");
  const checklistCard = el("div", { class: "card" });

  const renderChecklist = (items, quelle) => {
    const titel = Object.fromEntries(data.treffer.map((t) => [t.lesson.id, t.lesson.titel]));
    fill(checklistCard, 
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
    fill(summaryCard, el("strong", {}, titelText),
      el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }),
        istEntwurf ? " Claude gleicht den Entwurf mit deinen Lessons ab …" : istPlan ? " Claude erstellt den Plan aus Fachwissen und deinen Erfahrungen …" : " Claude fasst zusammen …"));
    try {
      const params = new URLSearchParams();
      if (neu) params.set("neu", "true");
      if (!istEntwurf) params.set("modus", data.modus);
      const res = await api(`/api/briefing/${data.id}/zusammenfassung?${params}`, { method: "POST" });
      showSummary(res);
    } catch (err) {
      fill(summaryCard, el("strong", {}, titelText),
        el("div", { class: "notice warn" }, err.message),
        el("button", { type: "button", onclick: () => loadSummary(neu) }, "Erneut versuchen"));
    }
  };

  const showSummary = (res) => {
    fill(summaryCard, 
      el("strong", {}, titelText),
      el("p", { class: "summary" }, res.zusammenfassung || "Claude sah keinen klaren Bezug zu dieser Situation. Die Lessons unten sind trotzdem die besten Treffer."),
      res.ki_hinweis ? el("p", { class: "muted small" }, res.ki_hinweis) : null,
      el("p", { class: "muted small" }, res.plan ? "Von Claude, aus Fachwissen und deinen Lessons. " : "Zusammengefasst von Claude, nur aus deinen Lessons. ",
        el("button", { type: "button", class: "ghost", style: "min-height:32px;padding:2px 6px", onclick: () => loadSummary(true) }, "Neu formulieren"),
        modusWechsel),
    );
    if (res.plan) { renderPlan(res.plan); return; }
    if (istEntwurf) {
      renderChecklist(res.ki_checkliste || [], res.ki_checkliste?.length ? "Was im Entwurf fehlt, laut deinen Lessons (Claude)" : "Claude hat keine Lücken gefunden.");
      const ok = res.abgleich?.beruecksichtigt || [];
      const titel = Object.fromEntries(data.treffer.map((t) => [t.lesson.id, t.lesson.titel]));
      fill(beruecksichtigtCard, ok.length ? el("details", { class: "card" },
        el("summary", {}, `Schon berücksichtigt (${ok.length})`),
        el("ul", { class: "checklist" }, ok.map((p) => el("li", {}, el("span", {}, "✓ "), el("span", {}, p.punkt, titel[p.lesson_id] ? el("span", { class: "src" }, `aus: ${titel[p.lesson_id]}`) : null))))) : "");
    } else if (res.ki_checkliste?.length) {
      renderChecklist(res.ki_checkliste, "Auf die Situation zugeschnitten (Claude)");
    }
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

  fill(container, el("div", {},
    kopf,
    !data.treffer.length ? el("div", { class: "notice info" }, el("strong", {}, "Dazu hast du noch keine eigenen Erfahrungen."),
      "Der Plan unten ist reines Allgemeinwissen von Claude. Nach der Aufgabe: ", el("a", { href: "#/erfassen" }, "eine Lesson erfassen"), ".") : null,
    data.ki_moeglich || data.zusammenfassung ? summaryCard : (data.ki_hinweis ? el("p", { class: "muted small" }, data.ki_hinweis) : null),
    besonderheitenCard,
    checklistCard,
    beruecksichtigtCard,
    data.treffer.length ? el("h2", {}, `Deine Erfahrungen (${data.treffer.length})`) : null,
    data.treffer.length ? el("p", { class: "muted small", style: "margin-top:0" }, "Markiere, was dir geholfen hat. Das verbessert künftige Briefings zu ähnlichen Situationen.") : null,
    lessonCards,
  ));
  if (data.zusammenfassung) showSummary(data);
  else if (data.ki_moeglich || data._wechsel) loadSummary();
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
      e.bilder?.length ? thumbsRow(e.bilder) : null,
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
    fill(results, el("p", { class: "muted" }, el("span", { class: "spinner", "aria-hidden": "true" }), " Suche …"));
    try {
      const [items, drafts] = await Promise.all([
        api(`/api/suche?${params}`),
        searchState.q.trim() ? api(`/api/entwuerfe?q=${encodeURIComponent(searchState.q)}`).catch(() => ({ eintraege: [] })) : { eintraege: [] },
      ]);
      fill(results, 
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
      fill(results, errorNotice(err));
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
    fotoSection(l.id, data.bilder || []),
    el("h2", {}, "Erlebt"),
    el("ul", { class: "card" }, data.protokoll.map((p) => el("li", {}, formatDate(p.datum), p.notiz ? ` · ${p.notiz}` : ""))),
  );
}

function fotoSection(lessonId, bilder) {
  const btn = el("button", { type: "button" }, "📷 Foto hinzufügen");
  const input = fotoInput(async (files) => {
    btn.disabled = true;
    try {
      const neu = await fotosHochladen(files);
      await api(`/api/lessons/${lessonId}/bilder`, { method: "POST", body: { bild_ids: neu.map((b) => b.id) } });
      toast("Foto angehängt.");
      viewLesson(lessonId);
    } catch (err) {
      btn.disabled = false;
      toast(err.message);
    }
  });
  btn.addEventListener("click", () => input.click());
  return el("div", {},
    el("h2", {}, `Fotos${bilder.length ? ` (${bilder.length})` : ""}`),
    bilder.length ? thumbsRow(bilder, {
      onRemove: async (b) => {
        if (!confirm("Foto von dieser Lesson entfernen?")) return;
        try { await api(`/api/lessons/${lessonId}/bilder/${b.id}`, { method: "DELETE" }); viewLesson(lessonId); }
        catch (err) { toast(err.message); }
      },
    }) : el("p", { class: "muted small", style: "margin-top:0" }, "Noch kein Foto. Zum Beispiel die Folie oder das Whiteboard, aus dem die Lesson stammt."),
    el("div", { class: "actions", style: "margin-top:8px" }, btn, input));
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
  const fotoOptionen = [["text", "Texterkennung (Foto bleibt lokal)"], ["bild", "Claude sieht das Foto"]];
  const fotoProBereich = bereichListe.filter((b) => b.aktiv).map((b) => {
    const sel = el("select", {
      id: `foto-${b.name}`,
      onchange: (e) => speichern({ bild_bereiche: { ...einst.bild_bereiche, [b.name]: e.target.value } }),
    }, fotoOptionen.map(([v, t]) => el("option", { value: v, selected: (einst.bild_bereiche[b.name] || (b.name === "Beruf" ? "text" : "bild")) === v }, t)));
    const wirksam = { text: "Texterkennung", bild: "Claude sieht das Foto", lokal: "nichts an Claude" }[status.bild_wege?.[b.name]] || "";
    return el("div", {}, el("label", { for: `foto-${b.name}` }, `Fotos ${b.name}`, el("span", { class: "hint" }, ` (wirksam: ${wirksam})`)), sel);
  });
  const ocrInfo = status.texterkennung?.verfuegbar ? "Texterkennung (Tesseract) ist eingerichtet." : `Texterkennung nicht verfügbar: ${status.texterkennung?.hinweis || "unbekannt"}`;
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
    el("p", { class: "muted small", style: "margin:16px 0 0" }, "Fotos: Ohne Bereichswahl gilt immer Texterkennung. Bereiche auf \u201Elokal\u201C schicken nie etwas an Claude."),
    el("div", { class: "grid2" }, fotoProBereich),
    el("p", { class: "small" }, ocrInfo),
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
