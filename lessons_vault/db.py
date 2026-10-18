"""SQLite-Schema, Migrationen und Verbindungsaufbau."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
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
    # Version 4: Einschätzung persönlich (1) / allgemein (0)
    """
    ALTER TABLE lessons ADD COLUMN spezifisch INTEGER;
    """,
    # Version 5: Fotos und Entwurfsabgleich im Briefing
    """
    CREATE TABLE bilder (
        id          TEXT PRIMARY KEY,
        breite      INTEGER NOT NULL,
        hoehe       INTEGER NOT NULL,
        groesse     INTEGER NOT NULL,
        ocr_text    TEXT NOT NULL DEFAULT '',
        ocr_status  TEXT NOT NULL DEFAULT 'offen' CHECK (ocr_status IN ('offen', 'fertig', 'fehler', 'aus')),
        erstellt_am TEXT NOT NULL
    );
    -- Ein Foto kann an mehreren Lessons hängen (eine Folie, mehrere Lessons).
    CREATE TABLE bild_links (
        bild_id  TEXT NOT NULL REFERENCES bilder(id) ON DELETE CASCADE,
        ziel_typ TEXT NOT NULL CHECK (ziel_typ IN ('lesson', 'entwurf', 'briefing')),
        ziel_id  TEXT NOT NULL,
        PRIMARY KEY (bild_id, ziel_typ, ziel_id)
    );
    CREATE INDEX idx_bild_links_ziel ON bild_links(ziel_typ, ziel_id);

    ALTER TABLE briefings ADD COLUMN entwurf_weg TEXT NOT NULL DEFAULT '';
    ALTER TABLE briefings ADD COLUMN entwurf_text TEXT NOT NULL DEFAULT '';
    ALTER TABLE briefings ADD COLUMN abgleich_json TEXT NOT NULL DEFAULT '';
    """,
    # Version 6: Briefing kombiniert eigene Erfahrung mit Claude-Wissen
    """
    ALTER TABLE briefings ADD COLUMN modus TEXT NOT NULL DEFAULT 'eigen';
    ALTER TABLE briefings ADD COLUMN plan_json TEXT NOT NULL DEFAULT '';
    """,
    # Version 7: "beruflich" als Eigenschaft eines Bereichs statt am Namen "Beruf" festgemacht
    """
    ALTER TABLE bereiche ADD COLUMN beruflich INTEGER NOT NULL DEFAULT 0;
    UPDATE bereiche SET beruflich = 1 WHERE name = 'Beruf';
    """,
    # Version 8: Schnellnotiz. Jede Erfassung landet zuerst als Entwurf; der Modus legt fest, wer strukturiert.
    # Bestehende Entwürfe stammen aus dem lokalen Weg und bleiben lokal.
    """
    ALTER TABLE entwuerfe ADD COLUMN modus TEXT NOT NULL DEFAULT 'lokal';
    ALTER TABLE entwuerfe ADD COLUMN freigabe INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE rueckmeldungen (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        art         TEXT NOT NULL,
        wert        TEXT NOT NULL,
        erstellt_am TEXT NOT NULL
    );
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

    def atomar_ausfuehren(self, script: str) -> None:
        """Skript mit eigenem BEGIN/COMMIT; bei Fehler Rollback."""
        with self._lock:
            try:
                self._conn.executescript(script)
            except Exception:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise

    def sichern(self, ziel: Path) -> None:
        """Konsistente Kopie per SQLite-Backup-API, auch im laufenden Betrieb."""
        with self._lock:
            ziel_conn = sqlite3.connect(str(ziel))
            try:
                self._conn.backup(ziel_conn)
            finally:
                ziel_conn.close()


def connect(path: Path | str) -> LockedConnection:
    datei = str(path) != ":memory:"
    if datei:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(path), check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    raw.execute("PRAGMA journal_mode = WAL")
    conn = LockedConnection(raw)
    migrate(conn, Path(path).parent / "sicherungen" if datei else None)
    return conn


def _seed_sql() -> str:
    """Standardbereiche als SQL, damit sie in derselben Transaktion wie Migration 1 landen."""

    def q(text: str) -> str:
        return "'" + text.replace("'", "''") + "'"

    zeilen = [
        f"INSERT INTO bereiche(name, aktiv, reihenfolge, beispiele) VALUES ({q(n)}, {a}, {i}, {q(b)});"
        for i, (n, a, b) in enumerate(STANDARD_BEREICHE)
    ]
    return "\n".join(zeilen)


def migrate(conn: LockedConnection, sicherungs_ordner: Path | None = None) -> None:
    """Führt ausstehende Migrationen aus, jede atomar.

    Python's executescript() committet vorher und läuft dann im Autocommit. Deshalb steht jede Migration
    in einem eigenen BEGIN/COMMIT samt user_version. Bricht sie ab, wird zurückgerollt und der alte,
    startbare Stand bleibt. Vor der ersten Migration einer bestehenden Datenbank entsteht eine Sicherung.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    ausstehend = list(enumerate(MIGRATIONS[version:], start=version + 1))
    if ausstehend and version > 0 and sicherungs_ordner is not None:
        sicherungs_ordner.mkdir(parents=True, exist_ok=True)
        zeit = datetime.now().strftime("%Y%m%d-%H%M%S")
        conn.sichern(sicherungs_ordner / f"vor-migration-v{version}-auf-v{len(MIGRATIONS)}-{zeit}.db")
    for index, script in ausstehend:
        seed = _seed_sql() if index == 1 else ""
        conn.atomar_ausfuehren(f"BEGIN;\n{script}\n{seed}\nPRAGMA user_version = {index};\nCOMMIT;")
