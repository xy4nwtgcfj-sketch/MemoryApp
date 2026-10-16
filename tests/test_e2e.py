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
from lessons_vault.briefing import BRIEFING_PROMPT  # noqa: E402
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

    page.goto(base)
    expect(page.locator("#capture-text")).to_be_visible()
    shot(page, "01-erfassen")

    # Erfassen mit KI-Entwurf
    page.fill("#capture-text", "Bankgespräch, Gehaltsnachweise vergessen, zweiter Termin")
    page.get_by_role("button", name="Strukturieren").click()
    expect(page.locator("#f-lesson")).to_have_value("Vor jedem Bankgespräch die Unterlagenliste anfordern.")
    expect(page.locator(".notice.warn")).to_contain_text("Herr Meier")
    expect(page.get_by_text("Ähnliche Lessons (1)")).to_be_visible()
    shot(page, "02-entwurf")
    assert fake.calls, "Claude-Client wurde nicht aufgerufen"

    # Speichern
    page.fill("#f-situation", "Termin bei der Bank für eine vermietete Wohnung.")
    page.get_by_role("button", name="Speichern").click()
    expect(page.locator("#toast")).to_contain_text("Gespeichert")

    # Suchen: Kompositum
    page.goto(f"{base}/#/suche")
    page.fill("#q", "Bank")
    expect(page.get_by_text("Treffer")).to_be_visible()
    expect(page.locator(".result h3").first).to_contain_text("Bank")
    shot(page, "03-suche")

    # Detail, erneut erlebt
    page.locator(".result").first.click()
    expect(page.locator(".rule-big")).to_be_visible()
    page.once("dialog", lambda d: d.accept("wieder passiert"))
    page.get_by_role("button", name="Erneut erlebt").click()
    expect(page.locator("#toast")).to_contain_text("Bestätigt")
    expect(page.locator(".badges")).to_contain_text("bestätigt")
    shot(page, "04-detail")

    # Einstellungen
    page.goto(f"{base}/#/einstellungen")
    expect(page.get_by_text("Erfolgskriterien")).to_be_visible()
    expect(page.locator("dd").first).to_have_text("4")
    shot(page, "05-einstellungen")

    # Manuelle Erfassung blockiert Speichern ohne Pflichtfelder
    page.goto(f"{base}/#/erfassen")
    page.fill("#capture-text", "Notar")
    page.get_by_role("button", name="Manuell").click()
    expect(page.get_by_role("button", name="Speichern")).to_be_disabled()
    expect(page.get_by_text("Noch offen:")).to_be_visible()

    # Keine horizontale Scrollbar auf Handybreite
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.errors == []


def test_lokaler_ablauf(server, page):
    base, _ = server
    expect = playwright.expect
    page.request.put(f"{base}/api/einstellungen", data=json.dumps({"strukturierung_bereiche": {"Beruf": "lokal"}}),
                     headers={"Content-Type": "application/json"})
    page.goto(f"{base}/#/erfassen")
    page.reload()
    page.get_by_role("button", name="Beruf").click()
    expect(page.get_by_text("Verarbeitung: lokal im Hintergrund.")).to_be_visible()
    page.fill("#capture-text", "Cutover, Schichtleiter fehlten, Inventur verzögert")
    page.get_by_role("button", name="Speichern").click()
    expect(page.locator("#toast")).to_contain_text("Wird lokal strukturiert")

    # Worker-Thread verarbeitet im Hintergrund; Prüfen-Ansicht aktualisiert sich
    page.goto(f"{base}/#/pruefen")
    for _ in range(20):
        if page.get_by_text("bereit zur Prüfung").count():
            break
        page.wait_for_timeout(250)
        page.reload()
    expect(page.get_by_text("bereit zur Prüfung")).to_be_visible()
    expect(page.locator("#pruefen-count")).to_have_text("1")
    shot(page, "06-pruefen")

    page.get_by_text("Cutover-Personal früh bestätigen").click()
    expect(page.get_by_text("Deine Notiz")).to_be_visible()
    expect(page.locator("#f-lesson")).to_have_value("Vor jedem Cutover die Personalplanung schriftlich bestätigen lassen.")
    shot(page, "07-entwurf-pruefen")
    page.get_by_role("button", name="Speichern").click()
    expect(page.locator("#toast")).to_contain_text("Gespeichert")
    expect(page.get_by_text("Nichts zu prüfen.")).to_be_visible()

    page.goto(f"{base}/#/einstellungen")
    expect(page.get_by_role("heading", name="KI-Strukturierung")).to_be_visible()
    expect(page.locator("#ki-Beruf")).to_have_value("lokal")
    shot(page, "08-einstellungen-ki")
    assert page.errors == []


def test_briefing(server, page):
    base, _ = server
    expect = playwright.expect
    page.goto(f"{base}/#/briefing")
    page.fill("#briefing-text", "Bankgespräch für die nächste Wohnung vorbereiten")
    page.get_by_role("button", name="Briefing erstellen").click()
    expect(page.get_by_text("Fordere die Unterlagenliste der Bank vorab an")).to_be_visible()
    expect(page.get_by_text("Auf die Situation zugeschnitten (Claude)")).to_be_visible()
    expect(page.locator(".checklist li")).to_have_count(2)
    expect(page.locator(".why").first).to_contain_text("Relevanz")
    text = page.locator("#briefing-result").inner_text()
    assert "überholt" not in text and "null" not in text
    shot(page, "09-briefing")

    page.locator(".feedback .up").first.click()
    expect(page.locator(".feedback .up").first).to_have_attribute("aria-pressed", "true")
    page.locator(".feedback .down").nth(1).click()
    expect(page.locator(".result.abgewertet")).to_have_count(1)

    # Verlauf und Wiederaufruf
    page.goto(f"{base}/#/briefing")
    page.reload()
    expect(page.get_by_role("heading", name="Frühere Briefings")).to_be_visible()
    expect(page.locator("a.result").first).to_contain_text("1 hilfreich")
    page.locator("a.result").first.click()
    expect(page.get_by_text("Fordere die Unterlagenliste der Bank vorab an")).to_be_visible()

    page.goto(f"{base}/#/einstellungen")
    expect(page.get_by_text("1 von 1 (1 bewertet)")).to_be_visible()
    assert page.errors == []


def test_spezifitaets_rueckfrage(server, page):
    base, _ = server
    expect = playwright.expect
    page.request.put(f"{base}/api/einstellungen", data=json.dumps({"strukturierung_bereiche": {}}),
                     headers={"Content-Type": "application/json"})
    page.goto(f"{base}/#/erfassen")
    page.reload()
    page.fill("#capture-text", "Projektplanung, Puffer zu knapp")
    page.get_by_role("button", name="Strukturieren").click()
    expect(page.get_by_text("Was ist dein persönlicher Teil?")).to_be_visible()
    expect(page.get_by_role("button", name="Speichern")).to_be_enabled()  # Rückfrage ist optional
    expect(page.locator("#f-spezifisch")).not_to_be_checked()
    shot(page, "10-spezifitaet-frage")

    page.fill("#rueckfrage-antwort", "Datenmigration, ich schätze sie jedes Mal um die Hälfte zu niedrig")
    page.get_by_role("button", name="Antworten").click()
    expect(page.locator("#f-lesson")).to_have_value("Bei jeder Welle die Datenmigration mit dem doppelten meiner Schätzung einplanen.")
    expect(page.locator("#f-spezifisch")).to_be_checked()
    page.get_by_role("button", name="Speichern").click()
    expect(page.locator("#toast")).to_contain_text("Gespeichert")
    page.locator("#toast a").click()
    expect(page.locator(".badges")).to_contain_text("persönlich")
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
    page.goto(f"{base}/#/erfassen")
    page.reload()
    page.locator("#view input[type=file]").set_input_files(str(folie_datei(tmp_path)))
    expect(page.get_by_text("Erkannter Text")).to_be_visible(timeout=15000)
    expect(page.locator("#ocr-text")).to_have_value(re.compile("Schichtleiter"))
    expect(page.locator(".thumbs img")).to_have_count(1)
    shot(page, "11-foto-text")
    anzahl = len(fake.calls)
    page.get_by_role("button", name="Lessons finden").click()
    expect(page.get_by_text("Gefundene Erfahrungen (2)")).to_be_visible()
    # Text-Weg: kein Bild an Claude
    assert all(isinstance(c["messages"][0]["content"], str) for c in fake.calls[anzahl:])
    page.locator("#kand-0").uncheck()
    shot(page, "12-kandidaten")
    page.get_by_role("button", name="Ausgewählte erfassen (1)").click()
    expect(page.get_by_text("Lesson 1 von 1 aus dem Foto")).to_be_visible()
    expect(page.get_by_text("1 Foto wird an die Lesson gehängt.")).to_be_visible()
    page.get_by_role("button", name="Speichern").click()
    expect(page.locator("#toast")).to_contain_text("Gespeichert")
    page.locator("#toast a").click()
    expect(page.get_by_role("heading", name="Fotos (1)")).to_be_visible()
    expect(page.locator(".thumbs img")).to_have_attribute("src", re.compile("^blob:"))
    page.locator(".thumb-open").click()
    expect(page.locator(".lightbox img")).to_have_attribute("src", re.compile("^blob:"))
    shot(page, "13-lightbox")
    kein_null(page)
    page.keyboard.press("Escape")
    expect(page.locator(".lightbox")).to_have_count(0)
    assert page.errors == []


@braucht_ocr
def test_entwurf_pruefen(server, page, tmp_path):
    base, fake = server
    expect = playwright.expect
    page.goto(f"{base}/#/briefing")
    page.reload()
    page.get_by_role("button", name="Beruf").click()
    page.locator("#view input[type=file]").set_input_files(str(folie_datei(tmp_path)))
    expect(page.get_by_text("Erkannter Text des Entwurfs")).to_be_visible(timeout=15000)
    page.get_by_role("button", name="Prüfen", exact=True).click()
    expect(page.get_by_text("Im Plan fehlt die schriftliche Personalfreigabe")).to_be_visible()
    expect(page.get_by_text("Was im Entwurf fehlt, laut deinen Lessons (Claude)")).to_be_visible()
    expect(page.get_by_text("Schon berücksichtigt (1)")).to_be_visible()
    expect(page.get_by_role("heading", name="Abgleich mit deinen Erfahrungen")).to_have_count(0)  # ist ein <strong>
    call = fake.calls[-1]
    assert call["system"] == ABGLEICH_PROMPT and isinstance(call["messages"][0]["content"], str)
    shot(page, "14-entwurf-pruefen")
    kein_null(page)
    # Suche ohne Entwürfe darf auch kein "null" zeigen
    page.goto(f"{base}/#/suche")
    page.fill("#q", "Cutover")
    expect(page.get_by_text("Treffer")).to_be_visible()
    kein_null(page)
    assert page.errors == []
