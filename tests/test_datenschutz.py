"""Härtung H1/H2: Lokal-Zusage ohne Bereichswahl, Prüfung vor dem Senden, beruflich als Bereichseigenschaft."""

import pytest
from fastapi.testclient import TestClient

from lessons_vault import main
from lessons_vault.briefing import BRIEFING_PROMPT, KOMBI_PROMPT
from lessons_vault.compliance import pruefen
from lessons_vault.config import Settings
from lessons_vault.embeddings import HashingProvider
from lessons_vault.foto import KANDIDATEN_PROMPT
from lessons_vault.main import create_app
from lessons_vault.structuring import Strukturierer

from .bilder import folie_jpeg
from .test_api import lesson_json
from .test_structuring import FakeClient, payload


def antwort(kwargs):
    if kwargs["system"] == KANDIDATEN_PROMPT:
        return {"kandidaten": [], "hinweis": ""}
    if kwargs["system"] == KOMBI_PROMPT:
        return {"zusammenfassung": "x", "abschnitte": [], "besonderheiten": []}
    if kwargs["system"] == BRIEFING_PROMPT:
        return {"zusammenfassung": "x", "checkliste": []}
    return payload()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    claude = FakeClient(antwort)
    app = create_app(Settings(db_path=tmp_path / "t.db", anthropic_api_key="", ollama_model=""),
                     Strukturierer(claude, "claude-opus-5-5"), HashingProvider())
    return TestClient(app), claude


def bild(client):
    return client.post("/api/bilder", files=[("dateien", ("f.jpg", folie_jpeg(), "image/jpeg"))]).json()[0]["id"]


# --- H1 -------------------------------------------------------------------
def test_ohne_bereich_nichts_an_claude_wenn_lokal_aktiv(env):
    client, claude = env
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}})
    r = client.post("/api/erfassen", json={"text": "Cutover bei Kunde Müller GmbH"}).json()
    assert r["modus"] == "sofort" and r["entwurf"]["ki_verwendet"] is False  # kein lokales Modell: manuell
    client.post("/api/erfassen/entwurf", json={"text": "x", "rueckfrage": "?", "antwort": "y"})
    assert claude.calls == []
    assert client.get("/api/status").json()["modus_standard"] == "manuell"
    # Mit Bereich Immobilien weiterhin Claude
    client.post("/api/erfassen", json={"text": "Bankgespräch", "bereich": "Immobilien"})
    assert len(claude.calls) == 1


def test_fotos_ohne_bereich_lokal_wenn_lokal_aktiv(env):
    client, claude = env
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}})
    bid = bild(client)
    assert client.post("/api/foto/vorbereiten", json={"bild_ids": [bid]}).json()["weg"] == "lokal"
    assert client.post("/api/foto/kandidaten", json={"bild_ids": [bid], "text": "abc def"}).status_code == 409
    assert claude.calls == []


def test_briefing_ohne_bereich_bei_standard_lokal(env):
    client, claude = env
    client.put("/api/einstellungen", json={"strukturierung_standard": "lokal"})
    data = client.post("/api/briefing", json={"situation": "Hypercare planen"}).json()
    assert data["ki_moeglich"] is False and "lokal" in data["ki_hinweis"]
    assert client.post(f"/api/briefing/{data['id']}/zusammenfassung").status_code == 409
    assert claude.calls == []


def test_beruflich_foto_nie_als_bild(env):
    client, claude = env
    client.put("/api/einstellungen", json={"bild_bereiche": {"Beruf": "bild"}})
    bid = bild(client)
    assert client.post("/api/foto/vorbereiten", json={"bild_ids": [bid], "bereich": "Beruf"}).json()["weg"] == "text"
    # Neuer beruflicher Bereich ebenfalls nur Texterkennung
    client.post("/api/bereiche", json={"name": "SAP", "beruflich": True})
    assert client.post("/api/foto/vorbereiten", json={"bild_ids": [bid], "bereich": "SAP"}).json()["weg"] == "text"
    client.post("/api/bereiche", json={"name": "Garten"})
    assert client.post("/api/foto/vorbereiten", json={"bild_ids": [bid], "bereich": "Garten"}).json()["weg"] == "bild"


# --- H2 -------------------------------------------------------------------
def test_pruefung_vor_dem_senden(env):
    client, claude = env
    r = client.post("/api/erfassen", json={"text": "Cutover bei Kunde Müller GmbH verschoben", "bereich": "Beruf"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "pruefung" and any("Müller GmbH" in h for h in detail["hinweise"])
    assert claude.calls == []
    r = client.post("/api/erfassen", json={"text": "Cutover bei Kunde Müller GmbH verschoben", "bereich": "Beruf", "freigabe": True})
    assert r.status_code == 200 and len(claude.calls) == 1


def test_sperrliste_blockiert_auch_mit_freigabe(env):
    client, claude = env
    client.put("/api/einstellungen", json={"sperrliste": ["Acme"]})
    for body in ({"text": "Go-live bei ACME", "bereich": "Beruf"}, {"text": "Go-live bei ACME", "bereich": "Beruf", "freigabe": True}):
        r = client.post("/api/erfassen", json=body)
        assert r.status_code == 422 and r.json()["detail"]["code"] == "sperrliste"
    r = client.post("/api/erfassen/entwurf", json={"text": "x", "bereich": "Immobilien", "rueckfrage": "?", "antwort": "acme", "freigabe": True})
    assert r.status_code == 422
    bid = bild(client)
    r = client.post("/api/foto/kandidaten", json={"bild_ids": [bid], "bereich": "Immobilien", "notiz": "von Acme", "freigabe": True})
    assert r.status_code == 422
    assert claude.calls == []


def test_briefing_situation_wird_geprueft(env):
    client, claude = env
    client.post("/api/lessons", json=lesson_json(bereich="Beruf", titel="Hypercare Personal"))
    bid = client.post("/api/briefing", json={"situation": "Hypercare bei Kunde Brenntag planen"}).json()["id"]
    r = client.post(f"/api/briefing/{bid}/zusammenfassung")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "pruefung"
    assert claude.calls == []
    assert client.post(f"/api/briefing/{bid}/zusammenfassung", params={"freigabe": True}).status_code == 200


def test_ohne_bereich_keine_zahlenwarnung(env):
    client, _ = env
    # Private Notiz mit Betrag: ohne Bereich nur Namensregeln, keine Rückfrage wegen Zahlen
    assert client.post("/api/erfassen", json={"text": "Sanierung kostete 12.000 €"}).status_code == 200


def test_beruflich_flag_steuert_zahlenpruefung():
    assert pruefen("Budget 4500 €", "Arbeit", beruflich=True)
    assert pruefen("Budget 4500 €", "Arbeit", beruflich=False) == []
    assert pruefen("Budget 4500 €", "Beruf")  # Standard: Name "Beruf"


def test_beruflich_umschaltbar(env):
    client, _ = env
    assert {b["name"]: b["beruflich"] for b in client.get("/api/bereiche").json()}["Beruf"] is True
    assert client.patch("/api/bereiche/Projekte", json={"beruflich": True}).json()["beruflich"] is True
