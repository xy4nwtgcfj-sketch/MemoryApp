// Eingang: gesicherte Notizen, die auf Prüfung warten. Fertige mit einem Tipp übernehmen.
import {
  anf, ansicht, api, el, errorNotice, fill, fokusAufTitel, grosserTitel, icon, kopf, kuerzen, leer, refreshStats,
  relTime, say, skeleton, status, thumbsRow, toast,
} from "./core.js";
import { abschlussKarte, bereitZumUebernehmen, entwurfKarte, rueckgaengig, uebernehmen } from "./entwurf.js";

let eingangTimer = null;

function zeile(e, { onUebernehmen }) {
  const titel = e.entwurf?.titel || kuerzen(e.rohtext.split("\n")[0], 80);
  if (e.status === "wartet" || e.status === "in_arbeit") {
    return el("li", { class: "li", "data-id": e.id },
      el("span", { class: "spinner", "aria-hidden": "true", style: "color:var(--text-3)" }),
      el("div", { class: "grow" }, el("span", {}, kuerzen(e.rohtext, 120)),
        el("span", { class: "li-sub" }, e.status === "in_arbeit" ? "wird gerade strukturiert" : e.modus === "lokal" ? "wartet auf deinen PC" : "wartet", ` · ${relTime(e.erstellt_am)}`)));
  }
  const ok = bereitZumUebernehmen(e);
  const grund = e.status === "fehler" ? "Strukturierung fehlgeschlagen"
    : e.entwurf?.pruefung ? "Namen prüfen, bevor es an Claude geht"
      : e.entwurf?.dublette ? "Kennst du vielleicht schon"
        : (e.entwurf?.compliance_hinweise || []).length ? "Datenschutz-Hinweis"
          : !e.entwurf?.lesson ? "Regel fehlt" : !e.entwurf?.bereich ? "Bereich fehlt" : "";
  const uebernehmenBtn = ok ? el("button", { type: "button", class: "primary", style: "flex:none", "aria-label": `„${kuerzen(e.entwurf.lesson, 60)}“ übernehmen`, onclick: (ev) => onUebernehmen(e, ev.currentTarget) }, icon("check"), "Übernehmen") : null;
  return el("li", { class: "li li-col", "data-id": e.id },
    el("a", { href: `#/entwurf/${e.id}`, style: "color:inherit;text-decoration:none;display:block" },
      e.entwurf?.lesson ? el("p", { class: "quote", style: "font-size:1.0625rem" }, anf(e.entwurf.lesson)) : el("p", { style: "margin:0;font-weight:600" }, anf(titel)),
      el("p", { class: "meta" },
        e.entwurf?.bereich ? el("span", {}, e.entwurf.bereich) : null,
        el("span", {}, relTime(e.erstellt_am)),
        e.entwurf?.ki_verwendet ? el("span", { class: "badge ai" }, icon("sparkles"), "Claude") : null,
        grund ? el("span", { class: "badge warn" }, grund) : null)),
    el("div", { class: "row", style: "justify-content:flex-end" },
      el("a", { class: "button text", href: `#/entwurf/${e.id}` }, ok ? "Ansehen" : "Prüfen", icon("chevron-right", "icon sm")),
      uebernehmenBtn));
}

export async function viewEingang() {
  const render = ansicht();
  kopf("Eingang");
  clearTimeout(eingangTimer);
  const liste = el("div", { id: "eingang-liste" });
  const hinweis = el("div");
  if (!render(grosserTitel("Eingang"), hinweis, liste)) return;
  fokusAufTitel();
  fill(liste, skeleton());

  let signatur = "";
  const uebernehmenEins = async (e, btn) => {
    btn?.setAttribute("aria-disabled", "true");
    try {
      const lesson = await uebernehmen(e);
      refreshStats();
      liste.querySelector(`[data-id="${e.id}"]`)?.remove();
      toast("Übernommen.", { aktion: { text: "Rückgängig", onclick: async () => { try { await rueckgaengig(lesson, e); laden(true); } catch (err) { toast(err.message, { fehler: true }); } } } });
      say("Übernommen.");
      laden(true);
    } catch (err) {
      btn?.removeAttribute("aria-disabled");
      toast(err.message, { fehler: true });
    }
  };

  async function laden(erzwingen = false) {
    if (!render.aktiv()) return;
    let data;
    try {
      data = await api("/api/entwuerfe");
    } catch (err) {
      fill(liste, errorNotice(err, { erneut: () => laden(true) }));
      return;
    }
    if (!render.aktiv()) return;
    const neu = JSON.stringify(data.eintraege.map((e) => [e.id, e.status, e.geaendert_am]));
    const offen = data.eintraege.filter((e) => e.status === "wartet" || e.status === "in_arbeit");
    if (neu !== signatur || erzwingen) {
      signatur = neu;
      // Fokus merken, damit die Aktualisierung VoiceOver nicht an den Anfang springen lässt
      const fokusId = document.activeElement?.closest?.("[data-id]")?.dataset.id;
      const bereit = data.eintraege.filter((e) => e.status === "fertig" || e.status === "fehler");
      const sofort = bereit.filter(bereitZumUebernehmen);
      if (!data.eintraege.length) {
        fill(liste, leer({ symbol: "inbox", titel: "Alles erledigt", text: "Notizen vom iPhone-Kurzbefehl, aus dem Startbestand oder mit „Später“ gesicherte Entwürfe landen hier.",
          aktionen: [el("a", { class: "button", href: "#/erfassen" }, icon("square-pen"), "Neue Lesson")] }));
      } else {
        fill(liste,
          bereit.length ? el("div", { class: "row", style: "margin-bottom:8px" },
            el("p", { class: "overline grow", style: "margin:0" }, `Bereit (${bereit.length})`),
            sofort.length > 1 ? el("button", { type: "button", class: "text", onclick: async (ev) => {
              ev.currentTarget.setAttribute("aria-disabled", "true");
              let n = 0;
              for (const e of sofort) { try { await uebernehmen(e); n += 1; } catch { /* einzeln prüfen */ } }
              refreshStats();
              toast(`${n} Lessons übernommen.`);
              laden(true);
            } }, `Alle ${sofort.length} übernehmen`) : null) : null,
          bereit.length ? el("ul", { class: "list" }, bereit.map((e) => zeile(e, { onUebernehmen: uebernehmenEins }))) : null,
          offen.length ? el("p", { class: "overline", style: "margin-top:24px" }, `In Arbeit (${offen.length})`) : null,
          offen.length ? el("ul", { class: "list" }, offen.map((e) => zeile(e, {}))) : null);
        if (fokusId) liste.querySelector(`[data-id="${fokusId}"] a, [data-id="${fokusId}"] button`)?.focus({ preventScroll: true });
      }
      if (!erzwingen && signatur) say(bereit.length ? `${bereit.length} bereit zum Prüfen.` : "");
    }
    const st = await status().catch(() => ({}));
    const lokal = st.lokal || {};
    const lokalWartet = offen.some((e) => e.modus === "lokal");
    fill(hinweis,
      lokalWartet && lokal.konfiguriert && !lokal.erreichbar
        ? el("div", { class: "notice warn" }, icon("alert"), el("div", {}, "Das lokale Modell (Ollama) ist nicht erreichbar. Die Notizen warten, bis es wieder läuft. Nichts geht verloren.")) : null,
      lokalWartet && lokal.erreichbar && !lokal.modell_installiert
        ? el("div", { class: "notice warn" }, icon("alert"), el("div", {}, `Das Modell ${lokal.modell} ist nicht installiert. Auf dem PC: `, el("code", {}, `ollama pull ${lokal.modell}`))) : null);
    clearTimeout(eingangTimer);
    if (offen.length) eingangTimer = setTimeout(() => { if (render.aktiv()) { refreshStats(); laden(); } }, 5000);
  }
  laden(true);
}

export async function viewEntwurf(id) {
  const render = ansicht();
  kopf("Entwurf", { text: "Eingang", href: "#/eingang" });
  let e;
  try {
    e = await api(`/api/entwuerfe/${encodeURIComponent(id)}`);
  } catch (err) {
    render(grosserTitel("Entwurf"), errorNotice(err), el("a", { href: "#/eingang" }, "Zum Eingang"));
    return;
  }
  const container = el("div");
  const notiz = el("details", { class: "card", open: e.status === "fehler" ? true : null },
    el("summary", {}, "Deine Notiz"),
    e.bilder?.length ? thumbsRow(e.bilder) : null,
    el("p", { style: "white-space:pre-wrap;margin:8px 0 0" }, e.rohtext),
    e.antwort ? el("p", { class: "small muted", style: "white-space:pre-wrap" }, `Ergänzung: ${e.antwort}`) : null,
    el("p", { class: "footnote" }, relTime(e.erstellt_am), e.modell ? ` · ${e.modell}` : "", e.dauer_sekunden ? ` · ${Math.round(e.dauer_sekunden)} s` : ""),
    el("div", { class: "actions" }, el("button", {
      type: "button", class: "text",
      onclick: async () => {
        try { await api(`/api/entwuerfe/${e.id}/neu`, { method: "POST" }); toast("Wird neu strukturiert."); location.hash = "#/eingang"; }
        catch (err) { toast(err.message, { fehler: true }); }
      },
    }, icon("refresh", "icon sm"), "Neu strukturieren")));
  if (!render(grosserTitel("Entwurf prüfen"), notiz, container)) return;
  fokusAufTitel();
  const zeigen = (eintrag) => entwurfKarte(container, eintrag, {
    onGesichert: (lesson, eintr, opts = {}) => {
      refreshStats();
      fill(container, abschlussKarte(lesson, eintr, { ...opts, modus: eintr.modus }));
      notiz.remove();
      toast(opts.bestaetigt ? "Als erneut erlebt gezählt." : "Gesichert.", {
        aktion: opts.bestaetigt ? null : { text: "Rückgängig", onclick: async () => { try { const neu = await rueckgaengig(lesson, eintr); location.hash = `#/entwurf/${neu.id}`; } catch (err) { toast(err.message, { fehler: true }); } } },
      });
      container.querySelector(".card")?.setAttribute("tabindex", "-1");
      container.querySelector(".card")?.focus();
    },
    onSpaeter: () => { location.hash = "#/eingang"; },
    spaeterText: "Zurück",
    onVerworfen: () => { refreshStats(); notiz.remove(); fill(container, el("p", { class: "muted" }, "Verworfen. ", el("a", { href: "#/eingang" }, "Zum Eingang"))); },
    onNeu: (neu) => zeigen(neu),
  });
  if (e.status === "wartet" || e.status === "in_arbeit") {
    fill(container, skeleton(e.modus === "lokal" ? "Wird auf deinem PC strukturiert …" : "Wird strukturiert …"));
    const warten = async () => {
      if (!render.aktiv()) return;
      try {
        const neu = await api(`/api/entwuerfe/${e.id}`);
        if (neu.status === "fertig" || neu.status === "fehler") return zeigen(neu);
      } catch { /* erneut */ }
      setTimeout(warten, 3000);
    };
    setTimeout(warten, 3000);
    return;
  }
  zeigen(e);
}
