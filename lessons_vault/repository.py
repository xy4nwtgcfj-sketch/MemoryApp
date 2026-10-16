"""Datenzugriff auf Lessons, Bereiche, Bestätigungen und Einstellungen."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np

from .models import Bereich, Einstellungen, Lesson, LessonImport, LessonIn, LessonUpdate

LESSON_COLUMNS = (
    "id, titel, situation, ereignis, lesson, massnahme, bereich, tags, schweregrad, status, "
    "bestaetigungen, erstellt_am, geaendert_am, quelle, embedding_modell, erfassung_sekunden"
)


class NotFound(Exception):
    pass


class Invalid(Exception):
    pass


def jetzt() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row_to_lesson(row: sqlite3.Row) -> Lesson:
    data = dict(row)
    data["tags"] = json.loads(data["tags"] or "[]")
    data.pop("embedding", None)
    return Lesson(**data)


def vector_to_blob(vector: np.ndarray | None) -> bytes | None:
    return None if vector is None else np.asarray(vector, dtype=np.float32).tobytes()


def blob_to_vector(blob: bytes | None) -> np.ndarray | None:
    return None if blob is None else np.frombuffer(blob, dtype=np.float32)


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # Bereiche -----------------------------------------------------------
    def bereiche(self, nur_aktive: bool = False) -> list[Bereich]:
        sql = "SELECT name, aktiv, beispiele FROM bereiche"
        if nur_aktive:
            sql += " WHERE aktiv = 1"
        sql += " ORDER BY reihenfolge, name"
        return [Bereich(name=r["name"], aktiv=bool(r["aktiv"]), beispiele=r["beispiele"]) for r in self.conn.execute(sql)]

    def bereich_existiert(self, name: str) -> bool:
        return self.conn.execute("SELECT 1 FROM bereiche WHERE name = ?", (name,)).fetchone() is not None

    def bereich_anlegen(self, bereich: Bereich) -> Bereich:
        if self.bereich_existiert(bereich.name):
            raise Invalid(f"Bereich '{bereich.name}' existiert bereits")
        with self.conn:
            reihenfolge = self.conn.execute("SELECT COALESCE(MAX(reihenfolge), -1) + 1 FROM bereiche").fetchone()[0]
            self.conn.execute(
                "INSERT INTO bereiche(name, aktiv, reihenfolge, beispiele) VALUES (?, ?, ?, ?)",
                (bereich.name.strip(), int(bereich.aktiv), reihenfolge, bereich.beispiele),
            )
        return bereich

    def bereich_aendern(self, name: str, aktiv: bool | None, beispiele: str | None) -> Bereich:
        if not self.bereich_existiert(name):
            raise NotFound(name)
        with self.conn:
            if aktiv is not None:
                self.conn.execute("UPDATE bereiche SET aktiv = ? WHERE name = ?", (int(aktiv), name))
            if beispiele is not None:
                self.conn.execute("UPDATE bereiche SET beispiele = ? WHERE name = ?", (beispiele, name))
        return next(b for b in self.bereiche() if b.name == name)

    # Einstellungen ------------------------------------------------------
    def einstellungen(self) -> Einstellungen:
        rows = {r["key"]: json.loads(r["value"]) for r in self.conn.execute("SELECT key, value FROM einstellungen")}
        return Einstellungen(**rows)

    def einstellungen_speichern(self, einstellungen: Einstellungen) -> Einstellungen:
        with self.conn:
            for key, value in einstellungen.model_dump().items():
                self.conn.execute(
                    "INSERT INTO einstellungen(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value, ensure_ascii=False)),
                )
        return einstellungen

    # Lessons ------------------------------------------------------------
    def _pruefe_bereich(self, name: str) -> None:
        if not self.bereich_existiert(name):
            raise Invalid(f"Unbekannter Bereich '{name}'")

    def anlegen(
        self,
        data: LessonIn | LessonImport,
        embedding: np.ndarray | None = None,
        embedding_modell: str = "",
    ) -> Lesson:
        self._pruefe_bereich(data.bereich)
        now = jetzt()
        if isinstance(data, LessonImport):
            lesson_id = data.id or str(uuid.uuid4())
            status, bestaetigungen = data.status, data.bestaetigungen
            if status == "neu" and bestaetigungen >= 2:
                status = "bestätigt"
            erstellt, geaendert, sekunden = data.erstellt_am or now, data.geaendert_am or now, None
        else:
            lesson_id, status, bestaetigungen = str(uuid.uuid4()), "neu", 1
            erstellt, geaendert, sekunden = now, now, data.erfassung_sekunden
        try:
            with self.conn:
                self.conn.execute(
                    f"INSERT INTO lessons({LESSON_COLUMNS}, embedding) VALUES ({', '.join('?' * 17)})",
                    (
                        lesson_id, data.titel, data.situation, data.ereignis, data.lesson, data.massnahme,
                        data.bereich, json.dumps(data.tags, ensure_ascii=False), data.schweregrad, status,
                        bestaetigungen, erstellt, geaendert, data.quelle, embedding_modell, sekunden,
                        vector_to_blob(embedding),
                    ),
                )
                self.conn.execute(
                    "INSERT INTO bestaetigungen(lesson_id, datum, notiz) VALUES (?, ?, ?)",
                    (lesson_id, erstellt, "erstmals erlebt"),
                )
        except sqlite3.IntegrityError as exc:
            raise Invalid(str(exc)) from exc
        return self.holen(lesson_id)

    def holen(self, lesson_id: str) -> Lesson:
        row = self.conn.execute(f"SELECT {LESSON_COLUMNS} FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if row is None:
            raise NotFound(lesson_id)
        return row_to_lesson(row)

    def existiert(self, lesson_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM lessons WHERE id = ?", (lesson_id,)).fetchone() is not None

    def aendern(
        self,
        lesson_id: str,
        update: LessonUpdate,
        embedding: np.ndarray | None = None,
        embedding_modell: str | None = None,
    ) -> Lesson:
        self.holen(lesson_id)
        changes: dict[str, Any] = update.model_dump(exclude_unset=True, exclude_none=True)
        if "bereich" in changes:
            self._pruefe_bereich(changes["bereich"])
        if "tags" in changes:
            changes["tags"] = json.dumps(changes["tags"], ensure_ascii=False)
        if embedding is not None:
            changes["embedding"] = vector_to_blob(embedding)
            changes["embedding_modell"] = embedding_modell or ""
        if not changes:
            return self.holen(lesson_id)
        changes["geaendert_am"] = jetzt()
        assignments = ", ".join(f"{key} = ?" for key in changes)
        try:
            with self.conn:
                self.conn.execute(f"UPDATE lessons SET {assignments} WHERE id = ?", (*changes.values(), lesson_id))
        except sqlite3.IntegrityError as exc:
            raise Invalid(str(exc)) from exc
        return self.holen(lesson_id)

    def embedding_setzen(self, lesson_id: str, embedding: np.ndarray, embedding_modell: str) -> None:
        """Nur Index-Pflege, ändert geaendert_am bewusst nicht."""
        with self.conn:
            self.conn.execute(
                "UPDATE lessons SET embedding = ?, embedding_modell = ? WHERE id = ?",
                (vector_to_blob(embedding), embedding_modell, lesson_id),
            )

    def loeschen(self, lesson_id: str) -> None:
        with self.conn:
            if self.conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,)).rowcount == 0:
                raise NotFound(lesson_id)

    def bestaetigen(self, lesson_id: str, notiz: str = "") -> Lesson:
        """Erneut erlebt: Zähler +1, Protokolleintrag, neu → bestätigt ab 2."""
        lesson = self.holen(lesson_id)
        now = jetzt()
        status = "bestätigt" if lesson.status == "neu" and lesson.bestaetigungen + 1 >= 2 else lesson.status
        with self.conn:
            self.conn.execute(
                "UPDATE lessons SET bestaetigungen = bestaetigungen + 1, status = ?, geaendert_am = ? WHERE id = ?",
                (status, now, lesson_id),
            )
            self.conn.execute(
                "INSERT INTO bestaetigungen(lesson_id, datum, notiz) VALUES (?, ?, ?)", (lesson_id, now, notiz.strip())
            )
        return self.holen(lesson_id)

    def bestaetigungs_protokoll(self, lesson_id: str) -> list[dict[str, str]]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT datum, notiz FROM bestaetigungen WHERE lesson_id = ? ORDER BY datum", (lesson_id,)
            )
        ]

    def liste(
        self,
        where: str = "",
        params: Iterable[Any] = (),
        limit: int = 50,
        offset: int = 0,
    ) -> list[Lesson]:
        sql = f"SELECT {LESSON_COLUMNS} FROM lessons {where} ORDER BY erstellt_am DESC LIMIT ? OFFSET ?"
        return [row_to_lesson(r) for r in self.conn.execute(sql, (*params, limit, offset))]

    def alle(self) -> list[Lesson]:
        return [row_to_lesson(r) for r in self.conn.execute(f"SELECT {LESSON_COLUMNS} FROM lessons ORDER BY erstellt_am")]

    def embeddings(self, where: str = "", params: Iterable[Any] = ()) -> list[tuple[str, str, np.ndarray]]:
        sql = f"SELECT id, embedding_modell, embedding FROM lessons WHERE embedding IS NOT NULL {where}"
        return [(r["id"], r["embedding_modell"], blob_to_vector(r["embedding"])) for r in self.conn.execute(sql, tuple(params))]

    def statistik(self) -> dict[str, Any]:
        q = self.conn.execute
        gesamt = q("SELECT COUNT(*) FROM lessons").fetchone()[0]
        pro_bereich = {r[0]: r[1] for r in q("SELECT bereich, COUNT(*) FROM lessons GROUP BY bereich")}
        pro_status = {r[0]: r[1] for r in q("SELECT status, COUNT(*) FROM lessons GROUP BY status")}
        letzte_7 = q("SELECT COUNT(*) FROM lessons WHERE quelle != 'import' AND erstellt_am >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-7 days')").fetchone()[0]
        letzte_30 = q("SELECT COUNT(*) FROM lessons WHERE quelle != 'import' AND erstellt_am >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-30 days')").fetchone()[0]
        importiert = q("SELECT COUNT(*) FROM lessons WHERE quelle = 'import'").fetchone()[0]
        dauer = q(
            "SELECT AVG(erfassung_sekunden), COUNT(erfassung_sekunden), "
            "SUM(CASE WHEN erfassung_sekunden <= 30 THEN 1 ELSE 0 END) FROM lessons WHERE erfassung_sekunden IS NOT NULL"
        ).fetchone()
        ohne_massnahme = q("SELECT COUNT(*) FROM lessons WHERE massnahme = '' AND status != 'überholt'").fetchone()[0]
        return {
            "gesamt": gesamt,
            "importiert": importiert,
            "neu_erfasst_7_tage": letzte_7,
            "neu_erfasst_30_tage": letzte_30,
            "pro_bereich": pro_bereich,
            "pro_status": pro_status,
            "erfassung_sekunden_schnitt": round(dauer[0], 1) if dauer[0] is not None else None,
            "erfassungen_gemessen": dauer[1],
            "erfassungen_unter_30s": dauer[2] or 0,
            "ohne_massnahme": ohne_massnahme,
        }
