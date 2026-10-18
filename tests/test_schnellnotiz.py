"""Schnellnotiz, sofortige Strukturierung über Entwürfe, Wochenrhythmus und Wiedersehen."""

import json

import pytest
from fastapi.testclient import TestClient

from lessons_vault import main
from lessons_vault.config import Settings
from lessons_vault.embeddings import HashingProvider
from lessons_vault.main import create_app
from lessons_vault.models import Entwurf
from lessons_vault.structuring import Strukturierer
from lessons_vault.worker import Hintergrund

from .test_api import lesson_json
from .test_structuring import FakeClient, payload


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    claude = FakeClient(lambda kwargs: payload())
    app = create_app(Settings(db_path=tmp_path / "t.db", anthropic_api_key="", ollama_model=""),
                     Strukturierer(claude, "claude-opus-5-5"), HashingProvider())
    return TestClient(app), claude, app


def test_notiz_wartet_und_liefert_entwurf(env):
    client, claude, _ = env
    r = client.post("/api/notiz?warten=true", json={"text": "Bankgespräch, Gehaltsnachweise vergessen", "bereich": "Immobilien"})
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["status"] == "fertig" and e["modus"] == "claude"
    assert e["entwurf"]["lesson"].startswith("Vor jedem Bankgespräch")
    assert len(claude.calls) == 1


def test_notiz_ohne_warten_wird_trotzdem_strukturiert(env):
    client, claude, _ = env
    r = client.post("/api/notiz", json={"text": "Bankgespräch", "bereich": "Immobilien"}).json()
    # Im Testclient laufen Hintergrundaufgaben vor der Rückgabe; danach ist der Entwurf fertig.
    assert client.get(f"/api/entwuerfe/{r['id']}").json()["status"] == "fertig"
    assert len(claude.calls) == 1


def test_notiz_mit_namen_geht_nicht_an_claude(env):
    client, claude, _ = env
    e = client.post("/api/notiz?warten=true", json={"text": "Cutover bei Kunde Müller GmbH verschoben", "bereich": "Beruf"}).json()
    assert claude.calls == []
    assert e["status"] == "fertig"
    assert e["entwurf"]["pruefung"]["code"] == "pruefung" and e["entwurf"]["pruefung"]["hinweise"]
    # Bewusste Freigabe: jetzt geht es an Claude
    e2 = client.post(f"/api/entwuerfe/{e['id']}/strukturieren", json={"freigabe": True}).json()
    assert e2["entwurf"]["ki_verwendet"] is True and e2["entwurf"]["pruefung"] is None
    assert len(claude.calls) == 1


def test_strukturieren_mit_geaendertem_text(env):
    client, claude, _ = env
    e = client.post("/api/notiz?warten=true", json={"text": "Cutover bei Kunde Müller GmbH verschoben", "bereich": "Beruf"}).json()
    e2 = client.post(f"/api/entwuerfe/{e['id']}/strukturieren", json={"text": "Cutover bei einem Logistikkunden verschoben"}).json()
    assert e2["rohtext"] == "Cutover bei einem Logistikkunden verschoben"
    assert e2["entwurf"]["ki_verwendet"] is True
    assert "Müller" not in json.dumps(claude.calls[0], ensure_ascii=False, default=str)


def test_sperrliste_blockiert_auch_im_hintergrund(env):
    client, claude, _ = env
    client.put("/api/einstellungen", json={"sperrliste": ["Projekt Falke"]})
    e = client.post("/api/notiz?warten=true", json={"text": "Projekt Falke Go-live verschoben", "bereich": "Immobilien"}).json()
    assert e["entwurf"]["pruefung"]["code"] == "sperrliste"
    e2 = client.post(f"/api/entwuerfe/{e['id']}/strukturieren", json={"freigabe": True}).json()
    assert e2["entwurf"]["pruefung"]["code"] == "sperrliste"
    assert claude.calls == []


def test_lokaler_bereich_geht_nie_an_claude(env):
    client, claude, _ = env
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}})
    e = client.post("/api/notiz?warten=true", json={"text": "Cutover verschoben", "bereich": "Beruf"}).json()
    # Kein lokales Modell: sofort manuell, aber als "lokal" gemerkt
    assert e["modus"] == "lokal" and e["status"] == "fertig" and e["entwurf"]["ki_verwendet"] is False
    # Auch nach dem Umstellen zurück auf Claude bleibt dieser Entwurf lokal
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {}})
    client.post(f"/api/entwuerfe/{e['id']}/strukturieren", json={"freigabe": True})
    assert claude.calls == []


def test_spaeter_ansehen_legt_fertigen_entwurf_ab(env):
    client, claude, _ = env
    entwurf = Entwurf(**{k: v for k, v in payload().items() if k != "dublette_von"}).model_dump()
    e = client.post("/api/notiz", json={"text": "Bankgespräch", "bereich": "Immobilien", "entwurf": entwurf}).json()
    assert e["status"] == "fertig" and e["entwurf"]["titel"] == entwurf["titel"]
    assert claude.calls == []
    assert client.get("/api/statistik").json()["offene_entwuerfe"] == 1


def test_worker_arbeitet_claude_ab_wenn_lokales_modell_fehlt(repo):
    lokal = repo.entwurf_anlegen("lokal", "text", modus="lokal")
    claude = repo.entwurf_anlegen("claude", "text", modus="claude")
    verarbeitet = []

    def verarbeiter(e):
        verarbeitet.append(e.rohtext)
        return Entwurf(titel=e.rohtext, ki_verwendet=True)

    w = Hintergrund(repo, HashingProvider(), verarbeiter, "m", bereit=lambda: False)
    assert w.verarbeite_naechsten()
    assert verarbeitet == ["claude"]
    assert repo.entwurf_holen(claude.id).status == "fertig"
    assert repo.entwurf_holen(lokal.id).status == "wartet"
    assert not w.verarbeite_naechsten() and w.wartet_auf_modell


def test_wochenrhythmus_und_bestaetigungen(env):
    client, _, _ = env
    lid = client.post("/api/lessons", json=lesson_json()).json()["lesson"]["id"]
    s = client.get("/api/statistik").json()
    assert s["woche_aktiv"] is True and s["aktive_wochen"] == 1 and s["wochen_betrachtet"] == 6
    assert s["bestaetigt_7_tage"] == 0
    client.post(f"/api/lessons/{lid}/bestaetigen", json={"notiz": "wieder"})
    assert client.get("/api/statistik").json()["bestaetigt_7_tage"] == 1


def test_import_zaehlt_nicht_als_aktive_woche(env):
    client, _, _ = env
    client.post("/api/import", json=[lesson_json(quelle="import")])
    assert client.get("/api/statistik").json()["aktive_wochen"] == 0


def test_wiedersehen(env):
    client, _, app = env
    assert client.get("/api/wiedersehen").json() is None
    lid = client.post("/api/lessons", json=lesson_json()).json()["lesson"]["id"]
    assert client.get("/api/wiedersehen").json() is None  # zu neu
    with app.state.repo.conn:
        app.state.repo.conn.execute("UPDATE lessons SET erstellt_am = '2026-01-01T10:00:00' WHERE id = ?", (lid,))
    assert client.get("/api/wiedersehen?tag=2026-10-18").json()["id"] == lid
    assert client.get(f"/api/wiedersehen?ausser={lid}").json() is None


def test_hilfreich_zaehler_und_rueckmeldung(env):
    client, _, _ = env
    lid = client.post("/api/lessons", json=lesson_json()).json()["lesson"]["id"]
    b = client.post("/api/briefing", json={"situation": "Bankgespräch morgen", "modus": "eigen"}).json()
    client.post(f"/api/briefing/{b['id']}/feedback", json={"lesson_id": lid, "bewertung": "hilfreich"})
    assert client.get(f"/api/lessons/{lid}").json()["hilfreich"] == 1
    assert client.post("/api/rueckmeldung", json={"art": "bremse", "wert": "Warten"}).status_code == 204
    assert client.post("/api/rueckmeldung", json={"art": "anderes", "wert": "x"}).status_code == 422
    assert client.get("/api/statistik").json()["bremsen"] == {"Warten": 1}


def test_gzip(env):
    client, _, _ = env
    r = client.get("/app.js", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
