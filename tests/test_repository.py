import pytest
from pydantic import ValidationError

from lessons_vault import db
from lessons_vault.models import Bereich, Einstellungen, LessonImport, LessonUpdate
from lessons_vault.repository import Invalid, NotFound

from .conftest import beispiel


def test_migration_idempotent_und_seed(conn):
    db.migrate(conn)
    namen = [r[0] for r in conn.execute("SELECT name FROM bereiche WHERE aktiv = 1 ORDER BY reihenfolge")]
    assert namen == ["Beruf", "Immobilien"]
    assert conn.execute("SELECT COUNT(*) FROM bereiche").fetchone()[0] == 5


def test_neue_lesson_status_neu(repo):
    lesson = repo.anlegen(beispiel())
    assert lesson.status == "neu"
    assert lesson.bestaetigungen == 1
    assert lesson.tags == ["Bank", "Finanzierung"]
    assert repo.bestaetigungs_protokoll(lesson.id)[0]["notiz"] == "erstmals erlebt"


def test_bestaetigung_setzt_status(repo):
    lesson = repo.anlegen(beispiel())
    lesson = repo.bestaetigen(lesson.id, "Zweite Wohnung, gleicher Fehler")
    assert lesson.status == "bestätigt"
    assert lesson.bestaetigungen == 2
    assert len(repo.bestaetigungs_protokoll(lesson.id)) == 2


def test_ueberholt_bleibt_ueberholt(repo):
    lesson = repo.anlegen(beispiel())
    repo.aendern(lesson.id, LessonUpdate(status="überholt"))
    assert repo.bestaetigen(lesson.id).status == "überholt"


def test_titel_max_80():
    with pytest.raises(ValidationError):
        beispiel(titel="x" * 81)


def test_unbekannter_bereich(repo):
    with pytest.raises(Invalid):
        repo.anlegen(beispiel(bereich="Gibtsnicht"))


def test_tags_bereinigt():
    assert beispiel(tags=[" #Bank", "bank", "", "Notar"]).tags == ["Bank", "Notar"]


def test_aendern_und_fts_sync(repo, conn):
    lesson = repo.anlegen(beispiel())
    repo.aendern(lesson.id, LessonUpdate(titel="Notartermin vorbereiten"))
    treffer = conn.execute("SELECT rowid FROM lessons_fts WHERE lessons_fts MATCH '\"notar\"'").fetchall()
    assert len(treffer) == 1
    assert conn.execute("SELECT COUNT(*) FROM lessons_fts WHERE lessons_fts MATCH '\"selbstauskunft\"'").fetchone()[0] == 0


def test_loeschen(repo):
    lesson = repo.anlegen(beispiel())
    repo.loeschen(lesson.id)
    with pytest.raises(NotFound):
        repo.holen(lesson.id)
    with pytest.raises(NotFound):
        repo.loeschen(lesson.id)


def test_import_mit_mehreren_bestaetigungen(repo):
    data = beispiel().model_dump(exclude={"quelle", "erfassung_sekunden"})
    lesson = repo.anlegen(LessonImport(**data, bestaetigungen=3, erstellt_am="2025-03-01T10:00:00+00:00"))
    assert lesson.status == "bestätigt"
    assert lesson.quelle == "import"
    assert lesson.erstellt_am.startswith("2025-03-01")


def test_bereiche_und_einstellungen(repo):
    repo.bereich_anlegen(Bereich(name="Gesundheit", aktiv=False))
    with pytest.raises(Invalid):
        repo.bereich_anlegen(Bereich(name="Gesundheit"))
    assert repo.bereich_aendern("Trading", True, None).aktiv
    repo.einstellungen_speichern(Einstellungen(sperrliste=["Acme"]))
    assert repo.einstellungen().sperrliste == ["Acme"]


def test_statistik(repo):
    repo.anlegen(beispiel(erfassung_sekunden=22))
    repo.anlegen(beispiel(erfassung_sekunden=40, massnahme=""))
    stat = repo.statistik()
    assert stat["gesamt"] == 2
    assert stat["neu_erfasst_7_tage"] == 2
    assert stat["erfassungen_unter_30s"] == 1
    assert stat["ohne_massnahme"] == 1
