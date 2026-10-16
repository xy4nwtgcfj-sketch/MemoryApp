---
quick: 001
slug: spezifitaets-check
created: 2026-10-16
---

# Quick 001: Spezifitäts-Check beim Erfassen

**Anlass:** Stefans Frage nach dem Mehrwert gegenüber Claude. Lessons, die nur Allgemeinwissen enthalten, liefert Claude ohnehin. Der Wert der App liegt im persönlichen Teil.

**Änderung (bewusste Abweichung vom Konzept 4.1):** Die eine erlaubte Rückfrage darf jetzt auch nach dem persönlichen Teil fragen, wenn keine Pflichtfelder fehlen. Weiterhin höchstens eine Frage; Pflichtfelder haben Vorrang. Die Spezifitäts-Rückfrage ist optional, Speichern bleibt möglich.

## Tasks
1. Schema/Prompt: spezifitaet (persoenlich/allgemein), spezifitaet_hinweis, rueckfrage_art (pflichtfeld/spezifitaet). Regel: persönliche Muster und Größenordnungen in der Lesson behalten (keine Kunden-/Personen-/Firmennamen).
2. Datenmodell: Spalte spezifisch (Migration v4), Import/Export, Statistik "Anteil persönlicher Lessons".
3. UI: Rückfrage-Box je nach Art, Hinweis bei "allgemein", Schalter "Persönliche Erfahrung" im Formular, Badge im Detail, Erfolgskriterium in Einstellungen.

## Verify
pytest (Strukturierung, API, E2E)
