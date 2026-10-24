"""Pydantic-Modelle für API und Repository."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Status = Literal["neu", "bestätigt", "überholt"]
Quelle = Literal["text", "sprache", "import"]
# Eintragsart: erfahrung = Ereignis mit Regel; wissen = Fakten und Zusammenhänge; vorgehen = Ablauf oder
# Checkliste; entscheidung = was entschieden wurde und warum. Die Felder bedeuten je Art etwas anderes
# (situation = Kontext, ereignis = Inhalt, lesson = Kernaussage, massnahme = Anwendung).
Art = Literal["erfahrung", "wissen", "vorgehen", "entscheidung"]
ARTEN: tuple[str, ...] = ("erfahrung", "wissen", "vorgehen", "entscheidung")
# Projektphase, nur für berufliche Bereiche; "" = phasenübergreifend
Phase = Literal["", "sales", "concept", "build", "test", "cutover", "hypercare"]
PHASEN: tuple[str, ...] = ("sales", "concept", "build", "test", "cutover", "hypercare")


def _clean_tags(tags: list[str]) -> list[str]:
    seen: list[str] = []
    for tag in tags:
        t = tag.strip().lstrip("#").strip()
        if t and t.lower() not in (s.lower() for s in seen):
            seen.append(t)
    return seen


class LessonBase(BaseModel):
    titel: str = Field(min_length=1, max_length=80)
    situation: str = Field(min_length=1)
    ereignis: str = Field(min_length=1)
    lesson: str = Field(min_length=1)
    massnahme: str = ""
    bereich: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    schweregrad: int = Field(ge=1, le=5)
    # True = persönliche Erfahrung, False = eher Allgemeinwissen, None = nicht eingeschätzt
    spezifisch: bool | None = None
    art: Art = "erfahrung"
    phase: Phase = ""

    @field_validator("titel", "situation", "ereignis", "lesson", "massnahme", "bereich")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return _clean_tags(value)


class LessonIn(LessonBase):
    quelle: Quelle = "text"
    erfassung_sekunden: float | None = Field(default=None, ge=0)
    entwurf_id: str | None = None
    bild_ids: list[str] = Field(default_factory=list, max_length=10)


class LessonImport(LessonBase):
    """Format für Startbestand und Backup-Import; id/Daten optional."""

    id: str | None = None
    status: Status = "neu"
    bestaetigungen: int = Field(default=1, ge=1)
    erstellt_am: str | None = None
    geaendert_am: str | None = None
    quelle: Quelle = "import"


class LessonUpdate(BaseModel):
    titel: str | None = Field(default=None, min_length=1, max_length=80)
    situation: str | None = Field(default=None, min_length=1)
    ereignis: str | None = Field(default=None, min_length=1)
    lesson: str | None = Field(default=None, min_length=1)
    massnahme: str | None = None
    bereich: str | None = None
    tags: list[str] | None = None
    schweregrad: int | None = Field(default=None, ge=1, le=5)
    status: Status | None = None
    spezifisch: bool | None = None
    art: Art | None = None
    phase: Phase | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _clean_tags(value)


class Lesson(LessonBase):
    id: str
    status: Status
    bestaetigungen: int
    erstellt_am: str
    geaendert_am: str
    quelle: Quelle
    embedding_modell: str = ""
    erfassung_sekunden: float | None = None


class Bereich(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    aktiv: bool = True
    beispiele: str = ""
    # Beruflich: strengere Namens- und Zahlenprüfung, Fotos standardmäßig nur per Texterkennung
    beruflich: bool = False


class BereichUpdate(BaseModel):
    aktiv: bool | None = None
    beispiele: str | None = None
    beruflich: bool | None = None


class Einstellungen(BaseModel):
    sperrliste: list[str] = Field(default_factory=list)
    # auto: Claude, wenn ein Key da ist, sonst lokal, wenn Ollama läuft, sonst manuell
    strukturierung_standard: Literal["auto", "claude", "lokal", "manuell"] = "auto"
    # Überschreibung pro Bereich, z. B. {"Beruf": "lokal"}
    strukturierung_bereiche: dict[str, Literal["claude", "lokal", "manuell"]] = Field(default_factory=dict)
    # Fotos: "text" = lokale Texterkennung, nur geprüfter Text an Claude; "bild" = Foto direkt an Claude.
    # Ohne Eintrag: Beruf "text", andere Bereiche "bild".
    bild_bereiche: dict[str, Literal["text", "bild"]] = Field(default_factory=dict)


class BestaetigungIn(BaseModel):
    notiz: str = ""
    entwurf_id: str | None = None
    bild_ids: list[str] = Field(default_factory=list, max_length=10)


class EntwurfAnfrage(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    quelle: Quelle = "text"
    bereich: str = ""
    freigabe: bool = False
    rueckfrage: str = ""
    antwort: str = ""


class DublettenKandidat(BaseModel):
    id: str
    titel: str
    lesson: str
    bereich: str
    status: Status
    bestaetigungen: int
    aehnlichkeit: float


class Entwurf(BaseModel):
    titel: str = ""
    situation: str = ""
    ereignis: str = ""
    lesson: str = ""
    massnahme: str = ""
    bereich: str = ""
    tags: list[str] = Field(default_factory=list)
    schweregrad: int = 3
    art: Art = "erfahrung"
    phase: Phase = ""
    quelle: Quelle = "text"
    rueckfrage: str = ""
    # "pflichtfeld": Pflichtangabe fehlt; "spezifitaet": Frage nach dem persönlichen Teil
    rueckfrage_art: Literal["", "pflichtfeld", "spezifitaet"] = ""
    spezifitaet: Literal["", "persoenlich", "allgemein"] = ""
    spezifitaet_hinweis: str = ""
    fehlende_felder: list[str] = Field(default_factory=list)
    compliance_hinweise: list[str] = Field(default_factory=list)
    dublette: DublettenKandidat | None = None
    dublette_begruendung: str = ""
    aehnliche: list[DublettenKandidat] = Field(default_factory=list)
    ki_verwendet: bool = False
    ki_modell: str = ""
    ki_fehler: str = ""
    # Im Hintergrund nicht an Claude gesendet, weil die Namensprüfung angeschlagen hat:
    # {"code": "pruefung"|"sperrliste", "meldung": ..., "hinweise": [...]}. Der Nutzer entscheidet in der App.
    pruefung: dict | None = None


EntwurfStatus = Literal["wartet", "in_arbeit", "fertig", "fehler"]
Modus = Literal["auto", "claude", "lokal", "manuell"]


class EntwurfEintrag(BaseModel):
    """Eintrag der Warteschlange für die Hintergrund-Strukturierung."""

    id: str
    rohtext: str
    quelle: Quelle
    bereich_vorgabe: str = ""
    status: EntwurfStatus
    rueckfrage: str = ""
    antwort: str = ""
    entwurf: Entwurf | None = None
    fehler: str = ""
    modell: str = ""
    dauer_sekunden: float | None = None
    erfassung_sekunden: float | None = None
    erstellt_am: str
    geaendert_am: str
    # claude, lokal oder manuell: festgelegt beim Erfassen. "lokal" geht nie an Claude.
    modus: str = "lokal"
    freigabe: bool = False


class NotizAnfrage(BaseModel):
    """Schnellnotiz: wird immer sofort als Entwurf gesichert, strukturiert wird danach."""

    text: str = Field(min_length=1, max_length=8000)
    quelle: Quelle = "text"
    bereich: str = ""
    erfassung_sekunden: float | None = Field(default=None, ge=0)
    bild_ids: list[str] = Field(default_factory=list, max_length=10)
    # Bereits fertiger Entwurf (z. B. "Später ansehen" nach der Strukturierung): nur ablegen.
    entwurf: Entwurf | None = None


class StrukturierenAnfrage(BaseModel):
    freigabe: bool = False
    text: str | None = Field(default=None, min_length=1, max_length=8000)


class RueckmeldungIn(BaseModel):
    art: Literal["bremse"]
    wert: str = Field(min_length=1, max_length=200)


class ErfassenAnfrage(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    quelle: Quelle = "text"
    bereich: str = ""
    erfassung_sekunden: float | None = Field(default=None, ge=0)
    bild_ids: list[str] = Field(default_factory=list, max_length=10)
    # Nutzer hat Hinweise der Namensprüfung gesehen und will trotzdem senden (Sperrliste blockiert immer)
    freigabe: bool = False


class FotoAnfrage(BaseModel):
    bild_ids: list[str] = Field(min_length=1, max_length=5)
    bereich: str = ""
    text: str = Field(default="", max_length=20000)
    notiz: str = Field(default="", max_length=2000)
    freigabe: bool = False


class BildLinks(BaseModel):
    bild_ids: list[str] = Field(min_length=1, max_length=10)


class AntwortIn(BaseModel):
    antwort: str = Field(min_length=1, max_length=4000)
