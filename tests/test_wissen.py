"""Wissensnetz: Verbindungen, Themenseiten, Pflege, Wiederholen, Dialog-Antworten merken und MCP."""

import re
import time
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from lessons_vault import main
from lessons_vault.briefing import DIALOG_PROMPT, KOMBI_PROMPT
from lessons_vault.config import Settings
from lessons_vault.embeddings import HashingProvider
from lessons_vault.main import create_app
from lessons_vault.models import DublettenKandidat
from lessons_vault.repository import INTERVALLE
from lessons_vault.structuring import SYSTEM_PROMPT, Strukturierer, beziehungen_auswerten
from lessons_vault.wissen import PFLEGE_PROMPT, SEITE_PROMPT, ZUORDNEN_PROMPT, Wissenspflege

from .conftest import beispiel
from .test_api import lesson_json
from .test_briefing import KOMBI_ANTWORT
from .test_structuring import FakeClient, payload


def _anzahl(kwargs, *pfad):
    schema = kwargs["output_config"]["format"]["schema"]
    for schritt in pfad:
        schema = schema[schritt]
    return len(schema["enum"])


def fake_antwort(kwargs, beziehung_zu=None):
    system = kwargs["system"]
    if system == ZUORDNEN_PROMPT:
        n = _anzahl(kwargs, "properties", "zuordnungen", "items", "properties", "nr")
        bestehend = re.findall(r'"id": "([\w-]+)"', kwargs["messages"][0]["content"])
        if bestehend:  # wie verlangt: bestehende Themen bevorzugen
            return {"neue_themen": [], "zuordnungen": [{"nr": i, "themen": [bestehend[0]]} for i in range(1, n + 1)]}
        return {"neue_themen": [{"schluessel": "n1", "titel": "Financing and Banks", "beschreibung": "Bank talks."},
                                {"schluessel": "n2", "titel": "Unused", "beschreibung": "Bekommt keine Einträge."}],
                "zuordnungen": [{"nr": i, "themen": ["n1", "gibtsnicht"]} for i in range(1, n + 1)]}
    if system == SEITE_PROMPT:
        return {"titel": "Financing", "zusammenfassung": "Prepare documents early.",
                "kernaussagen": [{"text": "Ask for the bank's document list first.", "quellen": [1, 99]},
                                 {"text": "Ohne Quelle fällt weg", "quellen": []}],
                "bewaehrt": [], "fallstricke": [{"text": "Missing pay slips", "quellen": [1]}],
                "widersprueche": [], "offene_fragen": ["How early to start?"]}
    if system == PFLEGE_PROMPT:
        return {"befunde": [
            {"art": "widerspruch", "titel": "Two rules disagree", "hinweis": "A says X, B says Y.", "vorschlag": "Decide.", "nrs": [1, 2]},
            {"art": "widerspruch", "titel": "Nur ein Eintrag", "hinweis": "", "vorschlag": "", "nrs": [1]},
            {"art": "luecke", "titel": "No entry on notary", "hinweis": "Nothing on notary.", "vorschlag": "Add one.", "nrs": []},
        ]}
    if system == DIALOG_PROMPT:
        return {"antwort": "- Agree pickup windows [E1].", "anpassung_sinnvoll": False, "anpassung_hinweis": ""}
    if system == KOMBI_PROMPT:
        return KOMBI_ANTWORT
    if system == SYSTEM_PROMPT and beziehung_zu:
        return payload(beziehungen=[{"id": beziehung_zu(), "art": "ergaenzt", "begruendung": "Adds the timing."},
                                    {"id": "fremd", "art": "ergaenzt", "begruendung": "unbekannt"}])
    return payload()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    ziel = {"id": ""}
    claude = FakeClient(lambda kw: fake_antwort(kw, beziehung_zu=(lambda: ziel["id"]) if ziel["id"] else None))
    settings = Settings(db_path=tmp_path / "t.db", anthropic_api_key="", voyage_api_key="", ollama_model="", worker_aktiv=False)
    app = create_app(settings, Strukturierer(claude, "claude-opus-5-5"), HashingProvider())
    client = TestClient(app)

    def add(**kw):
        return client.post("/api/lessons", json=lesson_json(**kw)).json()["lesson"]

    return client, claude, add, ziel, app


# ---------------------------------------------------------------- Repository
def test_beziehungen_im_repository(repo):
    a = repo.anlegen(beispiel(titel="A"))
    b = repo.anlegen(beispiel(titel="B"))
    c = repo.anlegen(beispiel(titel="C"))
    assert repo.beziehung_setzen(a.id, b.id, "ergaenzt", "detail")
    assert not repo.beziehung_setzen(b.id, a.id, "widerspricht")  # Gegenrichtung gibt es schon
    assert not repo.beziehung_setzen(a.id, a.id, "ergaenzt")
    assert repo.beziehung_setzen(c.id, a.id, "widerspricht")
    sicht = repo.beziehungen_von(a.id)
    assert {(x["id"], x["art"], x["richtung"]) for x in sicht} == {(b.id, "ergaenzt", "aus"), (c.id, "widerspricht", "ein")}
    # Graph-Erweiterung: Widerspruch zuerst, überholte nie
    assert [l.id for l in repo.verbundene([a.id])] == [c.id, b.id]
    repo.aendern(c.id, __import__("lessons_vault.models", fromlist=["LessonUpdate"]).LessonUpdate(status="überholt"))
    assert [l.id for l in repo.verbundene([a.id])] == [b.id]
    repo.beziehung_loeschen(b.id, a.id)  # Richtung egal
    repo.loeschen(c.id)  # Kaskade
    assert repo.beziehungen_von(a.id) == []


def test_wiederholung_mit_wachsenden_abstaenden(repo, conn):
    alt = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    ids = []
    for i in range(3):
        l = repo.anlegen(beispiel(titel=f"Eintrag {i}"))
        conn.execute("UPDATE lessons SET erstellt_am = ? WHERE id = ?", (alt, l.id))
        ids.append(l.id)
    heute = date.today().isoformat()
    erster = repo.wiedersehen(heute)
    assert erster and erster.id in ids
    r = repo.wiederholung_eintragen(erster.id, "parat", heute)
    assert r["stufe"] == 1 and r["tage"] == INTERVALLE[1]
    assert repo.wiedersehen(heute).id != erster.id  # nicht fällig, also ein anderer
    # Vergessen: Stufe 0, bald wieder fällig; nach Fälligkeit kommt er vor allen neuen
    repo.wiederholung_eintragen(erster.id, "vergessen", heute)
    spaeter = (date.today() + timedelta(days=INTERVALLE[0])).isoformat()
    assert repo.wiedersehen(spaeter).id == erster.id
    stand = repo.wiederholung_stand(spaeter)
    assert stand["faellig"] == 1 and stand["im_kreislauf"] == 1
    for _ in range(10):
        r = repo.wiederholung_eintragen(erster.id, "parat", heute)
    assert r["stufe"] == len(INTERVALLE) - 1


def test_themen_werden_veraltet_wenn_eintraege_sich_aendern(repo):
    from lessons_vault.models import LessonUpdate
    a = repo.anlegen(beispiel(titel="A"))
    thema = repo.thema_anlegen("Financing", "Immobilien")
    repo.thema_zuordnen(thema, [a.id, "gibtsnicht"])
    repo.thema_seite_setzen(thema, {"zusammenfassung": "x"})
    assert repo.themen()[0]["veraltet"] is False and repo.themen()[0]["anzahl"] == 1
    repo.aendern(a.id, LessonUpdate(lesson="Neue Kernaussage."))
    assert repo.themen()[0]["veraltet"] is True
    repo.thema_seite_setzen(thema, {"zusammenfassung": "x"})
    repo.loeschen(a.id)
    assert repo.themen()[0]["veraltet"] is True
    assert repo.leere_themen_entfernen() == 1 and repo.themen() == []


def test_pflege_kommt_nicht_doppelt(repo):
    a = repo.anlegen(beispiel(titel="A"))
    b = repo.anlegen(beispiel(titel="B"))
    assert repo.pflege_anlegen("doppelt", "Same", "h", "v", [a.id, b.id])
    assert not repo.pflege_anlegen("doppelt", "Same again", "h", "v", [b.id, a.id])
    punkt = repo.pflege_liste()[0]
    assert {l["id"] for l in punkt["lessons"]} == {a.id, b.id}
    repo.pflege_status(punkt["id"], "ignoriert")
    assert repo.pflege_liste() == [] and not repo.pflege_anlegen("doppelt", "x", "", "", [a.id, b.id])


def test_beziehungen_nur_zu_gezeigten_eintraegen():
    k = DublettenKandidat(id="a", titel="A", lesson="x", bereich="Beruf", status="neu", bestaetigungen=1, aehnlichkeit=0.5)
    d = DublettenKandidat(id="d", titel="D", lesson="x", bereich="Beruf", status="neu", bestaetigungen=1, aehnlichkeit=0.9)
    roh = [{"id": "a", "art": "widerspricht", "begruendung": "b"}, {"id": "a", "art": "ergaenzt", "begruendung": "doppelt"},
           {"id": "d", "art": "ergaenzt", "begruendung": "ist die Dublette"}, {"id": "x", "art": "ergaenzt", "begruendung": ""},
           {"id": "a", "art": "quatsch"}, "kein dict"]
    assert beziehungen_auswerten(roh, [k, d], dublette_id="d") == [{"id": "a", "titel": "A", "art": "widerspricht", "begruendung": "b"}]
    assert beziehungen_auswerten(None, [k]) == []


# ---------------------------------------------------------------- API
def test_entwurf_bringt_verbindungen_mit(env):
    client, _, add, ziel, _ = env
    alt = add(titel="Bank documents")
    ziel["id"] = alt["id"]
    eintrag = client.post("/api/notiz?warten=true", json={"text": "Vor jedem Bankgespräch Unterlagenliste anfordern, auch Gehaltsnachweise", "bereich": "Immobilien"}).json()
    assert eintrag["entwurf"]["beziehungen"] == [{"id": alt["id"], "titel": "Bank documents", "art": "ergaenzt", "begruendung": "Adds the timing."}]
    e = eintrag["entwurf"]
    neu = client.post("/api/lessons", json={**lesson_json(titel=e["titel"], lesson=e["lesson"]), "entwurf_id": eintrag["id"]}).json()["lesson"]
    detail = client.get(f"/api/lessons/{neu['id']}").json()
    assert [(b["id"], b["art"], b["richtung"]) for b in detail["beziehungen"]] == [(alt["id"], "ergaenzt", "aus")]
    assert client.get(f"/api/lessons/{alt['id']}").json()["beziehungen"][0]["richtung"] == "ein"
    # Von Hand verbinden und lösen
    dritter = add(titel="Third")
    assert client.post(f"/api/lessons/{dritter['id']}/beziehungen", json={"zu_id": alt["id"], "art": "beispiel_fuer"}).status_code == 201
    assert client.post(f"/api/lessons/{alt['id']}/beziehungen", json={"zu_id": dritter["id"], "art": "ergaenzt"}).status_code == 409
    assert client.delete(f"/api/lessons/{alt['id']}/beziehungen/{dritter['id']}").status_code == 200
    assert client.delete(f"/api/lessons/{alt['id']}/beziehungen/{dritter['id']}").status_code == 404


def warten_bis_fertig(client):
    for _ in range(100):
        data = client.get("/api/wissen").json()
        if not data["lauf"]["laeuft"]:
            return data
        time.sleep(0.05)
    raise AssertionError("Wissenslauf endet nicht")


def test_themen_aufbauen_verdichten_und_pruefen(env):
    client, claude, add, _, _ = env
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}})
    a = add(titel="Bank documents")
    b = add(titel="Bank timing", lesson="Start two months ahead.")
    for i in range(4):
        add(titel=f"Viewing {i}", lesson=f"Check the heating {i}.")
    geheim = add(titel="Lokales Geheimnis", bereich="Beruf")
    assert client.get("/api/wissen").json()["zahlen"]["ohne_thema"] == 7

    assert client.post("/api/wissen/lauf?arten=zuordnen,verdichten,pruefen").status_code == 202
    data = warten_bis_fertig(client)
    assert data["lauf"]["fehler"] == "" and "6 Einträge zugeordnet" in data["lauf"]["ergebnis"]
    assert [t["titel"] for t in data["themen"]] == ["Financing"]  # verdichtet, Titel geschärft; "Unused" nie angelegt
    thema = data["themen"][0]
    assert thema["anzahl"] == 6 and not thema["veraltet"] and thema["bereich"] == "Immobilien"
    assert data["zahlen"]["ohne_thema"] == 1  # nur der lokale Eintrag
    # Nichts aus dem lokalen Bereich ging an Claude
    assert all("Lokales Geheimnis" not in str(c["messages"]) for c in claude.calls)

    seite = client.get(f"/api/themen/{thema['id']}").json()
    assert seite["seite"]["kernaussagen"] == [{"text": "Ask for the bank's document list first.", "quellen": [seite["lessons"][0]["id"]]}]
    assert seite["seite"]["offene_fragen"] == ["How early to start?"] and len(seite["lessons"]) == 6

    pflege = client.get("/api/pflege").json()
    assert {p["art"] for p in pflege} == {"widerspruch", "luecke"}
    widerspruch = next(p for p in pflege if p["art"] == "widerspruch")
    assert len(widerspruch["lessons"]) == 2 and data["zahlen"]["pflege_offen"] == 2
    assert client.get("/api/wissen").json()["zahlen"]["widersprueche"] == 1  # als Verbindung gemerkt
    assert client.patch(f"/api/pflege/{widerspruch['id']}", json={"status": "erledigt"}).status_code == 200
    assert len(client.get("/api/pflege").json()) == 1 and len(client.get("/api/pflege?status=erledigt").json()) == 1

    # Neue Einträge landen beim nächsten Lauf im bestehenden Thema; einzelne Seite neu verdichten
    add(titel="Bank new")
    client.post("/api/wissen/lauf?arten=zuordnen")
    data = warten_bis_fertig(client)
    assert len(data["themen"]) == 1 and data["themen"][0]["anzahl"] == 7 and data["themen"][0]["veraltet"]
    assert client.post(f"/api/themen/{thema['id']}/verdichten").json()["veraltet"] is False
    assert client.get(f"/api/lessons/{a['id']}").json()["themen"] == [{"id": thema["id"], "titel": "Financing"}]
    assert b and geheim


def test_nachtlauf_nur_nachts_und_einmal(env):
    client, _, add, _, app = env
    pflege: Wissenspflege = app.state.wissenspflege
    add(titel="A")
    assert not pflege.nachtlauf_wenn_faellig(datetime(2026, 11, 9, 3, 0))  # noch keine Themen: Nutzer startet selbst
    client.post("/api/wissen/lauf?arten=zuordnen")
    warten_bis_fertig(client)
    assert not pflege.nachtlauf_wenn_faellig(datetime(2026, 11, 9, 14, 0))
    assert pflege.nachtlauf_wenn_faellig(datetime.now().replace(hour=3))
    warten_bis_fertig(client)
    assert not pflege.nachtlauf_wenn_faellig(datetime.now().replace(hour=4))


def test_wiederholen_api(env, tmp_path):
    client, _, add, _, app = env
    l = add(titel="Alt")
    alt = (datetime.now() - timedelta(days=20)).isoformat(timespec="seconds")
    app.state.repo.conn.execute("UPDATE lessons SET erstellt_am = ? WHERE id = ?", (alt, l["id"]))
    data = client.get("/api/wiederholen").json()
    assert [x["id"] for x in data["lessons"]] == [l["id"]] and data["stand"]["faellig"] == 0
    r = client.post(f"/api/wiederholen/{l['id']}", json={"ergebnis": "vergessen"}).json()
    assert r["stufe"] == 0 and r["stand"]["heute_wiederholt"] == 1
    assert client.post("/api/wiederholen/gibtsnicht", json={"ergebnis": "parat"}).status_code == 404
    assert client.get("/api/wiedersehen").json() is None  # in zwei Tagen wieder dran


def test_dialog_antwort_als_notiz_merken(env):
    client, _, add, _, _ = env
    add(titel="Schichtleiter bestätigen", situation="Hypercare", ereignis="Personal fehlte.", lesson="Schichtleiter schriftlich bestätigen.", bereich="Beruf")
    b = client.post("/api/briefing", json={"situation": "Hypercare nach Go-live planen", "modus": "kombiniert"}).json()
    client.post(f"/api/briefing/{b['id']}/zusammenfassung")
    r = client.post(f"/api/briefing/{b['id']}/dialog", json={"text": "Was ist mit den Carriern?", "modus": "frage"}).json()
    assert r["dialog"][1]["rolle"] == "claude"
    assert client.post(f"/api/briefing/{b['id']}/dialog/0/merken").status_code == 404  # Nutzerbeitrag
    r = client.post(f"/api/briefing/{b['id']}/dialog/1/merken")
    assert r.status_code == 201
    entwurf_id = r.json()["dialog"][1]["entwurf_id"]
    eintrag = client.get(f"/api/entwuerfe/{entwurf_id}").json()
    assert "Was ist mit den Carriern?" in eintrag["rohtext"] and "Agree pickup windows" in eintrag["rohtext"]
    assert "[[E:" not in eintrag["rohtext"] and eintrag["bereich_vorgabe"] == ""
    assert client.post(f"/api/briefing/{b['id']}/dialog/1/merken").status_code == 409


def test_briefing_nimmt_verbundene_eintraege_und_themen_mit(env):
    client, claude, add, _, app = env
    repo = app.state.repo
    treffer = add(titel="Cutover rehearsal", situation="Cutover", ereignis="Rehearsal missed steps.", lesson="Always rehearse the cutover.", bereich="Beruf")
    fern = add(titel="Unrelated words", situation="Zzz", ereignis="Qqq", lesson="Xyz completely different.", bereich="Beruf")
    repo.beziehung_setzen(fern["id"], treffer["id"], "widerspricht", "Says rehearsal is optional.")
    thema = repo.thema_anlegen("Cutover", "Beruf")
    repo.thema_zuordnen(thema, [treffer["id"]])
    repo.thema_seite_setzen(thema, {"zusammenfassung": "Rehearse twice.", "kernaussagen": [{"text": "Dress rehearsal is mandatory.", "quellen": []}],
                                    "fallstricke": [], "widersprueche": []})
    b = client.post("/api/briefing", json={"situation": "Cutover rehearsal planen", "modus": "kombiniert"}).json()
    durch = {t["lesson"]["id"]: t["gefunden_durch"] for t in b["treffer"]}
    assert durch[fern["id"]] == ["verbindung"]
    client.post(f"/api/briefing/{b['id']}/zusammenfassung")
    nachricht = claude.calls[-1]["messages"][0]["content"]
    assert "<themen>" in nachricht and "Dress rehearsal is mandatory." in nachricht and "widerspricht" in nachricht


# ---------------------------------------------------------------- MCP
def rpc(client, method, params=None, kennung=1, headers=None):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": kennung, "method": method, "params": params or {}}, headers=headers or {})


def test_mcp_server(env):
    client, _, add, _, _ = env
    client.put("/api/einstellungen", json={"strukturierung_bereiche": {"Beruf": "lokal"}, "sperrliste": ["Geheimfirma"]})
    l = add(titel="Bank documents", lesson="Request the document list.")
    lokal = add(titel="Bank secret local", bereich="Beruf")
    init = rpc(client, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t"}}).json()
    assert init["result"]["protocolVersion"] == "2025-03-26" and init["result"]["serverInfo"]["name"] == "lessons-vault"
    assert client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
    namen = {t["name"] for t in rpc(client, "tools/list").json()["result"]["tools"]}
    assert namen == {"suchen", "eintrag", "themen", "thema", "notiz_anlegen"}

    def call(name, **args):
        return rpc(client, "tools/call", {"name": name, "arguments": args}).json()["result"]

    gefunden = call("suchen", anfrage="Bank")
    assert not gefunden["isError"] and l["id"] in gefunden["content"][0]["text"] and lokal["id"] not in gefunden["content"][0]["text"]
    assert call("eintrag", id=lokal["id"])["isError"] is True
    assert "Request the document list." in call("eintrag", id=l["id"])["content"][0]["text"]
    assert call("notiz_anlegen", text="Bei der Geheimfirma war es so")["isError"] is True
    ok = call("notiz_anlegen", text="Notar early: book two weeks ahead", bereich="Immobilien")
    assert not ok["isError"] and "Eingang" in ok["content"][0]["text"]
    assert rpc(client, "tools/call", {"name": "gibtsnicht"}).json()["error"]["code"] == -32602
    assert rpc(client, "gibtsnicht").json()["error"]["code"] == -32601
    assert client.get("/mcp").status_code == 405


def test_mcp_braucht_token(tmp_path):
    settings = Settings(db_path=tmp_path / "t.db", token="GEHEIM", anthropic_api_key="", voyage_api_key="", ollama_model="", worker_aktiv=False)
    client = TestClient(create_app(settings, Strukturierer(None, "m"), HashingProvider()))
    assert rpc(client, "tools/list").status_code == 401
    assert rpc(client, "tools/list", headers={"Authorization": "Bearer GEHEIM"}).status_code == 200
