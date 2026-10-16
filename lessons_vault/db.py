"""SQLite-Schema, Migrationen und Verbindungsaufbau."""

from __future__ import annotations

import sqlite3
from pathlib import Path

STANDARD_BEREICHE = [
    # name, aktiv, beispiele
    ("Beruf", 1, "Rollout-Wellen, Cutover, Stakeholder, Eskalationen, Steering Committees"),
    ("Immobilien", 1, "Besichtigungen, Bankgespräche, Sanierung, Mieter, Notar"),
    ("Trading", 0, "Fehlentscheidungen, Regelbrüche, Setups, die funktioniert haben"),
    ("Projekte", 0, "Fehler beim Bauen eigener Apps, Spezifikation, Tooling"),
    ("Familie und Alltag", 0, "Reisen, Ausflüge, Anschaffungen"),
]

MIGRATIONS: list[str] = [
    # Version 1
    """
    CREATE TABLE bereiche (
        name        TEXT PRIMARY KEY,
        aktiv       INTEGER NOT NULL DEFAULT 1,
        reihenfolge INTEGER NOT NULL DEFAULT 0,
        beispiele   TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE lessons (
        id                 TEXT PRIMARY KEY,
        titel              TEXT NOT NULL CHECK (length(titel) BETWEEN 1 AND 80),
        situation          TEXT NOT NULL,
        ereignis           TEXT NOT NULL,
        lesson             TEXT NOT NULL,
        massnahme          TEXT NOT NULL DEFAULT '',
        bereich            TEXT NOT NULL REFERENCES bereiche(name) ON UPDATE CASCADE,
        tags               TEXT NOT NULL DEFAULT '[]',
        schweregrad        INTEGER NOT NULL CHECK (schweregrad BETWEEN 1 AND 5),
        status             TEXT NOT NULL DEFAULT 'neu' CHECK (status IN ('neu', 'bestätigt', 'überholt')),
        bestaetigungen     INTEGER NOT NULL DEFAULT 1 CHECK (bestaetigungen >= 1),
        erstellt_am        TEXT NOT NULL,
        geaendert_am       TEXT NOT NULL,
        quelle             TEXT NOT NULL CHECK (quelle IN ('text', 'sprache', 'import')),
        embedding          BLOB,
        embedding_modell   TEXT NOT NULL DEFAULT '',
        erfassung_sekunden REAL
    );
    CREATE INDEX idx_lessons_bereich ON lessons(bereich);
    CREATE INDEX idx_lessons_erstellt ON lessons(erstellt_am);

    CREATE TABLE bestaetigungen (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
        datum     TEXT NOT NULL,
        notiz     TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_bestaetigungen_lesson ON bestaetigungen(lesson_id);

    CREATE TABLE einstellungen (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    -- Trigram-Tokenizer: findet Teilwörter in deutschen Komposita,
    -- remove_diacritics macht die Suche umlauttolerant.
    CREATE VIRTUAL TABLE lessons_fts USING fts5(
        titel, situation, ereignis, lesson, massnahme, tags, bereich,
        content='lessons', content_rowid='rowid',
        tokenize='trigram remove_diacritics 1'
    );

    CREATE TRIGGER lessons_ai AFTER INSERT ON lessons BEGIN
        INSERT INTO lessons_fts(rowid, titel, situation, ereignis, lesson, massnahme, tags, bereich)
        VALUES (new.rowid, new.titel, new.situation, new.ereignis, new.lesson, new.massnahme, new.tags, new.bereich);
    END;
    CREATE TRIGGER lessons_ad AFTER DELETE ON lessons BEGIN
        INSERT INTO lessons_fts(lessons_fts, rowid, titel, situation, ereignis, lesson, massnahme, tags, bereich)
        VALUES ('delete', old.rowid, old.titel, old.situation, old.ereignis, old.lesson, old.massnahme, old.tags, old.bereich);
    END;
    CREATE TRIGGER lessons_au AFTER UPDATE OF titel, situation, ereignis, lesson, massnahme, tags, bereich ON lessons BEGIN
        INSERT INTO lessons_fts(lessons_fts, rowid, titel, situation, ereignis, lesson, massnahme, tags, bereich)
        VALUES ('delete', old.rowid, old.titel, old.situation, old.ereignis, old.lesson, old.massnahme, old.tags, old.bereich);
        INSERT INTO lessons_fts(rowid, titel, situation, ereignis, lesson, massnahme, tags, bereich)
        VALUES (new.rowid, new.titel, new.situation, new.ereignis, new.lesson, new.massnahme, new.tags, new.bereich);
    END;
    """,
]


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for index, script in enumerate(MIGRATIONS[version:], start=version + 1):
        with conn:
            conn.executescript(script)
            if index == 1:
                conn.executemany(
                    "INSERT INTO bereiche(name, aktiv, reihenfolge, beispiele) VALUES (?, ?, ?, ?)",
                    [(n, a, i, b) for i, (n, a, b) in enumerate(STANDARD_BEREICHE)],
                )
            conn.execute(f"PRAGMA user_version = {index}")
