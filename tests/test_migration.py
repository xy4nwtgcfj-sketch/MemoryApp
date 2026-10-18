import sqlite3

import pytest

from lessons_vault import db
from lessons_vault.models import LessonIn
from lessons_vault.repository import Repository

LESSON = LessonIn(titel="Alt", situation="s", ereignis="e", lesson="r", bereich="Beruf", schweregrad=3)


def test_frische_datenbank(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    rows = {r["name"]: r["beruflich"] for r in conn.execute("SELECT name, beruflich FROM bereiche")}
    assert rows["Beruf"] == 1 and rows["Immobilien"] == 0
    assert not (tmp_path / "sicherungen").exists()  # neue Datenbank braucht keine Sicherung


def test_upgrade_mit_daten_und_sicherung(tmp_path, monkeypatch):
    pfad = tmp_path / "x.db"
    monkeypatch.setattr(db, "MIGRATIONS", db.MIGRATIONS[:3])
    alt = db.connect(pfad)
    # Lesson direkt per SQL anlegen, weil das alte Schema (v3) neuere Spalten noch nicht kennt
    with alt:
        alt.execute(
        "INSERT INTO lessons(id, titel, situation, ereignis, lesson, bereich, schweregrad, erstellt_am, geaendert_am, quelle) "
        "VALUES ('L1', 'Alt', 's', 'e', 'r', 'Beruf', 3, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'text')"
    )
    alt.close()
    monkeypatch.undo()

    neu = db.connect(pfad)
    assert neu.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    assert Repository(neu).holen("L1").titel == "Alt"
    sicherungen = list((tmp_path / "sicherungen").glob("vor-migration-v3-*.db"))
    assert len(sicherungen) == 1
    with sqlite3.connect(sicherungen[0]) as s:
        assert s.execute("PRAGMA user_version").fetchone()[0] == 3
        assert s.execute("SELECT titel FROM lessons").fetchone()[0] == "Alt"


def test_abgebrochene_migration_rollt_zurueck(tmp_path, monkeypatch):
    pfad = tmp_path / "x.db"
    conn = db.connect(pfad)
    Repository(conn).anlegen(LESSON)
    conn.close()
    kaputt = "CREATE TABLE neu_x(a); ALTER TABLE gibtsnicht ADD COLUMN b INTEGER;"
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, kaputt])
    with pytest.raises(sqlite3.OperationalError):
        db.connect(pfad)
    monkeypatch.undo()
    # Alter Stand ist unverändert und startbar
    conn = db.connect(pfad)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'neu_x'").fetchone() is None
    assert len(Repository(conn).alle()) == 1
