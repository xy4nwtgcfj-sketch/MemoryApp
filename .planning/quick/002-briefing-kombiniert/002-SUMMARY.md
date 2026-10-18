---
quick: 002
completed: 2026-10-18
---

# Quick 002: Briefing kombiniert

- KOMBI_PROMPT: Plan in 3 bis 6 Abschnitten, Punkte mit quelle erfahrung/allgemein und lesson_nr (0 = allgemein), besonderheiten. Keine erfundenen Transaktionscodes, Tabellen oder Zahlen.
- kombi_auswerten: Erfahrungspunkte ohne gültige Lesson werden als allgemein geführt; leere Abschnitte entfallen; Zähler für Statistik.
- Migration v6 (modus, plan_json), Moduswechsel verwirft altes Ergebnis, LV_BRIEFING_EFFORT (Standard medium, max_tokens 16000).
- Kombiniert auch ohne passende Lessons möglich, mit Hinweis "reines Allgemeinwissen".
- UI: Umschalter "Mit Claude-Wissen / Nur meine Erfahrung" (gemerkt), Plan mit Quellenkennzeichnung, "Deine Besonderheiten", Kopieren als Markdown, Umschalten im Ergebnis.
- Tests: 135 passed (neu 5 API/Logik, 1 E2E).
