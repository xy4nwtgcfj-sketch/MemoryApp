---
quick: 001
completed: 2026-10-16
---

# Quick 001: Spezifitäts-Check

- Prompt: Claude bewertet spezifitaet (persoenlich/allgemein) mit Begründung und übernimmt persönliche Muster und Größenordnungen in die Regel. Rückfrage-Priorität: Pflichtfeld vor Spezifität, max. eine Frage, zweite Runde nie.
- Schema um rueckfrage_art, spezifitaet, spezifitaet_hinweis erweitert; unbekannte Werte werden bereinigt.
- Migration v4: lessons.spezifisch (NULL/0/1); Import, Export, Bearbeiten, Statistik (Anteil persönlicher Lessons, überholte ausgenommen).
- UI: Rückfrage "Was ist dein persönlicher Teil?" als optional gekennzeichnet, Hinweis bei verbleibendem "allgemein", Schalter "Persönliche Erfahrung" (vorbelegt, änderbar), Badge, Erfolgskriterium.
- Gilt auch für die lokale Hintergrund-Strukturierung (gleicher Prompt, Antwort über Prüfen).

Tests: 107 passed (neu: 3 Strukturierung, 1 API, 1 E2E).
