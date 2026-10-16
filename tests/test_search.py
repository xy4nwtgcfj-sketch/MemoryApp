import pytest

from lessons_vault.embeddings import HashingProvider
from lessons_vault.models import LessonUpdate
from lessons_vault.search import Filter, Suche, fts_query, suchbegriffe

from .conftest import beispiel


@pytest.fixture
def suche(repo):
    provider = HashingProvider()

    def add(**kw):
        data = beispiel(**kw)
        text = " ".join([data.titel, data.lesson, data.situation, data.ereignis])
        return repo.anlegen(data, provider.embed([text])[0], provider.name)

    add(titel="Finanzierungsbankgespräch vorbereiten", schweregrad=2)
    add(
        titel="Cutover-Plan mit Lager abstimmen", bereich="Beruf", schweregrad=5,
        situation="Rollout-Welle mit Go-live am Wochenende.", ereignis="Personal fehlte beim Cutover.",
        lesson="Vor jedem Cutover die Personalplanung bestätigen lassen.", tags=["Cutover"],
    )
    ueberholt = add(titel="Notar früh terminieren", lesson="Notartermin zwei Wochen vorher fixieren.", tags=["Notar"])
    repo.aendern(ueberholt.id, LessonUpdate(status="überholt"))
    return Suche(repo, provider)


def test_suchbegriffe():
    assert suchbegriffe("Was weiß ich über Bankgespräche?") == ["bankgespräch"]
    assert fts_query("ab") == ""


def test_kompositum(suche):
    treffer = suche.suchen("Bank", "volltext")
    assert [t.lesson.titel for t in treffer][0] == "Finanzierungsbankgespräch vorbereiten"


def test_umlaut_tolerant(suche):
    assert suche.suchen("gesprach", "volltext")


def test_frage_hybrid(suche):
    treffer = suche.suchen("Was weiß ich über Bankgespräche?")
    assert treffer[0].lesson.titel == "Finanzierungsbankgespräch vorbereiten"
    assert "volltext" in treffer[0].gefunden_durch


def test_filter(suche):
    assert all(t.lesson.bereich == "Beruf" for t in suche.suchen("vor", filt=Filter(bereich="Beruf")))
    assert [t.lesson.schweregrad for t in suche.suchen("", filt=Filter(schweregrad_min=4))] == [5]
    assert [t.lesson.status for t in suche.suchen("Notar", "volltext", Filter(status="überholt"))] == ["überholt"]
    assert suche.suchen("", filt=Filter(von="2099-01-01")) == []
    assert len(suche.suchen("", filt=Filter(bis="2099-01-01"))) == 3


def test_ueberholte_bleiben_sichtbar(suche):
    assert any(t.lesson.status == "überholt" for t in suche.suchen("Notar"))


def test_leere_suche_neueste_zuerst(suche):
    treffer = suche.suchen("")
    assert len(treffer) == 3
    assert treffer[0].lesson.erstellt_am >= treffer[-1].lesson.erstellt_am


def test_semantisch_ignoriert_fremdes_modell(repo):
    repo.anlegen(beispiel(), HashingProvider().embed(["Bank"])[0], "anderes-modell")
    assert Suche(repo, HashingProvider()).semantisch("Bank", Filter()) == []
