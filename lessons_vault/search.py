"""Volltext-, semantische und hybride Suche."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from .embeddings import EmbeddingProvider
from .models import Lesson
from .repository import Repository

Modus = Literal["hybrid", "volltext", "semantisch"]

STOPPWOERTER = {
    "aber", "alle", "als", "also", "auch", "auf", "aus", "bei", "bin", "bis", "das", "dass", "dem", "den", "der",
    "des", "die", "dies", "diese", "dieser", "doch", "ein", "eine", "einem", "einen", "einer", "für", "gibt",
    "habe", "haben", "hat", "ich", "ihr", "immer", "ist", "kann", "mal", "man", "mein", "meine", "mir", "mit",
    "nach", "nicht", "noch", "nur", "oder", "sich", "sie", "sind", "über", "und", "uns", "von", "vor", "war",
    "was", "weiß", "weiss", "wenn", "wer", "wie", "wir", "wird", "zum", "zur", "zu", "gelernt", "lessons",
    "lesson", "erfahrung", "erfahrungen", "wissen", "welche", "welcher", "gab", "gibt's",
}
RRF_K = 60


@dataclass
class Filter:
    bereich: str | None = None
    status: str | None = None
    schweregrad_min: int | None = None
    von: str | None = None
    bis: str | None = None
    ohne_ueberholt: bool = False
    art: str | None = None
    phase: str | None = None

    def sql(self, alias: str = "") -> tuple[str, list]:
        p = f"{alias}." if alias else ""
        clauses, params = [], []
        if self.art:
            clauses.append(f"{p}art = ?")
            params.append(self.art)
        if self.phase:
            clauses.append(f"{p}phase = ?")
            params.append(self.phase)
        if self.bereich:
            clauses.append(f"{p}bereich = ?")
            params.append(self.bereich)
        if self.status:
            clauses.append(f"{p}status = ?")
            params.append(self.status)
        elif self.ohne_ueberholt:
            clauses.append(f"{p}status != 'überholt'")
        if self.schweregrad_min:
            clauses.append(f"{p}schweregrad >= ?")
            params.append(self.schweregrad_min)
        if self.von:
            clauses.append(f"substr({p}erstellt_am, 1, 10) >= ?")
            params.append(self.von[:10])
        if self.bis:
            clauses.append(f"substr({p}erstellt_am, 1, 10) <= ?")
            params.append(self.bis[:10])
        return " AND ".join(clauses), params


@dataclass
class Treffer:
    lesson: Lesson
    score: float
    gefunden_durch: list[str] = field(default_factory=list)


def suchbegriffe(query: str) -> list[str]:
    woerter = re.findall(r"[\wäöüÄÖÜß]+", query.lower())
    begriffe = []
    for wort in woerter:
        if len(wort) < 3 or wort in STOPPWOERTER:
            continue
        # Plural/Flexion grob kappen, damit "Bankgespräche" auch "Bankgespräch" findet (Trigram = Teilstring).
        stamm = re.sub(r"(en|er|es|e|n|s)$", "", wort) if len(wort) > 5 else wort
        if stamm not in begriffe:
            begriffe.append(stamm)
    return begriffe


def fts_query(query: str) -> str:
    begriffe = suchbegriffe(query)
    return " OR ".join('"' + b.replace('"', '""') + '"' for b in begriffe)


class Suche:
    def __init__(self, repo: Repository, provider: EmbeddingProvider):
        self.repo = repo
        self.provider = provider

    def volltext(self, query: str, filt: Filter, limit: int = 50) -> list[tuple[str, float]]:
        match = fts_query(query)
        if not match:
            return []
        where, params = filt.sql("l")
        sql = (
            "SELECT l.id, bm25(lessons_fts, 4.0, 1.0, 1.0, 3.0, 1.0, 2.0, 0.5) AS rank "
            "FROM lessons_fts JOIN lessons l ON l.rowid = lessons_fts.rowid "
            f"WHERE lessons_fts MATCH ? {'AND ' + where if where else ''} ORDER BY rank LIMIT ?"
        )
        rows = self.repo.conn.execute(sql, (match, *params, limit)).fetchall()
        return [(r["id"], -r["rank"]) for r in rows]

    def semantisch(self, query: str, filt: Filter, limit: int = 50, min_score: float | None = None) -> list[tuple[str, float]]:
        where, params = filt.sql()
        rows = [r for r in self.repo.embeddings(f"AND {where}" if where else "", params) if r[1] == self.provider.name]
        if not rows or not query.strip():
            return []
        q = self.provider.embed([query], "query")[0]
        matrix = np.vstack([r[2] for r in rows])
        scores = matrix @ q
        schwelle = self.provider.kandidatenschwelle if min_score is None else min_score
        order = np.argsort(-scores)[:limit]
        return [(rows[i][0], float(scores[i])) for i in order if scores[i] >= schwelle]

    def suchen(self, query: str, modus: Modus = "hybrid", filt: Filter | None = None, limit: int = 30) -> list[Treffer]:
        filt = filt or Filter()
        if not query.strip():
            where, params = filt.sql()
            lessons = self.repo.liste(f"WHERE {where}" if where else "", params, limit=limit)
            return [Treffer(l, 0.0, []) for l in lessons]

        listen: dict[str, list[tuple[str, float]]] = {}
        if modus in ("hybrid", "volltext"):
            listen["volltext"] = self.volltext(query, filt)
        if modus in ("hybrid", "semantisch"):
            listen["semantisch"] = self.semantisch(query, filt)

        scores: dict[str, float] = {}
        quellen: dict[str, list[str]] = {}
        for name, eintraege in listen.items():
            for rang, (lesson_id, _) in enumerate(eintraege):
                scores[lesson_id] = scores.get(lesson_id, 0.0) + 1.0 / (RRF_K + rang + 1)
                quellen.setdefault(lesson_id, []).append(name)

        ids = sorted(scores, key=lambda i: scores[i], reverse=True)[:limit]
        return [Treffer(self.repo.holen(i), round(scores[i], 5), quellen[i]) for i in ids]
