import numpy as np
import pytest
from fastapi.testclient import TestClient

from lessons_vault import main
from lessons_vault.briefing import BRIEFING_PROMPT, KOMBI_PROMPT, faktor_bestaetigung, faktor_feedback, faktor_schwere, kombi_auswerten
from lessons_vault.config import Settings
from lessons_vault.embeddings import HashingProvider
from lessons_vault.main import create_app
from lessons_vault.structuring import Strukturierer

from .test_api import lesson_json
from .test_structuring import FakeClient, payload


KOMBI_ANTWORT = {
    "zusammenfassung": "Hypercare steht und fällt mit klaren Eskalationswegen.",
    "abschnitte": [
        {"titel": "Vorbereitung", "punkte": [
            {"punkt": "Hypercare-Team und Eskalationsstufen festlegen", "quelle": "allgemein", "lesson_nr": 0},
            {"punkt": "Schichtleiter für die ersten zwei Wochen schriftlich einplanen", "quelle": "erfahrung", "lesson_nr": 1},
        ]},
        {"titel": "Betrieb", "punkte": [
            {"punkt": "Tägliches Hypercare-Meeting", "quelle": "allgemein", "lesson_nr": 0},
            {"punkt": "Behauptete Erfahrung ohne Lesson", "quelle": "erfahrung", "lesson_nr": 0},
        ]},
        {"titel": "Leer", "punkte": []},
    ],
    "besonderheiten": [
        {"punkt": "Bei dir fehlte das Personal, nicht die Technik: Personal früher bestätigen als üblich", "lesson_nr": 1},
        {"punkt": "ohne Bezug", "lesson_nr": 0},
    ],
}


def antwort(kwargs):
    """Fake-Claude: Briefing-Aufrufe bekommen eine Zusammenfassung, alles andere einen Lesson-Entwurf."""
    if kwargs["system"] == KOMBI_PROMPT:
        return KOMBI_ANTWORT
    if kwargs["system"] == BRIEFING_PROMPT:
        return {
            "zusammenfassung": "Plane die Personalfreigabe früh.",
            "checkliste": [{"punkt": "Schichtleiter schriftlich bestätigen", "lesson_nr": 1}, {"punkt": "", "lesson_nr": 2}],
        }
    return payload()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    claude = FakeClient(antwort)
    settings = Settings(db_path=tmp_path / "t.db", anthropic_api_key="", voyage_api_key="", ollama_model="")
    app = create_app(settings, Strukturierer(claude, "claude-opus-5-5"), HashingProvider())
    client = TestClient(app)

    def add(**kw):
        return client.post("/api/lessons", json=lesson_json(**kw)).json()["lesson"]

    return client, claude, add


def test_faktoren():
    assert faktor_schwere(1) == pytest.approx(0.6) and faktor_schwere(5) == pytest.approx(1.0)
    assert faktor_bestaetigung(1) == 1.0 and faktor_bestaetigung(3) == pytest.approx(1.3) and faktor_bestaetigung(20) == pytest.approx(1.6)
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert faktor_feedback("x", [("x", "nicht_relevant", a)], a) == pytest.approx(0.7)
    assert faktor_feedback("x", [("x", "nicht_relevant", b)], a) == pytest.approx(1.0)  # andere Situation zählt nicht
    assert faktor_feedback("x", [("x", "hilfreich", None)], a) == pytest.approx(1.15)
    assert faktor_feedback("x", [("x", "nicht_relevant", a)] * 10, a) == pytest.approx(0.3)


def test_ranking_schwere_und_bestaetigung(env):
    client, _, add = env
    gleich = dict(situation="Projektplanung für eine Rollout-Welle.", ereignis="Zeitplan zu knapp.", bereich="Beruf",
                  lesson="Bei der Projektplanung Puffer für den Cutover einplanen.")
    leicht = add(titel="Projektplanung Puffer A", schweregrad=1, **gleich)
    schwer = add(titel="Projektplanung Puffer B", schweregrad=5, **gleich)
    oft = add(titel="Projektplanung Puffer C", schweregrad=1, **gleich)
    for _ in range(3):
        client.post(f"/api/lessons/{oft['id']}/bestaetigen", json={})
    weg = add(titel="Projektplanung Puffer D", schweregrad=5, **gleich)
    client.put(f"/api/lessons/{weg['id']}", json={"status": "überholt"})

    data = client.post("/api/briefing", json={"situation": "Projektplanung für Rollout Welle 4 schreiben", "modus": "eigen"}).json()
    ids = [t["lesson"]["id"] for t in data["treffer"]]
    assert weg["id"] not in ids
    assert ids.index(schwer["id"]) < ids.index(leicht["id"])
    assert ids.index(oft["id"]) < ids.index(leicht["id"])
    assert len(ids) <= 5
    assert data["checkliste"][0]["punkt"]
    assert data["ki_moeglich"] is True


def test_max_fuenf_und_bereichsfilter(env):
    client, _, add = env
    for i in range(7):
        add(titel=f"Bankgespräch Unterlagen {i}", lesson="Vor dem Bankgespräch Unterlagen prüfen.")
    add(titel="Bankgespräch im Beruf", bereich="Beruf", lesson="Bankgespräch vorbereiten.")
    data = client.post("/api/briefing", json={"situation": "Bankgespräch nächste Woche", "modus": "eigen"}).json()
    assert len(data["treffer"]) == 5
    data = client.post("/api/briefing", json={"situation": "Bankgespräch nächste Woche", "bereich": "Beruf", "modus": "eigen"}).json()
    assert [t["lesson"]["bereich"] for t in data["treffer"]] == ["Beruf"]


def test_nichts_passendes(env):
    client, _, add = env
    add(titel="Notar früh terminieren", lesson="Notartermin früh fixieren.", situation="Kauf.", ereignis="Termin zu spät.", tags=["Notar"])
    data = client.post("/api/briefing", json={"situation": "xyzqq vvvvv", "modus": "eigen"}).json()
    assert data["treffer"] == [] and data["ki_moeglich"] is False


def test_zusammenfassung(env):
    client, claude, add = env
    l1 = add(titel="Cutover Personal bestätigen", bereich="Beruf", lesson="Vor jedem Cutover Personal bestätigen.")
    bid = client.post("/api/briefing", json={"situation": "Cutover planen", "modus": "eigen"}).json()["id"]
    data = client.post(f"/api/briefing/{bid}/zusammenfassung").json()
    assert data["zusammenfassung"] == "Plane die Personalfreigabe früh."
    assert data["ki_checkliste"] == [{"punkt": "Schichtleiter schriftlich bestätigen", "lesson_id": l1["id"]}]
    call = claude.calls[-1]
    assert call["output_config"]["format"]["schema"]["properties"]["checkliste"]["items"]["properties"]["lesson_nr"]["enum"] == [1]
    assert "<situation>\nCutover planen\n</situation>" in call["messages"][0]["content"]
    # Zweiter Aufruf nutzt den gespeicherten Text, kein neuer API-Call
    anzahl = len(claude.calls)
    assert client.post(f"/api/briefing/{bid}/zusammenfassung").json()["zusammenfassung"]
    assert len(claude.calls) == anzahl
    client.post(f"/api/briefing/{bid}/zusammenfassung", params={"neu": True})
    assert len(claude.calls) == anzahl + 1
    # gespeichertes Briefing wieder abrufbar
    assert client.get(f"/api/briefing/{bid}").json()["zusammenfassung"]


def test_lokale_bereiche_nicht_an_claude(env):
    client, claude, add = env
    add(titel="Geheim Cutover Beruf", bereich="Beruf", lesson="Cutover Personal bestätigen.")
    add(titel="Cutover privat Umzug", bereich="Immobilien", lesson="Beim Umzug Cutover der Versorger planen.")
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}})
    data = client.post("/api/briefing", json={"situation": "Cutover planen", "modus": "eigen"}).json()
    assert len(data["treffer"]) == 2 and "lokalen Bereichen" in data["ki_hinweis"]
    client.post(f"/api/briefing/{data['id']}/zusammenfassung")
    prompt = claude.calls[-1]["messages"][0]["content"]
    assert "Umzug" in prompt and "Geheim" not in prompt

    nur_beruf = client.post("/api/briefing", json={"situation": "Cutover planen", "bereich": "Beruf", "modus": "eigen"}).json()
    assert nur_beruf["ki_moeglich"] is False
    assert client.post(f"/api/briefing/{nur_beruf['id']}/zusammenfassung").status_code == 409


def test_ohne_claude(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    app = create_app(Settings(db_path=tmp_path / "t.db", anthropic_api_key="", ollama_model=""), Strukturierer(None, "m"), HashingProvider())
    client = TestClient(app)
    client.post("/api/lessons", json=lesson_json())
    data = client.post("/api/briefing", json={"situation": "Bankgespräch", "modus": "eigen"}).json()
    assert data["treffer"] and data["ki_moeglich"] is False and "ANTHROPIC_API_KEY" in data["ki_hinweis"]


def test_claude_fehler_502(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    app = create_app(Settings(db_path=tmp_path / "t.db", anthropic_api_key="", ollama_model=""),
                     Strukturierer(FakeClient(payload(), stop_reason="refusal"), "m"), HashingProvider())
    client = TestClient(app)
    client.post("/api/lessons", json=lesson_json())
    bid = client.post("/api/briefing", json={"situation": "Bankgespräch", "modus": "eigen"}).json()["id"]
    r = client.post(f"/api/briefing/{bid}/zusammenfassung")
    assert r.status_code == 502 and "abgelehnt" in r.json()["detail"]


def test_feedback_verschiebt_ranking(env):
    client, _, add = env
    gleich = dict(situation="Besichtigung einer Wohnung.", ereignis="Mangel übersehen.", bereich="Immobilien", schweregrad=3)
    a = add(titel="Besichtigung Keller prüfen", lesson="Bei jeder Besichtigung den Keller auf Feuchtigkeit prüfen.", **gleich)
    b = add(titel="Besichtigung Dach prüfen", lesson="Bei jeder Besichtigung das Dach auf Schäden prüfen.", **gleich)
    situation = "Besichtigung Wohnung morgen"
    erstes = client.post("/api/briefing", json={"situation": situation, "modus": "eigen"}).json()
    oben = erstes["treffer"][0]["lesson"]["id"]
    unten = b["id"] if oben == a["id"] else a["id"]
    assert client.post(f"/api/briefing/{erstes['id']}/feedback", json={"lesson_id": oben, "bewertung": "nicht_relevant"}).json() == {oben: "nicht_relevant"}
    client.post(f"/api/briefing/{erstes['id']}/feedback", json={"lesson_id": unten, "bewertung": "hilfreich"})
    zweites = client.post("/api/briefing", json={"situation": situation, "modus": "eigen"}).json()
    assert zweites["treffer"][0]["lesson"]["id"] == unten
    assert zweites["treffer"][1]["faktoren"]["feedback"] < 1.0

    # Feedback zurücknehmen
    assert client.post(f"/api/briefing/{erstes['id']}/feedback", json={"lesson_id": oben, "bewertung": ""}).json() == {unten: "hilfreich"}
    stat = client.get("/api/statistik").json()
    assert stat["briefings"] == 2 and stat["briefings_hilfreich"] == 1 and stat["briefings_bewertet"] == 1
    verlauf = client.get("/api/briefings").json()
    assert verlauf[0]["situation"] == situation and verlauf[1]["hilfreich"] == 1
    assert client.delete(f"/api/briefing/{erstes['id']}").status_code == 204
    assert client.get(f"/api/briefing/{erstes['id']}").status_code == 404


def test_geloeschte_lesson_im_alten_briefing(env):
    client, _, add = env
    l = add(titel="Bankgespräch vorbereiten")
    bid = client.post("/api/briefing", json={"situation": "Bankgespräch", "modus": "eigen"}).json()["id"]
    client.delete(f"/api/lessons/{l['id']}")
    assert client.get(f"/api/briefing/{bid}").json()["treffer"] == []


def test_kombi_auswerten_sichert_quellen():
    from lessons_vault.models import Lesson
    l = Lesson(id="L1", titel="t", situation="s", ereignis="e", lesson="r", bereich="Beruf", schweregrad=3,
               status="neu", bestaetigungen=1, erstellt_am="x", geaendert_am="x", quelle="text")
    plan = kombi_auswerten(KOMBI_ANTWORT, [l])
    punkte = [p for a in plan["abschnitte"] for p in a["punkte"]]
    assert [a["titel"] for a in plan["abschnitte"]] == ["Vorbereitung", "Betrieb"]  # leere Abschnitte fallen weg
    assert punkte[1] == {"punkt": "Schichtleiter für die ersten zwei Wochen schriftlich einplanen", "quelle": "erfahrung", "lesson_id": "L1"}
    # "erfahrung" ohne gültige Lesson wird nie als eigene Erfahrung ausgewiesen
    assert punkte[3]["quelle"] == "allgemein" and punkte[3]["lesson_id"] is None
    assert plan["punkte_erfahrung"] == 1 and plan["punkte_gesamt"] == 4
    assert plan["besonderheiten"] == [{"punkt": KOMBI_ANTWORT["besonderheiten"][0]["punkt"], "lesson_id": "L1"}]


def test_kombiniert_ist_standard(env):
    client, claude, add = env
    l1 = add(titel="Schichtleiter in der Hypercare einplanen", bereich="Beruf",
             lesson="In der Hypercare die Schichtleiter für zwei Wochen schriftlich einplanen.")
    data = client.post("/api/briefing", json={"situation": "Plan für die Hypercare-Phase eines SAP-EWM-Projekts"}).json()
    assert data["modus"] == "kombiniert" and data["ki_moeglich"]
    r = client.post(f"/api/briefing/{data['id']}/zusammenfassung").json()
    call = claude.calls[-1]
    assert call["system"] == KOMBI_PROMPT
    assert call["output_config"]["effort"] == "medium" and call["max_tokens"] == 16000
    assert call["output_config"]["format"]["schema"]["properties"]["abschnitte"]["items"]["properties"]["punkte"]["items"]["properties"]["lesson_nr"]["enum"] == [0, 1]
    assert r["plan"]["abschnitte"][0]["punkte"][1]["lesson_id"] == l1["id"]
    assert r["zusammenfassung"].startswith("Hypercare")
    assert {p["quelle"] for p in r["ki_checkliste"]} == {"erfahrung", "allgemein"}
    stat = client.get("/api/statistik").json()
    assert stat["plan_punkte_erfahrung"] == 1 and stat["plan_punkte_gesamt"] == 4


def test_kombiniert_ohne_eigene_lessons(env):
    client, claude, _ = env
    data = client.post("/api/briefing", json={"situation": "Hypercare planen"}).json()
    assert data["treffer"] == [] and data["ki_moeglich"] is True
    client.post(f"/api/briefing/{data['id']}/zusammenfassung")
    assert "keine passenden vorhanden" in claude.calls[-1]["messages"][0]["content"]
    eigen = client.post("/api/briefing", json={"situation": "Hypercare planen", "modus": "eigen"}).json()
    assert eigen["ki_moeglich"] is False


def test_moduswechsel(env):
    client, claude, add = env
    add(titel="Hypercare Schichtleiter", lesson="In der Hypercare Schichtleiter einplanen.")
    bid = client.post("/api/briefing", json={"situation": "Hypercare planen"}).json()["id"]
    r = client.post(f"/api/briefing/{bid}/zusammenfassung").json()
    assert r["plan"] is not None
    r = client.post(f"/api/briefing/{bid}/zusammenfassung", params={"modus": "eigen"}).json()
    assert r["modus"] == "eigen" and r["plan"] is None and claude.calls[-1]["system"] == BRIEFING_PROMPT
    anzahl = len(claude.calls)
    client.post(f"/api/briefing/{bid}/zusammenfassung", params={"modus": "eigen"})  # gleicher Modus: gespeichert
    assert len(claude.calls) == anzahl
    assert client.post(f"/api/briefing/{bid}/zusammenfassung", params={"modus": "quatsch"}).status_code == 422


def test_kombiniert_lokal_bereich_nicht_an_claude(env):
    client, claude, add = env
    add(titel="Geheim Hypercare Beruf", bereich="Beruf", lesson="Hypercare Personal bestätigen.")
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}})
    data = client.post("/api/briefing", json={"situation": "Hypercare planen"}).json()
    client.post(f"/api/briefing/{data['id']}/zusammenfassung")
    assert "Geheim" not in claude.calls[-1]["messages"][0]["content"]
    nur_beruf = client.post("/api/briefing", json={"situation": "Hypercare planen", "bereich": "Beruf"}).json()
    assert nur_beruf["ki_moeglich"] is False
