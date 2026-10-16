"""Browser-Smoke-Test der PWA (wird übersprungen, wenn Playwright fehlt).

Startet die App mit gemocktem Claude-Client, damit der KI-Pfad ohne API-Key testbar ist.
"""

import glob
import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

from lessons_vault.config import Settings  # noqa: E402
from lessons_vault.embeddings import HashingProvider  # noqa: E402
from lessons_vault.main import create_app  # noqa: E402
from lessons_vault.structuring import Strukturierer  # noqa: E402

from .test_structuring import FakeClient, payload  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOTS = os.environ.get("LV_SCREENSHOTS")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    fake = FakeClient(payload(situation="Termin bei der Bank für eine vermietete Wohnung, Herr Meier als Berater."))
    settings = Settings(db_path=tmp_path_factory.mktemp("e2e") / "e2e.db")
    app = create_app(settings, Strukturierer(fake, "claude-opus-5-5"), HashingProvider())
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
