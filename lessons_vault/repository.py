"""Datenzugriff auf Lessons, Bereiche, Bestätigungen und Einstellungen."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np

from .models import Bereich, Einstellungen, Entwurf, EntwurfEintrag, Lesson, LessonImport, LessonIn, LessonUpdate

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
    def __init__(self, conn: Any):
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

    def lessons_ohne_embedding(self, modell: str, limit: int = 16) -> list[Lesson]:
        rows = self.conn.execute(
            f"SELECT {LESSON_COLUMNS} FROM lessons WHERE embedding IS NULL OR embedding_modell != ? "
            "ORDER BY erstellt_am LIMIT ?",
            (modell, limit),
        )
        return [row_to_lesson(r) for r in rows]

    # Entwürfe (Hintergrund-Warteschlange) ---------------------------------
    @staticmethod
    def _row_to_entwurf(row: Any) -> EntwurfEintrag:
        data = dict(row)
        raw = data.pop("entwurf_json")
        data["entwurf"] = Entwurf.model_validate_json(raw) if raw else None
        return EntwurfEintrag(**data)

    def entwurf_anlegen(self, rohtext: str, quelle: str, bereich_vorgabe: str = "", erfassung_sekunden: float | None = None) -> EntwurfEintrag:
        entwurf_id, now = str(uuid.uuid4()), jetzt()
        with self.conn:
            self.conn.execute(
                "INSERT INTO entwuerfe(id, rohtext, quelle, bereich_vorgabe, erfassung_sekunden, erstellt_am, geaendert_am) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (entwurf_id, rohtext.strip(), quelle, bereich_vorgabe, erfassung_sekunden, now, now),
            )
        return self.entwurf_holen(entwurf_id)

    def entwurf_holen(self, entwurf_id: str) -> EntwurfEintrag:
        row = self.conn.execute("SELECT * FROM entwuerfe WHERE id = ?", (entwurf_id,)).fetchone()
        if row is None:
            raise NotFound(entwurf_id)
        return self._row_to_entwurf(row)

    def entwuerfe(self) -> list[EntwurfEintrag]:
        rows = self.conn.execute("SELECT * FROM entwuerfe ORDER BY erstellt_am DESC")
        return [self._row_to_entwurf(r) for r in rows]

    def entwuerfe_zaehlen(self) -> dict[str, int]:
        counts = {"wartet": 0, "in_arbeit": 0, "fertig": 0, "fehler": 0}
        for row in self.conn.execute("SELECT status, COUNT(*) AS n FROM entwuerfe GROUP BY status"):
            counts[row["status"]] = row["n"]
        return counts

    def entwuerfe_suchen(self, begriffe: list[str], limit: int = 10) -> list[EntwurfEintrag]:
        if not begriffe:
            return []
        clauses = " OR ".join("lower(rohtext) LIKE ?" for _ in begriffe)
        rows = self.conn.execute(
            f"SELECT * FROM entwuerfe WHERE {clauses} ORDER BY erstellt_am DESC LIMIT ?",
            (*[f"%{b.lower()}%" for b in begriffe], limit),
        )
        return [self._row_to_entwurf(r) for r in rows]

    def naechsten_entwurf_reservieren(self) -> EntwurfEintrag | None:
        with self.conn:
            row = self.conn.execute(
                "SELECT id FROM entwuerfe WHERE status = 'wartet' ORDER BY erstellt_am LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self.conn.execute(
                "UPDATE entwuerfe SET status = 'in_arbeit', geaendert_am = ? WHERE id = ?", (jetzt(), row["id"])
            )
        return self.entwurf_holen(row["id"])

    def entwurf_ergebnis(self, entwurf_id: str, entwurf: Entwurf | None, status: str, fehler: str, modell: str, dauer: float) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE entwuerfe SET entwurf_json = ?, status = ?, fehler = ?, modell = ?, dauer_sekunden = ?, "
                "geaendert_am = ? WHERE id = ?",
                (entwurf.model_dump_json() if entwurf else "", status, fehler, modell, round(dauer, 1), jetzt(), entwurf_id),
            )

    def entwurf_neu_einreihen(self, entwurf_id: str, rueckfrage: str | None = None, antwort: str | None = None) -> EntwurfEintrag:
        eintrag = self.entwurf_holen(entwurf_id)
        if eintrag.status == "in_arbeit":
            raise Invalid("Entwurf wird gerade verarbeitet")
        with self.conn:
            self.conn.execute(
                "UPDATE entwuerfe SET status = 'wartet', fehler = '', rueckfrage = ?, antwort = ?, geaendert_am = ? WHERE id = ?",
                (eintrag.rueckfrage if rueckfrage is None else rueckfrage, eintrag.antwort if antwort is None else antwort, jetzt(), entwurf_id),
            )
        return self.entwurf_holen(entwurf_id)

    def entwurf_loeschen(self, entwurf_id: str) -> None:
        with self.conn:
            if self.conn.execute("DELETE FROM entwuerfe WHERE id = ?", (entwurf_id,)).rowcount == 0:
                raise NotFound(entwurf_id)

    def entwuerfe_zuruecksetzen(self) -> int:
        """Nach einem Neustart: abgebrochene Verarbeitungen wieder einreihen."""
        with self.conn:
            return self.conn.execute("UPDATE entwuerfe SET status = 'wartet' WHERE status = 'in_arbeit'").rowcount

    # Briefings -------------------------------------------------------------
    def briefing_anlegen(
        self,
        situation: str,
        bereich: str,
        treffer: list[dict[str, Any]],
        checkliste: list[dict[str, str]],
        embedding: np.ndarray | None,
        embedding_modell: str,
    ) -> str:
        briefing_id = str(uuid.uuid4())
        with self.conn:
            self.conn.execute(
                "INSERT INTO briefings(id, situation, bereich, treffer_json, checkliste_json, embedding, embedding_modell, erstellt_am) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (briefing_id, situation.strip(), bereich, json.dumps(treffer, ensure_ascii=False),
                 json.dumps(checkliste, ensure_ascii=False), vector_to_blob(embedding), embedding_modell, jetzt()),
            )
        return briefing_id

    def briefing_holen(self, briefing_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT id, situation, bereich, treffer_json, checkliste_json, zusammenfassung, ki_checkliste_json, ki_modell, erstellt_am "
            "FROM briefings WHERE id = ?",
            (briefing_id,),
        ).fetchone()
        if row is None:
            raise NotFound(briefing_id)
        data = dict(row)
        data["treffer"] = json.loads(data.pop("treffer_json"))
        data["checkliste"] = json.loads(data.pop("checkliste_json"))
        raw = data.pop("ki_checkliste_json")
        data["ki_checkliste"] = json.loads(raw) if raw else None
        data["feedback"] = self.feedback_fuer_briefing(briefing_id)
        return data

    def briefing_ki_setzen(self, briefing_id: str, zusammenfassung: str, checkliste: list[dict[str, str]], modell: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE briefings SET zusammenfassung = ?, ki_checkliste_json = ?, ki_modell = ? WHERE id = ?",
                (zusammenfassung, json.dumps(checkliste, ensure_ascii=False), modell, briefing_id),
            )

    def briefings(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT b.id, b.situation, b.bereich, b.erstellt_am, json_array_length(b.treffer_json) AS anzahl, "
            "(SELECT COUNT(*) FROM briefing_feedback f WHERE f.briefing_id = b.id AND f.bewertung = 'hilfreich') AS hilfreich "
            "FROM briefings b ORDER BY b.erstellt_am DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def briefing_loeschen(self, briefing_id: str) -> None:
        with self.conn:
            if self.conn.execute("DELETE FROM briefings WHERE id = ?", (briefing_id,)).rowcount == 0:
                raise NotFound(briefing_id)

    def feedback_setzen(self, briefing_id: str, lesson_id: str, bewertung: str | None) -> None:
        self.briefing_holen(briefing_id)
        self.holen(lesson_id)
        with self.conn:
            if bewertung:
                self.conn.execute(
                    "INSERT INTO briefing_feedback(briefing_id, lesson_id, bewertung, datum) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(briefing_id, lesson_id) DO UPDATE SET bewertung = excluded.bewertung, datum = excluded.datum",
                    (briefing_id, lesson_id, bewertung, jetzt()),
                )
            else:
                self.conn.execute(
                    "DELETE FROM briefing_feedback WHERE briefing_id = ? AND lesson_id = ?", (briefing_id, lesson_id)
                )

    def feedback_fuer_briefing(self, briefing_id: str) -> dict[str, str]:
        rows = self.conn.execute("SELECT lesson_id, bewertung FROM briefing_feedback WHERE briefing_id = ?", (briefing_id,))
        return {r["lesson_id"]: r["bewertung"] for r in rows}

    def feedback_alle(self, ausser_briefing: str = "") -> list[tuple[str, str, np.ndarray | None, str]]:
        rows = self.conn.execute(
            "SELECT f.lesson_id, f.bewertung, b.embedding, b.embedding_modell FROM briefing_feedback f "
            "JOIN briefings b ON b.id = f.briefing_id WHERE f.briefing_id != ?",
            (ausser_briefing,),
        )
        return [(r["lesson_id"], r["bewertung"], blob_to_vector(r["embedding"]), r["embedding_modell"]) for r in rows]

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
        offene_entwuerfe = q("SELECT COUNT(*) FROM entwuerfe").fetchone()[0]
        briefings = q("SELECT COUNT(*) FROM briefings").fetchone()[0]
        briefings_bewertet = q("SELECT COUNT(DISTINCT briefing_id) FROM briefing_feedback").fetchone()[0]
        briefings_hilfreich = q(
            "SELECT COUNT(DISTINCT briefing_id) FROM briefing_feedback WHERE bewertung = 'hilfreich'"
        ).fetchone()[0]
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
            "offene_entwuerfe": offene_entwuerfe,
            "briefings": briefings,
            "briefings_bewertet": briefings_bewertet,
            "briefings_hilfreich": briefings_hilfreich,
        }
