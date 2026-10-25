"""PowerPoint aus einem Briefing-Plan (lokal erzeugt, kein weiterer Claude-Aufruf).

Folien: Titel, "Worauf es ankommt", je Planabschnitt eine Folie (lange Abschnitte geteilt),
Besonderheiten aus eigener Erfahrung, blinde Flecken, Quellen. Der zusammenhängende Text steht in den Notizen.
Die Marke des Bereichs (Name, Farben, Schrift, Logo) bestimmt das Erscheinungsbild.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from .models import Marke

TEXT = RGBColor(0x1A, 0x1D, 0x21)
GRAU = RGBColor(0x5F, 0x65, 0x6E)
WEISS = RGBColor(0xFF, 0xFF, 0xFF)
PUNKTE_JE_FOLIE = 6

MARKE = re.compile(r"\s?\[\[E:([\w-]+)\]\]")


def text_ohne_marken(text: str) -> str:
    return MARKE.sub(" (own experience)", text or "").strip()


def _rgb(hexwert: str) -> RGBColor:
    h = hexwert.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _hell(farbe: RGBColor) -> bool:
    """Wahrgenommene Helligkeit; entscheidet über weiße oder dunkle Schrift auf der Titelfolie."""
    r, g, b = farbe[0], farbe[1], farbe[2]
    return (0.299 * r + 0.587 * g + 0.114 * b) > 160


@dataclass
class Thema:
    name: str
    untertitel: str
    primaer: RGBColor
    akzent: RGBColor
    schrift: str
    logo: bytes | None

    @classmethod
    def aus(cls, marke: Marke | None, logo: bytes | None) -> "Thema":
        if marke is None:
            return cls("", "", RGBColor(0x1F, 0x3A, 0x5F), RGBColor(0xD9, 0xA4, 0x41), "Calibri", logo)
        return cls(marke.name, marke.untertitel, _rgb(marke.farbe), _rgb(marke.akzent), marke.schrift or "Calibri", logo)

    @property
    def titel_schrift(self) -> RGBColor:
        return TEXT if _hell(self.primaer) else WEISS

    @property
    def titel_nebenschrift(self) -> RGBColor:
        return GRAU if _hell(self.primaer) else RGBColor(0xC8, 0xCE, 0xD6)

    @property
    def akzent_text(self) -> RGBColor:
        """Akzentfarbe als Textfarbe auf Weiß: helle Akzente (z. B. Deloitte-Grün) etwas abdunkeln."""
        if _hell(self.akzent):
            return RGBColor(int(self.akzent[0] * 0.7), int(self.akzent[1] * 0.7), int(self.akzent[2] * 0.7))
        return self.akzent


def _textfeld(folie, links, oben, breite, hoehe):
    feld = folie.shapes.add_textbox(links, oben, breite, hoehe)
    rahmen = feld.text_frame
    rahmen.word_wrap = True
    return rahmen


def _absatz(rahmen, text, *, groesse=18, farbe=TEXT, fett=False, erster=False, abstand=6, schrift="Calibri", rechts=False):
    absatz = rahmen.paragraphs[0] if erster else rahmen.add_paragraph()
    absatz.space_after = Pt(abstand)
    if rechts:
        absatz.alignment = PP_ALIGN.RIGHT
    lauf = absatz.add_run()
    lauf.text = text
    lauf.font.size = Pt(groesse)
    lauf.font.color.rgb = farbe
    lauf.font.bold = fett
    lauf.font.name = schrift
    return absatz


def _logo(praes, folie, thema: Thema, *, hoehe, rechts_oben=True):
    if not thema.logo:
        return
    try:
        bild = folie.shapes.add_picture(io.BytesIO(thema.logo), 0, 0, height=hoehe)
    except Exception:  # noqa: BLE001  defektes Logo darf die Präsentation nicht verhindern
        return
    if rechts_oben:
        bild.left = praes.slide_width - bild.width - Inches(0.5)
        bild.top = Inches(0.3)
    else:
        bild.left = Inches(0.9)
        bild.top = praes.slide_height - bild.height - Inches(0.7)


def _kopf(praes, thema: Thema, titel: str, kicker: str = ""):
    folie = praes.slides.add_slide(praes.slide_layouts[6])  # leer
    breite = praes.slide_width
    balken = folie.shapes.add_shape(1, 0, 0, breite, Inches(0.12))
    balken.fill.solid()
    balken.fill.fore_color.rgb = thema.primaer
    balken.line.fill.background()
    akzent = folie.shapes.add_shape(1, Inches(0.6), Inches(0.12), Inches(0.6), Inches(0.06))
    akzent.fill.solid()
    akzent.fill.fore_color.rgb = thema.akzent
    akzent.line.fill.background()
    titelbreite = breite - Inches(1.2) - (Inches(2.2) if thema.logo else 0)
    rahmen = _textfeld(folie, Inches(0.6), Inches(0.35), titelbreite, Inches(1.1))
    rahmen.vertical_anchor = MSO_ANCHOR.TOP
    if kicker:
        _absatz(rahmen, kicker.upper(), groesse=11, farbe=GRAU, fett=True, erster=True, abstand=2, schrift=thema.schrift)
        _absatz(rahmen, titel, groesse=26, farbe=thema.primaer, fett=True, schrift=thema.schrift)
    else:
        _absatz(rahmen, titel, groesse=26, farbe=thema.primaer, fett=True, erster=True, schrift=thema.schrift)
    _logo(praes, folie, thema, hoehe=Inches(0.55))
    return folie


def _fuss(praes, folie, thema: Thema, text: str):
    rahmen = _textfeld(folie, Inches(0.6), praes.slide_height - Inches(0.5), praes.slide_width - Inches(1.2), Inches(0.35))
    links = f"{thema.name}  ·  {text}" if thema.name else text
    _absatz(rahmen, links, groesse=10, farbe=GRAU, erster=True, schrift=thema.schrift)


def _punkte(rahmen, thema: Thema, punkte: list[dict[str, Any]], titel_von: dict[str, str]):
    erster = True
    for p in punkte:
        eigen = p.get("quelle") == "erfahrung" and p.get("lesson_id") in titel_von
        absatz = rahmen.paragraphs[0] if erster else rahmen.add_paragraph()
        erster = False
        absatz.space_after = Pt(10)
        zeichen = absatz.add_run()
        zeichen.text = "★  " if eigen else "•  "
        zeichen.font.size = Pt(18)
        zeichen.font.color.rgb = thema.akzent if eigen else GRAU
        zeichen.font.name = thema.schrift
        lauf = absatz.add_run()
        lauf.text = p["punkt"]
        lauf.font.size = Pt(18)
        lauf.font.color.rgb = TEXT
        lauf.font.name = thema.schrift
        if eigen:
            quelle = absatz.add_run()
            quelle.text = f"  ({titel_von[p['lesson_id']]})"
            quelle.font.size = Pt(12)
            quelle.font.color.rgb = thema.akzent_text
            quelle.font.name = thema.schrift


def briefing_pptx(
    situation: str, plan: dict[str, Any], lessons: dict[str, Any], erstellt_am: str = "",
    marke: Marke | None = None, logo: bytes | None = None,
) -> bytes:
    """lessons: lesson_id -> Lesson (für Titel der Quellen). marke/logo: Erscheinungsbild des Bereichs."""
    thema = Thema.aus(marke, logo)
    titel_von = {lid: l.titel for lid, l in lessons.items()}
    praes = Presentation()
    praes.slide_width, praes.slide_height = Inches(13.333), Inches(7.5)
    fuss = "★ from your own knowledge base  ·  other points: Claude's expertise, not verified"
    s = thema.schrift

    # 1 Titel
    folie = praes.slides.add_slide(praes.slide_layouts[6])
    flaeche = folie.shapes.add_shape(1, 0, 0, praes.slide_width, praes.slide_height)
    flaeche.fill.solid()
    flaeche.fill.fore_color.rgb = thema.primaer
    flaeche.line.fill.background()
    streifen = folie.shapes.add_shape(1, Inches(0.9), Inches(2.2), Inches(1.2), Inches(0.08))
    streifen.fill.solid()
    streifen.fill.fore_color.rgb = thema.akzent
    streifen.line.fill.background()
    if thema.name:
        kopfzeile = _textfeld(folie, Inches(0.9), Inches(0.5), praes.slide_width - Inches(1.8), Inches(0.6))
        _absatz(kopfzeile, thema.name, groesse=20, farbe=thema.titel_schrift, fett=True, erster=True, schrift=s)
    rahmen = _textfeld(folie, Inches(0.9), Inches(2.4), praes.slide_width - Inches(1.8), Inches(3))
    _absatz(rahmen, "BRIEFING", groesse=14, farbe=thema.akzent, fett=True, erster=True, abstand=10, schrift=s)
    _absatz(rahmen, situation, groesse=36, farbe=thema.titel_schrift, fett=True, abstand=16, schrift=s)
    datum = erstellt_am[:10] if erstellt_am else datetime.now().strftime("%Y-%m-%d")
    unterzeile = "  ·  ".join(t for t in (thema.untertitel, "Expertise and own experience", datum) if t)
    _absatz(rahmen, unterzeile, groesse=16, farbe=thema.titel_nebenschrift, schrift=s)
    _logo(praes, folie, thema, hoehe=Inches(0.9), rechts_oben=False)

    # 2 Worauf es ankommt
    folie = _kopf(praes, thema, "What matters most", "Summary")
    rahmen = _textfeld(folie, Inches(0.6), Inches(1.7), praes.slide_width - Inches(1.2), Inches(4.8))
    _absatz(rahmen, plan.get("zusammenfassung", ""), groesse=22, erster=True, abstand=14, schrift=s)
    eigen = plan.get("punkte_erfahrung", 0)
    gesamt = plan.get("punkte_gesamt", 0)
    if gesamt:
        _absatz(rahmen, f"{eigen} of {gesamt} points come from your own knowledge base.", groesse=14, farbe=thema.akzent_text, schrift=s)
    folie.notes_slide.notes_text_frame.text = text_ohne_marken(plan.get("ausarbeitung", ""))
    _fuss(praes, folie, thema, fuss)

    # 3 Abschnitte
    for abschnitt in plan.get("abschnitte", []):
        punkte = abschnitt.get("punkte", [])
        teile = [punkte[i:i + PUNKTE_JE_FOLIE] for i in range(0, len(punkte), PUNKTE_JE_FOLIE)] or [[]]
        for nr, teil in enumerate(teile, start=1):
            titel = abschnitt.get("titel", "") + (f" ({nr}/{len(teile)})" if len(teile) > 1 else "")
            folie = _kopf(praes, thema, titel, "Plan")  # Abschnittstitel kommen bereits auf Englisch von Claude
            rahmen = _textfeld(folie, Inches(0.6), Inches(1.7), praes.slide_width - Inches(1.2), Inches(5.0))
            _punkte(rahmen, thema, teil, titel_von)
            _fuss(praes, folie, thema, fuss)

    # 4 Besonderheiten
    besonderheiten = [b for b in plan.get("besonderheiten", []) if b.get("lesson_id") in titel_von]
    if besonderheiten:
        folie = _kopf(praes, thema, "Where your experience differs from common practice", "Own experience")
        rahmen = _textfeld(folie, Inches(0.6), Inches(1.7), praes.slide_width - Inches(1.2), Inches(5.0))
        _punkte(rahmen, thema, [{**b, "quelle": "erfahrung"} for b in besonderheiten], titel_von)
        _fuss(praes, folie, thema, fuss)

    # 5 Blinde Flecken: Themen ohne eigenen Eintrag, Lücke mit Fachwissen geschlossen
    luecken = plan.get("luecken") or []
    if luecken:
        folie = _kopf(praes, thema, "Blind spots: what your entries don't cover yet", "Gaps closed with expertise")
        rahmen = _textfeld(folie, Inches(0.6), Inches(1.7), praes.slide_width - Inches(1.2), Inches(5.0))
        for i, l in enumerate(luecken):
            _absatz(rahmen, l.get("titel", ""), groesse=18, farbe=thema.primaer, fett=True, erster=(i == 0), abstand=2, schrift=s)
            _absatz(rahmen, l.get("kern", ""), groesse=14, farbe=TEXT, abstand=10, schrift=s)
        folie.notes_slide.notes_text_frame.text = "\n\n".join(
            f"{l.get('titel', '')}\n{l.get('wissen', '')}" + (f"\nApply: {l['anwendung']}" if l.get("anwendung") else "") for l in luecken
        )
        _fuss(praes, folie, thema, "Claude's expertise, not verified · full text in the notes")

    # 6 Quellen
    genutzt = []
    for lid in [p.get("lesson_id") for a in plan.get("abschnitte", []) for p in a.get("punkte", [])] + \
            [b.get("lesson_id") for b in besonderheiten] + MARKE.findall(plan.get("ausarbeitung", "")):
        if lid in titel_von and lid not in genutzt:
            genutzt.append(lid)
    if genutzt:
        folie = _kopf(praes, thema, "Own entries used", "Sources")
        rahmen = _textfeld(folie, Inches(0.6), Inches(1.7), praes.slide_width - Inches(1.2), Inches(5.0))
        for i, lid in enumerate(genutzt):
            _absatz(rahmen, f"★  {titel_von[lid]}", groesse=14, erster=(i == 0), abstand=6, schrift=s)
        _fuss(praes, folie, thema, fuss)

    puffer = io.BytesIO()
    praes.save(puffer)
    return puffer.getvalue()


def dateiname(situation: str) -> str:
    kurz = re.sub(r"[^\w\- ]", "", situation, flags=re.UNICODE).strip()[:50].strip() or "Briefing"
    return f"Briefing {kurz}.pptx"
