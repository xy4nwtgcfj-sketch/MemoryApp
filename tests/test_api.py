import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lessons_vault.config import Settings
from lessons_vault.embeddings import HashingProvider
from lessons_vault.main import create_app
from lessons_vault.structuring import Strukturierer

from .test_structuring import FakeClient, payload

ROOT = Path(__file__).resolve().parents[1]


def lesson_json(**kw):
    data = dict(
        titel="Unterlagen vor Bankgespräch", situation="Finanzierung Wohnung.", ereignis="Nachweise fehlten.",
        lesson="Vor jedem Bankgespräch Unterlagenliste anfordern.", massnahme="", bereich="Immobilien",
        tags=["Bank"], schweregrad=2, quelle="text", erfassung_sekunden=21.5,
    )
    data.update(kw)
    return data


def make_client(tmp_path, token="", fake=None):
    settings = Settings(db_path=tmp_path / "t.db", token=token, anthropic_api_key="", voyage_api_key="", ollama_model="")
    app = create_app(settings, Strukturierer(fake, "claude-opus-5-5"), HashingProvider())
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    return make_client(tmp_path)


def test_status_ohne_ki(client):
    data = client.get("/api/status").json()
    assert data["ki"] is False and data["embeddings"] == "lokal-hashing-v1"


def test_crud_und_bestaetigen(client):
    r = client.post("/api/lessons", json=lesson_json())
    assert r.status_code == 201, r.text
    lid = r.json()["lesson"]["id"]
    assert r.json()["lesson"]["embedding_modell"] == "lokal-hashing-v1"
    r = client.put(f"/api/lessons/{lid}", json={"massnahme": "Checkliste"})
    assert r.json()["lesson"]["massnahme"] == "Checkliste"
    r = client.post(f"/api/lessons/{lid}/bestaetigen", json={"notiz": "wieder passiert"})
    assert r.json()["status"] == "bestätigt"
    detail = client.get(f"/api/lessons/{lid}").json()
    assert len(detail["protokoll"]) == 2
    assert client.delete(f"/api/lessons/{lid}").status_code == 204
    assert client.get(f"/api/lessons/{lid}").status_code == 404


def test_validierung(client):
    assert client.post("/api/lessons", json=lesson_json(titel="x" * 81)).status_code == 422
    assert client.post("/api/lessons", json=lesson_json(bereich="Nope")).status_code == 422
    assert client.post("/api/lessons", json=lesson_json(schweregrad=6)).status_code == 422


def test_compliance_beim_speichern(client):
    r = client.post("/api/lessons", json=lesson_json(bereich="Beruf", situation="Bei Kunde Müller GmbH."))
    assert any("Firmenname" in h for h in r.json()["compliance_hinweise"])


def test_suche_endpunkt(client):
    client.post("/api/lessons", json=lesson_json(titel="Finanzierungsbankgespräch"))
    client.post("/api/lessons", json=lesson_json(titel="Cutover planen", bereich="Beruf", lesson="Cutover früh planen."))
    treffer = client.get("/api/suche", params={"q": "Bank"}).json()
    assert treffer[0]["lesson"]["titel"] == "Finanzierungsbankgespräch"
    assert client.get("/api/suche", params={"q": "", "bereich": "Beruf"}).json()[0]["lesson"]["bereich"] == "Beruf"
    assert client.get("/api/suche", params={"modus": "falsch"}).status_code == 422


def test_entwurf_ohne_ki_mit_dublette(client):
    client.post("/api/lessons", json=lesson_json())
    r = client.post("/api/erfassen/entwurf", json={"text": "Unterlagen vor Bankgespräch", "quelle": "text"})
    data = r.json()
    assert data["ki_verwendet"] is False
    assert data["dublette"] is not None
    assert "lesson" in data["fehlende_felder"]


def test_entwurf_mit_ki(tmp_path):
    fake = FakeClient(payload(situation="Bei Kunde Brenntag im Lager."))
    client = make_client(tmp_path, fake=fake)
    data = client.post("/api/erfassen/entwurf", json={"text": "Bank Unterlagen vergessen", "quelle": "sprache"}).json()
    assert data["ki_verwendet"] is True and data["quelle"] == "sprache"
    assert data["bereich"] == "Immobilien"
    assert any("Brenntag" in h for h in data["compliance_hinweise"])
    schema = fake.calls[0]["output_config"]["format"]["schema"]
    assert schema["properties"]["bereich"]["enum"] == ["Beruf", "Immobilien"]


def test_sperrliste(client):
    client.put("/api/einstellungen", json={"sperrliste": ["Acme", " ", "acme2"]})
    assert client.get("/api/einstellungen").json()["sperrliste"] == ["Acme", "acme2"]
    data = client.post("/api/erfassen/entwurf", json={"text": "Probleme bei ACME"}).json()
    assert any("Sperrliste" in h for h in data["compliance_hinweise"])


def test_bereiche(client):
    assert client.post("/api/bereiche", json={"name": "Gesundheit"}).status_code == 201
    assert client.post("/api/bereiche", json={"name": "Gesundheit"}).status_code == 422
    assert client.patch("/api/bereiche/Trading", json={"aktiv": True}).json()["aktiv"] is True
    assert client.patch("/api/bereiche/Nope", json={"aktiv": True}).status_code == 404


def test_import_export_roundtrip(client, tmp_path):
    vorlage = json.loads((ROOT / "startbestand" / "vorlage.json").read_text(encoding="utf-8"))
    r = client.post("/api/import", json=vorlage).json()
    assert r == {"importiert": 3, "uebersprungen": 0, "fehler": []}
    export = client.get("/api/export").json()
    assert len(export["lessons"]) == 3
    assert any(l["status"] == "bestätigt" for l in export["lessons"])

    other = make_client(tmp_path / "zwei")
    assert other.post("/api/import", json=export).json()["importiert"] == 3
    assert other.post("/api/import", json=export).json()["uebersprungen"] == 3
    ids = sorted(l["id"] for l in other.get("/api/export").json()["lessons"])
    assert ids == sorted(l["id"] for l in export["lessons"])


def test_import_fehler(client):
    r = client.post("/api/import", json=[{"titel": "x"}, lesson_json(bereich="Unbekannt")]).json()
    assert r["importiert"] == 0 and len(r["fehler"]) == 2


def test_reindex_und_statistik(client):
    client.post("/api/lessons", json=lesson_json())
    assert client.post("/api/reindex").json()["neu_indexiert"] == 1
    stat = client.get("/api/statistik").json()
    assert stat["gesamt"] == 1 and stat["erfassungen_unter_30s"] == 1


def test_token(tmp_path):
    client = make_client(tmp_path, token="geheim")
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers={"Authorization": "Bearer falsch"}).status_code == 401
    assert client.get("/api/status", headers={"Authorization": "Bearer geheim"}).status_code == 200
    assert client.get("/").status_code == 200  # App-Shell bleibt ladbar


def test_compliance_endpunkt(client):
    r = client.post("/api/compliance", json={"text": "Herr Meier war sauer", "bereich": ""})
    assert any("Personenname" in h for h in r.json())



def test_spezifisch_speichern_und_statistik(client):
    a = client.post("/api/lessons", json=lesson_json(spezifisch=True)).json()["lesson"]
    client.post("/api/lessons", json=lesson_json(spezifisch=False))
    client.post("/api/lessons", json=lesson_json())
    assert a["spezifisch"] is True
    stat = client.get("/api/statistik").json()
    assert stat["lessons_eingeschaetzt"] == 2 and stat["lessons_persoenlich"] == 1
    r = client.put(f"/api/lessons/{a['id']}", json={"spezifisch": False}).json()
    assert r["lesson"]["spezifisch"] is False
    export = client.get("/api/export").json()
    assert sorted(str(l["spezifisch"]) for l in export["lessons"]) == ["False", "False", "None"]
