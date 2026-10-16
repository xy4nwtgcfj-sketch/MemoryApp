"""FastAPI-Anwendung: REST-API und Auslieferung der PWA."""

from __future__ import annotations

import hmac
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from . import __version__, db
from .compliance import lesson_text_fuer_pruefung, pruefen
from .config import Settings, load_settings
from .embeddings import EmbeddingFehler, EmbeddingProvider, create_provider, lesson_text, modell_installiert, ollama_status
from .models import (
    AntwortIn,
    Bereich,
    BereichUpdate,
    BestaetigungIn,
    DublettenKandidat,
    Einstellungen,
    Entwurf,
    EntwurfAnfrage,
    EntwurfEintrag,
    ErfassenAnfrage,
    Lesson,
    LessonImport,
    LessonIn,
    LessonUpdate,
)
from .repository import Invalid, NotFound, Repository
from .search import Filter, Suche, suchbegriffe
from .structuring import BasisStrukturierer, OllamaStrukturierer, create_strukturierer, manueller_entwurf
from .worker import Hintergrund

log = logging.getLogger("lessons_vault")
STATIC_DIR = Path(__file__).parent / "static"
TEXTFELDER = {"titel", "situation", "ereignis", "lesson", "massnahme", "tags"}


class LessonAntwort(BaseModel):
    lesson: Lesson
    compliance_hinweise: list[str] = []
    embedding_fehler: str = ""


class CompliancePruefung(BaseModel):
    text: str
    bereich: str = ""


class ImportErgebnis(BaseModel):
    importiert: int
    uebersprungen: int
    fehler: list[str]


def create_app(
    settings: Settings | None = None,
    strukturierer: BasisStrukturierer | None = None,
    provider: EmbeddingProvider | None = None,
    lokal: OllamaStrukturierer | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    conn = db.connect(settings.db_path)
    repo = Repository(conn)
    provider = provider or create_provider(
        settings.embedding_provider, settings.voyage_api_key, settings.voyage_model,
        settings.ollama_url, settings.ollama_embed_model,
    )
    strukturierer = strukturierer or create_strukturierer(settings.anthropic_api_key, settings.claude_model, settings.claude_effort)
    if lokal is None and settings.ollama_model:
        lokal = OllamaStrukturierer(settings.ollama_url, settings.ollama_model)
    suche = Suche(repo, provider)
    ollama_cache: dict[str, Any] = {"zeit": 0.0, "status": {"erreichbar": False, "modelle": []}}

    def lokal_status() -> dict[str, Any]:
        """Ollama-Status, 30 Sekunden zwischengespeichert."""
        if lokal is None:
            return {"erreichbar": False, "modelle": []}
        if time.monotonic() - ollama_cache["zeit"] > 30:
            ollama_cache["status"] = ollama_status(lokal.url)
            ollama_cache["zeit"] = time.monotonic()
        return ollama_cache["status"]

    def lokal_bereit() -> bool:
        status = lokal_status()
        return bool(lokal and status["erreichbar"] and modell_installiert(lokal.model, status["modelle"]))

    def modus_fuer(bereich: str, einst: Einstellungen | None = None) -> str:
        """Wirksamer Strukturierungsmodus: claude, lokal oder manuell."""
        einst = einst or repo.einstellungen()
        modus = einst.strukturierung_bereiche.get(bereich, einst.strukturierung_standard) if bereich else einst.strukturierung_standard
        if modus == "auto":
            if strukturierer.verfuegbar:
                return "claude"
            return "lokal" if lokal_bereit() else "manuell"
        if modus == "lokal" and lokal is None:
            return "manuell"
        return modus

    def lokale_bereiche(einst: Einstellungen | None = None) -> set[str]:
        einst = einst or repo.einstellungen()
        return {b.name for b in repo.bereiche() if modus_fuer(b.name, einst) == "lokal"}

    def verarbeite_lokal(eintrag: EntwurfEintrag) -> Entwurf:
        assert lokal is not None
        bereiche = bereiche_fuer(eintrag.bereich_vorgabe)
        voller_text = eintrag.rohtext if not eintrag.antwort else f"{eintrag.rohtext}\n{eintrag.antwort}"
        kandidaten = kandidaten_fuer(voller_text)
        ergebnis = lokal.strukturieren(eintrag.rohtext, eintrag.quelle, bereiche, kandidaten, eintrag.rueckfrage, eintrag.antwort)
        return fertigstellen(ergebnis, kandidaten, voller_text, eintrag.bereich_vorgabe)

    worker = Hintergrund(repo, provider, verarbeite_lokal, lokal.name if lokal else "")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.worker_aktiv:
            worker.start()
        yield
        worker.stop()

    app = FastAPI(title="Lessons Vault", version=__version__, lifespan=lifespan)
    app.state.repo = repo
    app.state.provider = provider
    app.state.strukturierer = strukturierer
    app.state.worker = worker

    def auth(request: Request) -> None:
        if not settings.token:
            return
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(supplied.encode(), settings.token.encode()):
            raise HTTPException(status_code=401, detail="Token fehlt oder ist falsch")

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"Nicht gefunden: {exc}"})

    @app.exception_handler(Invalid)
    async def _invalid(_: Request, exc: Invalid) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def embed_lesson(data: Any) -> tuple[Any, str, str]:
        text = lesson_text(data.titel, data.situation, data.ereignis, data.lesson, data.massnahme, data.tags)
        try:
            return provider.embed([text], "document")[0], provider.name, ""
        except EmbeddingFehler as exc:
            log.warning("%s", exc)
            return None, "", "Embedding fehlgeschlagen, Lesson ist nur per Volltext auffindbar. Später 'Neu indexieren'."

    def compliance(data: Any) -> list[str]:
        text = lesson_text_fuer_pruefung(data.titel, data.situation, data.ereignis, data.lesson, data.massnahme, tags=data.tags)
        return pruefen(text, data.bereich, repo.einstellungen().sperrliste)

    deps = [Depends(auth)]

    # Status und Konfiguration -------------------------------------------
    @app.get("/api/status", dependencies=deps)
    def status() -> dict[str, Any]:
        einst = repo.einstellungen()
        ls = lokal_status()
        return {
            "version": __version__,
            "ki": strukturierer.verfuegbar,
            "modell": settings.claude_model if strukturierer.verfuegbar else "",
            "embeddings": provider.name,
            "semantisch": provider.semantisch,
            "lokal": {
                "konfiguriert": lokal is not None,
                "modell": lokal.model if lokal else "",
                "erreichbar": ls["erreichbar"],
                "modell_installiert": bool(lokal and modell_installiert(lokal.model, ls["modelle"])),
                "embed_modell": settings.ollama_embed_model,
                "embed_modell_installiert": modell_installiert(settings.ollama_embed_model, ls["modelle"]),
            },
            "modi": {b.name: modus_fuer(b.name, einst) for b in repo.bereiche()},
            "modus_standard": modus_fuer("", einst),
        }

    @app.get("/api/bereiche", dependencies=deps)
    def bereiche_liste() -> list[Bereich]:
        return repo.bereiche()

    @app.post("/api/bereiche", dependencies=deps, status_code=201)
    def bereich_anlegen(bereich: Bereich) -> Bereich:
        return repo.bereich_anlegen(bereich)

    @app.patch("/api/bereiche/{name}", dependencies=deps)
    def bereich_aendern(name: str, update: BereichUpdate) -> Bereich:
        return repo.bereich_aendern(name, update.aktiv, update.beispiele)

    @app.get("/api/einstellungen", dependencies=deps)
    def einstellungen() -> Einstellungen:
        return repo.einstellungen()

    @app.put("/api/einstellungen", dependencies=deps)
    def einstellungen_speichern(data: Einstellungen) -> Einstellungen:
        data.sperrliste = sorted({s.strip() for s in data.sperrliste if s.strip()}, key=str.lower)
        bekannte = {b.name for b in repo.bereiche()}
        data.strukturierung_bereiche = {k: v for k, v in data.strukturierung_bereiche.items() if k in bekannte}
        return repo.einstellungen_speichern(data)

    # Erfassen ------------------------------------------------------------
    def kandidaten_fuer(text: str, ausschliessen: set[str] | None = None) -> list[DublettenKandidat]:
        filt = Filter(ohne_ueberholt=True)
        try:
            ergebnisse = suche.semantisch(text, filt, limit=15)
        except EmbeddingFehler:
            ergebnisse = suche.volltext(text, filt, limit=15)
        kandidaten = []
        for lesson_id, score in ergebnisse:
            l = repo.holen(lesson_id)
            if ausschliessen and l.bereich in ausschliessen:
                continue
            kandidaten.append(
                DublettenKandidat(
                    id=l.id, titel=l.titel, lesson=l.lesson, bereich=l.bereich, status=l.status,
                    bestaetigungen=l.bestaetigungen, aehnlichkeit=round(score, 3),
                )
            )
            if len(kandidaten) == 5:
                break
        return kandidaten

    def bereiche_fuer(vorgabe: str) -> list[Bereich]:
        aktive = repo.bereiche(nur_aktive=True)
        if vorgabe:
            passend = [b for b in repo.bereiche() if b.name == vorgabe]
            if passend:
                return passend
        return aktive

    def fertigstellen(ergebnis: Entwurf, kandidaten: list[DublettenKandidat], voller_text: str, vorgabe: str = "") -> Entwurf:
        if vorgabe and repo.bereich_existiert(vorgabe):
            ergebnis.bereich = vorgabe
            ergebnis.fehlende_felder = [f for f in ergebnis.fehlende_felder if f != "bereich"]
        if not ergebnis.ki_verwendet and kandidaten:
            besten = kandidaten[0]
            if besten.aehnlichkeit >= provider.dublettenschwelle:
                ergebnis.dublette = besten
                ergebnis.dublette_begruendung = f"Sehr ähnlicher Text (Ähnlichkeit {besten.aehnlichkeit:.2f})."
        ergebnis.aehnliche = [k for k in kandidaten if not ergebnis.dublette or k.id != ergebnis.dublette.id]
        lokale = pruefen(
            lesson_text_fuer_pruefung(voller_text, ergebnis.titel, ergebnis.situation, ergebnis.ereignis,
                                      ergebnis.lesson, ergebnis.massnahme, tags=ergebnis.tags),
            ergebnis.bereich,
            repo.einstellungen().sperrliste,
        )
        ergebnis.compliance_hinweise = list(dict.fromkeys([*lokale, *ergebnis.compliance_hinweise]))
        return ergebnis

    def sofort_entwurf(text: str, quelle: str, vorgabe: str, modus: str, rueckfrage: str = "", antwort: str = "") -> Entwurf:
        voller_text = text if not antwort else f"{text}\n{antwort}"
        bereiche = bereiche_fuer(vorgabe)
        if modus == "claude":
            # Datenschutz: Lessons aus lokal verarbeiteten Bereichen gehen nie an Claude.
            kandidaten = kandidaten_fuer(voller_text, ausschliessen=lokale_bereiche())
            ergebnis = strukturierer.strukturieren(text, quelle, bereiche, kandidaten, rueckfrage, antwort)  # type: ignore[arg-type]
        else:
            kandidaten = kandidaten_fuer(voller_text)
            ergebnis = manueller_entwurf(voller_text, quelle, bereiche)  # type: ignore[arg-type]
        return fertigstellen(ergebnis, kandidaten, voller_text, vorgabe)

    @app.post("/api/erfassen", dependencies=deps)
    def erfassen(anfrage: ErfassenAnfrage) -> dict[str, Any]:
        """Einstieg der Erfassung: sofortiger Entwurf (Claude/manuell) oder Warteschlange (lokal)."""
        vorgabe = anfrage.bereich if anfrage.bereich and repo.bereich_existiert(anfrage.bereich) else ""
        modus = modus_fuer(vorgabe)
        if modus == "lokal":
            eintrag = repo.entwurf_anlegen(anfrage.text, anfrage.quelle, vorgabe, anfrage.erfassung_sekunden)
            worker.wecken()
            return {"modus": "hintergrund", "eintrag": eintrag, "warteschlange": repo.entwuerfe_zaehlen()["wartet"]}
        return {"modus": "sofort", "entwurf": sofort_entwurf(anfrage.text, anfrage.quelle, vorgabe, modus)}

    @app.post("/api/erfassen/entwurf", dependencies=deps)
    def entwurf(anfrage: EntwurfAnfrage) -> Entwurf:
        vorgabe = anfrage.bereich if anfrage.bereich and repo.bereich_existiert(anfrage.bereich) else ""
        modus = modus_fuer(vorgabe)
        if modus == "lokal":
            # Rückfrage-Runde eines lokalen Bereichs nie über Claude schicken.
            modus = "manuell"
        return sofort_entwurf(anfrage.text, anfrage.quelle, vorgabe, modus, anfrage.rueckfrage, anfrage.antwort)

    # Entwürfe (Hintergrund) ----------------------------------------------
    @app.get("/api/entwuerfe", dependencies=deps)
    def entwuerfe(q: str = "") -> dict[str, Any]:
        eintraege = repo.entwuerfe_suchen(suchbegriffe(q)) if q.strip() else repo.entwuerfe()
        return {"eintraege": eintraege, "zaehler": repo.entwuerfe_zaehlen(), "aktuell": worker.aktueller_entwurf}

    @app.get("/api/entwuerfe/{entwurf_id}", dependencies=deps)
    def entwurf_holen(entwurf_id: str) -> EntwurfEintrag:
        return repo.entwurf_holen(entwurf_id)

    @app.post("/api/entwuerfe/{entwurf_id}/antwort", dependencies=deps)
    def entwurf_antwort(entwurf_id: str, data: AntwortIn) -> EntwurfEintrag:
        eintrag = repo.entwurf_holen(entwurf_id)
        frage = eintrag.entwurf.rueckfrage if eintrag.entwurf else ""
        eintrag = repo.entwurf_neu_einreihen(entwurf_id, rueckfrage=frage or "Ergänzung", antwort=data.antwort)
        worker.wecken()
        return eintrag

    @app.post("/api/entwuerfe/{entwurf_id}/neu", dependencies=deps)
    def entwurf_neu(entwurf_id: str) -> EntwurfEintrag:
        eintrag = repo.entwurf_neu_einreihen(entwurf_id)
        worker.wecken()
        return eintrag

    @app.delete("/api/entwuerfe/{entwurf_id}", dependencies=deps, status_code=204)
    def entwurf_loeschen(entwurf_id: str) -> None:
        repo.entwurf_loeschen(entwurf_id)

    @app.post("/api/compliance", dependencies=deps)
    def compliance_pruefen(data: CompliancePruefung) -> list[str]:
        return pruefen(data.text, data.bereich, repo.einstellungen().sperrliste)

    # Lessons -------------------------------------------------------------
    @app.get("/api/lessons", dependencies=deps)
    def lessons_liste(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> list[Lesson]:
        return repo.liste(limit=limit, offset=offset)

    @app.post("/api/lessons", dependencies=deps, status_code=201)
    def lesson_anlegen(data: LessonIn) -> LessonAntwort:
        eintrag = None
        if data.entwurf_id:
            eintrag = repo.entwurf_holen(data.entwurf_id)
            # Erfassungsdauer zählt bis zum Absenden des Rohtexts, nicht bis zur späteren Prüfung.
            data = data.model_copy(update={"quelle": eintrag.quelle, "erfassung_sekunden": eintrag.erfassung_sekunden})
        vector, modell, fehler = embed_lesson(data)
        lesson = repo.anlegen(data, vector, modell)
        if eintrag:
            repo.entwurf_loeschen(eintrag.id)
        return LessonAntwort(lesson=lesson, compliance_hinweise=compliance(data), embedding_fehler=fehler)

    @app.get("/api/lessons/{lesson_id}", dependencies=deps)
    def lesson_holen(lesson_id: str) -> dict[str, Any]:
        lesson = repo.holen(lesson_id)
        return {
            "lesson": lesson,
            "protokoll": repo.bestaetigungs_protokoll(lesson_id),
            "compliance_hinweise": compliance(lesson),
        }

    @app.put("/api/lessons/{lesson_id}", dependencies=deps)
    def lesson_aendern(lesson_id: str, update: LessonUpdate) -> LessonAntwort:
        vorher = repo.holen(lesson_id)
        changed = update.model_dump(exclude_unset=True, exclude_none=True)
        vector, modell, fehler = None, None, ""
        if TEXTFELDER & changed.keys():
            merged = vorher.model_copy(update=changed)
            vector, modell, fehler = embed_lesson(merged)
        lesson = repo.aendern(lesson_id, update, vector, modell)
        return LessonAntwort(lesson=lesson, compliance_hinweise=compliance(lesson), embedding_fehler=fehler)

    @app.delete("/api/lessons/{lesson_id}", dependencies=deps, status_code=204)
    def lesson_loeschen(lesson_id: str) -> None:
        repo.loeschen(lesson_id)

    @app.post("/api/lessons/{lesson_id}/bestaetigen", dependencies=deps)
    def lesson_bestaetigen(lesson_id: str, data: BestaetigungIn | None = None) -> Lesson:
        if data and data.entwurf_id:
            repo.entwurf_holen(data.entwurf_id)
        lesson = repo.bestaetigen(lesson_id, data.notiz if data else "")
        if data and data.entwurf_id:
            repo.entwurf_loeschen(data.entwurf_id)
        return lesson

    # Suche ---------------------------------------------------------------
    @app.get("/api/suche", dependencies=deps)
    def suchen(
        q: str = "",
        modus: str = Query("hybrid", pattern="^(hybrid|volltext|semantisch)$"),
        bereich: str | None = None,
        status: str | None = Query(None, pattern="^(neu|bestätigt|überholt)$"),
        schweregrad_min: int | None = Query(None, ge=1, le=5),
        von: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}"),
        bis: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}"),
        limit: int = Query(30, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        filt = Filter(bereich=bereich or None, status=status or None, schweregrad_min=schweregrad_min, von=von, bis=bis)
        try:
            treffer = suche.suchen(q, modus, filt, limit)  # type: ignore[arg-type]
        except EmbeddingFehler as exc:
            log.warning("%s", exc)
            treffer = suche.suchen(q, "volltext", filt, limit)
        return [{"lesson": t.lesson, "score": t.score, "gefunden_durch": t.gefunden_durch} for t in treffer]

    # Bestand ---------------------------------------------------------------
    @app.get("/api/export", dependencies=deps)
    def export() -> JSONResponse:
        payload = {
            "format": "lessons-vault",
            "version": 1,
            "exportiert_am": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bereiche": [b.model_dump() for b in repo.bereiche()],
            "lessons": [l.model_dump(exclude={"embedding_modell", "erfassung_sekunden"}) for l in repo.alle()],
        }
        stamp = datetime.now().strftime("%Y-%m-%d")
        return JSONResponse(
            payload, headers={"Content-Disposition": f'attachment; filename="lessons-vault-{stamp}.json"'}
        )

    @app.post("/api/import", dependencies=deps)
    def importieren(payload: dict[str, Any] | list[Any]) -> ImportErgebnis:
        if isinstance(payload, dict):
            for b in payload.get("bereiche", []):
                try:
                    bereich = Bereich(**b)
                except ValidationError:
                    continue
                if not repo.bereich_existiert(bereich.name):
                    repo.bereich_anlegen(bereich)
            eintraege = payload.get("lessons", [])
        else:
            eintraege = payload
        importiert, uebersprungen, fehler = 0, 0, []
        gueltige: list[LessonImport] = []
        for i, eintrag in enumerate(eintraege, start=1):
            try:
                item = LessonImport(**eintrag)
            except (ValidationError, TypeError) as exc:
                msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
                fehler.append(f"Eintrag {i}: {msg}")
                continue
            if item.id and repo.existiert(item.id):
                uebersprungen += 1
                continue
            if not repo.bereich_existiert(item.bereich):
                fehler.append(f"Eintrag {i} ({item.titel}): unbekannter Bereich '{item.bereich}'")
                continue
            gueltige.append(item)
        texte = [lesson_text(g.titel, g.situation, g.ereignis, g.lesson, g.massnahme, g.tags) for g in gueltige]
        vektoren: list[Any] = [None] * len(gueltige)
        try:
            for start in range(0, len(texte), 64):
                vektoren[start : start + 64] = provider.embed(texte[start : start + 64], "document")
        except EmbeddingFehler as exc:
            fehler.append(f"Embeddings fehlgeschlagen ({exc}). Lessons ohne Embedding importiert, bitte neu indexieren.")
        for item, vector in zip(gueltige, vektoren):
            try:
                repo.anlegen(item, vector, provider.name if vector is not None else "")
                importiert += 1
            except Invalid as exc:
                fehler.append(f"{item.titel}: {exc}")
        return ImportErgebnis(importiert=importiert, uebersprungen=uebersprungen, fehler=fehler)

    @app.post("/api/reindex", dependencies=deps)
    def reindex() -> dict[str, Any]:
        lessons = repo.alle()
        anzahl = 0
        for start in range(0, len(lessons), 64):
            batch = lessons[start : start + 64]
            texte = [lesson_text(l.titel, l.situation, l.ereignis, l.lesson, l.massnahme, l.tags) for l in batch]
            try:
                vektoren = provider.embed(texte, "document")
            except EmbeddingFehler as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            for lesson, vector in zip(batch, vektoren):
                repo.embedding_setzen(lesson.id, vector, provider.name)
                anzahl += 1
        return {"neu_indexiert": anzahl, "embeddings": provider.name}

    @app.get("/api/statistik", dependencies=deps)
    def statistik() -> dict[str, Any]:
        return repo.statistik()

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def app_factory() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app()
