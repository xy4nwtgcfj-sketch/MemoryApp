"""Regelbasierte Warnung vor Kunden-, Personen- und Firmendaten.

Bewusst einfach und erklärbar: Die Prüfung warnt, sie blockiert nicht. Deutsche
Substantive sind großgeschrieben, deshalb sucht sie nicht nach "jedem großen Wort",
sondern nach typischen Mustern (Rechtsform, Anrede, "Kunde X") und nach der
persönlichen Sperrliste, die der zuverlässigste Schutz ist.
"""

from __future__ import annotations

import re

RECHTSFORM = re.compile(
    r"\b([A-ZÄÖÜ0-9][\w&.\-]*(?:\s+[A-ZÄÖÜ0-9][\w&.\-]*){0,3})\s+"
    r"(GmbH(?:\s*&\s*Co\.?\s*KG)?|AG|SE|KGaA|KG|OHG|GbR|UG|e\.\s?V\.|Inc\.?|Ltd\.?|LLC|S\.A\.|N\.V\.|B\.V\.)(?![\w])"
)
ANREDE = re.compile(r"\b(Herr|Frau|Hr\.|Fr\.|Dr\.|Prof\.)\s+([A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?)")
KONTEXT_NAME = re.compile(
    r"\b(Kunde|Kunden|Kundin|Mandant|Mandanten|Lager|Werk|Standort|Niederlassung|Firma|Konzern|Projekt|Mieter|Mieterin|Makler|Maklerin|Verkäufer|Verkäuferin)"
    r"\s+((?:[A-ZÄÖÜ][\w\-]*|[A-Z0-9]{2,}[\w\-]*))"
)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
TELEFON = re.compile(r"(?<!\w)(?:\+\d{2}|0)\d[\d /-]{6,}\d")
BETRAG = re.compile(r"\d[\d.,]*\s?(?:€|EUR|Euro|Mio\.?|Mrd\.?|T€|k€)|(?:€|EUR)\s?\d[\d.,]*", re.IGNORECASE)
ZAHL = re.compile(r"(?<![\w.,])\d{3,}(?:[.,]\d+)*(?![\w])")
JAHR = re.compile(r"^(19|20)\d{2}$")

# Wörter nach "Kunde"/"Lager" usw., die keine Eigennamen sind.
GENERISCHE_FOLGEWOERTER = {
    "und", "oder", "mit", "ohne", "im", "in", "am", "an", "auf", "bei", "für", "von", "vom", "zum", "zur",
    "hat", "war", "ist", "will", "wollte", "muss", "sollte", "kann", "konnte", "wurde", "wird",
    "Seite", "Wunsch", "Anforderung", "Anforderungen", "Termin", "Abnahme", "Team", "Management",
    "Umzug", "Betrieb", "Prozess", "Prozesse", "Leitung", "Standort", "Lager", "Kunde",
}

ERLAUBTE_KUERZEL = {"SAP", "EWM", "ERP", "WMS", "MES", "PLM", "IT", "KPI", "UAT", "SIT", "PMO", "ROI", "FAQ", "RFC", "KYC", "ETF", "AfA", "WEG", "KfW", "NRW", "TMS", "S4", "S/4", "S/4HANA", "HANA", "BTP", "API", "QA"}


def _sperrbegriff_regex(begriff: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(begriff.strip())}(?!\w)", re.IGNORECASE)


def pruefen(text: str, bereich: str = "", sperrliste: list[str] | None = None) -> list[str]:
    """Liefert verständliche Warnungen; leere Liste heißt: nichts gefunden."""
    hinweise: list[str] = []

    def add(msg: str) -> None:
        if msg not in hinweise:
            hinweise.append(msg)

    for begriff in sperrliste or []:
        if begriff.strip() and _sperrbegriff_regex(begriff).search(text):
            add(f"Enthält Begriff aus deiner Sperrliste: \"{begriff.strip()}\"")

    for m in RECHTSFORM.finditer(text):
        add(f"Firmenname erkannt: \"{m.group(0).strip()}\". Abstrahieren, z. B. \"ein Logistikdienstleister\".")
    for m in ANREDE.finditer(text):
        add(f"Personenname erkannt: \"{m.group(0)}\". Besser Rolle nennen, z. B. \"die Projektleitung\".")
    for m in KONTEXT_NAME.finditer(text):
        name = m.group(2)
        if name in GENERISCHE_FOLGEWOERTER or name.lower() in GENERISCHE_FOLGEWOERTER or name in ERLAUBTE_KUERZEL:
            continue
        add(f"Möglicher Eigenname: \"{m.group(0)}\". Formuliere als eigenes Erfahrungswissen ohne Namen.")
    if EMAIL.search(text):
        add("E-Mail-Adresse erkannt. Kontaktdaten gehören nicht in eine Lesson.")
    if TELEFON.search(text):
        add("Telefonnummer erkannt. Kontaktdaten gehören nicht in eine Lesson.")

    if bereich == "Beruf":
        if BETRAG.search(text):
            add("Geldbetrag in beruflicher Lesson. Keine Zahlen aus Kundenprojekten, besser Größenordnung beschreiben.")
        zahlen = [z for z in ZAHL.findall(text) if not JAHR.match(z)]
        if zahlen:
            add(f"Konkrete Zahl(en) in beruflicher Lesson ({', '.join(zahlen[:3])}). Prüfen, ob das Kundendaten sind.")
    return hinweise


def lesson_text_fuer_pruefung(*felder: str, tags: list[str] | None = None) -> str:
    return "\n".join([*(f for f in felder if f), *(tags or [])])
