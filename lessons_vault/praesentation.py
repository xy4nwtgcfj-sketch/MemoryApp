"""PowerPoint aus einem Briefing-Plan (lokal erzeugt, kein weiterer Claude-Aufruf).

Folien: Titel, "Worauf es ankommt", je Planabschnitt eine Folie (lange Abschnitte geteilt),
Besonderheiten aus eigener Erfahrung, Quellen. Der zusammenhängende Text steht in den Notizen.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR
from pptx.util import Emu, Inches, Pt

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GOLD = RGBColor(0x8A, 0x5A, 0x10)
GOLD_LINIE = RGBColor(0xD9, 0xA4, 0x41)
TEXT = RGBColor(0x1A, 0x1D, 0x21)
GRAU = RGBColor(0x5F, 0x65, 0x6E)
PUNKTE_JE_FOLIE = 6

MARKE = re.compile(r"\s?\[\[E:([\w-]+)\]\]")


def text_ohne_marken(text: str) -> str:
    return MARKE.sub(" (own experience)", text or "").strip()


def _textfeld(folie, links, oben, breite, hoehe):
    feld = folie.shapes.add_textbox(links, oben, breite, hoehe)
    rahmen = feld.text_frame
    rahmen.word_wrap = True
    return rahmen


def _absatz(rahmen, text, *, groesse=18, farbe=TEXT, fett=False, erster=False, abstand=6):
    absatz = rahmen.paragraphs[0] if erster else rahmen.add_paragraph()
    absatz.space_after = Pt(abstand)
    lauf = absatz.add_run()
    lauf.text = text
    lauf.font.size = Pt(groesse)
    lauf.font.color.rgb = farbe
    lauf.font.bold = fett
    return absatz


def _kopf(praes, titel: str, kicker: str = ""):
    folie = praes.slides.add_slide(praes.slide_layouts[6])  # leer
    breite = praes.slide_width
    balken = folie.shapes.add_shape(1, 0, 0, breite, Inches(0.12))
    balken.fill.solid()
    balken.fill.fore_color.rgb = NAVY
    balken.line.fill.background()
    rahmen = _textfeld(folie, Inches(0.6), Inches(0.35), breite - Inches(1.2), Inches(1.1))
    rahmen.vertical_anchor = MSO_ANCHOR.TOP
    if kicker:
        _absatz(rahmen, kicker.upper(), groesse=11, farbe=GRAU, fett=True, erster=True, abstand=2)
        _absatz(rahmen, titel, groesse=26, farbe=NAVY, fett=True)
    else:
        _absatz(rahmen, titel, groesse=26, farbe=NAVY, fett=True, erster=True)
    return folie


def _fuss(praes, folie, text: str):
    rahmen = _textfeld(folie, Inches(0.6), praes.slide_height - Inches(0.5), praes.slide_width - Inches(1.2), Inches(0.35))
    _absatz(rahmen, text, groesse=10, farbe=GRAU, erster=True)


def _punkte(rahmen, punkte: list[dict[str, Any]], titel_von: dict[str, str]):
    erster = True
    for p in punkte:
        eigen = p.get("quelle") == "erfahrung" and p.get("lesson_id") in titel_von
        absatz = rahmen.paragraphs[0] if erster else rahmen.add_paragraph()
        erster = False
        absatz.space_after = Pt(10)
        zeichen = absatz.add_run()
        zeichen.text = "★  " if eigen else "•  "
        zeichen.font.size = Pt(18)
        zeichen.font.color.rgb = GOLD_LINIE if eigen else GRAU
        lauf = absatz.add_run()
        lauf.text = p["punkt"]
        lauf.font.size = Pt(18)
        lauf.font.color.rgb = TEXT
        if eigen:
            quelle = absatz.add_run()
            quelle.text = f"  ({titel_von[p['lesson_id']]})"
            quelle.font.size = Pt(12)
            quelle.font.color.rgb = GOLD


def briefing_pptx(situation: str, plan: dict[str, Any], lessons: dict[str, Any], erstellt_am: str = "") -> bytes:
    """lessons: lesson_id -> Lesson (für Titel der Quellen)."""
    titel_von = {lid: l.titel for lid, l in lessons.items()}
    praes = Presentation()
    praes.slide_width, praes.slide_height = Inches(13.333), Inches(7.5)
    fuss = "★ from your own experience  ·  other points: Claude's expertise, not verified"

    # 1 Titel
    folie = praes.slides.add_slide(praes.slide_layouts[6])
    flaeche = folie.shapes.add_shape(1, 0, 0, praes.slide_width, praes.slide_height)
    flaeche.fill.solid()
    flaeche.fill.fore_color.rgb = NAVY
    flaeche.line.fill.background()
    rahmen = _textfeld(folie, Inches(0.9), Inches(2.4), praes.slide_width - Inches(1.8), Inches(3))
    _absatz(rahmen, "BRIEFING", groesse=14, farbe=GOLD_LINIE, fett=True, erster=True, abstand=10)
    _absatz(rahmen, situation, groesse=36, farbe=RGBColor(0xFF, 0xFF, 0xFF), fett=True, abstand=16)
    datum = erstellt_am[:10] if erstellt_am else datetime.now().strftime("%Y-%m-%d")
    _absatz(rahmen, f"Expertise and own experience  ·  {datum}", groesse=16, farbe=RGBColor(0xC8, 0xD3, 0xE3))

    # 2 Worauf es ankommt
    folie = _kopf(praes, "What matters most", "Summary")
    rahmen = _textfeld(folie, Inches(0.6), Inches(1.7), praes.slide_width - Inches(1.2), Inches(4.8))
    _absatz(rahmen, plan.get("zusammenfassung", ""), groesse=22, erster=True, abstand=14)
    eigen = plan.get("punkte_erfahrung", 0)
    gesamt = plan.get("punkte_gesamt", 0)
    if gesamt:
        _absatz(rahmen, f"{eigen} of {gesamt} points come from your own experience.", groesse=14, farbe=GOLD)
    folie.notes_slide.notes_text_frame.text = text_ohne_marken(plan.get("ausarbeitung", ""))
    _fuss(praes, folie, fuss)

    # 3 Abschnitte
    for abschnitt in plan.get("abschnitte", []):
        punkte = abschnitt.get("punkte", [])
        teile = [punkte[i:i + PUNKTE_JE_FOLIE] for i in range(0, len(punkte), PUNKTE_JE_FOLIE)] or [[]]
        for nr, teil in enumerate(teile, start=1):
            titel = abschnitt.get("titel", "") + (f" ({nr}/{len(teile)})" if len(teile) > 1 else "")
            folie = _kopf(praes, titel, "Plan")  # Abschnittstitel kommen bereits auf Englisch von Claude
            rahmen = _textfeld(folie, Inches(0.6), Inches(1.7), praes.slide_width - Inches(1.2), Inches(5.0))
            _punkte(rahmen, teil, titel_von)
            _fuss(praes, folie, fuss)

    # 4 Besonderheiten
    besonderheiten = [b for b in plan.get("besonderheiten", []) if b.get("lesson_id") in titel_von]
    if besonderheiten:
        folie = _kopf(praes, "Where your experience differs from common practice", "Own experience")
        rahmen = _textfeld(folie, Inches(0.6), Inches(1.7), praes.slide_width - Inches(1.2), Inches(5.0))
        _punkte(rahmen, [{**b, "quelle": "erfahrung"} for b in besonderheiten], titel_von)
        _fuss(praes, folie, fuss)

    # 5 Quellen
    genutzt = []
    for lid in [p.get("lesson_id") for a in plan.get("abschnitte", []) for p in a.get("punkte", [])] + \
            [b.get("lesson_id") for b in besonderheiten] + MARKE.findall(plan.get("ausarbeitung", "")):
        if lid in titel_von and lid not in genutzt:
            genutzt.append(lid)
    if genutzt:
        folie = _kopf(praes, "Own lessons used", "Sources")
        rahmen = _textfeld(folie, Inches(0.6), Inches(1.7), praes.slide_width - Inches(1.2), Inches(5.0))
        for i, lid in enumerate(genutzt):
            _absatz(rahmen, f"★  {titel_von[lid]}", groesse=14, erster=(i == 0), abstand=6)

    puffer = io.BytesIO()
    praes.save(puffer)
    return puffer.getvalue()


def dateiname(situation: str) -> str:
    kurz = re.sub(r"[^\w\- ]", "", situation, flags=re.UNICODE).strip()[:50].strip() or "Briefing"
    return f"Briefing {kurz}.pptx"
