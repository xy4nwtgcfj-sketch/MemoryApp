import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lessons_vault import main
from lessons_vault.briefing import BRIEFING_PROMPT
from lessons_vault.config import Settings
from lessons_vault.embeddings import HashingProvider
from lessons_vault.foto import ABGLEICH_PROMPT, KANDIDATEN_PROMPT
from lessons_vault.images import Texterkennung
from lessons_vault.main import create_app
from lessons_vault.structuring import Strukturierer

from .bilder import folie_jpeg
from .test_api import lesson_json
from .test_structuring import FakeClient, payload

braucht_ocr = pytest.mark.skipif(not Texterkennung().verfuegbar, reason="Tesseract mit Deutsch nicht installiert")


def antwort(kwargs):
    system = kwargs["system"]
    if system == KANDIDATEN_PROMPT:
        return {"kandidaten": [
            {"titel": "Cutover früh abstimmen", "kern": "Der Cutover-Plan wurde zu spät mit dem Lager abgestimmt."},
            {"titel": "Schichtleiter einplanen", "kern": "Schichtleiter fehlten, die Inventur verzögerte sich."},
            {"titel": "", "kern": ""},
        ], "hinweis": ""}
    if system == ABGLEICH_PROMPT:
        return {"zusammenfassung": "Im Plan fehlt die Personalplanung.",
                "fehlt": [{"punkt": "Schichtleiter schriftlich bestätigen lassen", "lesson_nr": 1}],
                "beruecksichtigt": [{"punkt": "Cutover-Termin steht", "lesson_nr": 1}]}
    if system == BRIEFING_PROMPT:
        return {"zusammenfassung": "x", "checkliste": []}
    return payload()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    claude = FakeClient(antwort)
    settings = Settings(db_path=tmp_path / "t.db", anthropic_api_key="", voyage_api_key="", ollama_model="")
    app = create_app(settings, Strukturierer(claude, "claude-opus-5-5"), HashingProvider())
    return TestClient(app), claude, app


def hochladen(client, *bilder):
    files = [("dateien", (f"f{i}.jpg", b, "image/jpeg")) for i, b in enumerate(bilder or [folie_jpeg()])]
    r = client.post("/api/bilder", files=files)
    assert r.status_code == 201, r.text
    return [b["id"] for b in r.json()]


def bild_inhalte(call):
    content = call["messages"][0]["content"]
    return [b for b in content if isinstance(b, dict) and b.get("type") == "image"] if isinstance(content, list) else []


@braucht_ocr
def test_upload_ocr_und_abruf(env):
    client, *_ = env
    r = client.post("/api/bilder", files=[("dateien", ("f.jpg", folie_jpeg(), "image/jpeg"))]).json()[0]
    assert r["ocr_status"] == "fertig"
    bild = client.get(f"/api/bilder/{r['id']}", params={"variante": "vorschau"})
    assert bild.status_code == 200 and bild.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(bild.content)) as img:
        assert len(img.getexif()) == 0
    assert client.get("/api/bilder/00000000-0000-0000-0000-000000000000").status_code == 404


def test_upload_grenzen(env):
    client, *_ = env
    assert client.post("/api/bilder", files=[("dateien", ("x.jpg", b"kaputt", "image/jpeg"))]).status_code == 422
    zu_viele = [("dateien", (f"{i}.jpg", folie_jpeg(), "image/jpeg")) for i in range(6)]
    assert client.post("/api/bilder", files=zu_viele).status_code == 422


@braucht_ocr
def test_wege(env):
    client, claude, _ = env
    ids = hochladen(client)
    beruf = client.post("/api/foto/vorbereiten", json={"bild_ids": ids, "bereich": "Beruf"}).json()
    assert beruf["weg"] == "text" and "Schichtleiter" in beruf["text"]
    assert client.post("/api/foto/vorbereiten", json={"bild_ids": ids}).json()["weg"] == "text"
    assert client.post("/api/foto/vorbereiten", json={"bild_ids": ids, "bereich": "Immobilien"}).json()["weg"] == "bild"
    client.put("/api/einstellungen", json={"bild_bereiche": {"Immobilien": "text"}, "strukturierung_bereiche": {"Beruf": "lokal"}})
    assert client.post("/api/foto/vorbereiten", json={"bild_ids": ids, "bereich": "Immobilien"}).json()["weg"] == "text"
    assert client.post("/api/foto/vorbereiten", json={"bild_ids": ids, "bereich": "Beruf"}).json()["weg"] == "lokal"
    assert claude.calls == []  # Vorbereiten fragt Claude nie


def test_ohne_claude_alles_lokal(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    app = create_app(Settings(db_path=tmp_path / "t.db", anthropic_api_key="", ollama_model=""), Strukturierer(None, "m"), HashingProvider())
    client = TestClient(app)
    ids = hochladen(client)
    assert client.post("/api/foto/vorbereiten", json={"bild_ids": ids, "bereich": "Immobilien"}).json()["weg"] == "lokal"


def test_kandidaten_text_weg_schickt_kein_bild(env):
    client, claude, _ = env
    ids = hochladen(client)
    r = client.post("/api/foto/kandidaten", json={"bild_ids": ids, "bereich": "Beruf", "text": "Geprüfter Text der Folie"}).json()
    assert r["weg"] == "text" and [k["titel"] for k in r["kandidaten"]] == ["Cutover früh abstimmen", "Schichtleiter einplanen"]
    call = claude.calls[-1]
    assert bild_inhalte(call) == [] and "Geprüfter Text der Folie" in call["messages"][0]["content"]
    assert client.post("/api/foto/kandidaten", json={"bild_ids": ids, "bereich": "Beruf", "text": ""}).status_code == 422


def test_kandidaten_bild_weg(env):
    client, claude, _ = env
    ids = hochladen(client, folie_jpeg(), folie_jpeg())
    client.post("/api/foto/kandidaten", json={"bild_ids": ids, "bereich": "Immobilien", "notiz": "Kauf 2024"})
    bloecke = bild_inhalte(claude.calls[-1])
    assert len(bloecke) == 2 and bloecke[0]["source"]["media_type"] == "image/jpeg"


def test_kandidaten_lokal_409(env):
    client, claude, _ = env
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}})
    ids = hochladen(client)
    assert client.post("/api/foto/kandidaten", json={"bild_ids": ids, "bereich": "Beruf", "text": "x y z"}).status_code == 409
    assert claude.calls == []


def test_lesson_mit_fotos_und_aufraeumen(env):
    client, _, app = env
    ids = hochladen(client, folie_jpeg(), folie_jpeg())
    a = client.post("/api/lessons", json=lesson_json(bild_ids=ids)).json()["lesson"]
    b = client.post("/api/lessons", json=lesson_json(bild_ids=[ids[0]])).json()["lesson"]  # eine Folie, zwei Lessons
    assert len(client.get(f"/api/lessons/{a['id']}").json()["bilder"]) == 2
    assert client.delete(f"/api/lessons/{a['id']}/bilder/{ids[1]}").status_code == 204
    assert [x["id"] for x in client.get(f"/api/lessons/{a['id']}").json()["bilder"]] == [ids[0]]
    assert client.post(f"/api/lessons/{b['id']}/bilder", json={"bild_ids": [ids[1]]}).status_code == 200
    assert client.post("/api/lessons", json=lesson_json(bild_ids=["00000000-0000-0000-0000-000000000000"])).status_code == 404

    # Lesson löschen: Foto hängt noch an b, bleibt; verwaistes Foto wird nach Frist gelöscht
    client.delete(f"/api/lessons/{a['id']}")
    verwaist = hochladen(client)[0]
    repo = app.state.repo
    repo.conn.execute("UPDATE bilder SET erstellt_am = '2000-01-01T00:00:00+00:00' WHERE id = ?", (verwaist,))
    assert app.state.bilder_aufraeumen() == 1
    assert client.get(f"/api/bilder/{verwaist}").status_code == 404
    assert client.get(f"/api/bilder/{ids[0]}").status_code == 200
    assert not app.state.speicher.pfad(verwaist).exists()


def test_bestaetigen_haengt_foto_an(env):
    client, *_ = env
    lid = client.post("/api/lessons", json=lesson_json()).json()["lesson"]["id"]
    ids = hochladen(client)
    client.post(f"/api/lessons/{lid}/bestaetigen", json={"notiz": "von Folie", "bild_ids": ids})
    assert len(client.get(f"/api/lessons/{lid}").json()["bilder"]) == 1


def test_entwurf_traegt_fotos_zur_lesson(tmp_path, monkeypatch):
    from lessons_vault.structuring import OllamaStrukturierer

    from .ollama_mock import OllamaMock
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": True, "modelle": ["qwen2.5:7b"]})
    app = create_app(Settings(db_path=tmp_path / "t.db", anthropic_api_key="", ollama_model="qwen2.5:7b"), Strukturierer(None, "m"),
                     HashingProvider(), OllamaStrukturierer("http://o", "qwen2.5:7b", client=OllamaMock().client()))
    client = TestClient(app)
    ids = hochladen(client)
    eid = client.post("/api/erfassen", json={"text": "Folie Welle 3", "bild_ids": ids}).json()["eintrag"]["id"]
    assert len(client.get(f"/api/entwuerfe/{eid}").json()["bilder"]) == 1
    app.state.worker.verarbeite_naechsten()
    lid = client.post("/api/lessons", json=lesson_json(entwurf_id=eid)).json()["lesson"]["id"]
    assert len(client.get(f"/api/lessons/{lid}").json()["bilder"]) == 1


@braucht_ocr
def test_entwurf_pruefen_text_weg(env):
    client, claude, _ = env
    client.post("/api/lessons", json=lesson_json(titel="Schichtleiter vor Cutover bestätigen", bereich="Beruf",
                                                 lesson="Vor jedem Cutover die Schichtleiter schriftlich bestätigen lassen."))
    ids = hochladen(client)
    data = client.post("/api/briefing", json={"bild_ids": ids, "bereich": "Beruf", "entwurf_text": "Geprüfter Plantext Cutover Schichtleiter"}).json()
    assert data["entwurf_weg"] == "text" and data["situation"] == "Entwurf prüfen (1 Foto)"
    assert data["treffer"] and data["treffer"][0]["lesson"]["titel"].startswith("Schichtleiter")
    assert len(data["bilder"]) == 1 and data["ki_moeglich"]
    r = client.post(f"/api/briefing/{data['id']}/zusammenfassung").json()
    call = claude.calls[-1]
    assert call["system"] == ABGLEICH_PROMPT and bild_inhalte(call) == []
    assert "<entwurf>\nGeprüfter Plantext" in call["messages"][0]["content"]
    assert r["zusammenfassung"] == "Im Plan fehlt die Personalplanung."
    assert r["ki_checkliste"][0]["punkt"] == "Schichtleiter schriftlich bestätigen lassen"
    assert r["abgleich"]["beruecksichtigt"][0]["punkt"] == "Cutover-Termin steht"


@braucht_ocr
def test_entwurf_pruefen_bild_und_lokal(env):
    client, claude, _ = env
    client.post("/api/lessons", json=lesson_json(titel="Schichtleiter einplanen", lesson="Schichtleiter früh einplanen."))
    ids = hochladen(client)
    data = client.post("/api/briefing", json={"bild_ids": ids, "bereich": "Immobilien", "situation": "Umzugsplanung"}).json()
    assert data["entwurf_weg"] == "bild" and "Schichtleiter" in data["entwurf_text"]
    client.post(f"/api/briefing/{data['id']}/zusammenfassung")
    assert len(bild_inhalte(claude.calls[-1])) == 1

    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Immobilien": "lokal"}})
    anzahl = len(claude.calls)
    lokal = client.post("/api/briefing", json={"bild_ids": ids, "bereich": "Immobilien"}).json()
    assert lokal["ki_moeglich"] is False
    assert client.post(f"/api/briefing/{lokal['id']}/zusammenfassung").status_code == 409
    assert len(claude.calls) == anzahl


def test_text_weg_ohne_geprueften_text_kein_claude(env):
    client, *_ = env
    client.post("/api/lessons", json=lesson_json())
    ids = hochladen(client)
    data = client.post("/api/briefing", json={"bild_ids": ids, "situation": "Bankgespräch"}).json()
    assert data["entwurf_weg"] == "text" and data["ki_moeglich"] is False


def test_bild_braucht_token(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    app = create_app(Settings(db_path=tmp_path / "t.db", token="geheim", anthropic_api_key="", ollama_model=""), Strukturierer(None, "m"), HashingProvider())
    client = TestClient(app)
    h = {"Authorization": "Bearer geheim"}
    bid = client.post("/api/bilder", files=[("dateien", ("f.jpg", folie_jpeg(), "image/jpeg"))], headers=h).json()[0]["id"]
    assert client.get(f"/api/bilder/{bid}").status_code == 401
    assert client.get(f"/api/bilder/{bid}", headers=h).status_code == 200
