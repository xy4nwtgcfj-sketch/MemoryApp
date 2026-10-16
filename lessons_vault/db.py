"""SQLite-Schema, Migrationen und Verbindungsaufbau."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator

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
    # Version 2: Warteschlange für Hintergrund-Strukturierung
    """
    CREATE TABLE entwuerfe (
        id                 TEXT PRIMARY KEY,
        rohtext            TEXT NOT NULL,
        quelle             TEXT NOT NULL CHECK (quelle IN ('text', 'sprache', 'import')),
        bereich_vorgabe    TEXT NOT NULL DEFAULT '',
        status             TEXT NOT NULL DEFAULT 'wartet' CHECK (status IN ('wartet', 'in_arbeit', 'fertig', 'fehler')),
        rueckfrage         TEXT NOT NULL DEFAULT '',
        antwort            TEXT NOT NULL DEFAULT '',
        entwurf_json       TEXT NOT NULL DEFAULT '',
        fehler             TEXT NOT NULL DEFAULT '',
        modell             TEXT NOT NULL DEFAULT '',
        dauer_sekunden     REAL,
        erfassung_sekunden REAL,
        erstellt_am        TEXT NOT NULL,
        geaendert_am       TEXT NOT NULL
    );
    CREATE INDEX idx_entwuerfe_status ON entwuerfe(status, erstellt_am);
    """,
    # Version 3: Briefings und Feedback
    """
    CREATE TABLE briefings (
        id                 TEXT PRIMARY KEY,
        situation          TEXT NOT NULL,
        bereich            TEXT NOT NULL DEFAULT '',
        treffer_json       TEXT NOT NULL DEFAULT '[]',
        checkliste_json    TEXT NOT NULL DEFAULT '[]',
        zusammenfassung    TEXT NOT NULL DEFAULT '',
        ki_checkliste_json TEXT NOT NULL DEFAULT '',
        ki_modell          TEXT NOT NULL DEFAULT '',
        embedding          BLOB,
        embedding_modell   TEXT NOT NULL DEFAULT '',
        erstellt_am        TEXT NOT NULL
    );
    CREATE INDEX idx_briefings_erstellt ON briefings(erstellt_am);

    CREATE TABLE briefing_feedback (
        briefing_id TEXT NOT NULL REFERENCES briefings(id) ON DELETE CASCADE,
        lesson_id   TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
        bewertung   TEXT NOT NULL CHECK (bewertung IN ('hilfreich', 'nicht_relevant')),
        datum       TEXT NOT NULL,
        PRIMARY KEY (briefing_id, lesson_id)
    );
    CREATE INDEX idx_feedback_lesson ON briefing_feedback(lesson_id);
    """,
]


class Result:
    """Vollständig gelesenes Abfrageergebnis, damit kein Cursor die Sperre überlebt."""

    def __init__(self, rows: list[Any], rowcount: int):
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Any]:
        return list(self._rows)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._rows)


class LockedConnection:
    """Serialisiert den Zugriff auf eine SQLite-Verbindung (API-Threads und Hintergrund-Worker).

    `with conn:` hält die Sperre für die ganze Transaktion.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = threading.RLock()

    def execute(self, sql: str, params: Any = ()) -> Result:
        with self._lock:
            cursor = self._conn.execute(sql, params)
            return Result(cursor.fetchall(), cursor.rowcount)

    def executemany(self, sql: str, seq: Any) -> Result:
        with self._lock:
            cursor = self._conn.executemany(sql, seq)
            return Result([], cursor.rowcount)

    def executescript(self, script: str) -> None:
        with self._lock:
            self._conn.executescript(script)

    def __enter__(self) -> "LockedConnection":
        self._lock.acquire()
        self._conn.__enter__()
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            self._conn.__exit__(*exc)
        finally:
            self._lock.release()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def connect(path: Path | str) -> LockedConnection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(path), check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    raw.execute("PRAGMA journal_mode = WAL")
    conn = LockedConnection(raw)
    migrate(conn)
    return conn


def migrate(conn: LockedConnection) -> None:
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
