"""Browser-Smoke-Test der PWA (wird übersprungen, wenn Playwright fehlt).

Startet die App mit gemocktem Claude-Client, damit der KI-Pfad ohne API-Key testbar ist.
"""

import glob
import re
import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

from lessons_vault import main  # noqa: E402
from lessons_vault.briefing import BRIEFING_PROMPT, KOMBI_PROMPT  # noqa: E402
from lessons_vault.foto import ABGLEICH_PROMPT, KANDIDATEN_PROMPT  # noqa: E402
from lessons_vault.images import Texterkennung  # noqa: E402
from lessons_vault.config import Settings  # noqa: E402
from lessons_vault.embeddings import HashingProvider  # noqa: E402
from lessons_vault.main import create_app  # noqa: E402
from lessons_vault.structuring import OllamaStrukturierer, Strukturierer  # noqa: E402

from .ollama_mock import OllamaMock  # noqa: E402
from .test_structuring import FakeClient, payload  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOTS = os.environ.get("LV_SCREENSHOTS")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    entwurf = payload(situation="Termin bei der Bank für eine vermietete Wohnung, Herr Meier als Berater.")

    def antwort(kwargs):
        if kwargs["system"] == BRIEFING_PROMPT:
            return {
                "zusammenfassung": "Fordere die Unterlagenliste der Bank vorab an und prüfe die WEG-Protokolle vor dem Angebot.",
                "checkliste": [
                    {"punkt": "Unterlagenliste der Bank anfordern und abhaken", "lesson_nr": 1},
                    {"punkt": "WEG-Protokolle der letzten drei Jahre lesen", "lesson_nr": 2},
                ],
            }
        if kwargs["system"] == KOMBI_PROMPT:
            return {
                "zusammenfassung": "Hypercare braucht klare Eskalationswege und eingeplantes Personal vor Ort.",
                "abschnitte": [
                    {"titel": "Vor dem Go-live", "punkte": [
                        {"punkt": "Hypercare-Team, Dauer und Exit-Kriterien festlegen", "quelle": "allgemein", "lesson_nr": 0},
                        {"punkt": "Schichtleiter für die ersten zwei Wochen schriftlich bestätigen lassen", "quelle": "erfahrung", "lesson_nr": 1},
                    ]},
                    {"titel": "Während der Hypercare", "punkte": [
                        {"punkt": "Tägliches Hypercare-Meeting mit Ticket-Review", "quelle": "allgemein", "lesson_nr": 0},
                    ]},
                ],
                "besonderheiten": [{"punkt": "Bei dir scheiterte es am Personal, nicht an der Technik", "lesson_nr": 1}],
            }
        if kwargs["system"] == KANDIDATEN_PROMPT:
            return {"kandidaten": [
                {"titel": "Cutover früh mit dem Lager abstimmen", "kern": "Der Cutover-Plan wurde zu spät mit dem Lager abgestimmt."},
                {"titel": "Schichtleiter einplanen", "kern": "Schichtleiter fehlten beim Cutover, die Inventur verzögerte sich."},
            ], "hinweis": ""}
        if kwargs["system"] == ABGLEICH_PROMPT:
            return {"zusammenfassung": "Im Plan fehlt die schriftliche Personalfreigabe für das Cutover-Wochenende.",
                    "fehlt": [{"punkt": "Schichtleiter schriftlich bestätigen lassen", "lesson_nr": 1}],
                    "beruecksichtigt": [{"punkt": "Cutover-Termin ist gesetzt", "lesson_nr": 1}]}
        inhalt = kwargs["messages"][0]["content"]
        if isinstance(inhalt, list):
            inhalt = ""
        if "Puffer" in inhalt and "<antwort>" not in inhalt:
            return payload(titel="Puffer einplanen", lesson="Bei der Projektplanung Puffer einplanen.", bereich="Beruf",
                           spezifitaet="allgemein", spezifitaet_hinweis="Das würde jeder Ratgeber sagen.",
                           rueckfrage="Wo genau hat der Puffer bei dir gefehlt und wie viel?", rueckfrage_art="spezifitaet")
        if "Puffer" in inhalt:
            return payload(titel="Datenmigration doppelt einplanen", bereich="Beruf",
                           lesson="Bei jeder Welle die Datenmigration mit dem doppelten meiner Schätzung einplanen.",
                           spezifitaet="persoenlich", spezifitaet_hinweis="Eigenes wiederkehrendes Muster.")
        return entwurf

    fake = FakeClient(antwort)
    mp = pytest.MonkeyPatch()
    mp.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": True, "modelle": ["qwen2.5:7b"]})
    ollama = OllamaMock(payload(bereich="Beruf", titel="Cutover-Personal früh bestätigen", lesson="Vor jedem Cutover die Personalplanung schriftlich bestätigen lassen."))
    settings = Settings(db_path=tmp_path_factory.mktemp("e2e") / "e2e.db", anthropic_api_key="", ollama_model="qwen2.5:7b")
    app = create_app(
        settings, Strukturierer(fake, "claude-opus-5-5"), HashingProvider(),
        OllamaStrukturierer("http://ollama", "qwen2.5:7b", client=ollama.client()),
    )
    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", fake
    srv.should_exit = True
    thread.join(timeout=5)
    mp.undo()


@pytest.fixture(scope="module")
def page(server):
    with playwright.sync_playwright() as p:
        browser = None
        for exe in [None, "/opt/pw-browsers/chromium", *glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")]:
            try:
                browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
                break
            except Exception:
                continue
        if browser is None:
            pytest.skip("Kein Chromium verfügbar")
        context = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
        pg = context.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.errors = errors
        yield pg
        browser.close()


def kein_null(page):
    assert not re.search(r"\bnull\b|\bundefined\b", page.locator("#view").inner_text()), "null/undefined im UI"


def frisch(page, base, route="erfassen"):
    """Ohne Reste vorheriger Tests starten (Autosave, laufender Entwurf, offene Frage)."""
    page.goto(f"{base}/#/{route}")
    page.evaluate("""() => { for (const k of ['lv-laufend', 'lv-capture', 'lv-offen', 'lv-ausgang']) localStorage.removeItem(k);
        localStorage.setItem('lv-ernte-aus', String(Date.now())); localStorage.setItem('lv-rueckblick', 'x'); }""")
    page.reload()


def einstellungen(page, base, **data):
    page.request.put(f"{base}/api/einstellungen", data=json.dumps(data), headers={"Content-Type": "application/json"})


def shot(page, name):
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/{name}.png", full_page=True)


def test_ablauf(server, page):
    base, fake = server
    expect = playwright.expect

    # Startbestand importieren (über API, der Datei-Dialog ist im Headless-Browser umständlich)
    vorlage = json.loads((ROOT / "startbestand" / "vorlage.json").read_text(encoding="utf-8"))
    page.request.post(f"{base}/api/import", data=json.dumps(vorlage), headers={"Content-Type": "application/json"})

    frisch(page, base)
    expect(page.locator("#capture-text")).to_be_visible()
    expect(page).to_have_title(re.compile("^Erfassen"))
    shot(page, "01-erfassen")

    # Sichern: Notiz liegt sofort auf dem PC, Claude strukturiert, kompakte Karte
    page.fill("#capture-text", "Bankgespräch, Gehaltsnachweise vergessen, zweiter Termin")
    page.get_by_role("button", name="Sichern", exact=True).click()
    expect(page.locator("textarea.regel")).to_have_value("Vor jedem Bankgespräch die Unterlagenliste anfordern.")
    expect(page.locator(".notice.warn")).to_contain_text("Herr Meier")
    assert fake.calls, "Claude-Client wurde nicht aufgerufen"
    # Ersetzen mit einem Tipp
    page.get_by_role("button", name=re.compile("Herr Meier.*ersetzen")).click()
    page.locator("details.plain summary").click()
    expect(page.locator("textarea[name=situation]")).to_have_value(re.compile("eine Ansprechperson"))
    shot(page, "02-entwurf")

    page.locator(".sticky-actions button.primary").click()
    expect(page.get_by_text("Taucht wieder auf bei")).to_be_visible()
    expect(page.locator("#toast")).to_contain_text("Gesichert")

    # Rückgängig holt den Entwurf zurück
    page.locator("#toast").get_by_role("button", name="Rückgängig").click()
    expect(page.locator("textarea.regel")).to_be_visible()
    page.locator(".sticky-actions button.primary").click()
    expect(page.get_by_text("Taucht wieder auf bei")).to_be_visible()

    # Suchen: Kompositum
    page.goto(f"{base}/#/suche")
    page.fill("#q", "Bank")
    expect(page.locator("#treffer").get_by_text(re.compile("Treffer"))).to_be_visible()
    expect(page.locator(".result h3").first).to_contain_text("Bank")
    shot(page, "03-suche")

    # Detail, erneut erlebt (Dialog statt prompt)
    page.locator(".result").first.click()
    expect(page.locator(".quote")).to_be_visible()
    page.get_by_role("button", name="Erneut erlebt").click()
    page.locator("dialog textarea").fill("wieder passiert")
    page.locator("dialog").get_by_role("button", name="Zählen").click()
    expect(page.locator("#toast")).to_contain_text("Gezählt")
    expect(page.locator(".meta").first).to_contain_text("bestätigt")
    shot(page, "04-detail")

    # Einstellungen: Fortschritt
    page.goto(f"{base}/#/einstellungen")
    expect(page.get_by_role("heading", name="Fortschritt")).to_be_visible()
    expect(page.locator(".tile .num").first).to_contain_text("4")
    shot(page, "05-einstellungen")

    # Pflichtfelder: Regel fehlt -> Hinweis am Feld, Fokus dort
    frisch(page, base)
    page.fill("#capture-text", "Notar, Termin verschoben")
    page.get_by_role("button", name="Sichern", exact=True).click()
    page.locator("textarea.regel").fill("")
    page.locator(".sticky-actions button.primary").click()
    expect(page.locator("textarea.regel")).to_have_attribute("aria-invalid", "true")
    expect(page.get_by_text("Bitte die Regel in einem Satz notieren.")).to_be_visible()
    page.get_by_role("button", name="Später", exact=True).click()
    expect(page.locator("#toast")).to_contain_text("Eingang")

    # Keine horizontale Scrollbar auf Handybreite
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    kein_null(page)
    assert page.errors == []


def test_lokaler_ablauf(server, page):
    base, _ = server
    expect = playwright.expect
    einstellungen(page, base, strukturierung_bereiche={"Beruf": "lokal"})
    frisch(page, base)
    page.locator(".chip", has_text="Beruf").click()
    expect(page.get_by_text("Bleibt auf deinem PC")).to_be_visible()
    page.fill("#capture-text", "Cutover, Schichtleiter fehlten, Inventur verzögert")
    page.get_by_role("button", name="Sichern", exact=True).click()
    expect(page.get_by_text("Dein PC strukturiert die Notiz lokal")).to_be_visible()

    # Worker-Thread verarbeitet im Hintergrund; der Eingang aktualisiert sich
    page.goto(f"{base}/#/eingang")
    zeile = page.locator("li", has_text="Vor jedem Cutover die Personalplanung")
    expect(zeile).to_be_visible(timeout=15000)
    expect(page.locator("#eingang-count")).not_to_have_text("")
    shot(page, "06-eingang")

    # Übernehmen mit einem Tipp
    zeile.get_by_role("button", name=re.compile("übernehmen$")).click()
    expect(page.locator("#toast")).to_contain_text("Übernommen")
    expect(zeile).to_have_count(0)

    page.goto(f"{base}/#/einstellungen")
    gruppe = page.get_by_role("group", name="Datenschutz-Stufe Beruf")
    expect(gruppe.get_by_role("button", name="Nur lokal")).to_have_attribute("aria-pressed", "true")
    # Stufe umstellen speichert direkt
    gruppe.get_by_role("button", name="Text an Claude").click()
    expect(gruppe.get_by_role("button", name="Text an Claude")).to_have_attribute("aria-pressed", "true")
    assert page.request.get(f"{base}/api/einstellungen").json()["strukturierung_bereiche"].get("Beruf") != "lokal"
    shot(page, "08-einstellungen")
    assert page.errors == []


def test_briefing_kombiniert(server, page):
    base, fake = server
    expect = playwright.expect
    einstellungen(page, base, strukturierung_bereiche={})
    frisch(page, base, "briefing")
    page.evaluate("localStorage.setItem('lv-briefing-modus', 'kombiniert')")
    page.reload()
    page.fill("#briefing-text", "Plan für die Hypercare-Phase eines SAP-EWM-Projekts")
    page.get_by_role("button", name="Briefing erstellen").click()
    expect(page.get_by_text("Hypercare braucht klare Eskalationswege")).to_be_visible()
    expect(page.get_by_text("Hier weichst du vom Üblichen ab")).to_be_visible()
    expect(page.get_by_role("heading", name="Vor dem Go-live")).to_be_visible()
    expect(page.locator("button.src.eigen")).to_have_count(1)
    expect(page.get_by_text("1 aus deiner Erfahrung")).to_be_visible()
    expect(page.get_by_text(re.compile("^An Claude gesendet: deine Situation"))).to_be_visible()
    # Eingabe ist eingeklappt, Kopieren steht oben
    expect(page.locator("#briefing-text")).to_be_hidden()
    assert fake.calls[-1]["system"] == KOMBI_PROMPT
    # Quelle antippen zeigt die eigene Regel
    page.locator("button.src.eigen").click()
    expect(page.locator(".src-detail")).to_be_visible()
    shot(page, "15-briefing-kombiniert")
    kein_null(page)

    page.locator("#modus-schalter").click()
    expect(page.get_by_text("Auf die Situation zugeschnitten (Claude, aus deinen Lessons)")).to_be_visible()
    assert fake.calls[-1]["system"] == BRIEFING_PROMPT
    assert page.evaluate("localStorage.getItem('lv-briefing-modus')") == "eigen"
    kein_null(page)
    assert page.errors == []


def test_briefing(server, page):
    base, _ = server
    expect = playwright.expect
    frisch(page, base, "briefing")
    page.evaluate("localStorage.setItem('lv-briefing-modus', 'eigen')")
    page.reload()
    page.fill("#briefing-text", "Bankgespräch für die nächste Wohnung vorbereiten")
    page.get_by_role("button", name="Briefing erstellen").click()
    expect(page.get_by_text("Fordere die Unterlagenliste der Bank vorab an")).to_be_visible()
    expect(page.locator("#briefing-result .checklist li")).to_have_count(2)
    expect(page.locator(".relevanz").first).to_contain_text("%")
    text = page.locator("#briefing-result").inner_text()
    assert "überholt" not in text and "null" not in text
    shot(page, "09-briefing")

    page.locator(".feedback .up").first.click()
    expect(page.locator(".feedback .up").first).to_have_attribute("aria-pressed", "true")
    page.locator(".feedback .down").nth(1).click()
    expect(page.locator(".result.abgewertet")).to_have_count(1)
    # Offene Frage für später gemerkt
    assert page.evaluate("JSON.parse(localStorage.getItem('lv-offen')).situation").startswith("Bankgespräch")

    # Verlauf und Wiederaufruf
    page.goto(f"{base}/#/briefing")
    page.reload()
    expect(page.get_by_role("heading", name="Frühere Briefings")).to_be_visible()
    eintrag = page.locator(".list a", has_text="Bankgespräch für die nächste Wohnung")
    expect(eintrag).to_contain_text("1 hilfreich")
    eintrag.click()
    expect(page.get_by_text("Fordere die Unterlagenliste der Bank vorab an")).to_be_visible()

    page.goto(f"{base}/#/einstellungen")
    expect(page.locator(".tile", has_text="Briefings mit hilfreicher Lesson")).to_contain_text("1")
    assert page.errors == []


def test_offene_frage_am_naechsten_tag(server, page):
    base, _ = server
    expect = playwright.expect
    frisch(page, base)
    page.evaluate("localStorage.setItem('lv-offen', JSON.stringify({id: 'x', situation: 'Besichtigung Wuppertal', t: Date.now() - 20*3600*1000}))")
    page.reload()
    expect(page.get_by_text(re.compile("Wie lief „Besichtigung Wuppertal“"))).to_be_visible()
    page.get_by_role("button", name="Jetzt notieren").click()
    expect(page.locator("#capture-text")).to_have_value(re.compile("^Nach „Besichtigung Wuppertal“: "))
    assert page.errors == []


def test_spezifitaet_schaerfen_nach_dem_sichern(server, page):
    base, _ = server
    expect = playwright.expect
    einstellungen(page, base, strukturierung_bereiche={})
    frisch(page, base)
    page.fill("#capture-text", "Projektplanung, Puffer zu knapp")
    page.get_by_role("button", name="Sichern", exact=True).click()
    expect(page.locator("textarea.regel")).to_have_value("Bei der Projektplanung Puffer einplanen.")
    expect(page.locator("#draft input[role=switch]")).not_to_be_checked()  # Claude: eher Allgemeinwissen
    page.locator(".sticky-actions button.primary").click()
    expect(page.get_by_text("Schärfen?")).to_be_visible()
    shot(page, "10-schaerfen")
    page.locator("textarea[id^=schaerfen-]").fill("Datenmigration, ich schätze sie jedes Mal um die Hälfte zu niedrig")
    page.get_by_role("button", name="Ergänzen").click()
    expect(page.get_by_text("Geschärft.")).to_be_visible()
    expect(page.locator("#erfassen-oben .quote")).to_have_text("Bei jeder Welle die Datenmigration mit dem doppelten meiner Schätzung einplanen.")
    page.locator("#erfassen-oben").get_by_role("link", name="Ansehen").click()
    expect(page.locator(".meta").first).to_contain_text("eigene Erfahrung")
    assert page.errors == []


braucht_ocr = pytest.mark.skipif(not Texterkennung().verfuegbar, reason="Tesseract mit Deutsch nicht installiert")


def folie_datei(tmp_path):
    from .bilder import folie_jpeg
    pfad = tmp_path / "folie.jpg"
    pfad.write_bytes(folie_jpeg())
    return pfad


@braucht_ocr
def test_lessons_aus_foto(server, page, tmp_path):
    base, fake = server
    expect = playwright.expect
    einstellungen(page, base, strukturierung_bereiche={})
    frisch(page, base)
    page.locator("#view input[type=file]").first.set_input_files(str(folie_datei(tmp_path)))
    expect(page.locator("#ocr-text")).to_have_value(re.compile("Schichtleiter"), timeout=15000)
    expect(page.locator(".thumbs img")).to_have_count(1)
    shot(page, "11-foto-text")
    anzahl = len(fake.calls)
    page.get_by_role("button", name="Lessons finden").click()
    expect(page.get_by_text("Auf dem Foto gefunden (2)")).to_be_visible()
    # Text-Weg: kein Bild an Claude
    assert all(isinstance(c["messages"][0]["content"], str) for c in fake.calls[anzahl:])
    page.locator("#kand-0").uncheck()
    shot(page, "12-kandidaten")
    page.get_by_role("button", name="Ausgewählte übernehmen (1)").click()
    expect(page).to_have_url(re.compile("#/eingang$"))
    eintrag = next(e for e in page.request.get(f"{base}/api/entwuerfe").json()["eintraege"] if e["rohtext"].startswith("Schichtleiter einplanen"))
    page.goto(f"{base}/#/entwurf/{eintrag['id']}")
    expect(page.locator(".card.hero .thumbs img")).to_be_visible(timeout=15000)
    page.locator(".sticky-actions button.primary").click()
    page.get_by_role("link", name="Ansehen").click()
    expect(page.get_by_role("heading", name="Fotos (1)")).to_be_visible()
    expect(page.locator(".thumbs img")).to_have_attribute("src", re.compile("^blob:"))
    page.locator(".thumb-open").click()
    expect(page.locator("dialog.lightbox img")).to_have_attribute("src", re.compile("^blob:"))
    shot(page, "13-lightbox")
    kein_null(page)
    page.keyboard.press("Escape")
    expect(page.locator("dialog.lightbox")).to_have_count(0)
    expect(page.locator(".thumb-open")).to_be_focused()  # Fokus zurück auf das Vorschaubild
    assert page.errors == []


@braucht_ocr
def test_plan_gegenchecken(server, page, tmp_path):
    base, fake = server
    expect = playwright.expect
    einstellungen(page, base, strukturierung_bereiche={})
    frisch(page, base, "briefing")
    page.get_by_role("button", name="Beruf", exact=True).click()
    page.locator("#view input[type=file]").set_input_files(str(folie_datei(tmp_path)))
    expect(page.get_by_text("Erkannter Text des Entwurfs")).to_be_visible(timeout=15000)
    page.get_by_role("button", name="Gegenchecken", exact=True).click()
    expect(page.get_by_text("Im Plan fehlt die schriftliche Personalfreigabe")).to_be_visible()
    expect(page.get_by_text("Was im Entwurf fehlt, laut deinen Lessons (Claude)")).to_be_visible()
    expect(page.get_by_text("Schon berücksichtigt (1)")).to_be_visible()
    call = fake.calls[-1]
    assert call["system"] == ABGLEICH_PROMPT and isinstance(call["messages"][0]["content"], str)
    shot(page, "14-entwurf-pruefen")
    kein_null(page)
    page.goto(f"{base}/#/suche")
    page.fill("#q", "Cutover")
    expect(page.locator("#treffer").get_by_text(re.compile("Treffer"))).to_be_visible()
    kein_null(page)
    assert page.errors == []


def test_anmeldung_mit_token(page, tmp_path):
    expect = playwright.expect
    settings = Settings(db_path=tmp_path / "z.db", anthropic_api_key="", ollama_model="", token="geheim-123")
    app = create_app(settings, Strukturierer(None, "m"), HashingProvider())
    port = free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    try:
        page.goto(f"http://127.0.0.1:{port}/#/suche")
        expect(page.get_by_role("heading", name="Zugang")).to_be_visible()
        page.fill("#zugang-token", "falsch")
        page.get_by_role("button", name="Anmelden").click()
        expect(page.get_by_text("Das Token passt nicht")).to_be_visible()
        page.fill("#zugang-token", "geheim-123")
        page.get_by_role("button", name="Anmelden").click()
        expect(page.get_by_role("heading", name="Suchen")).to_be_visible()
        shot(page, "16-nach-anmeldung")
    finally:
        srv.should_exit = True
        thread.join(timeout=5)


def test_pruefung_ersetzen_und_senden(server, page):
    base, fake = server
    expect = playwright.expect
    einstellungen(page, base, strukturierung_bereiche={})
    frisch(page, base)
    page.get_by_role("button", name="Beruf", exact=True).click()
    page.fill("#capture-text", "Cutover bei Kunde Müller GmbH zu spät abgestimmt")
    anzahl = len(fake.calls)
    page.get_by_role("button", name="Sichern", exact=True).click()
    expect(page.get_by_text("Kurz prüfen, bevor es an Claude geht", exact=True)).to_be_visible()
    assert len(fake.calls) == anzahl  # noch nichts gesendet
    shot(page, "17-pruefung")
    page.get_by_role("button", name=re.compile("„Kunde Müller GmbH“ ersetzen")).click()
    # Nach dem Ersetzen fällt nichts mehr auf: geht automatisch an Claude
    expect(page.locator("textarea.regel")).to_be_visible()
    assert len(fake.calls) == anzahl + 1
    assert "Müller" not in json.dumps(fake.calls[-1], ensure_ascii=False, default=str)
    kein_null(page)
    assert page.errors == []


def test_offline_postausgang_und_autosave(server, page):
    base, _ = server
    expect = playwright.expect
    frisch(page, base)
    # Autosave: Text überlebt einen Neustart der App
    page.fill("#capture-text", "Halbe Notiz vor dem Neustart")
    page.wait_for_timeout(600)
    page.reload()
    expect(page.locator("#capture-text")).to_have_value("Halbe Notiz vor dem Neustart")
    expect(page.get_by_text("Deine letzte Notiz ist wiederhergestellt.")).to_be_visible()

    vorher = len(page.request.get(f"{base}/api/entwuerfe").json()["eintraege"])
    page.context.set_offline(True)
    page.get_by_role("button", name="Sichern", exact=True).click()
    expect(page.get_by_text("Auf dem iPhone gesichert", exact=True)).to_be_visible()
    assert page.evaluate("JSON.parse(localStorage.getItem('lv-ausgang')).length") == 1
    page.context.set_offline(False)
    page.evaluate("window.dispatchEvent(new Event('online'))")
    expect(page.locator("#toast")).to_contain_text("an den PC gesendet")
    assert page.evaluate("JSON.parse(localStorage.getItem('lv-ausgang')).length") == 0
    assert len(page.request.get(f"{base}/api/entwuerfe").json()["eintraege"]) == vorher + 1


def test_deep_link_und_startbestand(server, page):
    base, _ = server
    expect = playwright.expect
    frisch(page, base)
    page.goto(f"{base}/#/erfassen?text=Notiz%20vom%20Kurzbefehl&bereich=Immobilien")
    expect(page.locator("#capture-text")).to_have_value("Notiz vom Kurzbefehl")
    expect(page.get_by_role("button", name="Immobilien")).to_have_attribute("aria-pressed", "true")
    expect(page).to_have_url(re.compile("#/erfassen$"))

    page.goto(f"{base}/#/ernte?bereich=Immobilien")
    expect(page.get_by_text(re.compile("Frage 1 von 10"))).to_be_visible()
    page.fill("#ernte-antwort", "Energieausweis und Heizungsalter zuerst")
    page.get_by_role("button", name="Sichern und weiter").click()
    expect(page.get_by_text(re.compile("Frage 2 von 10"))).to_be_visible()
    page.get_by_role("button", name="Überspringen").click()
    expect(page.get_by_text(re.compile("Frage 3 von 10"))).to_be_visible()
    eintraege = page.request.get(f"{base}/api/entwuerfe").json()["eintraege"]
    assert any(e["rohtext"].startswith("Was prüfst du bei der nächsten Besichtigung zuerst?") for e in eintraege), [e["rohtext"][:60] for e in eintraege]
    kein_null(page)
    assert page.errors == []
