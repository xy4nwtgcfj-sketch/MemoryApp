import pytest
from fastapi.testclient import TestClient

from lessons_vault import main
from lessons_vault.config import Settings
from lessons_vault.embeddings import HashingProvider
from lessons_vault.main import create_app
from lessons_vault.structuring import OllamaStrukturierer, Strukturierer

from .ollama_mock import OllamaMock
from .test_api import lesson_json
from .test_structuring import FakeClient, payload


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": True, "modelle": ["qwen2.5:7b", "bge-m3:latest"]})
    claude = FakeClient(payload())
    ollama = OllamaMock(payload(bereich="Beruf", titel="Lokal strukturiert", rueckfrage="Welche Welle?"))
    settings = Settings(db_path=tmp_path / "t.db", anthropic_api_key="", voyage_api_key="", ollama_model="qwen2.5:7b")
    app = create_app(
        settings,
        Strukturierer(claude, "claude-opus-5-5"),
        HashingProvider(),
        OllamaStrukturierer("http://ollama", "qwen2.5:7b", client=ollama.client()),
    )
    return TestClient(app), app, claude, ollama


def test_status_zeigt_lokal(setup):
    client, *_ = setup
    data = client.get("/api/status").json()
    assert data["lokal"]["erreichbar"] and data["lokal"]["modell_installiert"] and data["lokal"]["embed_modell_installiert"]
    assert data["modus_standard"] == "claude"  # auto + Claude-Key → Claude


def test_routing_pro_bereich(setup):
    client, app, claude, ollama = setup
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal", "Gibtsnicht": "lokal"}})
    assert client.get("/api/einstellungen").json()["strukturierung_bereiche"] == {"Beruf": "lokal"}
    assert client.get("/api/status").json()["modi"]["Beruf"] == "lokal"

    r = client.post("/api/erfassen", json={"text": "Cutover Personal fehlte", "bereich": "Beruf", "erfassung_sekunden": 7}).json()
    assert r["modus"] == "hintergrund" and r["eintrag"]["status"] == "wartet"
    assert claude.calls == [] and ollama.chat_requests == []

    assert app.state.worker.verarbeite_naechsten()
    eintrag = client.get(f"/api/entwuerfe/{r['eintrag']['id']}").json()
    assert eintrag["status"] == "fertig" and eintrag["entwurf"]["titel"] == "Lokal strukturiert"
    assert eintrag["entwurf"]["bereich"] == "Beruf" and eintrag["entwurf"]["rueckfrage"] == "Welche Welle?"
    # Bereichsvorgabe schränkt das Schema ein
    assert ollama.chat_requests[0]["format"]["properties"]["bereich"]["enum"] == ["Beruf"]

    r2 = client.post("/api/erfassen", json={"text": "Bank Unterlagen", "bereich": "Immobilien"}).json()
    assert r2["modus"] == "sofort" and r2["entwurf"]["ki_modell"] == "claude:claude-opus-5-5"


def test_lokale_bereiche_gehen_nie_an_claude(setup):
    client, _, claude, _ = setup
    client.post("/api/lessons", json=lesson_json(bereich="Beruf", titel="Geheimes Bankgespräch Beruf"))
    client.post("/api/lessons", json=lesson_json(bereich="Immobilien", titel="Privates Bankgespräch"))
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}})
    client.post("/api/erfassen", json={"text": "Unterlagen vor Bankgespräch"})
    prompt = claude.calls[-1]["messages"][0]["content"]
    assert "Privates Bankgespräch" in prompt
    assert "Geheimes" not in prompt
    # Rückfrage-Runde eines lokalen Bereichs geht nicht an Claude
    anzahl = len(claude.calls)
    client.post("/api/erfassen/entwurf", json={"text": "x", "bereich": "Beruf", "rueckfrage": "?", "antwort": "y"})
    assert len(claude.calls) == anzahl


def test_standard_lokal_und_uebernahme(setup):
    client, app, claude, _ = setup
    client.put("/api/einstellungen", json={"strukturierung_standard": "lokal"})
    r = client.post("/api/erfassen", json={"text": "Bank Unterlagen", "quelle": "sprache", "erfassung_sekunden": 9.5}).json()
    eid = r["eintrag"]["id"]
    app.state.worker.verarbeite_naechsten()
    liste = client.get("/api/entwuerfe").json()
    assert liste["zaehler"]["fertig"] == 1 and client.get("/api/statistik").json()["offene_entwuerfe"] == 1

    res = client.post("/api/lessons", json=lesson_json(entwurf_id=eid, quelle="text", erfassung_sekunden=999))
    assert res.status_code == 201
    lesson = res.json()["lesson"]
    assert lesson["erfassung_sekunden"] == 9.5 and lesson["quelle"] == "sprache"
    assert client.get(f"/api/entwuerfe/{eid}").status_code == 404
    assert claude.calls == []


def test_antwort_neu_verwerfen_bestaetigen(setup):
    client, app, _, ollama = setup
    client.put("/api/einstellungen", json={"strukturierung_standard": "lokal"})
    eid = client.post("/api/erfassen", json={"text": "Welle"}).json()["eintrag"]["id"]
    app.state.worker.verarbeite_naechsten()

    r = client.post(f"/api/entwuerfe/{eid}/antwort", json={"antwort": "Welle 3"}).json()
    assert r["status"] == "wartet" and r["rueckfrage"] == "Welche Welle?"
    app.state.worker.verarbeite_naechsten()
    assert "Stelle keine weitere" in ollama.chat_requests[-1]["messages"][1]["content"]
    assert client.get(f"/api/entwuerfe/{eid}").json()["entwurf"]["rueckfrage"] == ""

    assert client.post(f"/api/entwuerfe/{eid}/neu").json()["status"] == "wartet"
    app.state.worker.verarbeite_naechsten()

    lid = client.post("/api/lessons", json=lesson_json()).json()["lesson"]["id"]
    r = client.post(f"/api/lessons/{lid}/bestaetigen", json={"notiz": "wieder", "entwurf_id": eid})
    assert r.json()["bestaetigungen"] == 2
    assert client.get(f"/api/entwuerfe/{eid}").status_code == 404

    eid2 = client.post("/api/erfassen", json={"text": "Notar Termin"}).json()["eintrag"]["id"]
    assert client.get("/api/entwuerfe", params={"q": "Notar"}).json()["eintraege"][0]["id"] == eid2
    assert client.delete(f"/api/entwuerfe/{eid2}").status_code == 204


def test_auto_ohne_claude_nutzt_lokal(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": True, "modelle": ["qwen2.5:7b"]})
    settings = Settings(db_path=tmp_path / "t.db", anthropic_api_key="", voyage_api_key="", ollama_model="qwen2.5:7b")
    app = create_app(settings, Strukturierer(None, "m"), HashingProvider(),
                     OllamaStrukturierer("http://ollama", "qwen2.5:7b", client=OllamaMock().client()))
    client = TestClient(app)
    assert client.post("/api/erfassen", json={"text": "x"}).json()["modus"] == "hintergrund"
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    app2 = create_app(Settings(db_path=tmp_path / "u.db", ollama_model="qwen2.5:7b", anthropic_api_key=""), Strukturierer(None, "m"), HashingProvider())
    assert TestClient(app2).post("/api/erfassen", json={"text": "x"}).json()["modus"] == "sofort"


def test_lifespan_startet_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    settings = Settings(db_path=tmp_path / "t.db", anthropic_api_key="", ollama_model="")
    app = create_app(settings, Strukturierer(None, "m"), HashingProvider())
    with TestClient(app) as client:
        assert client.get("/api/status").status_code == 200
        assert app.state.worker._thread.is_alive()
    assert not app.state.worker._thread.is_alive()


def test_einstellungen_teilweise_speichern(setup):
    client, *_ = setup
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}})
    client.put("/api/einstellungen", json={"sperrliste": ["Acme"]})
    data = client.get("/api/einstellungen").json()
    assert data["sperrliste"] == ["Acme"] and data["strukturierung_bereiche"] == {"Beruf": "lokal"}


def test_lokal_eingestellt_ohne_modell_bleibt_privat(tmp_path, monkeypatch):
    """Bereich auf lokal, aber kein Ollama-Modell konfiguriert: trotzdem nie an Claude."""
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    claude = FakeClient(payload())
    app = create_app(Settings(db_path=tmp_path / "t.db", anthropic_api_key="", ollama_model=""),
                     Strukturierer(claude, "m"), HashingProvider())
    client = TestClient(app)
    client.post("/api/lessons", json=lesson_json(bereich="Beruf", titel="Geheimes Bankgespräch Beruf"))
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}})
    assert client.get("/api/status").json()["modi"]["Beruf"] == "manuell"
    client.post("/api/erfassen", json={"text": "Unterlagen vor Bankgespräch", "bereich": "Immobilien"})
    assert "Geheimes" not in claude.calls[-1]["messages"][0]["content"]
    r = client.post("/api/erfassen", json={"text": "Bankgespräch", "bereich": "Beruf"}).json()
    assert r["modus"] == "sofort" and r["entwurf"]["ki_verwendet"] is False
