import threading

from lessons_vault.embeddings import EmbeddingFehler, HashingProvider
from lessons_vault.models import Entwurf
from lessons_vault.worker import Hintergrund

from .conftest import beispiel


def make_worker(repo, verarbeiter, provider=None):
    return Hintergrund(repo, provider or HashingProvider(), verarbeiter, "ollama:test", leerlauf_sekunden=0.05, backoff_sekunden=0.05)


def ok_entwurf(eintrag):
    return Entwurf(titel="T", situation="S", ereignis="E", lesson="L", bereich="Beruf", ki_verwendet=True, ki_modell="ollama:test")


def test_reihenfolge_und_status(repo):
    a = repo.entwurf_anlegen("erster", "text", erfassung_sekunden=5)
    b = repo.entwurf_anlegen("zweiter", "sprache")
    gesehen = []
    w = make_worker(repo, lambda e: (gesehen.append(e.rohtext), ok_entwurf(e))[1])
    assert w.verarbeite_naechsten() and w.verarbeite_naechsten() and not w.verarbeite_naechsten()
    assert gesehen == ["erster", "zweiter"]
    eintrag = repo.entwurf_holen(a.id)
    assert eintrag.status == "fertig" and eintrag.entwurf.titel == "T" and eintrag.modell == "ollama:test"
    assert eintrag.erfassung_sekunden == 5 and eintrag.dauer_sekunden is not None
    assert repo.entwurf_holen(b.id).quelle == "sprache"


def test_fehler_bleibt_erhalten(repo):
    e = repo.entwurf_anlegen("Rohtext bleibt", "text")

    def kaputt(_):
        raise ValueError("Modell weg")

    make_worker(repo, kaputt).verarbeite_naechsten()
    eintrag = repo.entwurf_holen(e.id)
    assert eintrag.status == "fehler" and "Modell weg" in eintrag.fehler and eintrag.rohtext == "Rohtext bleibt"


def test_manueller_rueckfall_gilt_als_fehler(repo):
    e = repo.entwurf_anlegen("x", "text")
    make_worker(repo, lambda _: Entwurf(titel="x", ki_verwendet=False, ki_fehler="Ollama nicht erreichbar")).verarbeite_naechsten()
    eintrag = repo.entwurf_holen(e.id)
    assert eintrag.status == "fehler" and eintrag.entwurf.titel == "x"


def test_neustart_setzt_in_arbeit_zurueck(repo):
    e = repo.entwurf_anlegen("x", "text")
    repo.naechsten_entwurf_reservieren()
    assert repo.entwurf_holen(e.id).status == "in_arbeit"
    assert repo.entwuerfe_zuruecksetzen() == 1
    assert repo.entwurf_holen(e.id).status == "wartet"


def test_antwort_reiht_neu_ein(repo):
    e = repo.entwurf_anlegen("x", "text")
    make_worker(repo, ok_entwurf).verarbeite_naechsten()
    eintrag = repo.entwurf_neu_einreihen(e.id, rueckfrage="Was genau?", antwort="Unterlagen fehlten")
    assert eintrag.status == "wartet" and eintrag.antwort == "Unterlagen fehlten"


def test_nachindexieren(repo):
    repo.anlegen(beispiel())
    repo.anlegen(beispiel(), HashingProvider().embed(["x"])[0], "altes-modell")
    w = make_worker(repo, ok_entwurf)
    assert w.nachindexieren() == 2
    assert w.nachindexieren() == 0
    assert {m for _, m, _ in repo.embeddings()} == {"lokal-hashing-v1"}


def test_thread_laeuft_und_ueberlebt_embedding_fehler(repo):
    class Kaputt(HashingProvider):
        name = "kaputt"

        def embed(self, texts, input_type="document"):
            raise EmbeddingFehler("weg")

    repo.anlegen(beispiel())
    fertig = threading.Event()

    def verarbeiter(e):
        fertig.set()
        return ok_entwurf(e)

    w = make_worker(repo, verarbeiter, Kaputt())
    w.start()
    try:
        repo.entwurf_anlegen("x", "text")
        w.wecken()
        assert fertig.wait(3)
    finally:
        w.stop()
    assert repo.entwuerfe_zaehlen()["fertig"] == 1


def test_parallele_zugriffe(repo):
    fehler = []

    def schreiben(n):
        try:
            for i in range(20):
                repo.entwurf_anlegen(f"{n}-{i}", "text")
                repo.naechsten_entwurf_reservieren()
        except Exception as exc:  # pragma: no cover
            fehler.append(exc)

    threads = [threading.Thread(target=schreiben, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert fehler == []
    assert repo.entwuerfe_zaehlen()["in_arbeit"] == 80
